"""Tests for pure-logic helpers in tasks.linkedin_profile.scrape."""

from tasks.linkedin_profile.scrape import (
    format_entry,
    pick_best_photo_url,
)


URL_100 = "https://media.licdn.com/dms/image/profile-displayphoto-scale_100_100/0/abc?t=tok"
URL_400 = "https://media.licdn.com/dms/image/profile-displayphoto-scale_400_400/0/abc?t=tok"
URL_800 = "https://media.licdn.com/dms/image/profile-displayphoto-crop_800_800/0/abc?t=tok"


def test_pick_best_photo_url_returns_largest():
    best = pick_best_photo_url([URL_100, URL_800, URL_400])
    assert best == URL_800


def test_pick_best_photo_url_handles_unknown_variants():
    odd = "https://media.licdn.com/dms/image/profile-displayphoto-mystery/0/abc"
    best = pick_best_photo_url([odd, URL_100])
    # URL_100 has size 100, odd has size 0 → URL_100 wins
    assert best == URL_100


def test_pick_best_photo_url_empty_returns_none():
    assert pick_best_photo_url([]) is None


def test_format_entry_bolds_first_line():
    out = format_entry(["Senior Engineer", "Acme Co.", "2020–Now"])
    assert out.startswith("**Senior Engineer**")
    assert "Acme Co." in out
    assert "2020–Now" in out


def test_format_entry_empty_returns_empty():
    assert format_entry([]) == ""
