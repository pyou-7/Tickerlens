from __future__ import annotations

import concurrent.futures
import datetime as dt
import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable

import yfinance as yf

from tickerlens.data.yahoo import yahoo_symbol

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10.0
_calendar_pool = concurrent.futures.ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="yahoo-calendar"
)


@dataclass
class EarningsEvent:
    ticker: str
    company_name: str | None
    earnings_date: str | None  # YYYY-MM-DD
    days_until: int | None
    eps_estimate_avg: float | None
    revenue_estimate_avg: float | None
    dividend_date: str | None
    ex_dividend_date: str | None
    is_watchlist: bool = False


def _safe_date_str(d: object) -> str | None:
    if d is None:
        return None
    if isinstance(d, (dt.date, dt.datetime)):
        return d.strftime("%Y-%m-%d")
    if isinstance(d, list) and d:
        first = d[0]
        if isinstance(first, (dt.date, dt.datetime)):
            return first.strftime("%Y-%m-%d")
        return str(first)[:10]
    s = str(d).strip()
    return s[:10] if s else None


def fetch_earnings_calendar(ticker: str, company_name: str | None = None) -> EarningsEvent:
    """Fetch upcoming earnings and dividend dates for a ticker. Never raises."""
    ticker_clean = yahoo_symbol(ticker)

    def _call() -> dict:
        t = yf.Ticker(ticker_clean)
        cal = getattr(t, "calendar", None)
        return cal if isinstance(cal, dict) else {}

    try:
        future = _calendar_pool.submit(_call)
        cal_data = future.result(timeout=_TIMEOUT_SECONDS)
    except Exception:
        logger.warning("Failed to fetch calendar for %s", ticker_clean, exc_info=False)
        cal_data = {}

    earnings_raw = cal_data.get("Earnings Date")
    earnings_str = _safe_date_str(earnings_raw)

    days_until: int | None = None
    if earnings_str:
        try:
            target_date = dt.date.fromisoformat(earnings_str)
            days_until = (target_date - dt.date.today()).days
        except Exception:
            days_until = None

    eps_avg = cal_data.get("Earnings Average")
    rev_avg = cal_data.get("Revenue Average")
    div_str = _safe_date_str(cal_data.get("Dividend Date"))
    ex_div_str = _safe_date_str(cal_data.get("Ex-Dividend Date"))

    return EarningsEvent(
        ticker=ticker_clean,
        company_name=company_name,
        earnings_date=earnings_str,
        days_until=days_until,
        eps_estimate_avg=float(eps_avg) if eps_avg is not None else None,
        revenue_estimate_avg=float(rev_avg) if rev_avg is not None else None,
        dividend_date=div_str,
        ex_dividend_date=ex_div_str,
    )


class CalendarCache:
    """Thread-safe TTL cache for earnings calendar events."""

    def __init__(
        self,
        ttl_seconds: float = 3600.0,  # 1 hour default
        fetch_fn: Callable[[str, str | None], EarningsEvent] = fetch_earnings_calendar,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self._fetch_fn = fetch_fn
        self._clock = clock
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, EarningsEvent]] = {}

    def get(self, ticker: str, company_name: str | None = None) -> EarningsEvent:
        ticker_up = ticker.upper().strip()
        now = self._clock()
        with self._lock:
            cached = self._cache.get(ticker_up)
            if cached is not None and (now - cached[0] < self.ttl_seconds):
                event = cached[1]
                if company_name and not event.company_name:
                    event.company_name = company_name
                return event

        # Fetch outside lock
        event = self._fetch_fn(ticker_up, company_name)
        with self._lock:
            self._cache[ticker_up] = (now, event)
        return event

    def peek(self, ticker: str) -> EarningsEvent | None:
        """Return the fresh-cached event without fetching; None when cold/stale.

        For render paths that must not block on the network — the caller can
        kick off :func:`warm_earnings_cache` and serve whatever is cached in
        the meantime.
        """
        with self._lock:
            cached = self._cache.get(ticker.upper().strip())
            if cached is None or (self._clock() - cached[0] >= self.ttl_seconds):
                return None
            return cached[1]

    def event_fresh(self, ticker: str) -> bool:
        """True when a fresh event exists for ``ticker`` (fetch would be a hit)."""
        with self._lock:
            cached = self._cache.get(ticker.upper().strip())
            return cached is not None and (
                self._clock() - cached[0] < self.ttl_seconds
            )


# Global default cache
default_calendar_cache = CalendarCache()

# Serializes background warmers so a burst of cold-cache renders spawns one
# refresher thread, not one per request.
_earn_warm_lock = threading.Lock()
_earn_warming = False


def peeked_earnings_event(ticker: str) -> EarningsEvent | None:
    """Fresh-cached earnings event, or None without fetching. Never raises."""
    try:
        return default_calendar_cache.peek(ticker)
    except Exception:
        logger.warning("Earnings calendar peek failed for %s", ticker, exc_info=True)
        return None


def warm_earnings_cache(tickers: list[str]) -> None:
    """Refresh earnings calendar events for ``tickers`` in a background thread.

    Render paths call this, then serve whatever :func:`peeked_earnings_event`
    has right now — the page never waits on Yahoo. The next render picks up
    the live values. At most one warmer runs at a time; never raises.
    """
    global _earn_warming
    try:
        with _earn_warm_lock:
            if _earn_warming:
                return
            cold = [t for t in tickers if not default_calendar_cache.event_fresh(t)]
            if not cold:
                return
            _earn_warming = True

        def _run() -> None:
            global _earn_warming
            try:
                for t in cold:
                    default_calendar_cache.get(t)
            except Exception:
                logger.warning(
                    "Background earnings calendar warm failed", exc_info=True
                )
            finally:
                with _earn_warm_lock:
                    _earn_warming = False

        threading.Thread(target=_run, daemon=True, name="earnings-warm").start()
    except Exception:
        logger.warning("Could not start earnings calendar warmer", exc_info=True)
        with _earn_warm_lock:
            _earn_warming = False
