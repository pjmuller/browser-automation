"""Send LinkedIn connection invitations with custom messages from a CSV.

Synchronous port of connect.ts. Drives the user's real Chrome over CDP
via lib.browser.attach() (which wraps sync_playwright).
"""

import csv
import random
import re
import sys
import time
from pathlib import Path
from typing import TypedDict

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from lib.browser import attach, find_or_new


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


def is_page_dead(err: Exception) -> bool:
    """True if the exception means our Page/Context handle is no longer usable."""
    msg = str(err).lower()
    return "target page, context or browser has been closed" in msg


def reacquire_page(ctx) -> Page:
    """Grab a fresh LinkedIn page handle from the live browser context."""
    page = find_or_new(ctx, lambda p: "linkedin.com" in p.url)
    return page


def process_profile(page: Page, profile: Profile) -> str:
    """Process a single profile: navigate, stage message, send."""
    vanity = vanity_from_url(profile["url"])
    if not vanity:
        return "error:bad_url"
    if len(profile["message"]) > 300:
        return "error:message_too_long"

    invite_url = f"https://www.linkedin.com/preload/custom-invite/?vanityName={vanity}"
    page.goto(invite_url, wait_until="domcontentloaded")

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

    print(f'  message staged:\n    "{profile["message"]}"', flush=True)

    page.get_by_role("button", name="Send invitation").click()
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

    too_long = [p for p in profiles if len(p["message"]) > 300]
    print(f"preflight: {len(profiles)} profiles loaded from {csv_path.name}", flush=True)
    if too_long:
        print(f"  {len(too_long)} message(s) exceed 300 chars and will error:", flush=True)
        for p in too_long:
            print(f"    {len(p['message'])}ch  {p['url']}", flush=True)

    results: list[Result] = []

    with attach() as ctx:
        page = reacquire_page(ctx)

        for i, profile in enumerate(profiles):
            print(f"\n[{i + 1}/{len(profiles)}] {profile['url']}", flush=True)
            try:
                status = process_profile(page, profile)
                print(f"  -> {status}", flush=True)
                results.append({"url": profile["url"], "status": status})
            except Exception as err:
                msg = str(err).split("\n")[0]
                if is_page_dead(err):
                    print(f"  ! page handle stale, re-acquiring: {msg}", flush=True)
                    try:
                        page = reacquire_page(ctx)
                        status = process_profile(page, profile)
                        print(f"  -> {status} (after recovery)", flush=True)
                        results.append({"url": profile["url"], "status": status})
                    except Exception as err2:
                        msg2 = str(err2).split("\n")[0]
                        print(f"  x error after recovery: {msg2}", flush=True)
                        results.append({"url": profile["url"], "status": f"error:{msg2}"})
                else:
                    print(f"  x error: {msg}", flush=True)
                    results.append({"url": profile["url"], "status": f"error:{msg}"})

            if i < len(profiles) - 1:
                # Longer cooldown every 10 profiles, shorter jitter between each.
                if (i + 1) % 10 == 0:
                    delay = random.uniform(45, 90)
                else:
                    delay = random.uniform(5, 15)
                print(f"  sleeping {delay:.1f}s...", flush=True)
                time.sleep(delay)

    print("\n=== summary ===")
    for r in results:
        print(f"  {r['status'].ljust(28)} {r['url']}")


if __name__ == "__main__":
    main()
