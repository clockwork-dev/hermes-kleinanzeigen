---
name: kleinanzeigen
description: "Search and monitor Kleinanzeigen by PLZ, radius, and price."
category: productivity
version: "1.0.0"
author: "Hermes Kleinanzeigen Skill Contributors"
license: MIT
platforms:
  - linux
  - macos
  - windows
metadata:
  hermes:
    tags:
      - kleinanzeigen
      - classifieds
      - germany
      - price-monitoring
      - shopping
---

# Kleinanzeigen

Search classifieds listings on `kleinanzeigen.de` (Germany) by keyword, 5-digit PLZ, radius, and price range, and monitor searches for new listings with SQLite deduplication.

## When to Use

- Searching Kleinanzeigen Germany for local or shipped items (e.g., bikes, electronics, furniture near a PLZ).
- Setting up recurring listing or price-drop checks with duplicate filtering (`kleinanzeigen_monitor` or `scripts/monitor.py` via `cronjob`).
- Don't use for non-German sites, automated messaging/bidding, or bypassing login/CAPTCHA walls.

## Prerequisites & Execution

1. **Primary: Native Plugin Mode (Preferred)**:
   When installed as a Hermes plugin, the native tools `kleinanzeigen_search` and `kleinanzeigen_monitor` are registered directly in your context. **Always use these tools first** — all dependencies and the SQLite database (`$HERMES_HOME/plugin-data/kleinanzeigen/seen_ads.db`) are managed automatically with zero terminal overhead and fast JSON responses.

2. **Secondary / Fallback: Standalone Skill Mode (via `terminal`)**:
   If the native plugin tools are not available (e.g. running in a minimal environment without plugin support), invoke the bundled Python scripts in `scripts/` via the Hermes `terminal` tool. Dependencies are declared in [requirements.txt](requirements.txt).

   Resolve an isolated Python interpreter using Hermes PM (works on Linux, macOS, and Windows Git Bash):

```bash
if [ -x "${HERMES_SKILL_DIR}/.venv/Scripts/python.exe" ]; then
  PY="${HERMES_SKILL_DIR}/.venv/Scripts/python.exe"
elif [ -x "${HERMES_SKILL_DIR}/.venv/bin/python" ]; then
  PY="${HERMES_SKILL_DIR}/.venv/bin/python"
elif command -v hermes >/dev/null 2>&1; then
  PY="$(hermes pm environment kleinanzeigen --requirement 'requests>=2.31,<3' --requirement 'beautifulsoup4>=4.12,<5' --requirement 'fake-useragent>=1.4,<3')"
elif python3 -c "import requests, bs4, fake_useragent" 2>/dev/null; then
  PY="python3"
else
  PY="python"
fi
```

If neither `hermes`, `${HERMES_SKILL_DIR}/.venv`, nor global packages are present, invoke directly via `uv run --with-requirements "${HERMES_SKILL_DIR}/requirements.txt" python "${HERMES_SKILL_DIR}/scripts/search_cli.py" ...`. Always quote `"$PY"` and `"${HERMES_SKILL_DIR}/scripts/..."` for Windows Git Bash compatibility.

## How to Run

Both CLIs exit `0` on success (`stdout` only) and `1` on errors (`stderr` only). Default `auto` mode uses lightweight HTTP first and only attempts Playwright fallback if installed and HTTP is blocked.

```bash
"$PY" "${HERMES_SKILL_DIR}/scripts/search_cli.py" "fahrrad" --plz 10115 --radius 10 --min-price 50 --max-price 500 --limit 10
```

```bash
"$PY" "${HERMES_SKILL_DIR}/scripts/monitor.py" "fahrrad" --plz 10115 --radius 10 --max-price 500 --format telegram --db "${HERMES_SKILL_DIR}/data/seen_ads.db"
```

## Quick Reference

### Natural-Language Parameter Mapping

| User Intent | CLI Flag | Validation / Allowed Values |
| --- | --- | --- |
| Item keywords | `query` (positional) | Required non-empty string |
| German postal code | `--plz <NNNNN>` | Optional 5-digit PLZ (`^\d{5}$`); omit for nationwide |
| Search radius (km) | `--radius <N>` | Requires `--plz`; only `0, 5, 10, 20, 30, 50, 100, 150, 200` |
| Price range (EUR) | `--min-price`, `--max-price` | Non-negative ints; `min <= max` |
| Result count | `--limit <N>` | Int `>= 1` (default `10`; paginates sequentially across pages) |

### Additional Flags & Environment Variables

