"""Tests for pure-logic helpers in tasks.linkedin_connect.connect."""

import io
import textwrap
from pathlib import Path

from tasks.linkedin_connect.connect import (
    load_profiles,
    vanity_from_url,
)


def test_vanity_from_url_simple():
    assert vanity_from_url("https://www.linkedin.com/in/stanalexandru") == "stanalexandru"


def test_vanity_from_url_trailing_slash():
    assert vanity_from_url("https://www.linkedin.com/in/stanalexandru/") == "stanalexandru"


def test_vanity_from_url_with_query():
    url = "https://www.linkedin.com/in/jane-doe-123/?utm_source=share"
    assert vanity_from_url(url) == "jane-doe-123"


def test_vanity_from_url_with_fragment():
    assert vanity_from_url("https://linkedin.com/in/abc#xyz") == "abc"


def test_vanity_from_url_bare_domain_returns_none():
    assert vanity_from_url("https://www.linkedin.com/feed/") is None


def test_vanity_from_url_garbage_returns_none():
    assert vanity_from_url("https://example.com/in/foo") is None


def test_load_profiles_strips_and_filters_blank_rows(tmp_path: Path):
    csv = tmp_path / "p.csv"
    csv.write_text(textwrap.dedent("""\
        url,message
        https://www.linkedin.com/in/a,"Hi A"
        , "blank row"
          https://www.linkedin.com/in/b   ,"  Hi B  "
    """))
    profiles = load_profiles(csv)
    assert profiles == [
        {"url": "https://www.linkedin.com/in/a", "message": "Hi A"},
        {"url": "https://www.linkedin.com/in/b", "message": "Hi B"},
    ]
