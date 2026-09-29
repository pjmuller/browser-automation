# kotwijs_login

Log in to the **kotwijs.be landlord portal** (`/login/landlord`) through the
running CloakBrowser. The authenticated session persists in the CloakBrowser
profile, so once logged in any follow-up scraping/automation task can attach and
act without re-authenticating.

Pure Playwright over CDP — no LLM, no API keys.

## What it does

1. Attach to the running CloakBrowser and find (or open) a kotwijs.be tab.
2. Navigate to `https://kotwijs.be/login/landlord` if not already there.
3. Dismiss the cookie banner (prefers "Enkel strikt noodzakelijke cookies").
4. Type the email + password (humanized keystrokes) and click **Aanmelden**.
5. Success = the URL leaves `/login`. On failure it scrapes any
   invalid-credentials message off the page and exits non-zero.

## Selectors

kotwijs randomizes input `id`s on each render (`emailAddressfb821548`,
`passwordBase64a3f2ec28`), so the script anchors on **field type and button
text**, never on `id`:

| Element | Selector |
| --- | --- |
| Email | `input[type=email]` |
| Password | `input[type=password]` |
| Submit | `get_by_role("button", name="Aanmelden")` |

## Run

```bash
uv run cloak                          # start (or keep open) the CloakBrowser
uv run kotwijs-login                  # prompts for the password (getpass)
KOTWIJS_PASSWORD=… uv run kotwijs-login
uv run kotwijs-login --email someone@example.com
```

Credentials resolution:
- **email** — `KOTWIJS_EMAIL` env → `--email` → default `piet@clipvakanties.be`.
- **password** — `KOTWIJS_PASSWORD` env → interactive `getpass` prompt (never
  echoed, never logged, never committed).

## Debugging

`explore.py` dumps the login form's inputs/buttons — re-run it whenever kotwijs
changes the page:

```bash
uv run kotwijs-login-explore
```
