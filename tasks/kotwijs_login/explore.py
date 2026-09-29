"""Explore the kotwijs.be landlord login page: dump form fields + buttons.

Run:  uv run kotwijs-login-explore
NO humanize() here — raw speed for poking at the DOM.
"""

import json

from lib.browser import attach, find_or_new

LOGIN_URL = "https://kotwijs.be/login/landlord"


def main() -> None:
    with attach() as ctx:
        page = find_or_new(ctx, lambda p: "kotwijs.be" in p.url)
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)

        dump = page.evaluate(
            """(() => {
              const fields = Array.from(document.querySelectorAll("input, button, a[role='button'], [type='submit']"))
                .map(el => {
                  const r = el.getBoundingClientRect();
                  return {
                    tag: el.tagName.toLowerCase(),
                    type: el.getAttribute("type"),
                    name: el.getAttribute("name"),
                    id: el.id || null,
                    placeholder: el.getAttribute("placeholder"),
                    aria: el.getAttribute("aria-label"),
                    autocomplete: el.getAttribute("autocomplete"),
                    text: (el.textContent || "").trim().slice(0, 60),
                    visible: r.width > 0 && r.height > 0,
                  };
                })
                .filter(e => e.visible);
              return { url: location.href, title: document.title, fields };
            })()"""
        )
        print(json.dumps(dump, indent=2))


if __name__ == "__main__":
    main()
