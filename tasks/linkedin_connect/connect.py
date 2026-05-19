"""Send LinkedIn connection invitations with custom messages from a CSV.

Synchronous port of connect.ts. Drives the user's real Chrome over CDP
via lib.browser.attach() (which wraps sync_playwright).
"""

import csv
import re
import sys
from pathlib import Path
from typing import Callable, TypedDict

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from lib.browser import attach, find_or_new, humanize


class Profile(TypedDict):
    url: str
    message: str


class Result(TypedDict):
    url: str
    status: str


HERE = Path(__file__).parent
VANITY_RE = re.compile(r"linkedin\.com/in/([^/?#]+)")


def load_profiles(path: Path) -> list[Profile]:
    """Load profiles from CSV (columns: url, message)."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        profiles: list[Profile] = []
        for row in reader:
            url = (row.get("url") or "").strip()
            if not url:
                continue
            message = (row.get("message") or "").strip()
            profiles.append({"url": url, "message": message})
        return profiles


def vanity_from_url(url: str) -> str | None:
    """Extract LinkedIn vanity name from a profile URL."""
    m = VANITY_RE.search(url)
    return m.group(1) if m else None


def process_profile(page: Page, profile: Profile, ask: Callable[[str], str]) -> str:
    """Process a single profile: navigate, stage message, ask for confirmation."""
    vanity = vanity_from_url(profile["url"])
    if not vanity:
        return "error:bad_url"
    if len(profile["message"]) > 300:
        return "error:message_too_long"

    invite_url = f"https://www.linkedin.com/preload/custom-invite/?vanityName={vanity}"
    page.goto(invite_url, wait_until="domcontentloaded")

    # Wait for the invitation dialog. If it doesn't appear in 8s, assume we can't invite.
    invite_dialog = page.get_by_role("dialog")
    add_note_btn = invite_dialog.get_by_role("button", name="Add a note")
    try:
        add_note_btn.wait_for(timeout=8000)
    except PlaywrightTimeoutError:
        return "skipped:no_invite_dialog"

    add_note_btn.click()

    textarea = page.locator("textarea#custom-message")
    textarea.wait_for(timeout=5000)
    textarea.fill(profile["message"])

    print(f'  message staged:\n    "{profile["message"]}"')
    answer = ask("  Press ENTER to send, 's' to skip, 'q' to quit: ").strip().lower()

    if answer == "q":
        return "quit_before_send"
    if answer == "s":
        page.get_by_role("button", name="Cancel adding a note").click()
        page.wait_for_timeout(300)
        # Also dismiss the outer "Add a note to your invitation?" dialog if still present.
        dismiss = page.get_by_role("button", name="Dismiss").first
        try:
            if dismiss.is_visible():
                dismiss.click()
        except Exception:
            pass
        return "skipped:user"

    page.get_by_role("button", name="Send invitation").click()
    # Wait for the dialog to disappear as confirmation.
    try:
        invite_dialog.wait_for(state="hidden", timeout=8000)
    except PlaywrightTimeoutError:
        pass
    return "sent"


def main() -> None:
    csv_arg = sys.argv[1] if len(sys.argv) > 1 else "profiles.csv"
    csv_path = Path(csv_arg)
    if not csv_path.is_absolute():
        csv_path = HERE / csv_path

    profiles = load_profiles(csv_path)
    if not profiles:
        print(f"No profiles found in {csv_path}")
        return

    results: list[Result] = []

    with attach() as ctx:
        page = find_or_new(ctx, lambda p: "linkedin.com" in p.url)
        humanize(page)

        for i, profile in enumerate(profiles):
            print(f"\n[{i + 1}/{len(profiles)}] {profile['url']}")
            try:
                status = process_profile(page, profile, input)
                print(f"  -> {status}")
                results.append({"url": profile["url"], "status": status})
                if status == "quit_before_send":
                    break
            except Exception as err:
                msg = str(err).split("\n")[0]
                print(f"  x error: {msg}")
                results.append({"url": profile["url"], "status": f"error:{msg}"})

    print("\n=== summary ===")
    for r in results:
        print(f"  {r['status'].ljust(28)} {r['url']}")


if __name__ == "__main__":
    main()
