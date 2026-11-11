"""Hermes Agent native plugin for searching and monitoring Kleinanzeigen Germany listings."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

_PLUGIN_ROOT = Path(__file__).resolve().parent
_SKILL_MD_PATH = _PLUGIN_ROOT / "skills" / "kleinanzeigen" / "SKILL.md"
_SKILL_DESCRIPTION = "Search and monitor Kleinanzeigen by PLZ, radius, and price."
_ALLOWED_RADII = [0, 5, 10, 20, 30, 50, 100, 150, 200]
_ALLOWED_FETCH_MODES = ["auto", "http", "browser"]
_ALLOWED_FORMATS = ["json", "telegram"]


def _search_properties() -> dict[str, Any]:
    return {
        "query": {
            "type": "string",
            "description": "Search keywords (e.g. 'fahrrad', 'rtx 4070'). Required non-empty string.",
        },
        "postal_code": {
            "type": "string",
            "description": "Optional German 5-digit postal code (PLZ, e.g. '10115'). Omit for nationwide search.",
        },
        "radius": {
            "type": "integer",
            "enum": list(_ALLOWED_RADII),
            "description": "Search radius in km around postal_code (requires postal_code).",
        },
        "min_price": {
            "type": "integer",
            "minimum": 0,
            "description": "Optional minimum price in EUR (>= 0).",
        },
        "max_price": {
            "type": "integer",
            "minimum": 0,
            "description": "Optional maximum price in EUR (>= 0).",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "default": 10,
            "description": "Maximum number of listings to return (default: 10).",
        },
        "fetch_mode": {
            "type": "string",
            "enum": list(_ALLOWED_FETCH_MODES),
            "default": "auto",
            "description": (
                "Fetch strategy: 'auto' tries HTTP first with optional Playwright fallback, "
                "'http' uses HTTP only, 'browser' uses Playwright directly."
            ),
        },
        "include_top_ads": {
            "type": "boolean",
            "default": False,
            "description": "Include sponsored Top-Anzeige / highlighted listings (default: false).",
        },
    }


SEARCH_SCHEMA: dict[str, Any] = {
    "name": "kleinanzeigen_search",
    "description": (
        "Search Kleinanzeigen Germany (kleinanzeigen.de) classifieds listings by keywords, "
        "optional 5-digit PLZ, radius, and price range. Returns structured JSON listings."
    ),
    "parameters": {
        "type": "object",
        "properties": _search_properties(),
        "required": ["query"],
        "additionalProperties": False,
    },
}

MONITOR_SCHEMA: dict[str, Any] = {
    "name": "kleinanzeigen_monitor",
    "description": (
        "Search Kleinanzeigen Germany and filter out previously seen ad IDs stored in SQLite, "
        "returning only newly discovered listings as JSON (with optional Telegram Markdown summary)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            **_search_properties(),
            "format": {
                "type": "string",
                "enum": list(_ALLOWED_FORMATS),
                "default": "json",
                "description": "Output format: 'json' (default) or 'telegram' (adds formatted 'message').",
            },
            "dry_run": {
                "type": "boolean",
                "default": False,
                "description": "Check against seen_ads without inserting newly found listings (default: false).",
            },
            "db_path": {
                "type": "string",
                "description": (
                    "Optional SQLite database path override (defaults to KLEINANZEIGEN_DB_PATH "
                    "or Hermes plugin-data/kleinanzeigen/seen_ads.db)."
                ),
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}


def _load_api():
    if __package__:
        from .skills.kleinanzeigen.scripts import kleinanzeigen_api
        return kleinanzeigen_api
    from skills.kleinanzeigen.scripts import kleinanzeigen_api
    return kleinanzeigen_api


def _load_monitor():
    if __package__:
        from .skills.kleinanzeigen.scripts import monitor
        return monitor
    from skills.kleinanzeigen.scripts import monitor
    return monitor


def _json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _default_plugin_db_path() -> Path:
    try:
        from plugins.plugin_storage import plugin_data_dir
        return plugin_data_dir("kleinanzeigen") / "seen_ads.db"
    except ImportError:
        pass

    try:
        from hermes_constants import get_hermes_home
        return get_hermes_home() / "plugin-data" / "kleinanzeigen" / "seen_ads.db"
    except ImportError:
        pass

    env_home = os.environ.get("HERMES_HOME", "").strip()
    if env_home:
        hermes_home = Path(env_home).expanduser()
    elif sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
        hermes_home = Path(local_appdata) / "hermes" if local_appdata else Path.home() / "AppData" / "Local" / "hermes"
    else:
        hermes_home = Path.home() / ".hermes"
    return hermes_home / "plugin-data" / "kleinanzeigen" / "seen_ads.db"


def _resolve_plugin_db_path(db_path: Any, validation_error_cls: type[Exception]) -> Path:
    if db_path is not None:
        if not isinstance(db_path, str) or not db_path.strip():
            raise validation_error_cls("db_path must be a non-empty string.")
        return Path(db_path.strip()).expanduser()

    env_path = os.environ.get("KLEINANZEIGEN_DB_PATH", "").strip()
    if env_path:
        return Path(env_path).expanduser()

    return _default_plugin_db_path()


def _extract_search_kwargs(args: dict[str, Any], validation_error_cls: type[Exception]) -> dict[str, Any]:
    query = "" if args.get("query") is None else args.get("query")
    postal_code = args.get("postal_code")
    radius = args.get("radius")
    min_price = args.get("min_price")
    max_price = args.get("max_price")
    limit = 10 if args.get("limit") is None else args.get("limit")
    fetch_mode = "auto" if args.get("fetch_mode") is None else args.get("fetch_mode")
    include_top_ads = False if args.get("include_top_ads") is None else args.get("include_top_ads")
    if not isinstance(include_top_ads, bool):
        raise validation_error_cls("include_top_ads must be a boolean.")

    return {
        "query": query,
        "postal_code": postal_code,
        "radius": radius,
        "min_price": min_price,
        "max_price": max_price,
        "limit": limit,
        "fetch_mode": fetch_mode,
        "use_playwright_fallback": fetch_mode != "http",
        "include_top_ads": include_top_ads,
    }


def _error_payload(exc: Exception, api: Any) -> str:
    if isinstance(exc, api.ValidationError):
        return _json_dumps({"ok": False, "error_type": "validation_error", "error": str(exc)})
    if isinstance(exc, api.KleinanzeigenBlockedError):
        return _json_dumps(
            {
                "ok": False,
                "error_type": "blocked",
                "status_code": exc.status_code,
                "url": exc.url,
                "reason": exc.reason,
                "error": str(exc),
            }
        )
    if isinstance(exc, api.KleinanzeigenError):
        return _json_dumps({"ok": False, "error_type": "kleinanzeigen_error", "error": str(exc)})
    if isinstance(exc, sqlite3.Error):
        return _json_dumps({"ok": False, "error_type": "database_error", "error": str(exc)})
    if isinstance(exc, OSError):
        return _json_dumps({"ok": False, "error_type": "io_error", "error": str(exc)})
    return _json_dumps({"ok": False, "error_type": "unexpected_error", "error": str(exc)})


def _handle_search(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    """Execute a one-shot Kleinanzeigen search and return JSON."""
    del kwargs
    payload = args if isinstance(args, dict) else {}
    api = _load_api()
    try:
        search_kwargs = _extract_search_kwargs(payload, api.ValidationError)
        listings = api.search_listings(**search_kwargs)
        return _json_dumps(
            {
                "ok": True,
                "query": str(search_kwargs["query"]).strip(),
                "postal_code": search_kwargs["postal_code"],
                "radius": search_kwargs["radius"],
                "fetch_mode": search_kwargs["fetch_mode"],
                "count": len(listings),
                "listings": listings,
            }
        )
    except Exception as exc:
        return _error_payload(exc, api)


def _handle_monitor(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    """Search Kleinanzeigen, deduplicate against SQLite seen_ads, and return JSON."""
    del kwargs
    payload = args if isinstance(args, dict) else {}
    api = _load_api()
    mon = _load_monitor()
    try:
        search_kwargs = _extract_search_kwargs(payload, api.ValidationError)
        fmt = "json" if payload.get("format") is None else payload.get("format")
        if not isinstance(fmt, str) or fmt not in _ALLOWED_FORMATS:
            raise api.ValidationError(f"Invalid format '{fmt}'. Allowed values: {tuple(_ALLOWED_FORMATS)}.")
        dry_run = False if payload.get("dry_run") is None else payload.get("dry_run")
        if not isinstance(dry_run, bool):
            raise api.ValidationError("dry_run must be a boolean.")
        resolved_db = _resolve_plugin_db_path(payload.get("db_path"), api.ValidationError)

        listings = api.search_listings(**search_kwargs)
        query_hash = mon.compute_query_hash(
            query=str(search_kwargs["query"]),
            postal_code=search_kwargs["postal_code"],
            radius=search_kwargs["radius"],
            min_price=search_kwargs["min_price"],
            max_price=search_kwargs["max_price"],
        )
        new_listings = mon.filter_and_record_listings(
            listings=listings,
            db_path=resolved_db,
            query_hash=query_hash,
            dry_run=dry_run,
        )
        result: dict[str, Any] = {
            "ok": True,
            "query": str(search_kwargs["query"]).strip(),
            "postal_code": search_kwargs["postal_code"],
            "radius": search_kwargs["radius"],
            "fetch_mode": search_kwargs["fetch_mode"],
            "format": fmt,
            "dry_run": dry_run,
            "db_path": str(resolved_db),
            "query_hash": query_hash,
            "total_fetched": len(listings),
            "new_count": len(new_listings),
            "listings": new_listings,
        }
        if fmt == "telegram":
            result["message"] = (
                mon.format_telegram_message(
                    listings=new_listings,
                    query=str(search_kwargs["query"]),
                    postal_code=search_kwargs["postal_code"],
                    radius=search_kwargs["radius"],
                )
                if new_listings
                else ""
            )
        return _json_dumps(result)
    except Exception as exc:
        return _error_payload(exc, api)


def register(ctx: Any) -> None:
    """Register Kleinanzeigen search/monitor tools and bundled skill on Hermes PluginContext."""
    ctx.register_tool(
        name="kleinanzeigen_search",
        toolset="kleinanzeigen",
        schema=SEARCH_SCHEMA,
        handler=_handle_search,
        description=SEARCH_SCHEMA["description"],
    )
    ctx.register_tool(
        name="kleinanzeigen_monitor",
        toolset="kleinanzeigen",
        schema=MONITOR_SCHEMA,
        handler=_handle_monitor,
        description=MONITOR_SCHEMA["description"],
    )
    if _SKILL_MD_PATH.is_file():
        ctx.register_skill(
            "kleinanzeigen",
            _SKILL_MD_PATH,
            description=_SKILL_DESCRIPTION,
            frontmatter={
                "name": "kleinanzeigen",
                "description": _SKILL_DESCRIPTION,
                "platforms": ["linux", "macos", "windows"],
            },
        )
