# browser_automation

Misc automation tasks on PJ's local macbook, driving a **CloakBrowser** stealth Chromium to perform jobs on the web.

## Goal

A small collection of Python scripts that automate everyday browser work (form filling, scraping, account chores, multi-step web flows) by attaching to a long-lived **CloakBrowser** instance over the Chrome DevTools Protocol (CDP). Not a cloud project — everything runs on this machine against a persistent stealth profile.

## Toolbox

1. **[CloakBrowser](https://cloakbrowser.com)** — primary. Stealth Chromium binary with C++ patches that defeat fingerprint-based bot detection (reCAPTCHA v3 ~0.9, Cloudflare Turnstile pass, FingerprintJS bypass). Used over CDP via `playwright.sync_api`. The launcher (`uv run cloak`) keeps one persistent stealth browser open on CDP :9222; every task attaches.
2. **[chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/skills/chrome-devtools-cli/SKILL.md)** — when an MCP-driven Claude Code session needs one-off interactive control of a non-CloakBrowser Chrome. Rarely needed now that CloakBrowser exposes CDP itself.

Rules of thumb:
- Deterministic flow with stable selectors → plain sync Playwright `page.*` calls through `lib.browser.attach()`.
- Target uses fingerprint detection (Cloudflare / reCAPTCHA / FingerprintJS) → CloakBrowser with `humanize(page)`.
- One-off interactive browser poking → just use the running CloakBrowser via `chrome-devtools-mcp` on `localhost:9222`.

## Connecting via CDP

`scripts/cloak.py` (alias `uv run cloak`) launches a long-lived CloakBrowser:

```bash
uv run cloak             # starts a stealth Chromium with CDP on :9222
```

Profile state persists in `~/.cloak-automation-profile` — log in once to LinkedIn / target sites; cookies & extensions survive.

Tasks attach via the helper in `lib/browser.py`:

```python
from lib.browser import attach, find_or_new, humanize

with attach() as ctx:                                # connect_over_cdp(CDP_URL)
    page = find_or_new(ctx, lambda p: "linkedin.com" in p.url)
    humanize(page)                                   # opt-in per page (prod scripts only)
    page.goto("https://...", wait_until="commit")
```

See `.agent/skills/cloak-browser.md` for the explore-then-script workflow.

## Tooling conventions (this machine)

Per `~/.claude/CLAUDE.md`:

- **Python**: `uv` only (`uv add`, `uv run`, `uv sync`). No pip / poetry / venv.
- **Versions**: `mise` only. `mise.toml` pins Python 3.13.
- **Env**: `mise.toml [env]` + `.env`. No `direnv`.
- **Secrets**: never commit `.env`. The repo has no LLM dependencies — CloakBrowser does it all without API keys.

CloakBrowser is a Python package: `cloakbrowser>=0.3.28`. Pulls in Playwright Python 1.60.

## Repo layout

```
/
  AGENTS.md                  # this file (also symlinked to .claude/CLAUDE.md)
  README.md
  pyproject.toml             # uv-managed; [project.scripts] declares all entry points
  mise.toml                  # python = "3.13"
  .env.example               # CDP_URL=http://localhost:9222
  scripts/
    cloak.py                 # long-lived CloakBrowser launcher
  lib/
    browser.py               # attach() / find_or_new() / humanize() helpers
  tasks/
    linkedin_connect/        # send connection requests with personalized notes
    linkedin_search/         # resolve LinkedIn handles for a CSV of names
    linkedin_profile/        # scrape a profile to markdown + image
  tests/                     # pure-logic unit tests (vanity parsing, scoring, etc.)
  .agent/skills/
    cloak-browser.md         # explore-then-script workflow
```

Each task in `tasks/<name>/` is self-contained with its own README explaining what it does and how to run it. CLI entry points are declared in `pyproject.toml`:

```
uv run cloak                       # launcher
uv run linkedin-connect            # tasks.linkedin_connect.connect:main
uv run linkedin-connect-explore
uv run linkedin-search
uv run linkedin-search-explore
uv run linkedin-profile <url>
uv run linkedin-profile-explore <url>
```

## Working agreements for AI agents

- Confirm before any destructive web action (deleting accounts, sending messages, posting publicly, money movement). Read-only / data-extraction tasks can proceed.
- Default to attaching via `lib.browser.attach()` over CDP rather than spawning a fresh Playwright browser, so the user's logged-in CloakBrowser session is reused.
- Production scripts call `humanize(page)` after attaching; explore scripts do NOT (they want raw speed for debugging).
- When a script needs credentials or 2FA, prompt the user — do not attempt to bypass.
- Never call `page.bring_to_front()` — CloakBrowser is a separate window; focus-stealing is unwanted.
- Prefer the smallest tool that works. If a 10-line `page.evaluate` does the job, don't bring in any LLM.
