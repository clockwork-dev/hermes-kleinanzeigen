"""Core Kleinanzeigen Germany search, validation, fetch, and HTML parsing module."""

from __future__ import annotations

import contextlib
import json
import math
import os
import random
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote_plus, urlencode, urljoin

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

ALLOWED_RADII: tuple[int, ...] = (0, 5, 10, 20, 30, 50, 100, 150, 200)
BASE_URL: str = "https://www.kleinanzeigen.de"
BLOCKED_RESOURCE_TYPES: frozenset[str] = frozenset({"image", "media", "font"})
BLOCKED_URL_PATTERNS: tuple[str, ...] = (
    "/liberty/",
    "/gdpr/",
    "promotion-frontend",
    "kameleoon",
    "sgtm-legacy",
)

_ALLOWED_FETCH_MODES: tuple[str, ...] = ("auto", "http", "browser")
_MAX_FETCH_RETRIES: int = 2
_MAX_PAGINATION_PAGES: int = 10
_PAGE_DELAY_SECONDS: float = 2.0
_MIN_PLAYWRIGHT_TIMEOUT_MS: int = 60000

_DEFAULT_USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
_BLOCKED_STATUS_CODES: frozenset[int] = frozenset({403, 429, 503})
_PLZ_PATTERN: re.Pattern[str] = re.compile(r"[0-9]{5}")
_PLZ_IN_TEXT_PATTERN: re.Pattern[str] = re.compile(r"\b[0-9]{5}\b")
_CLOUDFLARE_TITLE_PATTERN: re.Pattern[str] = re.compile(
    r"<title[^>]*>.*?(?:just a moment\.\.\.|attention required!?\s*\|\s*cloudflare|cloudflare.*challenge).*?</title>",
    re.IGNORECASE | re.DOTALL,
)
_PRICE_TEXT_PATTERN: re.Pattern[str] = re.compile(
    r"(?:€|\bEUR\b|\bVB\b|\bzu verschenken\b)",
    re.IGNORECASE,
)
_DATE_TEXT_PATTERN: re.Pattern[str] = re.compile(
    r"^(?:heute|gestern|\d{2}\.\d{2}\.\d{4})\b",
    re.IGNORECASE,
)
_BREADCRUMB_SELECTOR: str = "#srp-breadcrumb-summary, .breadcrump-summary"
_BREADCRUMB_PATTERN: re.Pattern[str] = re.compile(
    r"(\d+(?:\.\d+)*)\s*-\s*(\d+(?:\.\d+)*)\s+von\s+(\d+(?:\.\d+)*)"
)
_DISTANCE_ONLY_PATTERN: re.Pattern[str] = re.compile(
    r"^\(\d+(?:[.,]\d+)?\s*km\)$",
    re.IGNORECASE,
)
_TRAILING_DISTANCE_PATTERN: re.Pattern[str] = re.compile(
    r"\(\d+(?:[.,]\d+)?\s*km\)\s*$",
    re.IGNORECASE,
)
_DATA_URI_SRCSET_PATTERN: re.Pattern[str] = re.compile(
    r"data:[^,\s]+,[^\s,]+(?:\s+\d+(?:\.\d+)?[wx])?",
    re.IGNORECASE,
)
_IMAGE_RULE_PATTERN: re.Pattern[str] = re.compile(r"rule=\$_(\d+)")
_SRCSET_DESCRIPTOR_PATTERN: re.Pattern[str] = re.compile(
    r"^(\d+(?:\.\d+)?)([wx])$",
    re.IGNORECASE,
)
_TRANSIENT_ERROR_MARKERS: tuple[str, ...] = (
    "timeout",
    "timed out",
    "net::err_",
    "econnreset",
    "econnrefused",
    "etimedout",
    "enotfound",
    "connection reset",
    "connection refused",
    "connection closed",
    "connection aborted",
    "network",
    "dns",
    "name not resolved",
    "unreachable",
    "temporary failure",
)

_MOBILE_UA_MARKERS: tuple[str, ...] = (
    "mobile",
    "iphone",
    "ipad",
    "ipod",
    "android",
    "windows phone",
    "blackberry",
    "opera mini",
    "mobi",
)
_HTML_BLOCK_MARKERS: tuple[tuple[str, str], ...] = (
    ("ip-bereich vorübergehend gesperrt", "Akamai IP range block (IP-Bereich vorübergehend gesperrt)"),
    ("ip-bereich vor&uuml;bergehend gesperrt", "Akamai IP range block (IP-Bereich vorübergehend gesperrt)"),
    ("cf-turnstile", "Cloudflare Turnstile challenge detected"),
    ("g-recaptcha", "reCAPTCHA challenge detected"),
    ("hcaptcha", "hCaptcha challenge detected"),
    ("verify you are human", "Human verification challenge detected"),
    ("access denied", "Access Denied block page detected"),
)

__all__ = [
    "ALLOWED_RADII",
    "BASE_URL",
    "BLOCKED_RESOURCE_TYPES",
    "BLOCKED_URL_PATTERNS",
    "KleinanzeigenError",
    "ValidationError",
    "KleinanzeigenBlockedError",
    "resolve_location_id",
    "build_search_url",
    "parse_breadcrumb",
    "parse_listings_html",
    "search_listings",
]


class KleinanzeigenError(Exception):
    """Base exception for Kleinanzeigen search errors."""


class ValidationError(KleinanzeigenError):
    """Raised when search input parameters fail validation."""


class KleinanzeigenBlockedError(KleinanzeigenError):
    """Raised when Kleinanzeigen blocks or challenges a request."""

    def __init__(
        self,
        status_code: int | None = None,
        url: str = "",
        reason: str = "Request blocked by Kleinanzeigen anti-bot protection",
    ) -> None:
        if isinstance(status_code, str) and not url:
            reason = status_code
            status_code = None
        self.status_code: int | None = status_code
        self.url: str = url
        self.reason: str = reason
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        message = "Kleinanzeigen request blocked"
        if self.status_code is not None:
            message += f" (HTTP {self.status_code})"
        if self.reason:
            message += f": {self.reason}"
        if self.url:
            message += f" [{self.url}]"
        return message

    def __str__(self) -> str:
        return self._format_message()


