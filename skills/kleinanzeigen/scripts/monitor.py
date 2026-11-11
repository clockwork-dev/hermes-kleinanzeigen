"""Monitor Kleinanzeigen listings, persist seen IDs in SQLite, and emit new items."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import contextlib
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from typing import NoReturn

if __package__:
    from .kleinanzeigen_api import (
        KleinanzeigenBlockedError,
        KleinanzeigenError,
        ValidationError,
        search_listings,
    )
    from .search_cli import (
        add_search_arguments,
        configure_utf8_streams,
        load_html_override,
        report_error,
        resolve_fetch_options,
    )
else:
    _SCRIPT_DIR = Path(__file__).resolve().parent
    _SKILL_ROOT = _SCRIPT_DIR.parent
    if str(_SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPT_DIR))
    if str(_SKILL_ROOT) not in sys.path:
        sys.path.insert(0, str(_SKILL_ROOT))

    try:
        from kleinanzeigen_api import (
            KleinanzeigenBlockedError,
            KleinanzeigenError,
            ValidationError,
            search_listings,
        )
        from search_cli import (
            add_search_arguments,
            configure_utf8_streams,
            load_html_override,
            report_error,
            resolve_fetch_options,
        )
    except ImportError:
        from scripts.kleinanzeigen_api import (
            KleinanzeigenBlockedError,
            KleinanzeigenError,
            ValidationError,
            search_listings,
        )
        from scripts.search_cli import (
            add_search_arguments,
            configure_utf8_streams,
            load_html_override,
            report_error,
            resolve_fetch_options,
        )

MAX_DESCRIPTION_LENGTH = 160
_MARKDOWN_ESCAPE_RE = re.compile(r"([\\*_`\[\]])")
_SCHEMA_SQL = (
    "CREATE TABLE IF NOT EXISTS seen_ads ("
    "ad_id TEXT PRIMARY KEY, "
    "query_hash TEXT, "
    "seen_at TIMESTAMP)"
)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for monitor."""
    parser = argparse.ArgumentParser(
        description="Monitor Kleinanzeigen listings and output only newly seen ads.",
    )
    add_search_arguments(parser)
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help=(
            "SQLite database path (defaults to KLEINANZEIGEN_DB_PATH or "
            "~/.hermes/skills/kleinanzeigen/data/seen_ads.db)."
        ),
    )
    parser.add_argument(
        "--format",
        choices=["json", "telegram"],
        default="json",
        help="Output format for newly found listings (default: json).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Filter against seen_ads without inserting newly found listings.",
    )
    return parser


def resolve_db_path(cli_db: str | None = None) -> Path:
    """Resolve the SQLite database path from CLI option, env var, or default."""
    if cli_db is not None:
        if not cli_db.strip():
            raise ValidationError("--db path must not be empty.")
        return Path(cli_db).expanduser()

    env_path = os.environ.get("KLEINANZEIGEN_DB_PATH")
    if env_path and env_path.strip():
        return Path(env_path.strip()).expanduser()

    return Path.home() / ".hermes" / "skills" / "kleinanzeigen" / "data" / "seen_ads.db"


def compute_query_hash(
    query: str,
    postal_code: str | None = None,
    radius: int | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
) -> str:
    """Compute a deterministic SHA-256 hex digest for normalized search criteria."""
    normalized = [
        query.strip().lower(),
        (postal_code or "").strip(),
        radius,
        min_price,
        max_price,
    ]
    payload = json.dumps(normalized, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _fetch_existing_ids(conn: sqlite3.Connection, ad_ids: list[str]) -> set[str]:
    """Return the subset of ad_ids already recorded in seen_ads."""
    if not ad_ids:
        return set()

    existing: set[str] = set()
    chunk_size = 500
    for idx in range(0, len(ad_ids), chunk_size):
        chunk = ad_ids[idx : idx + chunk_size]
        placeholders = ",".join("?" for _ in chunk)
        rows = conn.execute(
            f"SELECT ad_id FROM seen_ads WHERE ad_id IN ({placeholders})",
            chunk,
        ).fetchall()
        existing.update(row[0] for row in rows)
    return existing


def filter_and_record_listings(
    listings: list[dict[str, str | None]],
    db_path: Path,
    query_hash: str,
    *,
    dry_run: bool = False,
) -> list[dict[str, str | None]]:
    """Filter out already-seen listings and persist new ones unless dry_run is True."""
    if str(db_path) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)

    candidate_ids = [
        ad_id for item in listings if (ad_id := item.get("id")) and isinstance(ad_id, str)
    ]

    with contextlib.closing(sqlite3.connect(str(db_path))) as conn:
        with conn:
            conn.execute(_SCHEMA_SQL)
            existing_ids = _fetch_existing_ids(conn, candidate_ids)

            new_listings: list[dict[str, str | None]] = []
            seen_in_batch: set[str] = set()
            for item in listings:
                ad_id = item.get("id")
                if not ad_id or ad_id in existing_ids or ad_id in seen_in_batch:
                    continue
                seen_in_batch.add(ad_id)
                new_listings.append(item)

            if new_listings and not dry_run:
                seen_at = datetime.now(timezone.utc).isoformat()
                conn.executemany(
                    "INSERT OR IGNORE INTO seen_ads (ad_id, query_hash, seen_at) "
                    "VALUES (?, ?, ?)",
                    [(item["id"], query_hash, seen_at) for item in new_listings],
                )

    return new_listings


