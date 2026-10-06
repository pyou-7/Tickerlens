from __future__ import annotations

import concurrent.futures
import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable

import yfinance as yf

logger = logging.getLogger(__name__)

# yfinance sets no socket timeout of its own — a stalled Yahoo connection
# would block the caller forever. All `.info` reads go through this wrapper.
_YAHOO_TIMEOUT_SECONDS = 15.0
_yahoo_pool = concurrent.futures.ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="yahoo-info"
)


def yahoo_symbol(ticker: str) -> str:
    """Normalize a display ticker to Yahoo Finance's symbol format.

    Yahoo uses hyphens where exchanges/SEC use dots (``BRK.B`` → ``BRK-B``);
    passing the dotted form makes yfinance return an empty ``info`` dict,
    which blanks price and market cap downstream.
    """
    return ticker.upper().strip().replace(".", "-")


def _fetch_info(ticker: str) -> dict:
    """Read ``yf.Ticker(ticker).info`` with a hard timeout. Never hangs."""
    symbol = yahoo_symbol(ticker)
    try:
        future = _yahoo_pool.submit(lambda: yf.Ticker(symbol).info)
    except RuntimeError:
        # Executor is shutting down (e.g. a background warmer outliving
        # process teardown) — treat as a timeout; callers never raise.
        raise TimeoutError(f"Yahoo Finance unavailable during shutdown ({ticker})") from None
    try:
        return future.result(timeout=_YAHOO_TIMEOUT_SECONDS)
    except concurrent.futures.TimeoutError:
        logger.warning("Yahoo Finance timed out for %s", ticker)
        raise TimeoutError(f"Yahoo Finance timed out for {ticker}") from None


@dataclass
class QuoteSnapshot:
    ticker: str
    last_price: float | None
    market_cap: float | None
    currency: str | None


def get_quote(ticker: str) -> QuoteSnapshot:
    """Fetch current price and market cap from Yahoo Finance."""
    try:
        info = _fetch_info(ticker)
        price = info.get("currentPrice")
        if price is None:
            price = info.get("regularMarketPrice")
        return QuoteSnapshot(
            ticker=ticker,
            last_price=price,
            market_cap=info.get("marketCap"),
            currency=info.get("currency"),
        )
    except Exception:
        logger.warning("Yahoo Finance quote failed for %s", ticker, exc_info=True)
        return QuoteSnapshot(ticker=ticker, last_price=None, market_cap=None, currency=None)


def get_day_change_pct(ticker: str) -> float | None:
    """Fetch the session day-change percent for a ticker. Never raises."""
    try:
        change = _fetch_info(ticker).get("regularMarketChangePercent")
        return float(change) if change is not None else None
    except Exception:
        logger.warning("Yahoo Finance day-change failed for %s", ticker, exc_info=True)
        return None