- `scripts/search_cli.py`:
  - `--browser`: Skip HTTP preflight and fetch via headless Playwright (mutually exclusive with `--no-browser`).
  - `--no-browser`: Disable Playwright fallback on HTTP block (mutually exclusive with `--browser`).
  - `--include-top-ads`: Include Top-Anzeige / highlighted sponsored ads.
  - `--html-file <path>`: Parse a saved HTML file offline without network calls.
- `scripts/monitor.py` (accepts all search flags above plus):
  - `--db <path>`: SQLite DB path (defaults to `KLEINANZEIGEN_DB_PATH` or `~/.hermes/skills/kleinanzeigen/data/seen_ads.db`).
  - `--format json|telegram`: Output format (default `json`).
  - `--dry-run`: Return unseen listings without updating SQLite.
- Optional Playwright & DB env vars:
  - `BROWSER_EXECUTABLE_PATH`: Path to an existing Chromium/Chrome binary for Playwright to launch.
  - `BROWSER_CDP_URL`: Connect Playwright to an external Chromium CDP endpoint instead of launching locally.
  - `BROWSER_DISABLE_RESOURCE_BLOCKING=1`: Disable Playwright blocking of images, media, fonts, and ad-tech/consent URLs (stylesheets stay enabled).
  - `KLEINANZEIGEN_DB_PATH`: Default SQLite DB path override for `scripts/monitor.py`.

## Procedure

### 1. Map parameters

Extract `query`, optional 5-digit `--plz`, optional `--min-price` / `--max-price`, and `--limit`. Snap requested distances to the nearest valid `--radius` step (`0, 5, 10, 20, 30, 50, 100, 150, 200`) only when `--plz` is provided. Multi-page queries paginate sequentially up to `--limit`.

### 2. Run search or monitor

Prefer `kleinanzeigen_search` / `kleinanzeigen_monitor` if available; otherwise execute `"${HERMES_SKILL_DIR}/scripts/search_cli.py"` or `"${HERMES_SKILL_DIR}/scripts/monitor.py"` via `terminal` and inspect `stdout`. Use `--browser` only when HTTP preflight is blocked and Playwright + Chromium are installed (`playwright install chromium --only-shell`, plus `playwright install-deps chromium` on headless Linux). For local HTML inspection, use `read_file`.

### 3. Handle bot protection

If the tool or CLI exits `1` with HTTP 403 (`IP-Bereich vorübergehend gesperrt`), 429/503, or a CAPTCHA/Turnstile notice on `stderr`:

- If HTTP-only `--no-browser` hit HTTP 403 without a CAPTCHA/Turnstile gate and Playwright/Chromium is available, retry with `--browser`; otherwise use `browser_exec` or `web_extract` on the search URL when available, or report the block clearly to the user.
- **Never attempt to solve, click through, wait out, or bypass any CAPTCHA, Turnstile, or anti-bot gate** (including during sequential pagination).

### 4. Format results for Telegram / chat

Format JSON results (or `monitor.py --format telegram` output, which stays silent on `stdout` when 0 new listings match) using this template:

```markdown
🔍 **Kleinanzeigen: [N] объявлений по запросу "[query]"**
📍 Локация: [PLZ] (+[radius] км)

1. **[Заголовок товара](URL)** — **Цена**
   📍 Локация
   📝 Краткое описание...
```

Adapt the location line to `Вся Германия` when `--plz` is omitted.

## Pitfalls

- Unquoted `${HERMES_SKILL_DIR}` in Git Bash on Windows strips backslashes (`\U`, `\k`); always quote `"$PY"` and `"${HERMES_SKILL_DIR}/..."`.
- Never hardcode `~/.hermes/skills/...` for script invocation on Windows (`~` resolves to `%USERPROFILE%`, whereas Hermes stores skills under `%HERMES_HOME%\skills`). Pass `--db "${HERMES_SKILL_DIR}/data/seen_ads.db"` when keeping standalone state inside the skill directory.
- Combining `--browser` and `--no-browser`, passing `--radius` without `--plz`, or passing a radius outside `0, 5, 10, 20, 30, 50, 100, 150, 200` raises `ValidationError`.
- Numeric `--min-price`/`--max-price` filters exclude pure `VB` listings with no numeric price.

## Verification

- [ ] Search parameters validated (5-digit PLZ, allowed radius step, `min <= max`).
- [ ] `"$PY"` and `"${HERMES_SKILL_DIR}/scripts/..."` quoted in `terminal` calls (or native plugin tools called).
- [ ] JSON parsed cleanly from `stdout` (or `No new listings.` handled silently).
- [ ] Any HTTP 403 / CAPTCHA block reported cleanly without bypass attempts.
- [ ] Telegram response matches the required markdown template.