def _escape_markdown(text: str) -> str:
    """Escape characters that could break Telegram Markdown links or bold spans."""
    return _MARKDOWN_ESCAPE_RE.sub(r"\\\1", text)


def _clean_text(text: str | None) -> str:
    """Collapse arbitrary whitespace into single spaces."""
    if not text:
        return ""
    return " ".join(text.split())


def _truncate_text(text: str, max_length: int = MAX_DESCRIPTION_LENGTH) -> str:
    """Truncate text cleanly at a word boundary without splitting escapes."""
    cleaned = _clean_text(text)
    if len(cleaned) <= max_length:
        return cleaned
    if max_length <= 3:
        return cleaned[:max_length]
    cutoff = max_length - 3
    truncated = cleaned[:cutoff].rstrip()
    if " " in truncated:
        word_boundary = truncated.rsplit(" ", 1)[0]
        if len(word_boundary) >= cutoff // 2:
            truncated = word_boundary
    return f"{truncated}..."


def _sanitize_url(url: str | None) -> str:
    """Encode spaces and parentheses in URLs for valid Markdown link targets."""
    cleaned = (url or "").strip()
    return cleaned.replace(" ", "%20").replace("(", "%28").replace(")", "%29")


def _format_location_header(postal_code: str | None, radius: int | None) -> str:
    """Format the Telegram location header line based on PLZ and radius."""
    plz = (postal_code or "").strip()
    if plz and radius is not None:
        return f"📍 Локация: {_escape_markdown(plz)} (+{radius} км)"
    if plz:
        return f"📍 Локация: {_escape_markdown(plz)}"
    return "📍 Локация: Вся Германия"


def format_telegram_message(
    listings: list[dict[str, str | None]],
    query: str,
    postal_code: str | None = None,
    radius: int | None = None,
) -> str:
    """Format new listings as Telegram-friendly Markdown with Russian headers."""
    safe_query = _escape_markdown(_clean_text(query))
    lines = [
        f'🔍 **Kleinanzeigen: {len(listings)} объявлений по запросу "{safe_query}"**',
        _format_location_header(postal_code, radius),
    ]

    for index, item in enumerate(listings, start=1):
        title = _escape_markdown(_clean_text(item.get("title")) or "Без названия")
        price = _escape_markdown(_clean_text(item.get("price")) or "Цена не указана")
        url = _sanitize_url(item.get("url"))

        if url:
            header = f"{index}. **[{title}]({url})** — **{price}**"
        else:
            header = f"{index}. **{title}** — **{price}**"

        entry_lines = [header]

        location = _clean_text(item.get("location"))
        if location:
            entry_lines.append(f"   📍 {_escape_markdown(location)}")

        description = _truncate_text(item.get("description") or "")
        if description:
            entry_lines.append(f"   📝 {_escape_markdown(description)}")

        lines.append("")
        lines.extend(entry_lines)

    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Kleinanzeigen monitor CLI."""
    configure_utf8_streams()
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        db_path = resolve_db_path(args.db)
        html_override = load_html_override(args.html_file)
        fetch_mode, use_playwright_fallback = resolve_fetch_options(args)
        listings = search_listings(
            query=args.query,
            postal_code=args.plz,
            radius=args.radius,
            min_price=args.min_price,
            max_price=args.max_price,
            limit=args.limit,
            fetch_mode=fetch_mode,
            use_playwright_fallback=use_playwright_fallback,
            include_top_ads=args.include_top_ads,
            html_override=html_override,
        )
        query_hash = compute_query_hash(
            query=args.query,
            postal_code=args.plz,
            radius=args.radius,
            min_price=args.min_price,
            max_price=args.max_price,
        )
        new_listings = filter_and_record_listings(
            listings=listings,
            db_path=db_path,
            query_hash=query_hash,
            dry_run=args.dry_run,
        )
    except (ValidationError, KleinanzeigenBlockedError, KleinanzeigenError, ValueError, OSError, sqlite3.Error) as exc:
        return report_error(exc)
    except Exception as exc:
        return report_error(exc)

    if args.format == "json":
        print(json.dumps(new_listings, ensure_ascii=False, indent=2))
    elif new_listings:
        print(
            format_telegram_message(
                listings=new_listings,
                query=args.query,
                postal_code=args.plz,
                radius=args.radius,
            )
        )
    else:
        print("No new listings.", file=sys.stderr)

    return 0


def _entrypoint() -> NoReturn:
    raise SystemExit(main())


if __name__ == "__main__":
    _entrypoint()