def _validate_non_negative_int(value: int | None, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValidationError(f"{field_name} must be >= 0.")
    return value


def _validate_positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValidationError(f"{field_name} must be an integer >= 1.")
    return value


def _validate_fetch_options(
    fetch_mode: str,
    use_playwright_fallback: bool,
    timeout: float,
) -> Literal["auto", "http", "browser"]:
    if not isinstance(fetch_mode, str) or fetch_mode not in _ALLOWED_FETCH_MODES:
        raise ValidationError(
            f"Invalid fetch_mode '{fetch_mode}'. Allowed values: {_ALLOWED_FETCH_MODES}."
        )
    if not isinstance(use_playwright_fallback, bool):
        raise ValidationError("use_playwright_fallback must be a boolean.")
    if fetch_mode == "browser" and not use_playwright_fallback:
        raise ValidationError("Cannot combine browser fetch mode with Playwright disabled.")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValidationError("timeout must be a positive number.")
    return fetch_mode  # type: ignore[return-value]


def _validate_search_params(
    query: str,
    postal_code: str | None = None,
    radius: int | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    limit: int = 10,
    page: int = 1,
) -> tuple[str, str | None, int | None, int | None, int | None, int, int]:
    if not isinstance(query, str) or not query.strip():
        raise ValidationError("query must be a non-empty string.")
    clean_query = query.strip()

    clean_postal: str | None = None
    if postal_code is not None:
        if not isinstance(postal_code, str):
            raise ValidationError("postal_code must be a 5-digit German PLZ string.")
        stripped_postal = postal_code.strip()
        if not _PLZ_PATTERN.fullmatch(stripped_postal):
            raise ValidationError(
                f"Invalid postal_code '{postal_code}'. Expected a 5-digit German PLZ."
            )
        clean_postal = stripped_postal

    if radius is not None:
        if clean_postal is None:
            raise ValidationError("radius cannot be specified without postal_code.")
        if isinstance(radius, bool) or not isinstance(radius, int) or radius not in ALLOWED_RADII:
            raise ValidationError(
                f"Invalid radius '{radius}'. Allowed values: {ALLOWED_RADII}."
            )

    clean_min = _validate_non_negative_int(min_price, "min_price")
    clean_max = _validate_non_negative_int(max_price, "max_price")
    if clean_min is not None and clean_max is not None and clean_min > clean_max:
        raise ValidationError("min_price cannot be greater than max_price.")

    clean_limit = _validate_positive_int(limit, "limit")
    clean_page = _validate_positive_int(page, "page")
    return clean_query, clean_postal, radius, clean_min, clean_max, clean_limit, clean_page


def _is_desktop_user_agent(user_agent: str) -> bool:
    lower = user_agent.lower()
    return bool(user_agent.strip()) and not any(
        marker in lower for marker in _MOBILE_UA_MARKERS
    )


def _get_user_agent() -> str:
    try:
        import fake_useragent

        try:
            ua = fake_useragent.UserAgent(
                browsers=["Chrome", "Edge"],
                platforms=["desktop"],
            )
        except TypeError:
            ua = fake_useragent.UserAgent()

        for _ in range(3):
            candidate = ua.random
            if isinstance(candidate, str) and _is_desktop_user_agent(candidate):
                return candidate.strip()
    except Exception:
        pass
    return _DEFAULT_USER_AGENT


def _build_headers() -> dict[str, str]:
    return {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        "Referer": f"{BASE_URL}/",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": _get_user_agent(),
    }


def _detect_block(status_code: int | None, html: str) -> str | None:
    lower_html = html.lower() if html else ""
    matched_marker: str | None = None

    for marker, description in _HTML_BLOCK_MARKERS:
        if marker in lower_html:
            matched_marker = description
            break

    if matched_marker is None and html and _CLOUDFLARE_TITLE_PATTERN.search(html):
        matched_marker = "Cloudflare challenge page detected"

    if status_code in _BLOCKED_STATUS_CODES:
        if matched_marker:
            return f"HTTP {status_code}: {matched_marker}"
        return f"HTTP {status_code} response received"

    return matched_marker


def _id_from_location_dict(entry: dict[object, object]) -> str | None:
    for field in ("id", "locationId", "key", "value"):
        raw = entry.get(field)
        if raw is None or isinstance(raw, bool):
            continue
        cleaned = str(raw).strip().lstrip("_")
        if cleaned and cleaned != "0":
            return cleaned
    return None


def _extract_location_id(payload: Any, postal_code: str) -> str | None:
    if isinstance(payload, list):
        fallback_id: str | None = None
        for entry in payload:
            if isinstance(entry, dict):
                candidate = _id_from_location_dict(entry)
                if not candidate:
                    continue
                row_text = " ".join(str(v) for v in entry.values() if v is not None)
                if postal_code in row_text:
                    return candidate
                if fallback_id is None:
                    fallback_id = candidate
            elif isinstance(entry, (str, int)) and not isinstance(entry, bool):
                cleaned = str(entry).strip().lstrip("_")
                if cleaned.isdigit() and int(cleaned) > 0:
                    return cleaned
        return fallback_id

    if isinstance(payload, dict):
        direct = _id_from_location_dict(payload)
        if direct:
            return direct

        for wrapper_key in ("locations", "recommendations", "suggestions", "results", "items"):
            nested = payload.get(wrapper_key)
            if isinstance(nested, (list, dict)):
                found = _extract_location_id(nested, postal_code)
                if found:
                    return found

        fallback_id = None
        for key, value in payload.items():
            cleaned_key = str(key).strip().lstrip("_")
            if cleaned_key.isdigit() and int(cleaned_key) > 0:
                if postal_code in str(value):
                    return cleaned_key
                if fallback_id is None:
                    fallback_id = cleaned_key
        return fallback_id

    return None


def resolve_location_id(
    postal_code: str,
    session: Any,
    headers: dict[str, str] | None,
    timeout: float = 10.0,
) -> str | None:
    """Best-effort lookup of Kleinanzeigen locationId for a German postal code.

    Returns None silently on any network error, block, or unexpected payload so
    search can fall back to locationStr-based URL resolution.
    """
    if not isinstance(postal_code, str) or not postal_code.strip():
        return None

    clean_postal = postal_code.strip()
    url = f"{BASE_URL}/s-ort-empfehlungen.json?query={quote_plus(clean_postal)}"
    requester = session if session is not None else requests

    try:
        req_headers = dict(headers) if headers else _build_headers()
        req_headers["Accept"] = "application/json, text/javascript, */*; q=0.01"
        resp = requester.get(
            url,
            headers=req_headers,
            timeout=timeout,
            allow_redirects=True,
        )
        if getattr(resp, "status_code", None) != 200:
            return None
        if _detect_block(resp.status_code, getattr(resp, "text", "") or ""):
            return None
        payload = resp.json()
        return _extract_location_id(payload, clean_postal)
    except Exception:
        return None


def build_search_url(
    query: str,
    postal_code: str | None = None,
    radius: int | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    location_id: str | None = None,
    page: int = 1,
) -> str:
    """Build a canonical Kleinanzeigen search URL for ``s-seite:{page}``."""
    clean_query, clean_postal, clean_radius, clean_min, clean_max, _, clean_page = (
        _validate_search_params(
            query=query,
            postal_code=postal_code,
            radius=radius,
            min_price=min_price,
            max_price=max_price,
            limit=1,
            page=page,
        )
    )

    price_path = ""
    if clean_min is not None or clean_max is not None:
        min_str = str(clean_min) if clean_min is not None else ""
        max_str = str(clean_max) if clean_max is not None else ""
        price_path = f"/s-preis:{min_str}:{max_str}"

    params: dict[str, str] = {"keywords": clean_query}
    if clean_postal is not None:
        params["locationStr"] = clean_postal
        if location_id is not None and str(location_id).strip():
            params["locationId"] = str(location_id).strip()
        if clean_radius is not None:
            params["radius"] = str(clean_radius)
    elif location_id is not None and str(location_id).strip():
        params["locationId"] = str(location_id).strip()

    return f"{BASE_URL}{price_path}/s-seite:{clean_page}?{urlencode(params)}"


def parse_breadcrumb(html: str) -> tuple[int | None, int | None]:
    """Parse Kleinanzeigen's breadcrumb summary into ``(total_results, total_pages)``.

    Accepts either full search result HTML (extracting ``#srp-breadcrumb-summary`` or
    ``.breadcrump-summary``) or a raw breadcrumb text string. Returns ``(None, None)``
    when no valid summary is found, or ``(total_results, None)`` when the range does
    not start at 1 so page size cannot be determined reliably.
    """
    if not isinstance(html, str) or not html.strip():
        return None, None

    text = html
    if "<" in html and ">" in html:
        soup = BeautifulSoup(html, "html.parser")
        summary_elem = soup.select_one(_BREADCRUMB_SELECTOR)
        if summary_elem is None:
            return None, None
        text = summary_elem.get_text(" ", strip=True)

    normalized = _normalize_text(text.replace("\xa0", " "))
    match = _BREADCRUMB_PATTERN.search(normalized)
    if not match:
        return None, None

    try:
        page_start = int(match.group(1).replace(".", ""))
        page_end = int(match.group(2).replace(".", ""))
        total = int(match.group(3).replace(".", ""))
    except ValueError:
        return None, None

    if page_start != 1:
        return total, None
    page_size = page_end
    if page_size <= 0:
        return total, None
    return total, math.ceil(total / page_size)


def _decode_response_text(resp: Any) -> str:
    raw_text = getattr(resp, "text", "") or ""
    encoding = getattr(resp, "encoding", None)
    content = getattr(resp, "content", None)
    headers = getattr(resp, "headers", None) or {}
    content_type = headers.get("Content-Type", "") or headers.get("content-type", "")

    if (
        encoding == "ISO-8859-1"
        and isinstance(content, (bytes, bytearray))
        and content
        and "charset" not in content_type.lower()
    ):
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return raw_text
    return raw_text


_CHROMIUM_BIN_NAMES: tuple[str, ...] = (
    "chrome.exe",
    "chrome",
    "chromium.exe",
    "chromium",
    "chrome-headless-shell.exe",
    "chrome-headless-shell",
)
_MACOS_APP_EXECUTABLES: tuple[tuple[str, str], ...] = (
    ("Google Chrome for Testing.app", "Google Chrome for Testing"),
    ("Chromium.app", "Chromium"),
)
_SYSTEM_CHROMIUM_COMMANDS: tuple[str, ...] = (
    "chromium",
    "chromium-browser",
    "google-chrome",
)
_MISSING_BINARY_MARKERS: tuple[str, ...] = (
    "executable doesn't exist",
    "please run the following command to download new browsers",
    "executable not found",
    "browser executable",
)
_MISSING_SHARED_LIB_MARKERS: tuple[str, ...] = (
    "host system is missing dependencies",
    "error while loading shared libraries",
    "cannot open shared object file",
    "libnspr4",
    "libnss3",
    "playwright install-deps",
)


def _resource_blocking_disabled() -> bool:
    return os.environ.get("BROWSER_DISABLE_RESOURCE_BLOCKING", "").strip() == "1"


def _get_cdp_url() -> str | None:
    return os.environ.get("BROWSER_CDP_URL", "").strip() or None


def _is_runnable_file(path: Path) -> bool:
    return path.is_file() and (sys.platform == "win32" or os.access(path, os.X_OK))


def _resolve_configured_browser_executable() -> str | None:
    raw = os.environ.get("BROWSER_EXECUTABLE_PATH", "").strip()
    if not raw:
        return None
    candidate = Path(raw).expanduser()
    if candidate.is_file():
        return str(candidate)
    if "/" not in raw and "\\" not in raw:
        resolved = shutil.which(raw)
        if resolved:
            return resolved
    raise FileNotFoundError(
        f"Configured BROWSER_EXECUTABLE_PATH does not exist or is not a file: {raw}"
    )


def _hermes_home_candidates() -> list[Path]:
    homes: list[Path] = []
    env_home = os.environ.get("HERMES_HOME", "").strip()
    if env_home:
        homes.append(Path(env_home).expanduser())
    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
        if local_appdata:
            homes.append(Path(local_appdata) / "hermes")
    homes.append(Path.home() / ".hermes")

    unique: list[Path] = []
    seen: set[str] = set()
    for home in homes:
        key = str(home)
        if key not in seen:
            seen.add(key)
            unique.append(home)
    return unique


def _chromium_dir_sort_key(path: Path) -> tuple[int, str]:
    suffix = path.name.removeprefix("chromium-")
    try:
        return (int(suffix), path.name)
    except ValueError:
        return (-1, path.name)


def _discover_chromium_executables() -> list[str]:
    candidates: list[str] = []

    for home in _hermes_home_candidates():
        tools_dir = home / "tools"
        if not tools_dir.is_dir():
            continue
        chromium_dirs = sorted(
            (p for p in tools_dir.glob("chromium-*") if p.is_dir()),
            key=_chromium_dir_sort_key,
            reverse=True,
        )
        for chromium_dir in chromium_dirs:
            search_dirs = [chromium_dir]
            for child in sorted(chromium_dir.iterdir()):
                if child.is_dir() and child.name.lower().startswith(("chrome", "chromium")):
                    search_dirs.append(child)
            for subdir in search_dirs:
                for bin_name in _CHROMIUM_BIN_NAMES:
                    exe = subdir / bin_name
                    if _is_runnable_file(exe):
                        candidates.append(str(exe))
                for app_name, bin_name in _MACOS_APP_EXECUTABLES:
                    exe = subdir / app_name / "Contents" / "MacOS" / bin_name
                    if _is_runnable_file(exe):
                        candidates.append(str(exe))

    if sys.platform != "win32":
        baked = Path("/etc/hermes/chromium-executable-path")
        if baked.is_file():
            try:
                baked_exe = Path(baked.read_text(encoding="utf-8-sig").strip())
                if _is_runnable_file(baked_exe):
                    candidates.append(str(baked_exe))
            except OSError:
                pass

    for cmd in _SYSTEM_CHROMIUM_COMMANDS:
        found = shutil.which(cmd)
        if found:
            candidates.append(found)

    return list(dict.fromkeys(candidates))


def _is_missing_browser_binary_error(exc: BaseException) -> bool:
    if isinstance(exc, FileNotFoundError):
        return True
    msg = str(exc).lower()
    return (
        any(marker in msg for marker in _MISSING_BINARY_MARKERS)
        or ("playwright install" in msg and "install-deps" not in msg)
    )


def _is_missing_shared_libs_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(marker in msg for marker in _MISSING_SHARED_LIB_MARKERS)


def _format_playwright_launch_error(exc: BaseException) -> str:
    if isinstance(exc, FileNotFoundError) and "BROWSER_EXECUTABLE_PATH" in str(exc):
        return str(exc)
    if _is_missing_shared_libs_error(exc):
        return (
            "Playwright Chromium failed to launch because required OS shared libraries "
            "are missing (e.g., libnspr4.so, libnss3.so). Install system browser "
            "dependencies ('playwright install-deps chromium'), set BROWSER_CDP_URL to "
            "a remote Chromium instance, or use fetch_mode='http'."
        )
    if _is_missing_browser_binary_error(exc):
        return (
            "Playwright Chromium executable not found. Run 'playwright install chromium "
            "--only-shell', set BROWSER_EXECUTABLE_PATH or BROWSER_CDP_URL, or use "
            "fetch_mode='http'."
        )
    return f"Playwright startup failed: {exc}"


def _block_heavy_resources(route: Any) -> None:
    """Abort heavy media/font/image/ad-tech routes unless resource blocking is disabled."""
    if _resource_blocking_disabled():
        route.continue_()
        return

    request = route.request
    resource_type = str(getattr(request, "resource_type", "") or "").lower()
    url = str(getattr(request, "url", "") or "")

    if resource_type in BLOCKED_RESOURCE_TYPES or any(
        pattern in url for pattern in BLOCKED_URL_PATTERNS
    ):
        route.abort()
    else:
        route.continue_()


def _retry_delay(attempt: int) -> float:
    return min((2 ** attempt) + random.uniform(0.1, 0.5), 5.0)


def _is_transient_network_error(exc: BaseException) -> bool:
    if isinstance(exc, KleinanzeigenError):
        return False
    if isinstance(exc, (TimeoutError, ConnectionError, requests.Timeout, requests.ConnectionError)):
        return True
    if "timeout" in type(exc).__name__.lower():
        return True
    message = str(exc).lower()
    return any(marker in message for marker in _TRANSIENT_ERROR_MARKERS)


class _PlaywrightSession:
    """Reusable sync Playwright browser and context for sequential page fetches."""

    def __init__(
        self,
        *,
        headers: dict[str, str],
        timeout: float,
        initial_status: int | None = None,
        initial_reason: str = "",
        initial_url: str = "",
    ) -> None:
        self._headers = headers
        self._timeout_ms = max(int(timeout * 1000), _MIN_PLAYWRIGHT_TIMEOUT_MS)
        self._initial_status = initial_status
        self._initial_reason = initial_reason
        self._initial_url = initial_url
        self._playwright_cm: Any = None
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None

    def _launch_chromium(self) -> Any:
        configured = _resolve_configured_browser_executable()
        if configured is not None:
            return self._playwright.chromium.launch(
                headless=True,
                executable_path=configured,
            )

        try:
            return self._playwright.chromium.launch(headless=True)
        except Exception as launch_exc:
            if not _is_missing_browser_binary_error(launch_exc):
                raise
            fallbacks = _discover_chromium_executables()
            if not fallbacks:
                raise
            last_exc: Exception = launch_exc
            for exe_path in fallbacks:
                try:
                    return self._playwright.chromium.launch(
                        headless=True,
                        executable_path=exe_path,
                    )
                except Exception as fallback_exc:
                    last_exc = fallback_exc
            raise last_exc

    def __enter__(self) -> _PlaywrightSession:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            if self._initial_reason:
                raise KleinanzeigenBlockedError(
                    status_code=self._initial_status,
                    url=self._initial_url,
                    reason=(
                        f"{self._initial_reason} "
                        "(playwright fallback unavailable; install optional browser extra or use fetch_mode='http')"
                    ),
                ) from exc
            raise KleinanzeigenError(
                "Playwright is unavailable for browser fetch mode; install optional "
                f"browser extra or use fetch_mode='http': {exc}"
            ) from exc

        try:
            self._playwright_cm = sync_playwright()
            self._playwright = self._playwright_cm.__enter__()
            cdp_url = _get_cdp_url()
            if cdp_url:
                self._browser = self._playwright.chromium.connect_over_cdp(cdp_url)
            else:
                self._browser = self._launch_chromium()
            self._context = self._browser.new_context(
                locale="de-DE",
                user_agent=self._headers.get("User-Agent", _DEFAULT_USER_AGENT),
                extra_http_headers={
                    "Accept-Language": self._headers.get(
                        "Accept-Language", "de-DE,de;q=0.9,en;q=0.8"
                    ),
                },
            )
            route_fn = getattr(self._context, "route", None)
            if not _resource_blocking_disabled() and callable(route_fn):
                route_fn("**/*", _block_heavy_resources)
            return self
        except KleinanzeigenError:
            self._close_resources()
            raise
        except Exception as exc:
            self._close_resources()
            detail = _format_playwright_launch_error(exc)
            if self._initial_reason:
                raise KleinanzeigenBlockedError(
                    status_code=self._initial_status,
                    url=self._initial_url,
                    reason=f"{self._initial_reason}; {detail}",
                ) from exc
            raise KleinanzeigenError(detail) from exc

    def __exit__(self, *args: object) -> None:
        self._close_resources()

    def _close_resources(self) -> None:
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright_cm is not None:
            try:
                self._playwright_cm.__exit__(None, None, None)
            except Exception:
                pass
            self._playwright_cm = None
            self._playwright = None

    def fetch_page(
        self,
        url: str,
        *,
        initial_status: int | None = None,
        initial_reason: str = "",
    ) -> str:
        """Load a single URL in a fresh page, clear cookies, and validate against blocks."""
        for attempt in range(_MAX_FETCH_RETRIES + 1):
            page = None
            try:
                page = self._context.new_page()
                response = page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=self._timeout_ms,
                )
                pw_status = response.status if response is not None else None
                pw_url = getattr(page, "url", None) or url
                pw_html = page.content()
            except Exception as exc:
                if attempt < _MAX_FETCH_RETRIES and _is_transient_network_error(exc):
                    time.sleep(_retry_delay(attempt))
                    continue
                if initial_reason:
                    raise KleinanzeigenBlockedError(
                        status_code=initial_status,
                        url=url,
                        reason=f"{initial_reason}; playwright fallback failed: {exc}",
                    ) from exc
                raise KleinanzeigenError(f"Playwright error fetching {url}: {exc}") from exc
            finally:
                if page is not None:
                    close_page = getattr(page, "close", None)
                    if callable(close_page):
                        try:
                            close_page()
                        except Exception:
                            pass
                clear_cookies = getattr(self._context, "clear_cookies", None)
                if callable(clear_cookies):
                    try:
                        clear_cookies()
                    except Exception:
                        pass

            pw_block_reason = _detect_block(pw_status, pw_html)
            if pw_block_reason is not None:
                raise KleinanzeigenBlockedError(
                    status_code=pw_status,
                    url=pw_url,
                    reason=pw_block_reason,
                )
            if pw_status is not None and pw_status >= 400:
                raise KleinanzeigenError(f"HTTP {pw_status} fetching {pw_url}")
            return pw_html

        raise KleinanzeigenError(f"Playwright error fetching {url}")


