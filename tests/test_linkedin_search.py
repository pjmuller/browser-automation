"""Tests for the scoring / classification helpers in linkedin_search.search."""

from tasks.linkedin_search.search import (
    classify,
    clean_query,
    company_stems,
    extract_headline,
    name_tokens,
    normalize,
    score_candidate,
)


def test_normalize_diacritics():
    assert normalize("José Núñez") == "jose nunez"


def test_normalize_punctuation_collapses_to_space():
    assert normalize("Jean-Luc O'Brien, Jr.") == "jean luc o brien jr"


def test_name_tokens_drops_short_tokens():
    # "A" is 1-char, dropped; "Al" is 2-char, kept.
    assert name_tokens("A Al Alex") == ["al", "alex"]


def test_company_stems_strips_tld():
    assert company_stems("Datawarehouse.io") == ["datawarehouse"]


def test_company_stems_drops_corp_words():
    assert company_stems("Acme Inc.") == ["acme"]
    assert company_stems("The Acme Corporation") == ["acme"]


def test_company_stems_empty():
    assert company_stems("") == []


def test_clean_query_strips_punctuation():
    assert clean_query("Krzysztof (Kris) Szyszkiewicz") == "Krzysztof Kris Szyszkiewicz"
    assert clean_query("Foo [Bar] & Baz") == "Foo Bar Baz"


def test_score_candidate_no_name_match_returns_zero():
    row = {"full_name": "James Elmer", "company": "", "title": ""}
    score, reasons = score_candidate("someone unrelated here", row)
    assert score == 0
    assert reasons == ["no name token"]


def test_score_candidate_full_name_and_company():
    row = {"full_name": "James Elmer", "company": "Datawarehouse.io", "title": ""}
    text = "James Elmer · Co-Founder & CEO at Datawarehouse.io"
    score, reasons = score_candidate(text.lower(), row)
    # tokens=2 hits (+2), adjacent (+2), company match (+3 + 1) = 8
    assert score == 8
    assert "all name tokens" in reasons
    assert "first+last adjacent" in reasons
    assert "company matched" in reasons


def test_score_candidate_partial_name_hit():
    row = {"full_name": "James Elmer", "company": "", "title": ""}
    text = "james somebody"
    score, _ = score_candidate(text, row)
    # only "james" hits → score = 1, no adjacency
    assert score == 1


def test_score_candidate_title_bonus():
    row = {"full_name": "Ada Lovelace", "company": "", "title": "Founder & CEO"}
    text = "ada lovelace - founder at place"
    score, reasons = score_candidate(text, row)
    # name=2, adj=+2, title token "founder" hits (+1) = 5
    assert score == 5
    assert any("title:" in r for r in reasons)


def test_classify_none_when_empty():
    assert classify([], has_company=True) == "none"


def test_classify_confident_with_company_and_lead():
    candidates = [
        {"handle": "a", "url": "", "text": "", "score": 8},
        {"handle": "b", "url": "", "text": "", "score": 3},
    ]
    assert classify(candidates, has_company=True) == "confident"


def test_classify_confident_single_candidate():
    candidates = [{"handle": "a", "url": "", "text": "", "score": 2}]
    assert classify(candidates, has_company=False) == "confident"


def test_classify_ambiguous_when_lead_is_thin():
    candidates = [
        {"handle": "a", "url": "", "text": "", "score": 5},
        {"handle": "b", "url": "", "text": "", "score": 4},
    ]
    # has_company=True but gap is only 1 → ambiguous
    assert classify(candidates, has_company=True) == "ambiguous"


def test_classify_confident_no_company_needs_clear_lead():
    candidates = [
        {"handle": "a", "url": "", "text": "", "score": 4},
        {"handle": "b", "url": "", "text": "", "score": 1},
    ]
    assert classify(candidates, has_company=False) == "confident"


def test_extract_headline_strips_name_and_bullet():
    text = "James Elmer • 2nd Co-Founder & CEO at Datawarehouse.io"
    assert extract_headline(text, "James Elmer").startswith("Co-Founder & CEO")


def test_extract_headline_caps_at_200():
    long = "Name " + ("x" * 500)
    assert len(extract_headline(long, "Name")) == 200
