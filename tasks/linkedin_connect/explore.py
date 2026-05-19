"""Explore LinkedIn invitation dialog structure for development."""

import json
import sys

from lib.browser import attach, find_or_new


DIALOG_DUMP_JS = """(() => {
  const dialog = document.querySelector("[role='dialog']");
  if (!dialog) return { found: false };
  const buttons = Array.from(dialog.querySelectorAll("button")).map((b) => ({
    text: (b.textContent || "").trim().replace(/\\s+/g, " ").slice(0, 60),
    ariaLabel: b.getAttribute("aria-label"),
  }));
  const textareas = Array.from(dialog.querySelectorAll("textarea")).map((t) => ({
    name: t.getAttribute("name"),
    id: t.id,
    placeholder: t.getAttribute("placeholder"),
    maxLength: t.getAttribute("maxlength"),
  }));
  return {
    found: true,
    heading: (dialog.querySelector("h2, h1, [role='heading']")?.textContent || "").trim().slice(0, 100),
    buttons,
    textareas,
  };
})()"""


CLICK_ADD_NOTE_JS = """(() => {
  const dialog = document.querySelector("[role='dialog']");
  if (!dialog) return;
  const btn = Array.from(dialog.querySelectorAll("button")).find(
    (b) => b.getAttribute("aria-label") === "Add a note"
  );
  if (btn) btn.click();
})()"""


def main() -> None:
    vanity = sys.argv[1] if len(sys.argv) > 1 else "stanalexandru"
    invite_url = f"https://www.linkedin.com/preload/custom-invite/?vanityName={vanity}"
    print(f"Using vanityName: {vanity}")
    print(f"Navigating to: {invite_url}\n")

    with attach() as ctx:
        page = find_or_new(ctx, lambda p: "linkedin.com" in p.url)

        try:
            page.goto(invite_url, wait_until="commit", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(2500)

        print(f"Landed on: {page.url}")

        dialog_info = page.evaluate(DIALOG_DUMP_JS)
        print("Dialog after navigation:", json.dumps(dialog_info, indent=2))

        print("\nClicking 'Add a note'...")
        page.evaluate(CLICK_ADD_NOTE_JS)
        page.wait_for_timeout(1000)

        note_info = page.evaluate(DIALOG_DUMP_JS)
        print("Note dialog:", json.dumps(note_info, indent=2))


if __name__ == "__main__":
    main()