def _fetch_html_http(
    url: str,
    session: requests.Session,
    headers: dict[str, str],
    *,
    timeout: float,
) -> tuple[str, int | None, str]:
    """Fetch a single URL over HTTP, retrying only transient network timeouts/errors."""
    for attempt in range(_MAX_FETCH_RETRIES + 1):
        try:
            resp = session.get(
                url,
                headers=headers,
                timeout=timeout,
                allow_redirects=True,
            )
        except requests.RequestException as exc:
            if attempt < _MAX_FETCH_RETRIES and _is_transient_network_error(exc):
                time.sleep(_retry_delay(attempt))
                continue
            raise KleinanzeigenError(f"Network error fetching {url}: {exc}") from exc

        final_url = getattr(resp, "url", None) or url
        status_code = getattr(resp, "status_code", None)
        return _decode_response_text(resp), status_code, final_url

    raise KleinanzeigenError(f"Network error fetching {url}")


def _normalize_text(text: str) -> str:
    return " ".join(text.split())


def _element_classes(elem: Tag | None) -> set[str]:
    if elem is None:
        return set()
    raw_classes = elem.get("class")
    if isinstance(raw_classes, list):
        return {str(c).strip() for c in raw_classes if str(c).strip()}
    if isinstance(raw_classes, str):
        return {c for c in raw_classes.split() if c}
    return set()


