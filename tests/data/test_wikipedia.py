from __future__ import annotations

from unittest.mock import patch

import httpx

from tickerlens.data.wikipedia import (
    _best_title,
    _fetch_extract,
    _relevance_overlap,
    _search_title,
    _search_titles,
    _title_relevant,
    get_description,
)


def _boom(*args, **kwargs):
    raise httpx.InvalidURL("Invalid port: ':1]'")


class _FakeResp:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


def _extract_response(words: int, page_type: str = "standard") -> _FakeResp:
    return _FakeResp({"type": page_type, "extract": " ".join(["word"] * words)})


def test_search_title_invalid_url_returns_none() -> None:
    """httpx.InvalidURL is not an HTTPError subclass; it must still be
    swallowed per this module's None-on-network-error contract."""
    with patch("tickerlens.data.wikipedia.httpx.get", side_effect=_boom):
        assert _search_title("Apple Inc") is None


def test_fetch_extract_invalid_url_returns_none() -> None:
    with patch("tickerlens.data.wikipedia.httpx.get", side_effect=_boom):
        assert _fetch_extract("Apple Inc.") is None


def test_fetch_extract_accepts_short_but_real_summary() -> None:
    """Batch 47: the old 50-word floor discarded real company summaries —
    Broadcom's live summary measured 48 words, Visa's 32, GE's 20."""
    with patch(
        "tickerlens.data.wikipedia.httpx.get", return_value=_extract_response(48)
    ):
        extract = _fetch_extract("Broadcom")
    assert extract is not None and len(extract.split()) == 48


def test_fetch_extract_rejects_stub() -> None:
    with patch(
        "tickerlens.data.wikipedia.httpx.get", return_value=_extract_response(10)
    ):
        assert _fetch_extract("Some Tiny Co") is None


def test_fetch_extract_rejects_disambiguation_by_type() -> None:
    """Disambiguation pages can carry non-trivial extracts; reject by type."""
    with patch(
        "tickerlens.data.wikipedia.httpx.get",
        return_value=_extract_response(60, page_type="disambiguation"),
    ):
        assert _fetch_extract("O") is None


def test_title_relevant_rejects_wrong_person_page() -> None:
    """Batch 47: the old bag-of-words check accepted 'William Procter
    (industrialist)' for 'PROCTER & GAMBLE Co' because 'procter' appeared
    somewhere in the title."""
    assert _title_relevant("William Procter (industrialist)", "PROCTER & GAMBLE Co") is False


def test_title_relevant_first_word_agreement() -> None:
    assert _title_relevant("Broadcom", "Broadcom Inc.") is True
    assert _title_relevant("Pfizer", "PFIZER INC") is True
    assert _title_relevant("Lockheed Corporation", "LOCKHEED MARTIN CORP") is True


def test_title_relevant_fallback_without_parenthetical() -> None:
    """Lead-word-in-title fallback covers trade names and punctuation
    mismatches, as long as the title isn't a parenthetical-disambiguated page."""
    assert _title_relevant("John Deere", "DEERE & CO") is True
    assert _title_relevant("Domino's", "DOMINOS PIZZA INC") is True
    assert _title_relevant("Kimberly-Clark", "KIMBERLY CLARK CORP") is True
    assert _title_relevant("The Coca-Cola Company", "COCA COLA CO") is True


def test_title_relevant_ticker_acronym_page() -> None:
    """Article titles that are literally the ticker (AMD, BNY)."""
    assert _title_relevant("AMD", "ADVANCED MICRO DEVICES INC", ticker="AMD") is True
    assert _title_relevant("BNY", "Bank of New York Mellon Corp", ticker="BNY") is True
    # ...but a ticker match must not rescue an unrelated title
    assert _title_relevant("News Corp", "Applied Digital Corp.", ticker="APLD") is False


def test_title_relevant_rejects_unrelated_pages() -> None:
    assert _title_relevant("News Corp", "Applied Digital Corp.") is False
    assert _title_relevant("Meta Platforms", "HORTON D R INC /DE/") is False
    assert (
        _title_relevant("List of companies based in Minneapolis–Saint Paul", "WELLS FARGO & COMPANY/MN")
        is False
    )
    assert _title_relevant("Marathon Petroleum", "MPLX LP") is False


def test_get_description_threads_ticker_into_relevance() -> None:
    """End-to-end: acronym title accepted only when the ticker matches."""
    with (
        patch("tickerlens.data.wikipedia._best_title", return_value="AMD"),
        patch(
            "tickerlens.data.wikipedia.httpx.get",
            return_value=_extract_response(40),
        ),
    ):
        assert get_description("ADVANCED MICRO DEVICES INC", ticker="AMD") is not None
    with patch("tickerlens.data.wikipedia._best_title", return_value=None):
        assert get_description("ADVANCED MICRO DEVICES INC") is None


def test_search_titles_returns_list_and_empty_on_error() -> None:
    with patch(
        "tickerlens.data.wikipedia.httpx.get",
        return_value=_FakeResp({"query": {"search": [{"title": "A"}, {"title": "B"}]}}),
    ):
        assert _search_titles("x") == ["A", "B"]
    with patch("tickerlens.data.wikipedia.httpx.get", side_effect=_boom):
        assert _search_titles("x") == []
    # backward-compat wrapper
    with patch(
        "tickerlens.data.wikipedia.httpx.get",
        return_value=_FakeResp({"query": {"search": [{"title": "A"}]}}),
    ):
        assert _search_title("x") == "A"


