"""Unit tests for the search ranking (PRD §4.10) and sibling tickers (PRD §4.9)."""

from __future__ import annotations

from tickerlens.services.search import MAX_SUGGESTIONS, search_companies, sibling_tickers

ENTRIES = [
    {"ticker": "T", "name": "AT&T Inc.", "cik": "0000732717"},
    {"ticker": "TSLA", "name": "Tesla, Inc.", "cik": "0001318605"},
    {"ticker": "TMUS", "name": "T-Mobile US, Inc.", "cik": "0001283699"},
    {"ticker": "AAPL", "name": "Apple Inc.", "cik": "0000320193"},
    {"ticker": "MSFT", "name": "Microsoft Corporation", "cik": "0000789019"},
]


def _tickers(query: str, entries=ENTRIES) -> list[str]:
    return [r.ticker for r in search_companies(query, entries)]


def test_exact_ticker_match_ranks_first() -> None:
    # PRD: "T" -> AT&T first, even while other T-names also match.
    assert _tickers("t")[0] == "T"


def test_ticker_prefix_beats_name_match() -> None:
    assert _tickers("tsl") == ["TSLA"]


def test_name_prefix_match() -> None:
    assert _tickers("apple") == ["AAPL"]


def test_ticker_prefix_beats_name_prefix() -> None:
    # "appl": AAPL ticker-prefix outranks any name-prefix match.
    entries = ENTRIES + [{"ticker": "XYZ", "name": "Appleseed Inc.", "cik": "0000000001"}]
    assert _tickers("appl", entries)[0] == "AAPL"


def test_name_contains_match() -> None:
    assert _tickers("micro") == ["MSFT"]


def test_case_insensitive() -> None:
    assert _tickers("AaPl") == ["AAPL"]
    assert _tickers("TESLA") == ["TSLA"]


def test_ties_break_alphabetically_by_ticker() -> None:
    # Both TMUS and TSLA are ticker-prefix matches for "t"; TMUS < TSLA.
    tickers = _tickers("t")
    assert tickers.index("TMUS") < tickers.index("TSLA")


def test_caps_suggestions_at_eight() -> None:
    entries = [
        {"ticker": f"TST{i:02d}", "name": f"Test Company {i}", "cik": f"{i:010d}"}
        for i in range(12)
    ]
    assert len(search_companies("test", entries)) == MAX_SUGGESTIONS == 8


def test_empty_query_returns_nothing() -> None:
    assert search_companies("", ENTRIES) == []
    assert search_companies("   ", ENTRIES) == []


def test_no_match_returns_nothing() -> None:
    assert search_companies("zzz-no-such-company", ENTRIES) == []


def test_result_carries_cik() -> None:
    (result,) = search_companies("aapl", ENTRIES)
    assert result.cik == "0000320193"
    assert result.name == "Apple Inc."


def test_entries_from_tickers_uses_title_field() -> None:
    from tickerlens.services.search import _entries_from_tickers

    entries = _entries_from_tickers(
        {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}
    )
    assert entries == [
        {"ticker": "AAPL", "name": "Apple Inc.", "cik": "0000320193"}
    ]


SIBLING_ENTRIES = [
    {"ticker": "GOOGL", "name": "Alphabet Inc.", "cik": "0001652044"},
    {"ticker": "GOOG", "name": "Alphabet Inc.", "cik": "0001652044"},
    {"ticker": "BRK.B", "name": "Berkshire Hathaway Inc.", "cik": "0001067983"},
    {"ticker": "BRK.A", "name": "Berkshire Hathaway Inc.", "cik": "0001067983"},
    {"ticker": "AAPL", "name": "Apple Inc.", "cik": "0000320193"},
]


def test_sibling_tickers_returns_same_cik_excluding_self() -> None:
    assert sibling_tickers("0001652044", "GOOG", SIBLING_ENTRIES) == ["GOOGL"]
    assert sibling_tickers("0001652044", "GOOGL", SIBLING_ENTRIES) == ["GOOG"]


def test_sibling_tickers_sorted_and_excludes_self_case_insensitive() -> None:
    assert sibling_tickers("0001067983", "brk.b", SIBLING_ENTRIES) == ["BRK.A"]


def test_sibling_tickers_empty_for_single_class() -> None:
    assert sibling_tickers("0000320193", "AAPL", SIBLING_ENTRIES) == []


def test_sibling_tickers_empty_for_unknown_cik() -> None:
    assert sibling_tickers("0000000000", "ZZZ", SIBLING_ENTRIES) == []