def _has_class_or_ancestor_class(elem: Tag, class_name: str, stop_at: Tag) -> bool:
    current: Tag | None = elem
    while current is not None:
        if class_name in _element_classes(current):
            return True
        if current is stop_at:
            break
        parent = current.parent
        current = parent if isinstance(parent, Tag) else None
    return False


def _decode_astro_value(value: Any) -> Any:
    """Decode Astro's island prop serialization ([kind, payload] pairs)."""
    if (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], int)
        and not isinstance(value[0], bool)
    ):
        kind, inner = value
        if kind == 0 and isinstance(inner, dict):
            return {k: _decode_astro_value(v) for k, v in inner.items()}
        if kind == 1 and isinstance(inner, list):
            return [_decode_astro_value(v) for v in inner]
        return inner
    return value


def _parse_ad_previews(raw_props: list[Any]) -> dict[str, dict[str, Any]]:
    """Map ad ID to preview metadata decoded from Astro island props."""
    previews: dict[str, dict[str, Any]] = {}

    def collect(node: Any) -> None:
        if isinstance(node, dict):
            if "id" in node and any(
                key in node for key in ("sortingDate", "topAd", "appliedFeatures")
            ):
                previews[str(node["id"])] = node
            for value in node.values():
                collect(value)
        elif isinstance(node, list):
            for item in node:
                collect(item)

    for raw in raw_props:
        if not isinstance(raw, str):
            continue
        try:
            props = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if isinstance(props, dict):
            collect({k: _decode_astro_value(v) for k, v in props.items()})

    return previews


