from __future__ import annotations

from unittest.mock import patch

import httpx

from tickerlens.data.wikipedia import (
    _best_title,
    _fetch_extract,
    _relevance_overlap,
    _search_title,
    _search_titles,
    _strict_title_match,
    _strip_corp_suffix,
    _title_relevant,
    _word_set,
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


# ---- Batch 54: corporate-suffix fallback search ----


def test_strip_corp_suffix() -> None:
    """Batch 54: trailing state tags and one corporate-suffix token are
    stripped for the fallback query; anything else is untouched."""
    assert _strip_corp_suffix("Atlassian Corp") == "Atlassian"
    assert _strip_corp_suffix("AMERICAN TOWER CORP /MA/") == "AMERICAN TOWER"
    assert _strip_corp_suffix("WELLS FARGO & COMPANY/MN") == "WELLS FARGO"
    assert _strip_corp_suffix("HORTON D R INC /DE/") == "HORTON D R"
    assert _strip_corp_suffix("STEVEN MADDEN, LTD.") == "STEVEN MADDEN"
    assert _strip_corp_suffix("MPLX LP") == "MPLX"
    assert _strip_corp_suffix("3M CO") == "3M"
    assert _strip_corp_suffix("Maplebear Inc.") == "Maplebear"
    assert _strip_corp_suffix("Atlassian") == "Atlassian"
    assert _strip_corp_suffix("3M") == "3M"
    # Never empties the name.
    assert _strip_corp_suffix("Inc") == "Inc"


def test_word_set_keeps_short_words() -> None:
    """Batch 54: strict matching needs '3M' and 'D. R.' to survive, unlike
    _normalize_words which drops <=2-char tokens for relevance scoring."""
    assert _word_set("3M") == {"3m"}
    assert _word_set("D. R. Horton") == {"d", "r", "horton"}
    assert _word_set("Wells Fargo") == {"wells", "fargo"}


def test_strict_title_match() -> None:
    """Batch 54: the fallback only accepts an article *named* the stripped
    company name — a merely similar article is declined, not misattributed
    (batch-47 IBM/Commodore class)."""
    assert _strict_title_match("Atlassian", "Atlassian") is True
    assert _strict_title_match("American Tower", "AMERICAN TOWER") is True
    assert _strict_title_match("D. R. Horton", "HORTON D R") is True
    assert _strict_title_match("3M", "3M") is True
    assert _strict_title_match("Wells Fargo", "WELLS FARGO") is True
    # Suffix on the title side is stripped before comparing.
    assert _strict_title_match("American Tower Corporation", "AMERICAN TOWER") is True
    # Similar but not the same entity: declined.
    assert _strict_title_match("Applied Digital Data Systems", "Applied Digital") is False
    assert _strict_title_match("Wells Fargo History Museum", "WELLS FARGO") is False
    assert _strict_title_match("Steve Madden", "STEVEN MADDEN") is False
    # Never-relevant exclusions still apply.
    assert _strict_title_match("Atlassian (company)", "Atlassian") is True
    assert _strict_title_match("List of Atlassian products", "Atlassian") is False


def _search_by_query(mapping: dict) -> object:
    def _fake(query: str, limit: int = 5):
        return mapping.get(query, [])

    return _fake


def test_best_title_fallback_rescues_suffix_poisoned_search() -> None:
    """Batch 54 (live TEAM case): 'Atlassian Corp company' returns junk with
    zero relevance; the stripped-name fallback finds the article."""
    mapping = {
        "Atlassian Corp": ["8x8", "Dragoneer Investment Group"],
        "Atlassian": ["Atlassian", "Confluence (software)"],
    }
    with patch(
        "tickerlens.data.wikipedia._search_titles",
        side_effect=_search_by_query(mapping),
    ):
        assert _best_title("Atlassian Corp", ticker="TEAM") == "Atlassian"


def test_best_title_fallback_declines_similar_article() -> None:
    """Batch 54 (live APLD case): the stripped search surfaces the 1969
    terminal maker 'Applied Digital Data Systems' — strict matching
    declines it instead of misattributing (None stays None)."""
    mapping = {
        "Applied Digital Corp.": [],
        "Applied Digital": ["Applied Digital Data Systems", "Applied Materials"],
    }
    with patch(
        "tickerlens.data.wikipedia._search_titles",
        side_effect=_search_by_query(mapping),
    ):
        assert _best_title("Applied Digital Corp.", ticker="APLD") is None


def test_best_title_fallback_accepts_reordered_initials() -> None:
    """Batch 54 (live DHI case): word-set equality is order-insensitive so
    'D. R. Horton' matches 'HORTON D R'."""
    mapping = {
        "HORTON D R INC /DE/": ["D.R. Horton (disambiguation)"],
        "HORTON D R": ["D. R. Horton"],
    }
    with patch(
        "tickerlens.data.wikipedia._search_titles",
        side_effect=_search_by_query(mapping),
    ):
        assert _best_title("HORTON D R INC /DE/", ticker="DHI") == "D. R. Horton"


def test_best_title_fallback_not_consulted_when_primary_hits() -> None:
    """Batch 54: the fallback only fires when the primary search yields no
    relevant title — the 122 companies with descriptions are untouched."""
    with patch(
        "tickerlens.data.wikipedia._search_titles",
        return_value=["Block, Inc."],
    ) as mock_search:
        assert _best_title("Block, Inc.", ticker="XYZ") == "Block, Inc."
        assert mock_search.call_count == 1


def test_best_title_fallback_skipped_when_nothing_to_strip() -> None:
    """Batch 54: no second search when the name has no corporate suffix."""
    with patch(
        "tickerlens.data.wikipedia._search_titles",
        return_value=["8x8", "Dragoneer Investment Group"],
    ) as mock_search:
        assert _best_title("Atlassian", ticker="TEAM") is None
        assert mock_search.call_count == 1


def test_best_title_alias_rescues_dba() -> None:
    """Batch 58 (live CART case): the legal-name search's top hit IS
    'Instacart' but word-agreement against 'Maplebear Inc.' rejects it;
    the curated alias retries with the DBA name and takes the exact
    article."""
    mapping = {
        "Maplebear Inc.": ["Instacart", "AppFolio"],
        "Maplebear": [],
        "Instacart": ["Instacart", "Instacart (disambiguation)"],
    }
    with patch(
        "tickerlens.data.wikipedia._search_titles",
        side_effect=_search_by_query(mapping),
    ):
        assert _best_title("Maplebear Inc.", ticker="CART") == "Instacart"


def test_best_title_alias_rescues_spelling_drift() -> None:
    """Batch 58 (live SHOO case): 'steve' vs 'steven' defeats every
    word-agreement path for 'STEVEN MADDEN, LTD.'; the alias retries with
    the exact company-article title."""
    mapping = {
        "STEVEN MADDEN, LTD.": ["Steve Madden, Ltd.", "Steve Madden"],
        "STEVEN MADDEN": ["Steve Madden, Ltd.", "Steve Madden"],
        "Steve Madden, Ltd.": ["Steve Madden, Ltd.", "Steve Madden"],
    }
    with patch(
        "tickerlens.data.wikipedia._search_titles",
        side_effect=_search_by_query(mapping),
    ):
        assert _best_title("STEVEN MADDEN, LTD.", ticker="SHOO") == "Steve Madden, Ltd."


def test_best_title_alias_declines_person_page() -> None:
    """Batch 58: the alias retry demands an exact squashed-title match, so
    when the company article is absent the founder's 'Steve Madden' page
    is declined instead of misattributed (batch-47 class). A fuzzy
    relevance path would have accepted it on first-word agreement."""
    mapping = {
        "STEVEN MADDEN, LTD.": [],
        "STEVEN MADDEN": [],
        "Steve Madden, Ltd.": ["Steve Madden"],
    }
    with patch(
        "tickerlens.data.wikipedia._search_titles",
        side_effect=_search_by_query(mapping),
    ):
        assert _best_title("STEVEN MADDEN, LTD.", ticker="SHOO") is None


def test_best_title_alias_not_consulted_when_primary_hits() -> None:
    """Batch 58: the alias fires last, so companies that already resolve
    via the legal name are untouched — the 'Instacart' query is never
    issued."""
    with patch(
        "tickerlens.data.wikipedia._search_titles",
        return_value=["Maplebear (company)"],
    ) as mock_search:
        assert _best_title("Maplebear Inc.", ticker="CART") == "Maplebear (company)"
        assert mock_search.call_count == 1


def test_best_title_alias_ticker_lookup_case_insensitive() -> None:
    """Batch 58: the map is keyed by canonical ticker regardless of the
    caller's casing."""
    mapping = {
        "Maplebear Inc.": [],
        "Maplebear": [],
        "Instacart": ["Instacart"],
    }
    with patch(
        "tickerlens.data.wikipedia._search_titles",
        side_effect=_search_by_query(mapping),
    ):
        assert _best_title("Maplebear Inc.", ticker="cart") == "Instacart"


def test_best_title_alias_stays_none_without_article() -> None:
    """Batch 58 (live AGNC case): no Wikipedia article exists, so no alias
    is curated and None stays None — the map must never point at a parent
    or subsidiary as a consolation prize."""
    mapping = {
        "AGNC Investment Corp.": ["American Capital", "List of S&P 400 companies"],
        "AGNC Investment": [],
    }
    with patch(
        "tickerlens.data.wikipedia._search_titles",
        side_effect=_search_by_query(mapping),
    ):
        assert _best_title("AGNC Investment Corp.", ticker="AGNC") is None


def test_best_title_alias_rescues_apostrophe_join() -> None:
    """Batch 64 (live ORLY case): 'O REILLY AUTOMOTIVE INC' — Wikipedia's
    top hit IS the right article, but the apostrophe-join ('o'+'reilly'
    normalizes to 'oreilly', not the company's 'o'+'reilly' pair) zeroes
    the word-overlap relevance score, so every relevance path rejects it
    and the DBA alias retries with the exact company-article title."""
    mapping = {
        "O REILLY AUTOMOTIVE INC": ["O'Reilly Auto Parts", "Terex"],
        "O REILLY AUTOMOTIVE": [],
        "O'Reilly Auto Parts": ["O'Reilly Auto Parts", "NASCAR O'Reilly Auto Parts Series"],
    }
    with patch(
        "tickerlens.data.wikipedia._search_titles",
        side_effect=_search_by_query(mapping),
    ):
        assert _best_title("O REILLY AUTOMOTIVE INC", ticker="ORLY") == "O'Reilly Auto Parts"


def test_best_title_alias_rejects_series_page() -> None:
    """Batch 64: the alias retry demands an exact squashed-title match, so
    when only the NASCAR series page (sponsored by O'Reilly) comes back,
    it is declined instead of misattributed."""
    mapping = {
        "O REILLY AUTOMOTIVE INC": ["Terex"],
        "O REILLY AUTOMOTIVE": [],
        "O'Reilly Auto Parts": ["NASCAR O'Reilly Auto Parts Series"],
    }
    with patch(
        "tickerlens.data.wikipedia._search_titles",
        side_effect=_search_by_query(mapping),
    ):
        assert _best_title("O REILLY AUTOMOTIVE INC", ticker="ORLY") is None
