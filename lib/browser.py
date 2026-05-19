"""Attach a Playwright client to the running CloakBrowser."""

import os
from contextlib import contextmanager
from playwright.sync_api import sync_playwright, BrowserContext, Page
from cloakbrowser import human

DEFAULT_CDP = os.environ.get("CDP_URL", "http://localhost:9222")


@contextmanager
def attach(cdp_url: str = DEFAULT_CDP):
    """Yield the first existing context of the running CloakBrowser."""
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(cdp_url)
        try:
            yield browser.contexts[0]
        finally:
            browser.close()  # detach only; launcher owns the browser


def find_or_new(ctx: BrowserContext, predicate=lambda p: True) -> Page:
    """Pick the first matching open page, else open a new tab."""
    for page in ctx.pages:
        if predicate(page):
            return page
    return ctx.new_page()


def humanize(page: Page) -> Page:
    """Apply CloakBrowser's humanize patches to the page's context.

    `human.patch_page` requires internal cfg/cursor state; the public,
    stable entry point is `patch_context`, which patches every page in the
    context (including the one passed in). Idempotent across calls.

    Pages attached over CDP have `viewport_size == None` (Playwright didn't
    launch the browser, so it doesn't know the viewport). Humanized clicks
    need a viewport to plot a cursor path, so we copy the live
    innerWidth/innerHeight onto the page before patching.
    """
    if page.viewport_size is None:
        try:
            wh = page.evaluate("({w: window.innerWidth, h: window.innerHeight})")
            if wh and wh.get("w") and wh.get("h"):
                page.set_viewport_size({"width": wh["w"], "height": wh["h"]})
        except Exception:
            pass
    cfg = human.resolve_config()
    human.patch_context(page.context, cfg)
    return page