def _extract_page_ad_previews(soup: BeautifulSoup) -> dict[str, dict[str, Any]]:
    raw_props: list[Any] = []
    for island in soup.select("astro-island[props]"):
        raw = island.get("props")
        if raw is not None:
            raw_props.append(str(raw))
    return _parse_ad_previews(raw_props)


def _extract_ld_json(article: Tag) -> dict[str, Any] | None:
    for script in article.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, list):
            for entry in payload:
                if isinstance(entry, dict):
                    return entry
    return None


def _is_banner_card(article: Tag, parent_li: Tag | None) -> bool:
    for elem in (article, parent_li):
        classes = _element_classes(elem)
        if any(c in {"ad-banner", "banner"} or c.endswith("-banner") for c in classes):
            return True
    if article.select_one(".ad-banner, .banner") and not article.select_one(
        "h2, h3, .aditem-main--title-line, a[href*='/s-anzeige/']"
    ):
        return True
    return False


def _is_top_ad(
    article: Tag,
    parent_li: Tag | None,
    *,
    preview: dict[str, Any] | None = None,
) -> bool:
    if preview:
        if preview.get("topAd") is True:
            return True
        applied = preview.get("appliedFeatures")
        if isinstance(applied, list) and any(
            str(feature).strip().upper() == "TOP_AD" for feature in applied
        ):
            return True

    for elem in (article, parent_li):
        classes = _element_classes(elem)
        if "is-topad" in classes or "is-highlight" in classes:
            return True

    if article.select_one(".badge-topad, .is-topad, .is-highlight, [data-testid*='topad']"):
        return True

    for tag in article.find_all(True):
        aria_label = str(tag.get("aria-label") or "").lower()
        title_attr = str(tag.get("title") or "").lower()
        if "top-anzeige" in aria_label or "top-anzeige" in title_attr:
            return True

        tag_classes = _element_classes(tag)
        if any("description" in c for c in tag_classes):
            continue
        if tag.name in {"span", "i", "b", "strong", "small", "label", "button", "div", "p"}:
            if tag.find(["article", "h2", "h3", "p"]):
                continue
            text = _normalize_text(tag.get_text(" ", strip=True)).lower()
            if text == "top-anzeige" or (len(text) <= 40 and "top-anzeige" in text):
                return True

    return False


def _extract_first_text(root: Tag, selectors: tuple[str, ...]) -> str:
    for selector in selectors:
        elem = root.select_one(selector)
        if elem is not None:
            text = _normalize_text(elem.get_text(" ", strip=True))
            if text:
                return text
    return ""


