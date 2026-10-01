"""Unit tests for EdgarClient ticker resolution."""

import pytest

from tickerlens.data.edgar import EdgarClient


def _client_with_tickers(monkeypatch) -> EdgarClient:
    client = EdgarClient()
    monkeypatch.setattr(
        client,
        "company_tickers",
        lambda: {
            "0": {"ticker": "BRK-B", "cik_str": "1067983", "title": "Berkshire Hathaway Inc"},
            "1": {"ticker": "AAPL", "cik_str": "320193", "title": "Apple Inc"},
        },
    )
    return client


def test_cik_for_ticker_exact_match(monkeypatch) -> None:
    client = _client_with_tickers(monkeypatch)
    assert client.cik_for_ticker("aapl") == "0000320193"


def test_cik_for_ticker_normalizes_dot_and_slash_to_hyphen(monkeypatch) -> None:
    # Everyone types BRK.B / BRK/A; SEC lists BRK-B / BRK-A.
    client = _client_with_tickers(monkeypatch)
    assert client.cik_for_ticker("BRK.B") == "0001067983"
    assert client.cik_for_ticker("brk.b") == "0001067983"


def test_cik_for_ticker_still_raises_for_unknown(monkeypatch) -> None:
    client = _client_with_tickers(monkeypatch)
    with pytest.raises(KeyError):
        client.cik_for_ticker("ZZZZ")
