# LLM Context & Agent Architecture Guide: hermes-kleinanzeigen

> Machine-readable technical reference and operational guidelines for LLMs and AI coding agents working on, maintaining, or integrating `clockwork-dev/hermes-kleinanzeigen`.

---

## 1. Project Purpose & Scope

- **Repository**: `clockwork-dev/hermes-kleinanzeigen`
- **Target Platform**: [Hermes Agent](https://github.com/NousResearch/hermes-agent) (by Nous Research)
- **Domain**: Classifieds search and polling monitor for **Kleinanzeigen Germany** (`https://www.kleinanzeigen.de`).
- **Distribution Model**:
  1. **Primary & Recommended**: Native Hermes Plugin (v2 manifest via `plugin.yaml`, exposes `kleinanzeigen_search` and `kleinanzeigen_monitor` tools).
  2. **Secondary / Fallback**: Standalone Hermes Skill (`skills/kleinanzeigen/SKILL.md`), invoked via shell subprocess commands.

---

## 2. Directory Layout & Key Files

```text
.
├── plugin.yaml                          # Hermes Plugin Manifest (v2 specification)
├── __init__.py                          # Plugin entrypoint: register(ctx)
├── pyproject.toml                       # Python package configuration (build-backend = "hatchling.build")
├── docs/                                # GitHub Pages static documentation website
│   ├── index.html                       # Semantic WCAG AA document with interactive query builder
│   ├── style.css                        # Pure CSS (dark/light themes, full mobile responsiveness)
│   ├── app.js                           # URL builder matching python API, theme switcher, copy handler
│   ├── DESIGN.md                        # Antislop style direction & dials
│   └── ARCHITECTURE.md                  # Comprehensive technical deep-dive
├── skills/
│   └── kleinanzeigen/
│       ├── SKILL.md                     # Skill instructions loaded into LLM context
│       ├── requirements.txt             # Core dependencies (requests, beautifulsoup4, fake-useragent)
│       ├── LICENSE                      # Standalone MIT license copy
│       └── scripts/
│           ├── __init__.py
│           ├── kleinanzeigen_api.py     # Core engine: URL builder, HTTP fetcher, Playwright fallback, parser
│           ├── search_cli.py            # CLI wrapper returning JSON to stdout
│           └── monitor.py               # SQLite deduplicator for cron jobs (JSON & Telegram Markdown)
└── tests/
    └── test_kleinanzeigen.py            # 121 offline unit & integration tests using HTML fixtures
```

---

## 3. Core Engine Architecture (`kleinanzeigen_api.py`)

### 3.1. Canonical Search URL Construction
- URL Path: `/s-preis:{min}:{max}/s-seite:{page}`
- Query Parameters: `?keywords={query}&locationStr={plz}&radius={radius}`
- Validation:
  - `postal_code`: strictly 5 digits (`^\d{5}$`).
  - `radius`: strictly one of `{0, 5, 10, 20, 30, 50, 100, 150, 200}`.
  - `min_price` / `max_price`: non-negative integers; `min_price <= max_price`.

### 3.2. Fetching Strategy (Dual-Engine)
1. **HTTP First (`fetch_mode="http"` or `"auto"`)**:
   - Uses `requests.Session` with desktop Chrome/Edge User-Agents (`fake_useragent`).
   - If HTTP 200: passes HTML to the parser.
   - If HTTP 403 (Akamai / IP-range block): in `auto` mode, automatically switches to Playwright if installed.
2. **Headless Browser Fallback (`fetch_mode="browser"`)**:
   - Uses `playwright.sync_api.sync_playwright` (Chromium).
   - Strict resource interception: blocks images, media, fonts, and stylesheets to maximize throughput and minimize memory.
   - Sequential crawl delay: minimum 1.5s between consecutive page requests. Context cookies are cleared between pages.

### 3.3. HTML Parsing (Hybrid Astro / BEM)
- Primary card selector: `article.adlist-item[data-adid]` or `article[data-adid]`.
- TopAd exclusion: filters out sponsored listings (`is-topad`, `badge-topad`, Astro `<astro-island>` with `topAd: true`).
- Price extraction: leaf-node matching to avoid grabbing shipping text (`+ Versand`) or date stamps.

### 3.4. Deduplication (`monitor.py`)
- SQLite table: `seen_ads(ad_id TEXT PRIMARY KEY, query_hash TEXT, seen_at TEXT)`.
- Query hash: SHA-256 over normalized search parameters (`query`, `postal_code`, `radius`, `price_range`).
- Emits newly discovered listings as structured JSON or Telegram Markdown.

---

## 4. Strict Security & Anti-Bot Rules for AI Agents

When editing or generating code for this repository, AI agents MUST follow these rules:

1. **Anti-Bot & CAPTCHA Integrity**:
   - NEVER write routines to solve, click through, or bypass Cloudflare Turnstile, reCAPTCHA, hCaptcha, or anti-bot proof-of-work challenges.
   - When HTTP 403 or anti-bot challenge is encountered and Playwright cannot obtain the listing markup, raise `KleinanzeigenBlockedError` and exit gracefully.
2. **Credential Safety**:
   - NEVER commit IP addresses, root/user passwords, SSH keys, or GitHub personal access tokens (`ghp_`, `github_pat_`).
   - All tests MUST remain 100% offline using mock fixtures.
3. **Execution Safety**:
   - NEVER introduce dynamic code execution (`eval()`, `exec()`, `os.system()`, `__import__()`, `pickle.loads()`).
   - All SQLite queries MUST use parameterized queries (`?`). Never format strings into SQL.
   - External processes MUST use `subprocess.run(list_args, shell=False)`.

---

## 5. Antislop & UI Guidelines for `docs/`

- **Visual Direction**: `docs/DESIGN.md` (ENERGY: 1, RHYTHM: 2, MOTION: 1).
- **Prohibited Patterns**:
  - Zero em dashes (`—`) in user-facing text. Use commas, colons, or parentheses.
  - Zero fake testimonials, fake stats (`10k+ users`), or template badges (`AI-powered`).
  - Zero non-functional interactive elements. Every button, toggle, and link must have real behavior.
- **Mobile Standard**: All elements must wrap cleanly; touch targets must be &ge; 44px; no horizontal overflow.

---

## 6. How to Run Verification

```bash
# 1. Run full test suite (121 tests, offline)
pytest -v

# 2. Validate Hermes Plugin specification
hermes plugins validate .

# 3. Verify CLI commands
python skills/kleinanzeigen/scripts/search_cli.py --help
python skills/kleinanzeigen/scripts/monitor.py --help
```