def _extract_url(article: Tag) -> str:
    data_href = str(article.get("data-href") or "").strip()
    if data_href and data_href != "#" and not data_href.startswith("javascript:"):
        return urljoin(BASE_URL, data_href)

    link_selectors = (
        ".aditem-main--title-line a[href]",
        "h2 a[href]",
        "h3 a[href]",
        "a.ellipsis[href]",
        "a[href*='/s-anzeige/']",
        "a[href]",
    )
    for selector in link_selectors:
        for link in article.select(selector):
            href = str(link.get("href") or "").strip()
            if href and href != "#" and not href.startswith("javascript:"):
                return urljoin(BASE_URL, href)
    return ""


def _extract_title(article: Tag, *, ld_json: dict[str, Any] | None = None) -> str:
    title = _extract_first_text(
        article,
        (
            ".aditem-main--title-line a",
            ".aditem-main--title-line",
            "[data-testid='ad-title']",
            "[data-testid*='title']",
            "h2 a",
            "h3 a",
            "a.ellipsis",
            "h2",
            "h3",
        ),
    )
    if title:
        return title

    # Skip thumbnail wrapper links that only carry an image-count badge.
    for link in article.select("a[href*='/s-anzeige/']"):
        if link.select_one("img, [data-image-container]"):
            continue
        text = _normalize_text(link.get_text(" ", strip=True))
        if text:
            return text

    if ld_json:
        for key in ("title", "name"):
            raw = ld_json.get(key)
            if isinstance(raw, str):
                cleaned = _normalize_text(raw)
                if cleaned:
                    return cleaned

    for link in article.select("a[href*='/s-anzeige/']"):
        text = _normalize_text(link.get_text(" ", strip=True))
        if text:
            return text
    return ""


def _find_matching_leaf_text(
    article: Tag,
    *,
    tags: tuple[str, ...],
    skip_class_tokens: tuple[str, ...],
    pattern: re.Pattern[str],
    max_length: int,
    skip_nodes: set[int] | None = None,
    skip_line_through: bool = False,
) -> tuple[str, Tag | None]:
    for elem in article.find_all(list(tags)):
        if elem.find(["span", "p", "div", "strong", "article"]):
            continue
        if skip_nodes and (
            id(elem) in skip_nodes or any(id(p) in skip_nodes for p in elem.parents)
        ):
            continue
        if skip_line_through and _has_class_or_ancestor_class(elem, "line-through", article):
            continue
        classes = _element_classes(elem)
        if any(token in c for c in classes for token in skip_class_tokens):
            continue
        if elem.find_parent(["h2", "h3"]):
            continue
        text = _normalize_text(elem.get_text(" ", strip=True))
        if text and len(text) <= max_length and pattern.search(text):
            return text, elem
    return "", None


def _extract_price(article: Tag) -> str:
    for elem in article.select("h3 ~ div > p.font-strong"):
        if _has_class_or_ancestor_class(elem, "line-through", article):
            continue
        text = _normalize_text(elem.get_text(" ", strip=True))
        if text:
            return text

    classic_selectors = (
        ".aditem-main--middle--price-shipping--price",
        ".aditem-main--price",
        "[data-testid='ad-price']",
        "[data-testid*='price']",
        ".price",
    )
    for selector in classic_selectors:
        for elem in article.select(selector):
            if _has_class_or_ancestor_class(elem, "line-through", article):
                continue
            text = _normalize_text(elem.get_text(" ", strip=True))
            if text:
                return text

    for elem in article.select("[class*='price']"):
        if _has_class_or_ancestor_class(elem, "line-through", article):
            continue
        classes = _element_classes(elem)
        if any("shipping" in c and not c.endswith("--price") for c in classes):
            continue
        if elem.select_one("[class*='price']"):
            continue
        text = _normalize_text(elem.get_text(" ", strip=True))
        if text:
            return text

    description_nodes = {id(node) for node in article.select("h3 + p")}
    matched_text, _ = _find_matching_leaf_text(
        article,
        tags=("p", "span", "strong", "div"),
        skip_class_tokens=("description", "title", "location", "shipping", "line-through"),
        pattern=_PRICE_TEXT_PATTERN,
        max_length=40,
        skip_nodes=description_nodes,
        skip_line_through=True,
    )
    return matched_text


def _clean_location_text(text: str) -> str:
    if not text:
        return ""
    value = str(text).replace("\xa0", " ")
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    value = _normalize_text(" ".join(lines))
    for prefix in ("Standort", "Ort"):
        if value.lower().startswith(prefix.lower()):
            rest = value[len(prefix) :]
            if not rest or rest[0] in (" ", ":", "-", "|", "•", "\t"):
                value = rest.strip(" :-|•")
                break
    return value.strip()


def _append_adjacent_distance(elem: Tag, location_text: str) -> str:
    if not location_text or _TRAILING_DISTANCE_PATTERN.search(location_text):
        return location_text

    candidates: list[Tag] = []
    next_sib = elem.find_next_sibling()
    if isinstance(next_sib, Tag):
        candidates.append(next_sib)
    parent = elem.parent
    if isinstance(parent, Tag) and parent.name in {"div", "span", "p"}:
        parent_next = parent.find_next_sibling()
        if isinstance(parent_next, Tag):
            candidates.append(parent_next)

    for candidate in candidates:
        cand_text = _normalize_text(candidate.get_text(" ", strip=True).replace("\xa0", " "))
        if _DISTANCE_ONLY_PATTERN.fullmatch(cand_text):
            return f"{location_text} {cand_text}"
    return location_text


def _pre_h3_location_spans(article: Tag) -> list[tuple[str, Tag]]:
    heading = article.select_one("h3")
    if heading is None:
        return []

    spans: list[tuple[str, Tag]] = []
    for node in article.descendants:
        if node is heading:
            break
        if not isinstance(node, Tag) or node.name != "span":
            continue
        if node.find(["span", "p", "div", "strong", "article"]):
            continue
        if node.find_parent("a") or node.find_parent(attrs={"data-image-container": True}):
            continue
        classes = _element_classes(node)
        if any(
            token in c
            for c in classes
            for token in ("price", "date", "top", "badge", "shipping", "line-through")
        ):
            continue
        cleaned = _clean_location_text(node.get_text(" ", strip=True))
        if not cleaned or len(cleaned) > 80:
            continue
        if (
            _DATE_TEXT_PATTERN.match(cleaned)
            or _DISTANCE_ONLY_PATTERN.fullmatch(cleaned)
            or "top-anzeige" in cleaned.lower()
            or cleaned.isdigit()
        ):
            continue
        spans.append((cleaned, node))
    return spans