class QuoteCache:
    """Thread-safe TTL cache for Yahoo quotes and day-change percents.

    Page renders must not block on repeated network calls (the home page
    renders the 10-stock popular bar on every load), and a transient Yahoo
    failure must not blank previously-good data: on fetch failure the last
    good value is served until it expires, then None. Never raises.
    """

    def __init__(
        self,
        ttl_seconds: float = 300,
        *,
        fetch_quote: Callable[[str], QuoteSnapshot] = get_quote,
        fetch_change_pct: Callable[[str], float | None] = get_day_change_pct,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self._fetch_quote = fetch_quote
        self._fetch_change_pct = fetch_change_pct
        self._clock = clock
        self._lock = threading.Lock()
        self._quotes: dict[str, tuple[float, QuoteSnapshot]] = {}
        self._changes: dict[str, tuple[float, float | None]] = {}

    def _fresh(self, stored_at: float) -> bool:
        return self._clock() - stored_at < self.ttl_seconds

    def quote_fresh(self, ticker: str) -> bool:
        """True when a fresh quote entry exists (even if fields are None)."""
        with self._lock:
            hit = self._quotes.get(ticker.upper())
            return hit is not None and self._fresh(hit[0])

    def change_pct_fresh(self, ticker: str) -> bool:
        """True when a fresh day-change entry exists (even if the value is None)."""
        with self._lock:
            hit = self._changes.get(ticker.upper())
            return hit is not None and self._fresh(hit[0])

    def peek_change_pct(self, ticker: str) -> float | None:
        """Return the cached day-change percent only if fresh; never fetches.

        For render paths that must not block on the network — the caller can
        kick off :func:`warm_change_pct_cache` and serve seed/fallback data
        in the meantime.
        """
        with self._lock:
            hit = self._changes.get(ticker.upper())
            return hit[1] if hit and self._fresh(hit[0]) else None

    def peek_quote(self, ticker: str) -> QuoteSnapshot | None:
        """Return the cached quote only if fresh; never fetches, never raises."""
        with self._lock:
            hit = self._quotes.get(ticker.upper())
            return hit[1] if hit and self._fresh(hit[0]) else None

    def get_quote(self, ticker: str) -> QuoteSnapshot:
        key = ticker.upper()
        with self._lock:
            hit = self._quotes.get(key)
            if hit and self._fresh(hit[0]):
                return hit[1]
        try:
            quote = self._fetch_quote(ticker)
            with self._lock:
                self._quotes[key] = (self._clock(), quote)
            return quote
        except Exception:
            logger.warning("Cached quote fetch failed for %s", ticker, exc_info=True)
            with self._lock:
                hit = self._quotes.get(key)
                return hit[1] if hit else QuoteSnapshot(
                    ticker=ticker, last_price=None, market_cap=None, currency=None)

    def get_change_pct(self, ticker: str) -> float | None:
        key = ticker.upper()
        with self._lock:
            hit = self._changes.get(key)
            if hit and self._fresh(hit[0]):
                return hit[1]
        try:
            change = self._fetch_change_pct(ticker)
            with self._lock:
                self._changes[key] = (self._clock(), change)
            return change
        except Exception:
            logger.warning("Cached day-change fetch failed for %s", ticker, exc_info=True)
            with self._lock:
                hit = self._changes.get(key)
                return hit[1] if hit else None


# Process-wide cache shared by page renders (5-minute TTL).
_quote_cache = QuoteCache()

# Serializes background warmers so a burst of cold-cache renders spawns one
# refresher thread, not one per request.
_warm_lock = threading.Lock()
_warming = False

_quote_warm_lock = threading.Lock()
_quote_warming = False


def cached_quote(ticker: str) -> QuoteSnapshot:
    """TTL-cached quote; never raises."""
    return _quote_cache.get_quote(ticker)


def peeked_quote(ticker: str) -> QuoteSnapshot | None:
    """Fresh-cached quote snapshot, or None without fetching. Never raises."""
    try:
        return _quote_cache.peek_quote(ticker)
    except Exception:
        logger.warning("Quote cache peek failed for %s", ticker, exc_info=True)
        return None


def cached_day_change_pct(ticker: str) -> float | None:
    """TTL-cached day-change percent; never raises."""
    return _quote_cache.get_change_pct(ticker)


def peeked_day_change_pct(ticker: str) -> float | None:
    """Fresh-cached day-change percent, or None without fetching. Never raises."""
    try:
        return _quote_cache.peek_change_pct(ticker)
    except Exception:
        logger.warning("Quote cache peek failed for %s", ticker, exc_info=True)
        return None


def warm_change_pct_cache(tickers: list[str]) -> None:
    """Refresh day-change percents for ``tickers`` in a background thread.

    Render paths call this, then serve whatever :func:`peeked_day_change_pct`
    (or a static seed) has right now — the page never waits on Yahoo. The
    next render picks up the live values. At most one warmer runs at a time;
    never raises.
    """
    global _warming
    try:
        with _warm_lock:
            if _warming:
                return
            cold = [t for t in tickers if not _quote_cache.change_pct_fresh(t)]
            if not cold:
                return
            _warming = True

        def _run() -> None:
            global _warming
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
                    list(pool.map(_quote_cache.get_change_pct, cold))
            except Exception:
                logger.warning("Background day-change warm failed", exc_info=True)
            finally:
                with _warm_lock:
                    _warming = False

        threading.Thread(target=_run, daemon=True, name="yahoo-warm").start()
    except Exception:
        logger.warning("Could not start quote cache warmer", exc_info=True)
        with _warm_lock:
            _warming = False


def warm_quote_cache(tickers: list[str]) -> None:
    """Refresh quotes for ``tickers`` in a background thread. Never raises."""
    global _quote_warming
    try:
        with _quote_warm_lock:
            if _quote_warming:
                return
            cold = [t for t in tickers if not _quote_cache.quote_fresh(t)]
            if not cold:
                return
            _quote_warming = True

        def _run() -> None:
            global _quote_warming
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
                    list(pool.map(_quote_cache.get_quote, cold))
            except Exception:
                logger.warning("Background quote warm failed", exc_info=True)
            finally:
                with _quote_warm_lock:
                    _quote_warming = False

        threading.Thread(target=_run, daemon=True, name="yahoo-quote-warm").start()
    except Exception:
        logger.warning("Could not start quote cache warmer", exc_info=True)
        with _quote_warm_lock:
            _quote_warming = False
