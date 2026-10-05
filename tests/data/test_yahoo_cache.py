"""Tests for the Yahoo quote layer: day-change fetch and the TTL QuoteCache."""

from __future__ import annotations

import pytest

from tickerlens.data import yahoo
from tickerlens.data.yahoo import QuoteCache, QuoteSnapshot, get_day_change_pct


def _snapshot(price: float | None = 100.0) -> QuoteSnapshot:
    return QuoteSnapshot(ticker="AAPL", last_price=price, market_cap=1e12, currency="USD")


def test_get_day_change_pct_never_raises(monkeypatch) -> None:
    class _Boom:
        @property
        def info(self):  # noqa: D102
            raise RuntimeError("yahoo down")

    monkeypatch.setattr(yahoo.yf, "Ticker", lambda ticker: _Boom())
    assert get_day_change_pct("AAPL") is None


def test_quote_cache_serves_second_call_without_refetch() -> None:
    calls: list[str] = []

    def fetch(ticker: str) -> QuoteSnapshot:
        calls.append(ticker)
        return _snapshot()

    now = [1000.0]
    cache = QuoteCache(ttl_seconds=60, fetch_quote=fetch, clock=lambda: now[0])
    assert cache.get_quote("AAPL").last_price == 100.0
    now[0] += 10.0  # still within TTL
    assert cache.get_quote("aapl").last_price == 100.0  # case-insensitive key
    assert calls == ["AAPL"]


def test_quote_cache_refetches_after_ttl_expiry() -> None:
    calls: list[str] = []

    def fetch(ticker: str) -> QuoteSnapshot:
        calls.append(ticker)
        return _snapshot(price=float(len(calls) * 10))

    now = [0.0]
    cache = QuoteCache(ttl_seconds=60, fetch_quote=fetch, clock=lambda: now[0])
    assert cache.get_quote("AAPL").last_price == 10.0
    now[0] += 61.0
    assert cache.get_quote("AAPL").last_price == 20.0
    assert calls == ["AAPL", "AAPL"]


def test_quote_cache_fetch_failure_serves_stale_then_none() -> None:
    now = [0.0]

    def good(ticker: str) -> QuoteSnapshot:
        return _snapshot(price=42.0)

    def boom(ticker: str) -> QuoteSnapshot:
        raise RuntimeError("yahoo down")

    cache = QuoteCache(ttl_seconds=60, fetch_quote=good, clock=lambda: now[0])
    assert cache.get_quote("AAPL").last_price == 42.0
    # Failure inside the TTL window returns the stored value, never raises.
    cache._fetch_quote = boom
    now[0] += 30.0
    assert cache.get_quote("AAPL").last_price == 42.0
    # Failure after expiry with no good value at all → all-None snapshot.
    empty = QuoteCache(ttl_seconds=60, fetch_quote=boom, clock=lambda: now[0])
    q = empty.get_quote("ZZZZ")
    assert (q.last_price, q.market_cap, q.currency) == (None, None, None)


def test_change_pct_cache_dedupes_and_falls_back_on_failure() -> None:
    calls: list[str] = []

    def fetch(ticker: str) -> float | None:
        calls.append(ticker)
        return 2.5

    now = [0.0]
    cache = QuoteCache(ttl_seconds=60, fetch_change_pct=fetch, clock=lambda: now[0])
    assert cache.get_change_pct("NVDA") == 2.5
    now[0] += 10.0
    assert cache.get_change_pct("NVDA") == 2.5
    assert calls == ["NVDA"]

    def boom(ticker: str) -> float | None:
        raise RuntimeError("yahoo down")

    # Stale value served on failure within TTL.
    cache._fetch_change_pct = boom
    now[0] += 20.0
    assert cache.get_change_pct("NVDA") == 2.5
    # No prior value → None, never raises.
    empty = QuoteCache(ttl_seconds=60, fetch_change_pct=boom, clock=lambda: now[0])
    assert empty.get_change_pct("ZZZZ") is None


def test_change_pct_zero_is_cached_not_dropped() -> None:
    cache = QuoteCache(ttl_seconds=60, fetch_change_pct=lambda ticker: 0.0)
    assert cache.get_change_pct("AAPL") == 0.0