def _extract_location(article: Tag) -> str:
    explicit_selectors = (
        ".aditem-main--top--left",
        "[data-testid='ad-location']",
        "[data-testid*='location']",
        ".aditem-main--location",
        ".location",
    )
    for selector in explicit_selectors:
        elem = article.select_one(selector)
        if elem is not None:
            cleaned = _clean_location_text(elem.get_text(" ", strip=True))
            if cleaned:
                return _append_adjacent_distance(elem, cleaned)

    top_block = article.select_one(".aditem-main--top")
    if top_block is not None:
        for child in top_block.find_all(["div", "span", "p"]):
            if child.find(["span", "p", "div", "strong", "article"]):
                continue
            classes = _element_classes(child)
            if any("right" in c or "date" in c for c in classes):
                continue
            cleaned = _clean_location_text(child.get_text(" ", strip=True))
            if (
                cleaned
                and not _DATE_TEXT_PATTERN.match(cleaned)
                and not _DISTANCE_ONLY_PATTERN.fullmatch(cleaned)
            ):
                return _append_adjacent_distance(child, cleaned)

    pre_h3_spans = _pre_h3_location_spans(article)
    for cleaned, span_elem in pre_h3_spans:
        if _PLZ_IN_TEXT_PATTERN.search(cleaned):
            return _append_adjacent_distance(span_elem, cleaned)

    plz_text, plz_elem = _find_matching_leaf_text(
        article,
        tags=("span", "p", "div"),
        skip_class_tokens=("description", "price", "title"),
        pattern=_PLZ_IN_TEXT_PATTERN,
        max_length=80,
    )
    if plz_text and plz_elem is not None:
        cleaned = _clean_location_text(plz_text)
        if cleaned:
            return _append_adjacent_distance(plz_elem, cleaned)

    if pre_h3_spans:
        cleaned, span_elem = pre_h3_spans[0]
        return _append_adjacent_distance(span_elem, cleaned)

    return ""


def _is_non_description_paragraph(elem: Tag, article: Tag) -> bool:
    if _has_class_or_ancestor_class(elem, "line-through", article):
        return True
    classes = _element_classes(elem)
    if "font-strong" in classes:
        return True
    if any(
        token in c
        for c in classes
        for token in ("price", "shipping", "location", "top", "date")
    ):
        return True
    if elem.has_attr("data-dhl-promotion") or elem.select_one("[data-dhl-promotion]") is not None:
        return True
    if "flex" in classes and not any(
        isinstance(child, NavigableString) and child.strip() for child in elem.contents
    ):
        return True
    return False


def _extract_description(
    article: Tag,
    *,
    title: str,
    price: str,
    location: str,
) -> str:
    explicit_selectors = (
        ".aditem-main--middle--description",
        "[data-testid='ad-description']",
        "[data-testid*='description']",
        ".aditem-main--description",
        ".description",
        "h3 + p",
    )
    for selector in explicit_selectors:
        elem = article.select_one(selector)
        if elem is None or _is_non_description_paragraph(elem, article):
            continue
        text = _normalize_text(elem.get_text(" ", strip=True))
        if text and text not in {title, price, location} and not _DATE_TEXT_PATTERN.match(text):
            return text

    for candidate in article.select(".aditem-main--middle p, p"):
        if _is_non_description_paragraph(candidate, article):
            continue
        text = _normalize_text(candidate.get_text(" ", strip=True))
        if not text:
            continue
        if text in {title, price, location} or _DATE_TEXT_PATTERN.match(text):
            continue
        return text

    return ""


def _parse_srcset_candidates(raw_srcset: str) -> list[tuple[str, float]]:
    cleaned = _DATA_URI_SRCSET_PATTERN.sub("", raw_srcset)
    candidates: list[tuple[str, float]] = []
    for chunk in cleaned.split(","):
        tokens = chunk.strip().split()
        if not tokens:
            continue
        url = tokens[0].strip()
        if not url or url.startswith("data:") or "placeholder" in url.lower():
            continue
        score = 0.0
        if len(tokens) > 1:
            desc_match = _SRCSET_DESCRIPTOR_PATTERN.match(tokens[1].strip())
            if desc_match:
                num = float(desc_match.group(1))
                unit = desc_match.group(2).lower()
                score = num if unit == "w" else num * 1000.0
        rule_match = _IMAGE_RULE_PATTERN.search(url)
        if score == 0.0 and rule_match:
            score = float(rule_match.group(1))
        candidates.append((url, score))
    return candidates


def _is_tiny_or_placeholder_image_url(url: str) -> bool:
    lower = url.lower()
    return "$_" "2.auto" in lower or "placeholder" in lower


def _pick_srcset_url(raw_srcset: str, *, prefer_highest: bool) -> str | None:
    candidates = _parse_srcset_candidates(raw_srcset)
    if not candidates:
        return None

    for url, _ in candidates:
        if "$_35.auto" in url.lower() or "$_59.auto" in url.lower():
            return url

    non_tiny = [(url, score) for url, score in candidates if not _is_tiny_or_placeholder_image_url(url)]
    pool = non_tiny if non_tiny else candidates
    if prefer_highest and len(pool) > 1:
        best_url, _ = max(pool, key=lambda item: item[1])
        return best_url
    return pool[0][0]


def _extract_image_url(
    article: Tag,
    *,
    ld_json: dict[str, Any] | None = None,
) -> str | None:
    img_candidates: list[Tag] = []
    for selector in (
        "[data-image-container] img",
        ".aditem-image img",
        ".imagebox img",
        "[data-testid*='image'] img",
        "[class*='image'] img",
        "img",
    ):
        for img in article.select(selector):
            if img not in img_candidates:
                img_candidates.append(img)

    tiny_fallback: str | None = None
    for img in img_candidates:
        raw_src = str(img.get("src") or "").strip()
        src_is_tiny_or_data = bool(
            raw_src
            and (
                raw_src.startswith("data:")
                or _is_tiny_or_placeholder_image_url(raw_src)
            )
        )

        for attr in ("data-src", "data-lazy-src"):
            raw_val = img.get(attr)
            if not raw_val:
                continue
            val = str(raw_val).strip()
            if not val or val.startswith("data:") or "placeholder" in val.lower():
                continue
            if _is_tiny_or_placeholder_image_url(val):
                if tiny_fallback is None:
                    tiny_fallback = urljoin(BASE_URL, val)
                continue
            return urljoin(BASE_URL, val)

        for attr in ("data-srcset", "srcset"):
            raw_set = img.get(attr)
            if not raw_set:
                continue
            picked = _pick_srcset_url(str(raw_set), prefer_highest=src_is_tiny_or_data)
            if picked:
                if _is_tiny_or_placeholder_image_url(picked):
                    if tiny_fallback is None:
                        tiny_fallback = urljoin(BASE_URL, picked)
                    continue
                return urljoin(BASE_URL, picked)

        if raw_src and not raw_src.startswith("data:") and "placeholder" not in raw_src.lower():
            resolved = urljoin(BASE_URL, raw_src)
            if _is_tiny_or_placeholder_image_url(raw_src):
                if tiny_fallback is None:
                    tiny_fallback = resolved
                continue
            return resolved

    if ld_json:
        for key in ("contentUrl", "image"):
            raw_ld_img = ld_json.get(key)
            if isinstance(raw_ld_img, str):
                cleaned = raw_ld_img.strip()
                if cleaned and not cleaned.startswith("data:"):
                    return urljoin(BASE_URL, cleaned)

    return tiny_fallback


