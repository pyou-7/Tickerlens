from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock, patch

import pytest

from tickerlens.data.calendar import (
    CalendarCache,
    EarningsEvent,
    _safe_date_str,
    fetch_earnings_calendar,
)


def test_safe_date_str() -> None:
    assert _safe_date_str(None) is None
    assert _safe_date_str(dt.date(2026, 11, 15)) == "2026-11-15"
    assert _safe_date_str([dt.date(2026, 12, 1)]) == "2026-12-01"
    assert _safe_date_str("2026-10-25 00:00:00") == "2026-10-25"


def test_calendar_cache_hit() -> None:
    mock_fetch = MagicMock()
    mock_fetch.return_value = EarningsEvent(
        ticker="AAPL",
        company_name="Apple Inc.",
        earnings_date="2026-11-01",
        days_until=28,
        eps_estimate_avg=1.65,
        revenue_estimate_avg=95000000000.0,
        dividend_date=None,
        ex_dividend_date=None,
    )

    now = 1000.0
    cache = CalendarCache(ttl_seconds=300, fetch_fn=mock_fetch, clock=lambda: now)

    # First fetch
    res1 = cache.get("AAPL")
    assert res1.ticker == "AAPL"
    assert res1.earnings_date == "2026-11-01"
    assert mock_fetch.call_count == 1

    # Second fetch within TTL
    now = 1100.0
    res2 = cache.get("AAPL")
    assert res2.earnings_date == "2026-11-01"
    assert mock_fetch.call_count == 1  # Cache hit, no second call

    # Third fetch after TTL
    now = 1400.0
    res3 = cache.get("AAPL")
    assert mock_fetch.call_count == 2


def _aapl_event() -> EarningsEvent:
    return EarningsEvent(
        ticker="AAPL",
        company_name="Apple Inc.",
        earnings_date="2026-11-01",
        days_until=28,
        eps_estimate_avg=1.65,
        revenue_estimate_avg=95000000000.0,
        dividend_date=None,
        ex_dividend_date=None,
    )


def test_peek_returns_none_when_cold_and_never_fetches() -> None:
    calls: list[str] = []

    def fetch(ticker: str, name: str | None = None) -> EarningsEvent:
        calls.append(ticker)
        return _aapl_event()

    cache = CalendarCache(ttl_seconds=300, fetch_fn=fetch)
    assert cache.peek("AAPL") is None
    assert calls == []
    assert not cache.event_fresh("AAPL")


def test_peek_returns_cached_event_when_fresh() -> None:
    calls: list[str] = []

    def fetch(ticker: str, name: str | None = None) -> EarningsEvent:
        calls.append(ticker)
        return _aapl_event()

    cache = CalendarCache(ttl_seconds=300, fetch_fn=fetch)
    cache.get("AAPL")
    assert calls == ["AAPL"]
    peeked = cache.peek("AAPL")
    assert peeked is not None
    assert peeked.earnings_date == "2026-11-01"
    assert calls == ["AAPL"]  # peek never fetches
    assert cache.event_fresh("AAPL")


def test_peek_returns_none_when_stale() -> None:
    now = [1000.0]

    def fetch(ticker: str, name: str | None = None) -> EarningsEvent:
        return _aapl_event()

    cache = CalendarCache(ttl_seconds=300, fetch_fn=fetch, clock=lambda: now[0])
    cache.get("AAPL")
    now[0] = 1400.0  # past the 300s TTL
    assert cache.peek("AAPL") is None
    assert not cache.event_fresh("AAPL")


def test_warm_earnings_cache_populates_in_background() -> None:
    import time as _time

    from tickerlens.data import calendar as cal_mod

    calls: list[str] = []
    cache = CalendarCache(
        ttl_seconds=3600,
        fetch_fn=lambda t, n=None: (calls.append(t), _aapl_event())[1],
    )
    orig = cal_mod.default_calendar_cache
    cal_mod.default_calendar_cache = cache
    try:
        assert cal_mod.peeked_earnings_event("AAPL") is None
        cal_mod.warm_earnings_cache(["AAPL"])
        deadline = _time.time() + 10
        while cal_mod.peeked_earnings_event("AAPL") is None and _time.time() < deadline:
            _time.sleep(0.05)
        peeked = cal_mod.peeked_earnings_event("AAPL")
        assert peeked is not None
        assert peeked.earnings_date == "2026-11-01"
        assert calls == ["AAPL"]
        # A second call while warm does not spawn another fetch round.
        before = len(calls)
        cal_mod.warm_earnings_cache(["AAPL"])
        _time.sleep(0.3)
        assert len(calls) == before
    finally:
        cal_mod.default_calendar_cache = orig


def test_warm_earnings_cache_never_raises() -> None:
    from tickerlens.data import calendar as cal_mod

    def boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("nope")

    orig = cal_mod.threading.Thread
    cal_mod.threading.Thread = boom  # type: ignore[assignment]
    try:
        cal_mod.warm_earnings_cache(["AAPL"])  # must not raise
    finally:
        cal_mod.threading.Thread = orig


def test_cache_normalizes_dotted_and_hyphen_ticker_spellings() -> None:
    """BRK.B and BRK-B share one cache entry (batch-23; mirrors batch-17 QuoteCache fix)."""
    mock_fetch = MagicMock()
    mock_fetch.return_value = EarningsEvent(
        ticker="BRK-B",
        company_name="Berkshire Hathaway Inc.",
        earnings_date="2026-11-07",
        days_until=32,
        eps_estimate_avg=None,
        revenue_estimate_avg=None,
        dividend_date=None,
        ex_dividend_date=None,
    )
    cache = CalendarCache(ttl_seconds=300, fetch_fn=mock_fetch)

    res1 = cache.get("BRK.B")
    assert res1.earnings_date == "2026-11-07"
    assert mock_fetch.call_count == 1

    # The hyphenated spelling is a cache hit, not a second Yahoo fetch.
    res2 = cache.get("BRK-B")
    assert res2.earnings_date == "2026-11-07"
    assert mock_fetch.call_count == 1

    # peek is spelling-insensitive too
    assert cache.peek("BRK.B") is not None
    assert cache.peek("BRK-B") is not None
    assert cache.event_fresh("BRK.B")
    assert cache.event_fresh("BRK-B")


def test_prefetch_fetches_cold_tickers_concurrently() -> None:
    import time as _time

    def slow_fetch(ticker: str, name: str | None = None) -> EarningsEvent:
        _time.sleep(0.3)
        return EarningsEvent(
            ticker=ticker,
            company_name=name,
            earnings_date="2026-11-01",
            days_until=26,
            eps_estimate_avg=None,
            revenue_estimate_avg=None,
            dividend_date=None,
            ex_dividend_date=None,
        )

    cache = CalendarCache(ttl_seconds=300, fetch_fn=slow_fetch)
    tickers = ["T1", "T2", "T3", "T4"]
    start = _time.monotonic()
    cache.prefetch(tickers)
    elapsed = _time.monotonic() - start

    # Serial would take >= 1.2s; concurrent should be ~one round-trip.
    assert elapsed < 0.9
    for t in tickers:
        assert cache.event_fresh(t)


def test_prefetch_never_raises() -> None:
    def boom(ticker: str, name: str | None = None) -> EarningsEvent:
        raise RuntimeError("yahoo down")

    cache = CalendarCache(ttl_seconds=300, fetch_fn=boom)
    cache.prefetch(["T1", "T2"])  # must not raise
    assert not cache.event_fresh("T1")
