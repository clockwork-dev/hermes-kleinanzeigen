# Contributing to hermes-kleinanzeigen

Thank you for helping improve **hermes-kleinanzeigen**! Please review the development workflow, validation gates, and strict safety rules below before submitting a pull request.

See also:
- [README.md](README.md) — overview, installation, and CLI reference
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — detailed module and schema design
- [CHANGELOG.md](CHANGELOG.md) — release notes

---

## Development Setup

Python **3.11 or newer** is required (CI tests Python `3.11`, `3.12`, `3.13`, and `3.14` across Linux, macOS, and Windows).

### Linux / macOS

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e ".[dev]"
# Or without editable install:
# uv pip install --python .venv/bin/python -r skills/kleinanzeigen/requirements.txt pytest
```

### Windows (PowerShell)

```powershell
uv venv .venv
uv pip install --python .\.venv\Scripts\python.exe -e ".[dev]"
# Or without editable install:
# uv pip install --python .\.venv\Scripts\python.exe -r skills/kleinanzeigen/requirements.txt pytest
```

Standard `python -m venv .venv` + `pip install -e ".[dev]"` works identically if `uv` is not installed.

### Optional Browser Fallback Setup (Playwright)

Unit tests mock Playwright and run completely offline without Chromium. Install the optional browser extra only if you need to work with live Playwright runs:

```bash
pip install -e ".[browser]"
playwright install chromium --only-shell
# On headless Linux / Debian:
sudo playwright install-deps chromium
```

---

## Testing & Validation Commands

Run all checks from the repository root before opening a PR.

### 1. Bytecode Syntax & Offline Unit Tests

Linux / macOS:

```bash
.venv/bin/python -m py_compile __init__.py skills/kleinanzeigen/scripts/__init__.py skills/kleinanzeigen/scripts/kleinanzeigen_api.py skills/kleinanzeigen/scripts/search_cli.py skills/kleinanzeigen/scripts/monitor.py tests/test_kleinanzeigen.py
.venv/bin/python -m pytest -v
```

Windows (PowerShell):

```powershell
.\.venv\Scripts\python.exe -m py_compile __init__.py skills/kleinanzeigen/scripts/__init__.py skills/kleinanzeigen/scripts/kleinanzeigen_api.py skills/kleinanzeigen/scripts/search_cli.py skills/kleinanzeigen/scripts/monitor.py tests/test_kleinanzeigen.py
.\.venv\Scripts\python.exe -m pytest -v
```

> **Note**: Tests in [`tests/test_kleinanzeigen.py`](tests/test_kleinanzeigen.py) must remain 100% offline using HTML fixtures and mocks—never add live network requests to `tests/`.

### 2. Hermes Plugin Validation & Doctor (when Hermes CLI is installed)

```bash
hermes plugins validate . --json
hermes plugins doctor --ci .
```

Both commands verify `plugin.yaml`, `pyproject.toml` dependency alignment, tool registration in `__init__.py`, collision checks, and runtime isolation.

### 3. Hermes Skill Linter (`skill_linter`)

If you have a local `hermes-agent` checkout (for example under `$HERMES_HOME/hermes-agent`), verify `skills/kleinanzeigen/SKILL.md` produces zero findings:

```bash
# Run from your hermes-agent checkout using its Python environment
python -c "import sys; from pathlib import Path; sys.path.insert(0, '.'); from tools.skill_linter import lint_skill; findings = lint_skill(Path('/path/to/hermes-kleinanzeigen/skills/kleinanzeigen/SKILL.md')); print(findings); raise SystemExit(1 if findings else 0)"
```

Keep `skills/kleinanzeigen/` free of files flagged by `skill_linter` (`README.md`, `CHANGELOG.md`, `install.sh`, `.env`, `.env.example`, `.gitignore`), and avoid introducing unguarded POSIX-only primitives (`fcntl`, `termios`, `osascript`, `/proc/`, `apt-get`, `systemctl`) so all three platforms (`linux`, `macos`, `windows`) remain supported.

---

## Dual Plugin + Standalone Skill Guidelines

- Keep [`skills/kleinanzeigen/`](skills/kleinanzeigen/) completely self-contained. Scripts under `skills/kleinanzeigen/scripts/` must never import from the repository root (`__init__.py`).
- Preserve both package-relative imports and standalone script imports in `search_cli.py` and `monitor.py`.
- Keep [`plugin.yaml`](plugin.yaml) (`provides_tools`, `pip_dependencies`, `optional_env`) and [`__init__.py`](__init__.py) (`SEARCH_SCHEMA`, `MONITOR_SCHEMA`, `register(ctx)`) synchronized with [`pyproject.toml`](pyproject.toml) and [`skills/kleinanzeigen/requirements.txt`](skills/kleinanzeigen/requirements.txt).
- Preserve the MIT license attribution in [`LICENSE`](LICENSE) and [`skills/kleinanzeigen/LICENSE`](skills/kleinanzeigen/LICENSE).

---

## Strict Security & Anti-Bot Policy

Contributions violating any of the following rules will be rejected:

1. **No CAPTCHA or Anti-Bot Bypassing**:
   - Do **not** add code, browser automation steps, CAPTCHA-solver integrations, proof-of-work solvers, or `SKILL.md` instructions that solve, click through, wait out, or bypass CAPTCHAs, Cloudflare Turnstile, reCAPTCHA, hCaptcha, or IP blocks.
   - Any HTTP `403`, `429`, `503`, or challenge page detected by `_detect_block()` must immediately raise `KleinanzeigenBlockedError` and surface cleanly to the user.
2. **No Secrets, Private Infrastructure, or Runtime Databases**:
   - Never commit API keys, tokens, passwords, private IP addresses, or personal usernames/paths in code, docs, fixtures, or tests. Use generic placeholders (`%LOCALAPPDATA%`, `$HERMES_HOME`, `~`, `<owner>/<repo>`).
   - Never commit SQLite databases (`*.db`, `data/`), `.venv/`, or live captured HTML files containing personal seller details.
3. **Polite Request Cadence**:
   - Respect Kleinanzeigen's servers: keep sequential pagination bounded (`_MAX_PAGINATION_PAGES = 10`) with inter-page delays (`_PAGE_DELAY_SECONDS = 2.0`), and keep default monitoring intervals conservative (30–60 minutes).

---

## Pull Request Checklist

- [ ] Code changes are cross-platform (Linux, macOS, Windows PowerShell & Git Bash).
- [ ] `python -m py_compile` and `pytest -v` pass with zero failures or skipped assertions.
- [ ] `hermes plugins validate . --json` and `hermes plugins doctor --ci .` pass (if Hermes is available).
- [ ] `skills/kleinanzeigen/SKILL.md` passes `skill_linter.lint_skill` with zero findings.
- [ ] Documentation (`README.md`, `docs/ARCHITECTURE.md`, `CHANGELOG.md`) reflects any new flags, environment variables, or schema changes.
- [ ] No credentials, private IPs, usernames, `.db` files, or anti-bot bypass logic were introduced.