def _parse_card(
    article: Tag,
    *,
    include_top_ads: bool,
    preview: dict[str, Any] | None = None,
) -> dict[str, str | None] | None:
    ad_id = str(article.get("data-adid") or "").strip()
    if not ad_id:
        return None

    parent_li = article.find_parent("li")
    if _is_banner_card(article, parent_li):
        return None

    if not include_top_ads and _is_top_ad(article, parent_li, preview=preview):
        return None

    ld_json = _extract_ld_json(article)
    url = _extract_url(article)
    title = _extract_title(article, ld_json=ld_json)
    if not title and not url:
        return None

    price = _extract_price(article)
    location = _extract_location(article)
    description = _extract_description(
        article,
        title=title,
        price=price,
        location=location,
    )
    image_url = _extract_image_url(article, ld_json=ld_json)

    return {
        "id": ad_id,
        "title": title,
        "price": price,
        "location": location,
        "url": url,
        "image_url": image_url,
        "description": description,
    }


def _extract_listings_page(
    html: str,
    *,
    include_top_ads: bool,
    limit: int | None = None,
) -> tuple[list[dict[str, str | None]], int]:
    soup = BeautifulSoup(html, "html.parser")
    previews = _extract_page_ad_previews(soup)
    articles = soup.select("article[data-adid]")

    results: list[dict[str, str | None]] = []
    seen_ids: set[str] = set()
    for article in articles:
        ad_id = str(article.get("data-adid") or "").strip()
        item = _parse_card(
            article,
            include_top_ads=include_top_ads,
            preview=previews.get(ad_id),
        )
        if item is None:
            continue
        item_id = str(item["id"])
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        results.append(item)
        if limit is not None and len(results) >= limit:
            break

    return results, len(articles)


def parse_listings_html(
    html: str,
    limit: int = 10,
    *,
    include_top_ads: bool = False,
) -> list[dict[str, str | None]]:
    """Parse Kleinanzeigen search result HTML into normalized listing dictionaries."""
    if not isinstance(html, str):
        raise ValidationError("html must be a string.")
    clean_limit = _validate_positive_int(limit, "limit")
    if not html.strip():
        return []

    results, _ = _extract_listings_page(
        html,
        include_top_ads=include_top_ads,
        limit=clean_limit,
    )
    return results


def search_listings(
    query: str,
    postal_code: str | None = None,
    radius: int | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    limit: int = 10,
    *,
    fetch_mode: Literal["auto", "http", "browser"] = "auto",
    use_playwright_fallback: bool = True,
    timeout: float = 20.0,
    include_top_ads: bool = False,
    html_override: str | None = None,
) -> list[dict[str, str | None]]:
    """Validate search parameters, fetch Kleinanzeigen results, and return listings."""
    clean_mode = _validate_fetch_options(fetch_mode, use_playwright_fallback, timeout)
    clean_query, clean_postal, clean_radius, clean_min, clean_max, clean_limit, _ = (
        _validate_search_params(
            query=query,
            postal_code=postal_code,
            radius=radius,
            min_price=min_price,
            max_price=max_price,
            limit=limit,
            page=1,
        )
    )

    if html_override is not None:
        return parse_listings_html(
            html_override,
            limit=clean_limit,
            include_top_ads=include_top_ads,
        )

    headers = _build_headers()
    allow_playwright = clean_mode == "browser" or (
        clean_mode == "auto" and use_playwright_fallback
    )

    with contextlib.ExitStack() as stack:
        http_session = (
            stack.enter_context(requests.Session())
            if clean_mode in ("auto", "http")
            else None
        )
        pw_session: _PlaywrightSession | None = None
        if clean_mode == "browser":
            pw_session = stack.enter_context(
                _PlaywrightSession(headers=headers, timeout=timeout)
            )

        def fetch_page(page_url: str) -> str:
            nonlocal pw_session
            if pw_session is not None:
                return pw_session.fetch_page(page_url)

            assert http_session is not None
            html_text, status_code, final_url = _fetch_html_http(
                page_url,
                session=http_session,
                headers=headers,
                timeout=timeout,
            )
            block_reason = _detect_block(status_code, html_text)
            if block_reason is not None:
                if not allow_playwright:
                    raise KleinanzeigenBlockedError(
                        status_code=status_code,
                        url=final_url,
                        reason=block_reason,
                    )
                pw_session = stack.enter_context(
                    _PlaywrightSession(
                        headers=headers,
                        timeout=timeout,
                        initial_status=status_code,
                        initial_reason=block_reason,
                        initial_url=final_url,
                    )
                )
                return pw_session.fetch_page(
                    page_url,
                    initial_status=status_code,
                    initial_reason=block_reason,
                )

            if status_code is not None and status_code >= 400:
                raise KleinanzeigenError(f"HTTP {status_code} fetching {final_url}")
            return html_text

        page1_url = build_search_url(
            query=clean_query,
            postal_code=clean_postal,
            radius=clean_radius,
            min_price=clean_min,
            max_price=clean_max,
            page=1,
        )
        page1_html = fetch_page(page1_url)
        all_results, _ = _extract_listings_page(
            page1_html,
            include_top_ads=include_top_ads,
            limit=clean_limit,
        )
        seen_ids: set[str] = {str(item["id"]) for item in all_results}

        if len(all_results) < clean_limit:
            _, total_pages = parse_breadcrumb(page1_html)
            if total_pages is not None and total_pages > 1:
                max_pages = min(total_pages, _MAX_PAGINATION_PAGES)
                for page_num in range(2, max_pages + 1):
                    if len(all_results) >= clean_limit:
                        break
                    time.sleep(_PAGE_DELAY_SECONDS)
                    page_url = build_search_url(
                        query=clean_query,
                        postal_code=clean_postal,
                        radius=clean_radius,
                        min_price=clean_min,
                        max_price=clean_max,
                        page=page_num,
                    )
                    page_html = fetch_page(page_url)
                    page_items, raw_card_count = _extract_listings_page(
                        page_html,
                        include_top_ads=include_top_ads,
                    )
                    if raw_card_count == 0 or not page_items:
                        break
                    for item in page_items:
                        item_id = str(item["id"])
                        if item_id in seen_ids:
                            continue
                        seen_ids.add(item_id)
                        all_results.append(item)
                        if len(all_results) >= clean_limit:
                            break

    return all_results
