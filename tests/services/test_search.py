from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tickerlens.services.search import CompanySearchResult, CompanySearchService


@pytest.fixture
def mock_edgar_client():
    client = MagicMock()
    # Mock SEC company_tickers.json response
    client.company_tickers.return_value = {
        "0": {"cik_str": 732717, "ticker": "T", "title": "AT&T INC."},
        "1": {"cik_str": 1318605, "ticker": "TSLA", "title": "Tesla, Inc."},
        "2": {"cik_str": 1418121, "ticker": "APLE", "title": "Apple Hospitality REIT, Inc."},
        "3": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "4": {"cik_str": 1938109, "ticker": "PAPL", "title": "Pineapple Financial Inc."},
        "5": {"cik_str": 789019, "ticker": "MSFT", "title": "MICROSOFT CORP"},
        "6": {"cik_str": 2488, "ticker": "AMD", "title": "ADVANCED MICRO DEVICES INC"},
        "7": {"cik_str": 1144800, "ticker": "TAC", "title": "TRANSALTA CORP"},
    }
    return client


def test_search_empty_or_whitespace(mock_edgar_client):
    service = CompanySearchService(edgar_client=mock_edgar_client)
    assert service.search("") == []
    assert service.search("   ") == []


def test_exact_ticker_match_ranks_first(mock_edgar_client):
    service = CompanySearchService(edgar_client=mock_edgar_client)
    results = service.search("T")
    assert len(results) > 0
    # "T" must be first
    assert results[0].ticker == "T"
    assert results[0].name == "AT&T INC."
    assert results[0].cik == "0000732717"


def test_ticker_prefix_match(mock_edgar_client):
    service = CompanySearchService(edgar_client=mock_edgar_client)
    results = service.search("tsl")
    assert len(results) == 1
    assert results[0].ticker == "TSLA"


def test_company_name_prefix_and_market_cap_tie_breaker(mock_edgar_client):
    service = CompanySearchService(edgar_client=mock_edgar_client)
    # Inject mock market caps: Apple Inc. has $3T, Apple Hospitality has $2B
    service._market_cap_cache = {
        "0000320193": 3_000_000_000_000.0,
        "0001418121": 2_000_000_000.0,
    }
    service._market_cap_cached_at = 9999999999.0

    results = service.search("apple")
    tickers = [r.ticker for r in results]
    # Apple Inc (AAPL) and Apple Hospitality (APLE) are name prefix matches (Rank 3)
    # AAPL has higher market cap, so it ranks before APLE
    assert tickers[0] == "AAPL"
    assert tickers[1] == "APLE"
    # Pineapple Financial is substring (Rank 5), so it ranks after
    assert "PAPL" in tickers
    assert tickers.index("PAPL") > tickers.index("APLE")


def test_word_prefix_in_company_name(mock_edgar_client):
    service = CompanySearchService(edgar_client=mock_edgar_client)
    # Searching "micro" should match MICROSOFT CORP (name prefix, rank 3)
    # and ADVANCED MICRO DEVICES (word prefix, rank 4)
    results = service.search("micro")
    tickers = [r.ticker for r in results]
    assert "MSFT" in tickers
    assert "AMD" in tickers
    assert tickers.index("MSFT") < tickers.index("AMD")


def test_search_limit(mock_edgar_client):
    service = CompanySearchService(edgar_client=mock_edgar_client)
    results = service.search("a", limit=2)
    assert len(results) == 2


def test_case_insensitivity(mock_edgar_client):
    service = CompanySearchService(edgar_client=mock_edgar_client)
    res_lower = service.search("aapl")
    res_upper = service.search("AAPL")
    res_mixed = service.search("AaPl")
    assert res_lower == res_upper == res_mixed
    assert res_lower[0].ticker == "AAPL"
