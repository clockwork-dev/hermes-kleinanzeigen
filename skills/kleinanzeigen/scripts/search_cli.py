"""CLI entrypoint for searching Kleinanzeigen listings."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path
import sqlite3
import sys
from typing import Literal, NoReturn

if __package__:
    from .kleinanzeigen_api import (
        ALLOWED_RADII,
        KleinanzeigenBlockedError,
        KleinanzeigenError,
        ValidationError,
        search_listings,
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
            ALLOWED_RADII,
            KleinanzeigenBlockedError,
            KleinanzeigenError,
            ValidationError,
            search_listings,
        )
    except ImportError:
        from scripts.kleinanzeigen_api import (
            ALLOWED_RADII,
            KleinanzeigenBlockedError,
            KleinanzeigenError,
            ValidationError,
            search_listings,
        )


FetchMode = Literal["auto", "http", "browser"]


def configure_utf8_streams() -> None:
    """Reconfigure stdout and stderr to UTF-8 for Windows compatibility."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def add_search_arguments(parser: argparse.ArgumentParser) -> None:
    """Register shared Kleinanzeigen search flags on an ArgumentParser."""
    parser.add_argument(
        "query",
        help="Search keywords (e.g. 'fahrrad', 'rtx 4070').",
    )
    parser.add_argument(
        "--plz",
        type=str,
        default=None,
        help="German 5-digit postal code (PLZ).",
    )
    parser.add_argument(
        "--radius",
        type=int,
        default=None,
        choices=ALLOWED_RADII,
        help="Search radius in km around --plz.",
    )
    parser.add_argument(
        "--min-price",
        type=int,
        default=None,
        help="Minimum price in EUR.",
    )
    parser.add_argument(
        "--max-price",
        type=int,
        default=None,
        help="Maximum price in EUR.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of listings to return (default: 10).",
    )
    browser_group = parser.add_mutually_exclusive_group()
    browser_group.add_argument(
        "--browser",
        action="store_true",
        help="Fetch directly via headless Playwright, skipping the HTTP requests preflight.",
    )
    browser_group.add_argument(
        "--no-browser",
        action="store_true",
        help="Disable Playwright fallback and only use HTTP requests.",
    )
    parser.add_argument(
        "--include-top-ads",
        action="store_true",
        help="Include sponsored Top-Anzeige / highlighted listings.",
    )
    parser.add_argument(
        "--html-file",
        type=str,
        default=None,
        help="Optional local HTML file path to parse instead of live HTTP.",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for search_cli."""
    parser = argparse.ArgumentParser(
        description="Search Kleinanzeigen Germany listings and print JSON to stdout.",
    )
    add_search_arguments(parser)
    return parser


def load_html_override(html_file: str | None) -> str | None:
    """Read an optional local HTML fixture file for offline parsing."""
    if html_file is None:
        return None
    if not html_file.strip():
        raise ValidationError("--html-file path must not be empty.")
    path = Path(html_file).expanduser()
    return path.read_text(encoding="utf-8-sig", errors="replace")


def resolve_fetch_options(args: argparse.Namespace) -> tuple[FetchMode, bool]:
    """Map CLI browser flags to search_listings (fetch_mode, use_playwright_fallback)."""
    use_browser = bool(getattr(args, "browser", False))
    no_browser = bool(getattr(args, "no_browser", False))
    if use_browser and no_browser:
        raise ValidationError("Cannot combine --browser and --no-browser.")
    if use_browser:
        return "browser", True
    if no_browser:
        return "http", False
    return "auto", True


def execute_search(args: argparse.Namespace) -> list[dict[str, str | None]]:
    """Run search_listings using parsed CLI arguments."""
    html_override = load_html_override(args.html_file)
    fetch_mode, use_playwright_fallback = resolve_fetch_options(args)
    return search_listings(
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


def report_error(exc: BaseException) -> int:
    """Write a concise error message to stderr and return exit code 1."""
    if isinstance(exc, ValidationError):
        print(f"Validation error: {exc}", file=sys.stderr)
    elif isinstance(exc, KleinanzeigenBlockedError):
        status = exc.status_code if exc.status_code is not None else "unknown"
        print(
            f"Blocked by Kleinanzeigen (status={status}): {exc.reason} ({exc.url})",
            file=sys.stderr,
        )
    elif isinstance(exc, KleinanzeigenError):
        print(f"Kleinanzeigen error: {exc}", file=sys.stderr)
    elif isinstance(exc, sqlite3.Error):
        print(f"Database error: {exc}", file=sys.stderr)
    elif isinstance(exc, OSError):
        print(f"File/IO error: {exc}", file=sys.stderr)
    else:
        print(f"Unexpected error: {exc}", file=sys.stderr)
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Kleinanzeigen search CLI."""
    configure_utf8_streams()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        results = execute_search(args)
    except Exception as exc:
        return report_error(exc)

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


def _entrypoint() -> NoReturn:
    raise SystemExit(main())


if __name__ == "__main__":
    _entrypoint()
