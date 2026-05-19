# browser_automation

Local browser automation scripts driving a **CloakBrowser** stealth Chromium over CDP. See [AGENTS.md](AGENTS.md) for the toolbox and conventions.

## First-time setup

```bash
mise install                              # Python 3.13
uv sync                                   # installs cloakbrowser + playwright
uv run python -m cloakbrowser install     # ~140 MB stealth Chromium → ~/.cloakbrowser/
cp .env.example .env
```

Log in to LinkedIn / target sites once — run the launcher in **headed** mode so a real window opens:

```bash
CLOAK_HEADED=1 uv run cloak
```

Log in inside that window. Cookies & session persist in `~/.cloak-automation-profile`. Ctrl-C to quit when done. After this you can run cloak headlessly forever.

## Running

```bash
uv run cloak              # headless by default — runs in background, no focus stolen
uv run linkedin-connect   # in another terminal: attach over CDP :9222
```

If a re-login is needed (session expired, captcha, 2FA): kill the headless launcher and run `CLOAK_HEADED=1 uv run cloak` again.

## Tasks

- [`tasks/linkedin_connect/`](tasks/linkedin_connect/README.md) — send personalized LinkedIn connection requests from a CSV, with a human approval gate per profile.
- [`tasks/linkedin_search/`](tasks/linkedin_search/README.md) — resolve LinkedIn handles for a CSV of (full name, optional company) rows, with confidence scoring and ambiguous-case fallback.
- [`tasks/linkedin_profile/`](tasks/linkedin_profile/README.md) — scrape a LinkedIn profile (topcard, about, experience, education, skills, mutuals, profile photo) into a markdown file with YAML frontmatter.
