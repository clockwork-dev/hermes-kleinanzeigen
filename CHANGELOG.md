# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-11-11

### Added
- **Dual Hermes Plugin + Standalone Skill packaging**:
  - Added [`plugin.yaml`](plugin.yaml) (manifest v2, `kind: standalone`), [`__init__.py`](__init__.py) (`register(ctx)` exposing `kleinanzeigen_search`, `kleinanzeigen_monitor`, and the bundled `kleinanzeigen` skill), and [`pyproject.toml`](pyproject.toml) (`requires-python >= 3.11`, optional `[browser]` and `[dev]` extras).
  - Added self-contained [`skills/kleinanzeigen/`](skills/kleinanzeigen/) skill bundle (`SKILL.md`, `requirements.txt`, `LICENSE`, and `scripts/`) compatible with `hermes skills install` and `hermes pm environment`.
- **Core search, fetch, and HTML parsing engine (`skills/kleinanzeigen/scripts/kleinanzeigen_api.py`)**:
  - Input validation for `query`, 5-digit German `postal_code`, `ALLOWED_RADII` (`0, 5, 10, 20, 30, 50, 100, 150, 200`), `min_price` / `max_price`, `limit`, `page`, `fetch_mode`, and `timeout`.
  - Canonical `build_search_url()` (`/s-preis:{min}:{max}/s-seite:{page}` with `locationStr` and `radius`) plus best-effort `resolve_location_id()`.
  - Three fetch modes (`auto`, `http`, `browser`) and offline `html_override`, with transient network retries and breadcrumb-driven sequential pagination (`parse_breadcrumb()`).
  - Optional Playwright Chromium engine (`_PlaywrightSession`) with heavy subresource blocking (`BLOCKED_RESOURCE_TYPES`, `BLOCKED_URL_PATTERNS`, `BROWSER_DISABLE_RESOURCE_BLOCKING`), `BROWSER_CDP_URL` support, and cross-platform Chromium discovery (`BROWSER_EXECUTABLE_PATH`, `$HERMES_HOME/tools/chromium-*`, `/etc/hermes/chromium-executable-path`, system `PATH`).
  - Multi-generation parser (`parse_listings_html()`) supporting Astro SSR (`<astro-island>` `topAd` / `appliedFeatures`), `application/ld+json` fallbacks, and classic BEM/Tailwind cards, excluding banner and Top-Anzeige cards by default.
- **CLI tools & SQLite monitoring (`search_cli.py`, `monitor.py`)**:
  - `search_cli.py` with UTF-8 Windows stream handling, `--browser` / `--no-browser`, `--include-top-ads`, `--html-file`, and JSON `stdout`.
  - `monitor.py` with SHA-256 `query_hash` tracking, SQLite `seen_ads` deduplication, `--dry-run`, `--db` / `KLEINANZEIGEN_DB_PATH` resolution, and Russian Telegram Markdown formatting (`--format telegram`).
- **Tests, documentation, and CI**:
  - Offline unit and CLI/plugin integration suite in [`tests/test_kleinanzeigen.py`](tests/test_kleinanzeigen.py).
  - Project documentation (`README.md`, [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`CONTRIBUTING.md`](CONTRIBUTING.md)) and GitHub Actions CI matrix ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

### Security
- Implemented strict block detection (`_detect_block()`, `KleinanzeigenBlockedError`) for HTTP `403`/`429`/`503`, Akamai IP range blocks, Cloudflare Turnstile, reCAPTCHA, and hCaptcha without any CAPTCHA solving or anti-bot bypass logic.
