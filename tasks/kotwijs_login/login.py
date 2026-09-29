"""Log in to the kotwijs.be landlord portal via the running CloakBrowser.

Credentials:
  - email    : KOTWIJS_EMAIL env var, else --email, else the default below.
  - password : KOTWIJS_PASSWORD env var, else a getpass prompt (never logged).

Run:  uv run kotwijs-login                 # prompts for password
      KOTWIJS_PASSWORD=... uv run kotwijs-login

Selectors are by field type + button text — kotwijs randomizes input `id`s
(e.g. `emailAddressfb821548`), so never anchor on them.
"""

import argparse
import getpass
import os
import sys

from lib.browser import attach, find_or_new, humanize

LOGIN_URL = "https://kotwijs.be/login/landlord"
DEFAULT_EMAIL = "piet@clipvakanties.be"


def _dismiss_cookies(page) -> None:
    """Click the cookie banner away if it's present (best effort)."""
    for label in ("Enkel strikt noodzakelijke cookies toestaan", "Alle cookies toestaan"):
        btn = page.get_by_role("button", name=label)
        try:
            if btn.count() and btn.first.is_visible():
                btn.first.click()
                page.wait_for_timeout(400)
                return
        except Exception:
            pass


def main() -> None:
    ap = argparse.ArgumentParser(description="Log in to the kotwijs landlord portal.")
    ap.add_argument("--email", default=os.environ.get("KOTWIJS_EMAIL", DEFAULT_EMAIL))
    args = ap.parse_args()

    password = os.environ.get("KOTWIJS_PASSWORD") or getpass.getpass(
        f"kotwijs password for {args.email}: "
    )
    if not password:
        sys.exit("No password provided.")

    with attach() as ctx:
        page = find_or_new(ctx, lambda p: "kotwijs.be" in p.url)
        humanize(page)

        if "kotwijs.be/login/landlord" not in page.url:
            page.goto(LOGIN_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(1200)

        _dismiss_cookies(page)

        # kotwijs uses React controlled inputs that drop/reorder fast humanized
        # keystrokes (observed: "piet@..." → "tipes.be"). fill() sets the value
        # atomically and still dispatches the input events React needs.
        email_box = page.locator("input[type=email]").first
        pw_box = page.locator("input[type=password]").first
        email_box.click()
        email_box.fill(args.email)
        pw_box.click()
        pw_box.fill(password)

        page.get_by_role("button", name="Aanmelden").first.click()

        # Success = we navigate off the login page. Give it a few seconds.
        try:
            page.wait_for_function(
                "() => !location.pathname.startsWith('/login')", timeout=15000
            )
            print(f"✓ Logged in — now at {page.url}")
        except Exception:
            err = page.evaluate(
                """(() => {
                  const t = document.body.innerText || '';
                  const m = t.match(/(ongeldig|onjuist|incorrect|invalid|fout)[^\\n]*/i);
                  return m ? m[0].slice(0, 120) : null;
                })()"""
            )
            print(f"✗ Still on login page ({page.url}).", file=sys.stderr)
            if err:
                print(f"  Page says: {err}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