def test_best_title_prefers_highest_overlap() -> None:
    """Batch 47: Wikipedia ranks 'Lockheed Corporation' above 'Lockheed
    Martin' for 'LOCKHEED MARTIN CORP company' — the name-contained,
    strictly-higher-overlap override picks the right page."""
    candidates = [
        "Lockheed Corporation",
        "Lockheed Martin",
        "Martin Marietta",
        "Lockheed Martin Space",
        "Malcolm Lockheed",
    ]
    with patch(
        "tickerlens.data.wikipedia._search_titles", return_value=candidates
    ):
        assert _best_title("LOCKHEED MARTIN CORP") == "Lockheed Martin"


def test_best_title_does_not_promote_subsidiary_or_case() -> None:
    """Batch 47 dry-run regressions: a higher-overlap subsidiary
    ('Domino's Pizza Group plc'), legal case ('U.S. v. Microsoft'), or
    museum ('Wells Fargo History Museum') must not displace the relevant
    top hit — their titles add words beyond the company name."""
    with patch(
        "tickerlens.data.wikipedia._search_titles",
        return_value=["Domino's", "Domino's Pizza Group plc"],
    ):
        assert _best_title("DOMINOS PIZZA INC") == "Domino's"
    with patch(
        "tickerlens.data.wikipedia._search_titles",
        return_value=["Microsoft", "United States v. Microsoft Corp."],
    ):
        assert _best_title("MICROSOFT CORP") == "Microsoft"


def test_best_title_top_hit_irrelevant_requires_name_contained() -> None:
    """The museum page is Wells-Fargo-related but the wrong entity; its
    title adds words beyond the name, so WFC stays description-less."""
    candidates = [
        "List of companies based in Minneapolis–Saint Paul",
        "Forum Communications Company",
        "Wells Fargo History Museum",
    ]
    with patch(
        "tickerlens.data.wikipedia._search_titles", return_value=candidates
    ):
        assert _best_title("WELLS FARGO & COMPANY/MN") is None


def test_title_relevant_rejects_parenthetical_titles() -> None:
    assert _title_relevant("Procter & Gamble (P&G) Pakistan", "PROCTER & GAMBLE Co") is False
    assert _title_relevant("William Procter (industrialist)", "PROCTER & GAMBLE Co") is False
    # ...but the "(company)" disambiguator marks the primary company article
    assert _title_relevant("Amazon (company)", "AMAZON COM INC") is True


def test_title_relevant_rejects_lawsuit_articles() -> None:
    """Batch 47: Wikipedia ranks 'United States v. Microsoft Corp.' above
    'Microsoft' for 'MICROSOFT CORP company' — a lawsuit article must never
    serve as the company description."""
    assert _title_relevant("United States v. Microsoft Corp.", "MICROSOFT CORP") is False
    assert _title_relevant("Omega S. A. v. Costco Wholesale Corp.", "COSTCO WHOLESALE CORP") is False


def test_title_relevant_rejects_list_articles() -> None:
    """Batch 47: 'List of mergers and acquisitions by Microsoft' outranked
    'Microsoft' in a live ranking fluctuation — list articles are never the
    company page."""
    assert (
        _title_relevant("List of mergers and acquisitions by Microsoft", "MICROSOFT CORP")
        is False
    )


def test_best_title_exact_name_match_wins() -> None:
    """A relevant hit whose word set equals the company name is the canonical
    article ('Tesla, Inc.' beats the higher-ranked 'Tesla Energy' division)."""
    candidates = ["Tesla Energy", "Tesla", "History of Tesla, Inc.", "Tesla, Inc."]
    with patch(
        "tickerlens.data.wikipedia._search_titles", return_value=candidates
    ):
        assert _best_title("TESLA INC") == "Tesla, Inc."
    with patch(
        "tickerlens.data.wikipedia._search_titles",
        return_value=["Amazon (company)", "Diapers.com"],
    ):
        assert _best_title("AMAZON COM INC") == "Amazon (company)"


def test_best_title_lawsuit_top_hit_falls_through() -> None:
    candidates = [
        "United States v. Microsoft Corp.",
        "List of mergers and acquisitions by Microsoft",
        "Microsoft",
    ]
    with patch(
        "tickerlens.data.wikipedia._search_titles", return_value=candidates
    ):
        assert _best_title("MICROSOFT CORP") == "Microsoft"


def test_best_title_skips_irrelevant_hits() -> None:
    candidates = ["News Corp", "Fox Corporation"]
    with patch(
        "tickerlens.data.wikipedia._search_titles", return_value=candidates
    ):
        assert _best_title("Applied Digital Corp.", ticker="APLD") is None


def test_best_title_ticker_exact_match_wins() -> None:
    with patch(
        "tickerlens.data.wikipedia._search_titles",
        return_value=["Advanced Micro Devices", "AMD"],
    ):
        assert _best_title("ADVANCED MICRO DEVICES INC", ticker="AMD") == "AMD"


def test_relevance_overlap_scores() -> None:
    assert _relevance_overlap("Lockheed Martin", "LOCKHEED MARTIN CORP") == 2
    assert _relevance_overlap("Lockheed Corporation", "LOCKHEED MARTIN CORP") == 1
    assert _relevance_overlap("AMD", "ADVANCED MICRO DEVICES INC", ticker="AMD") == 100
