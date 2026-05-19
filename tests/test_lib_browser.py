"""Tests for lib.browser pure-Python surface (no real browser).

We don't spin up CloakBrowser here — just verify the helpers' shape and that
`find_or_new` selects the right page from a fake context.
"""

from unittest.mock import MagicMock

from lib import browser


def test_find_or_new_returns_matching_page():
    p1 = MagicMock()
    p1.url = "https://example.com/foo"
    p2 = MagicMock()
    p2.url = "https://linkedin.com/feed/"
    ctx = MagicMock()
    ctx.pages = [p1, p2]

    got = browser.find_or_new(ctx, lambda p: "linkedin.com" in p.url)
    assert got is p2
    ctx.new_page.assert_not_called()


def test_find_or_new_opens_new_when_no_match():
    ctx = MagicMock()
    ctx.pages = []
    fresh = MagicMock()
    ctx.new_page.return_value = fresh

    got = browser.find_or_new(ctx, lambda p: "linkedin.com" in p.url)
    assert got is fresh
    ctx.new_page.assert_called_once_with()


def test_humanize_calls_patch_context(monkeypatch):
    called = []

    def fake_patch_context(context, cfg):
        called.append((context, cfg))

    sentinel_cfg = object()
    monkeypatch.setattr(browser.human, "resolve_config", lambda: sentinel_cfg)
    monkeypatch.setattr(browser.human, "patch_context", fake_patch_context)

    page = MagicMock()
    out = browser.humanize(page)
    assert out is page
    assert called == [(page.context, sentinel_cfg)]
