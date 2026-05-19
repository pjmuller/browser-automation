"""Dump LinkedIn people-search result structure for picking stable selectors.

    uv run linkedin-search-explore "James Elmer Datawarehouse.io"
"""

import json
import sys
from urllib.parse import quote

from lib.browser import attach, find_or_new


DUMP_JS = r"""(() => {
  const main = document.querySelector("main") || document.body;

  // Profile anchors are the most stable signal — LinkedIn rotates wrapper
  // class names but /in/<vanity> URLs survive.
  const anchors = Array.from(main.querySelectorAll("a[href*='/in/']"));
  const byHandle = new Map();
  for (const a of anchors) {
    const href = a.getAttribute("href") || "";
    const m = href.match(/\/in\/([^\/\?#]+)/);
    if (!m) continue;
    const handle = decodeURIComponent(m[1]);
    const text = (a.textContent || "").trim().replace(/\s+/g, " ");
    const prev = byHandle.get(handle);
    if (!prev || text.length > prev.text.length) {
      byHandle.set(handle, { handle, href, text: text.slice(0, 200) });
    }
  }

  const bodyText = document.body.innerText || "";
  const m = bodyText.match(/No results|did not match/i);
  return {
    url: location.href,
    title: document.title,
    handlesFound: byHandle.size,
    results: Array.from(byHandle.values()).slice(0, 10),
    bodySnippet: m ? m[0] : null,
  };
})()"""


def main() -> None:
    query = " ".join(sys.argv[1:]) or "James Elmer Datawarehouse.io"
    url = (
        "https://www.linkedin.com/search/results/people/?keywords="
        + quote(query)
    )

    print(f"Navigating: {url}")
    with attach() as ctx:
        page = find_or_new(ctx, lambda p: "linkedin.com" in p.url)
        # NOTE: do NOT humanize — explore is read-only debugging.
        # NOTE: do NOT bring_to_front — never steal focus from the user.

        try:
            page.goto(url, wait_until="commit", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(3000)

        dump = page.evaluate(DUMP_JS)
        print(json.dumps(dump, indent=2))


if __name__ == "__main__":
    main()
