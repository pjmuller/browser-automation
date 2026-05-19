"""Explore LinkedIn profile page structure for development."""

import json
import re
import sys

from lib.browser import attach, find_or_new


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python explore.py <linkedin-profile-url>")
        sys.exit(1)

    profile_url = sys.argv[1]
    slug_match = re.search(r"linkedin\.com/in/([^/?#]+)", profile_url)
    if not slug_match:
        print("Invalid LinkedIn profile URL (expected /in/<slug>)")
        sys.exit(1)
    slug = slug_match.group(1)

    with attach() as ctx:
        page = find_or_new(ctx, lambda p: "linkedin.com" in p.url)

        print(f"Navigating: {profile_url}")
        try:
            page.goto(profile_url, wait_until="commit", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(3000)

        # Look for key sections
        dump = page.evaluate(f"""(() => {{
            const tc = document.querySelector("[componentkey*='Topcard']");
            const topcard = tc ? {{
              name: (tc.querySelector("h1, h2")?.textContent || "").trim(),
              found: true
            }} : {{ found: false }};

            const aboutSection = document.querySelector("section[componentkey$='About']") ||
              Array.from(document.querySelectorAll("section")).find(s => {{
                const h = s.querySelector("h2");
                return h && h.textContent.toLowerCase().includes("about");
              }});
            const about = aboutSection ? {{
              found: true,
              hasExpandableBox: !!aboutSection.querySelector("[data-testid='expandable-text-box']")
            }} : {{ found: false }};

            const expSection = document.querySelector("section[componentkey*='ExperienceTopLevel']");
            const exp = expSection ? {{
              found: true,
              itemCount: expSection.querySelectorAll("[componentkey^='entity-collection-item']").length
            }} : {{ found: false }};

            const eduSection = document.querySelector("section[componentkey*='EducationTopLevel']");
            const edu = eduSection ? {{
              found: true,
              itemCount: eduSection.querySelectorAll("[componentkey^='entity-collection-item']").length
            }} : {{ found: false }};

            return {{
              url: location.href,
              topcard,
              about,
              experience: exp,
              education: edu,
              slug: "{slug}"
            }};
          }})()""")

        print(json.dumps(dump, indent=2))


if __name__ == "__main__":
    main()