def test_peek_returns_value_only_when_fresh() -> None:
    now = [0.0]
    cache = QuoteCache(ttl_seconds=60, fetch_change_pct=lambda ticker: 3.0,
                       clock=lambda: now[0])
    assert cache.peek_change_pct("AAPL") is None  # never fetched → not fresh
    assert cache.get_change_pct("AAPL") == 3.0    # populates
    assert cache.peek_change_pct("AAPL") == 3.0
    assert cache.change_pct_fresh("AAPL") is True
    now[0] += 61.0
    assert cache.peek_change_pct("AAPL") is None
    assert cache.change_pct_fresh("AAPL") is False


def test_peek_never_fetches() -> None:
    calls: list[str] = []

    def fetch(ticker: str) -> float | None:
        calls.append(ticker)
        return 1.0

    cache = QuoteCache(ttl_seconds=60, fetch_change_pct=fetch)
    assert cache.peek_change_pct("AAPL") is None
    assert calls == []


def test_warm_change_pct_cache_populates_in_background() -> None:
    import time as _time

    from tickerlens.data import yahoo as yahoo_mod

    calls: list[str] = []
    cache = QuoteCache(ttl_seconds=60, fetch_change_pct=lambda t: (calls.append(t), 9.9)[1])
    monkeypatch_cache = yahoo_mod._quote_cache
    yahoo_mod._quote_cache = cache
    try:
        assert yahoo_mod.peeked_day_change_pct("NVDA") is None
        yahoo_mod.warm_change_pct_cache(["NVDA", "AAPL"])
        deadline = _time.time() + 10
        while sorted(calls) != ["AAPL", "NVDA"] and _time.time() < deadline:
            _time.sleep(0.05)
        assert yahoo_mod.peeked_day_change_pct("NVDA") == 9.9
        assert sorted(calls) == ["AAPL", "NVDA"]
        # A second call while warm does not spawn another fetch round.
        before = len(calls)
        yahoo_mod.warm_change_pct_cache(["NVDA", "AAPL"])
        _time.sleep(0.3)
        assert len(calls) == before
    finally:
        yahoo_mod._quote_cache = monkeypatch_cache


def test_warm_change_pct_cache_never_raises() -> None:
    from tickerlens.data import yahoo as yahoo_mod

    def boom(tickers: list[str]) -> None:
        raise RuntimeError("nope")

    orig = yahoo_mod.threading.Thread
    yahoo_mod.threading.Thread = boom  # type: ignore[assignment]
    try:
        yahoo_mod.warm_change_pct_cache(["NVDA"])  # must not raise
    finally:
        yahoo_mod.threading.Thread = orig


def test_fetch_info_timeout_never_hangs(monkeypatch) -> None:
    import time as _time

    class _Slow:
        @property
        def info(self):  # noqa: D102
            _time.sleep(5)
            return {}

    monkeypatch.setattr(yahoo.yf, "Ticker", lambda ticker: _Slow())
    monkeypatch.setattr(yahoo, "_YAHOO_TIMEOUT_SECONDS", 0.05)
    start = _time.monotonic()
    with pytest.raises(TimeoutError):
        yahoo._fetch_info("AAPL")
    assert _time.monotonic() - start < 2
    # …and the public day-change entry point still never raises on a stall.
    assert get_day_change_pct("AAPL") is None


def test_yahoo_symbol_normalizes_dots_to_hyphens() -> None:
    from tickerlens.data.yahoo import yahoo_symbol

    assert yahoo_symbol("BRK.B") == "BRK-B"
    assert yahoo_symbol("brk.b") == "BRK-B"
    assert yahoo_symbol("AAPL") == "AAPL"
    assert yahoo_symbol(" BRK-B ") == "BRK-B"


def test_fetch_info_uses_yahoo_symbol(monkeypatch) -> None:
    """BRK.B must query Yahoo as BRK-B, or yfinance returns an empty info dict."""
    seen: list[str] = []

    class _Ticker:
        def __init__(self, symbol: str) -> None:
            seen.append(symbol)

        @property
        def info(self) -> dict:
            return {"currentPrice": 500.0, "marketCap": 1e12, "currency": "USD"}

    monkeypatch.setattr(yahoo.yf, "Ticker", _Ticker)
    quote = yahoo.get_quote("BRK.B")
    assert seen == ["BRK-B"]
    assert quote.last_price == 500.0
    assert quote.market_cap == 1e12


def test_determine_cap_tier_unknown_when_missing() -> None:
    from tickerlens.services.ai_analysis import _determine_cap_tier

    assert _determine_cap_tier(None)[0] == "Unknown"
    assert _determine_cap_tier(0)[0] == "Unknown"
    assert _determine_cap_tier(1_100_000_000_000)[0] == "Mega-Cap"
