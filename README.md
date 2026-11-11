# hermes-kleinanzeigen

An open-source [Hermes Agent](https://github.com/NousResearch/hermes-agent) **plugin and standalone skill** for searching and monitoring classifieds listings on **Kleinanzeigen Germany** (`kleinanzeigen.de`) by keyword, 5-digit German postal code (PLZ), search radius, and price range.

## Table of Contents

- [Features](#features)
- [Repository Layout](#repository-layout)
- [Installation](#installation)
- [Optional Browser Fallback (When HTTP Returns 403)](#optional-browser-fallback-when-http-returns-403)
- [Native Plugin Tools](#native-plugin-tools)
- [CLI Usage (`skills/kleinanzeigen/scripts/search_cli.py`)](#cli-usage-skillskleinanzeigenscriptssearch_clipy)
- [Automated Monitoring (`skills/kleinanzeigen/scripts/monitor.py`)](#automated-monitoring-skillskleinanzeigenscriptsmonitorpy)
- [Telegram Output Example](#telegram-output-example)
- [Bot Protection, Troubleshooting & Legal Notes](#bot-protection-troubleshooting--legal-notes)
- [Development & Testing](#development--testing)
- [Documentation & Further Reading](#documentation--further-reading)
- [Acknowledgments](#acknowledgments)
- [License](#license)

## Features

- **Dual Plugin + Standalone Skill repository**: Install as a native Hermes plugin (exposing `kleinanzeigen_search` and `kleinanzeigen_monitor` tools plus the bundled skill) or install only `skills/kleinanzeigen/` via `hermes skills install`.
- **Lightweight HTTP-first fetching**: Uses `requests`, `beautifulsoup4`, and `fake-useragent` out-of-the-box without requiring Chromium on hosts where HTTP succeeds (including minimal headless Linux).
- **Optional Playwright fallback**: Supports headless Chromium (`--browser` / `fetch_mode="browser"`, or automatic fallback in `auto` mode when Playwright is installed) with heavy subresource blocking—while strictly refusing to solve or bypass CAPTCHAs or Turnstile challenges.
- **Canonical URL builder & Astro/BEM parser**: Builds canonical `/s-preis:{min}:{max}/s-seite:{page}` search URLs (supporting `locationStr` + `radius` including `0`) and parses both Astro SSR markup (`<astro-island>` `topAd` metadata, `application/ld+json` fallbacks, `[data-image-container]` images) and classic BEM/Tailwind cards while excluding `Top-Anzeige` placements by default.
- **Sequential multi-page pagination**: Reads breadcrumb page totals and fetches additional result pages sequentially up to `--limit` (with polite delays and context cookie clearing between pages).
- **SQLite-backed cron monitoring**: Tracks seen listing IDs by normalized SHA-256 query hash in SQLite (`seen_ads`) and emits only newly discovered listings as JSON or Telegram-ready Markdown.
- **Cross-platform support**: Works on Linux, macOS, and Windows (PowerShell and Hermes Git Bash `terminal`).

## Repository Layout

```text
.
├── .github/
│   └── workflows/
│       └── ci.yml                       # Cross-platform CI matrix (Linux/macOS/Windows, Python 3.11–3.14)
├── .gitignore
├── CHANGELOG.md                         # Release history (Keep a Changelog)
├── CONTRIBUTING.md                      # Dev setup, Hermes validation/linting, and anti-bot policy
├── LICENSE                              # MIT License (including DanielWTE/ebay-kleinanzeigen-api notice)
├── README.md                            # Dual Plugin + Standalone Skill documentation
├── __init__.py                          # Hermes plugin entrypoint (register(ctx))
├── docs/
│   └── ARCHITECTURE.md                  # Technical design, parser, Playwright, SQLite, and runtime paths
├── plugin.yaml                          # Hermes plugin manifest v2
├── pyproject.toml                       # Package metadata and optional [browser]/[dev] extras
├── skills/
│   └── kleinanzeigen/
│       ├── LICENSE                      # MIT License copy for standalone skill installs
│       ├── SKILL.md                     # Hermes Agent skill definition and workflow
│       ├── requirements.txt             # Core lightweight deps (+ optional Playwright note)
│       └── scripts/
│           ├── __init__.py
│           ├── kleinanzeigen_api.py     # Validation, URL builder, HTTP/Playwright fetcher, parser
│           ├── monitor.py               # SQLite deduplicating monitor CLI (JSON & Telegram)
│           └── search_cli.py            # One-shot search CLI (JSON stdout)
└── tests/                               # Offline unit & CLI test suite with HTML fixtures
```

## Installation

### Primary & Recommended: Hermes Plugin

Installing as a **native Hermes plugin** is the recommended method. Hermes Plugin Manager automatically manages dependencies (`requests`, `beautifulsoup4`, `fake-useragent`) in Hermes's environment, registers native function tools (`kleinanzeigen_search`, `kleinanzeigen_monitor`), and provides the skill instructions with **zero manual virtualenv configuration**:

```bash
# One-command installation from GitHub
hermes plugins install clockwork-dev/hermes-kleinanzeigen --enable --yes-deps

# Or install from a local git clone via file:// URL
hermes plugins install "file:///path/to/hermes-kleinanzeigen" --enable --yes-deps
```

Verify the plugin state:

```bash
hermes plugins list
hermes plugins doctor kleinanzeigen
```

---

### Secondary / Fallback: Standalone Skill (Advanced / Minimal Environments)

> [!NOTE]
> Use this method **only** if you are operating in a minimal Hermes setup where plugins are disabled or restricted. In standalone skill mode, Hermes **does not** automatically install Python dependencies, and the agent must execute scripts through the shell (`terminal`) instead of calling native tools.

Install only `skills/kleinanzeigen/` via `hermes skills install`:

```bash
hermes skills install clockwork-dev/hermes-kleinanzeigen/kleinanzeigen
```

Or manually copy `skills/kleinanzeigen/`:
- **Linux / macOS**: `~/.hermes/skills/kleinanzeigen/`
- **Windows**: `%LOCALAPPDATA%\hermes\skills\productivity\kleinanzeigen\`

#### Managing Dependencies for Standalone Skill Mode

Because standalone skills do not auto-install dependencies, provision an isolated environment with Hermes PM:

```bash
# Linux / macOS / Windows Git Bash
PY="$(hermes pm environment kleinanzeigen \
  --requirement 'requests>=2.31,<3' \
  --requirement 'beautifulsoup4>=4.12,<5' \
  --requirement 'fake-useragent>=1.4,<3')"
"$PY" "${HERMES_SKILL_DIR}/scripts/search_cli.py" "fahrrad" --plz 10115 --radius 10 --max-price 500
```

```powershell
# Windows PowerShell
$env:PY = hermes pm environment kleinanzeigen `
  --requirement 'requests>=2.31,<3' `
  --requirement 'beautifulsoup4>=4.12,<5' `
  --requirement 'fake-useragent>=1.4,<3'
& $env:PY "$env:LOCALAPPDATA\hermes\skills\productivity\kleinanzeigen\scripts\search_cli.py" "fahrrad" --plz 10115 --radius 10 --max-price 500
```

For manual CLI usage outside of Hermes (`uv` or standard `venv`):

```bash
# Linux / macOS
uv venv .venv
uv pip install --python .venv/bin/python -r skills/kleinanzeigen/requirements.txt

# Windows PowerShell
uv venv .venv
uv pip install --python .\.venv\Scripts\python.exe -r skills/kleinanzeigen/requirements.txt
```

## Optional Browser Fallback (When HTTP Returns 403)

Default `auto` mode performs an HTTP `requests` fetch first and works without Playwright or Chromium on hosts whose IP is not blocked (including minimal headless Linux servers).

Only install Playwright + Chromium if your IP receives HTTP `403` (`IP-Bereich vorübergehend gesperrt`):

```bash
# Plugin / package checkout: install optional browser dependency
pip install ".[browser]"
# Or in a standalone skill venv:
# uv pip install --python .venv/bin/python "playwright>=1.49.0"

# Download headless Chromium shell (all platforms)
playwright install chromium --only-shell

# Headless Linux / Debian only: install missing OS shared libraries (libnspr4, libnss3, libgbm1, etc.)
sudo playwright install-deps chromium
```

> **Reusing an existing browser binary**: Set `BROWSER_EXECUTABLE_PATH` to point Playwright at an existing Chrome/Chromium executable, or set `BROWSER_CDP_URL` to connect to an already-running Chromium instance via CDP.

## Native Plugin Tools

When enabled as a plugin, Hermes exposes two tools directly to the model:

| Tool | Parameters | Behavior |
| --- | --- | --- |
| `kleinanzeigen_search` | `query` (required), `postal_code`, `radius`, `min_price`, `max_price`, `limit` (default `10`), `fetch_mode` (`"auto"` \| `"http"` \| `"browser"`), `include_top_ads` | Runs `search_listings(...)` and returns JSON listings and count |
| `kleinanzeigen_monitor` | Same search parameters plus `format` (`"json"` \| `"telegram"`), `dry_run`, `db_path` | Deduplicates seen ads in SQLite (`$HERMES_HOME/plugin-data/kleinanzeigen/seen_ads.db` by default) |

## CLI Usage (`skills/kleinanzeigen/scripts/search_cli.py`)

`search_cli.py` writes a JSON array of listing objects to `stdout` and diagnostics/errors to `stderr` (exit code `0` on success, `1` on validation, block, or runtime error).

```bash
# Linux / macOS
.venv/bin/python skills/kleinanzeigen/scripts/search_cli.py "fahrrad" --plz 10115 --radius 10 --min-price 50 --max-price 500 --limit 10
```

```powershell
# Windows PowerShell
.\.venv\Scripts\python.exe skills\kleinanzeigen\scripts\search_cli.py "fahrrad" --plz 10115 --radius 10 --min-price 50 --max-price 500 --limit 10
```

### Options

| Flag | Description | Notes |
| --- | --- | --- |
| `query` | Positional search keywords | Required, non-empty |
| `--plz` | 5-digit German postal code | Optional (`^\d{5}$`); omit for nationwide search |
| `--radius` | Search radius in km | Requires `--plz`; allowed: `0, 5, 10, 20, 30, 50, 100, 150, 200` |
| `--min-price` | Minimum price in EUR | Integer `>= 0` |
| `--max-price` | Maximum price in EUR | Integer `>= 0`, must satisfy `min <= max` |
| `--limit` | Maximum listings to return | Integer `>= 1` (default `10`; paginates sequentially across pages) |
| `--browser` | Fetch directly via headless Playwright | Skips `requests` HTTP preflight; mutually exclusive with `--no-browser` |
| `--no-browser` | Disable Playwright fallback | HTTP-only mode; mutually exclusive with `--browser` |
| `--include-top-ads` | Include `Top-Anzeige` / highlighted ads | Excluded by default (classic DOM and Astro `topAd` metadata) |
| `--html-file` | Path to saved search HTML | Offline parsing without network requests |

### Environment Variables

| Variable | Effect | Default |
| --- | --- | --- |
| `BROWSER_EXECUTABLE_PATH` | Path to an explicit Chromium/Chrome executable for Playwright | Auto-discovered (Playwright cache / Hermes tools / system `PATH`) |
| `BROWSER_CDP_URL` | Connect Playwright to an existing Chromium endpoint via `connect_over_cdp` | Unset (local headless launch) |
| `BROWSER_DISABLE_RESOURCE_BLOCKING` | Set to `1` to disable interception of `image`, `media`, `font`, and ad-tech/consent URLs (stylesheets stay enabled) | Blocking enabled |
| `KLEINANZEIGEN_DB_PATH` | Override default SQLite database path for `monitor.py` | `~/.hermes/skills/kleinanzeigen/data/seen_ads.db` |

### JSON Output Schema

```json
[
  {
    "id": "2987654321",
    "title": "Gravel Bike 28 Zoll Top Zustand",
    "price": "420 € VB",
    "location": "10115 Berlin-Mitte",
    "url": "https://www.kleinanzeigen.de/s-anzeige/gravel-bike-28-zoll/2987654321-217-3352",
    "image_url": "https://img.kleinanzeigen.de/api/v1/prod-ads/images/ab/abcd.jpg?rule=$_35.JPG",
    "description": "Kaum gefahrenes Gravel Bike mit Scheibenbremsen..."
  }
]
```

## Automated Monitoring (`skills/kleinanzeigen/scripts/monitor.py`)

`monitor.py` accepts all `search_cli.py` flags (including `--browser` and `--no-browser`, which do not affect SQLite `query_hash` deduplication) plus SQLite state tracking so repeated runs emit **only newly seen listings**.

| Extra Flag | Description | Default |
| --- | --- | --- |
| `--db` | Path to SQLite database | `$KLEINANZEIGEN_DB_PATH` or `~/.hermes/skills/kleinanzeigen/data/seen_ads.db` |
| `--format` | Output format (`json` or `telegram`) | `json` |
| `--dry-run` | Print unseen ads without writing to SQLite | `false` |

> **Windows DB path tip**: Pass `--db "${HERMES_SKILL_DIR}/data/seen_ads.db"` (or set `KLEINANZEIGEN_DB_PATH`) when running standalone scripts so state stays under `%LOCALAPPDATA%\hermes\...` rather than `%USERPROFILE%\.hermes\...`.

SQLite table created automatically:

```sql
CREATE TABLE IF NOT EXISTS seen_ads (
    ad_id TEXT PRIMARY KEY,
    query_hash TEXT,
    seen_at TIMESTAMP
);
```

When `--format telegram` finds zero unseen listings, it prints nothing to `stdout` and logs `No new listings.` to `stderr`, preventing empty cron notifications.

### Linux / macOS Cron Example

```cron
*/30 * * * * cd ~/.hermes/skills/kleinanzeigen && .venv/bin/python scripts/monitor.py "rtx 4080" --plz 80331 --radius 50 --max-price 900 --format telegram >> /tmp/kleinanzeigen.log 2>&1
```

### Windows Task Scheduler Example

- **Program/script**: `%LOCALAPPDATA%\hermes\skills\productivity\kleinanzeigen\.venv\Scripts\python.exe`
- **Arguments**: `scripts\monitor.py "fahrrad" --plz 10115 --radius 10 --max-price 500 --format telegram --db data\seen_ads.db`
- **Start in**: `%LOCALAPPDATA%\hermes\skills\productivity\kleinanzeigen`

Or let Hermes Agent schedule checks natively with its built-in `cronjob` tool (calling `kleinanzeigen_monitor` when the plugin is enabled).

## Telegram Output Example

```markdown
🔍 **Kleinanzeigen: 2 объявлений по запросу "fahrrad"**
📍 Локация: 10115 (+10 км)

1. **[Gravel Bike 28 Zoll Top Zustand](https://www.kleinanzeigen.de/s-anzeige/gravel-bike-28-zoll/2987654321-217-3352)** — **420 € VB**
   📍 10115 Berlin-Mitte
   📝 Kaum gefahrenes Gravel Bike mit Scheibenbremsen...
```

## Bot Protection, Troubleshooting & Legal Notes

- **HTTP 403 / IP-range blocks & fetch modes**: Datacenter, VPN, and some IP ranges may receive HTTP `403` (`IP-Bereich vorübergehend gesperrt.`) on raw `requests` calls. Default `auto` mode tries HTTP first and falls back to Playwright if installed; pass `--browser` (`fetch_mode="browser"`) to skip the HTTP preflight, or `--no-browser` (`fetch_mode="http"`) for HTTP-only mode.
- **Missing Chromium / shared libraries**: If Playwright is not installed or headless Linux lacks OS shared libs (`libnspr4.so`, `libnss3.so`, etc.), `kleinanzeigen_api.py` returns an actionable error explaining how to install `[browser]` / `playwright install chromium --only-shell` / `playwright install-deps chromium`.
- **Strict non-bypass policy**: Neither the scripts, plugin tools, nor `SKILL.md` ever attempt to solve, click through, wait out, or bypass CAPTCHAs, Cloudflare Turnstile, or proof-of-work gates.
- **Terms of Service**: Use this project responsibly for personal, non-commercial search and low-frequency monitoring (e.g., every 30–60 minutes) without overloading `kleinanzeigen.de`.

## Development & Testing

Linux / macOS:

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/python -m pytest -v
hermes plugins validate .
```

Windows (PowerShell):

```powershell
uv venv .venv
uv pip install --python .\.venv\Scripts\python.exe -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -v
hermes plugins validate .
```

## Documentation & Further Reading

- [Architecture Guide](docs/ARCHITECTURE.md) — dual Plugin + Standalone Skill design, validation rules, URL builder, Playwright Chromium discovery & resource blocking, Astro/BEM/JSON-LD parser, SQLite schema, and cross-platform storage paths
- [Skill Definition](skills/kleinanzeigen/SKILL.md) — Hermes Agent skill metadata, parameter mapping, and execution workflow
- [Contributing Guide](CONTRIBUTING.md) — cross-platform dev setup, `pytest` / `hermes plugins validate` / `hermes plugins doctor` / `skill_linter`, and strict anti-bot and security rules
- [Changelog](CHANGELOG.md) — release history

## Acknowledgments

- Playwright browser management, resource interception (`BROWSER_DISABLE_RESOURCE_BLOCKING`, `BROWSER_CDP_URL`), sequential pagination, breadcrumb parsing, and Astro / `<astro-island>` / JSON-LD extraction patterns are adapted from [`DanielWTE/ebay-kleinanzeigen-api`](https://github.com/DanielWTE/ebay-kleinanzeigen-api) (MIT License, `Copyright (c) 2023 Daniel`).

## License

Released under the [MIT License](LICENSE).
