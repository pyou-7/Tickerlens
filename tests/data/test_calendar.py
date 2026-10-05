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
