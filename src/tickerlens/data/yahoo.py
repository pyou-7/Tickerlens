from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel
import yfinance as yf

logger = logging.getLogger(__name__)

PriceRange = Literal["1d", "5d", "1mo", "6mo", "ytd", "1y", "3y", "5y", "10y", "max"]

_RANGE_LABELS: dict[PriceRange, str] = {
    "1d": "Today",
    "5d": "5D",
    "1mo": "1M",
    "6mo": "6M",
    "ytd": "YTD",
    "1y": "1Y",
    "3y": "3Y",
    "5y": "5Y",
    "10y": "10Y",
    "max": "Max",
}

_RANGE_INTERVALS: dict[PriceRange, str] = {
    "1d": "5m",
    "5d": "15m",
    "1mo": "1d",
    "6mo": "1d",
    "ytd": "1d",
    "1y": "1d",
    "3y": "1d",
    "5y": "1d",
    "10y": "1d",
    "max": "1d",
}


@dataclass
class QuoteSnapshot:
    ticker: str
    last_price: float | None
    market_cap: float | None
    currency: str | None


class PriceHistory(BaseModel):
    """Normalized adjusted-close series for the stock-price chart."""

    ticker: str
    range_key: PriceRange
    range_label: str
    currency: str | None = None
    timestamps: list[str]
    prices: list[float]
    change_amount: float | None = None
    change_pct: float | None = None
    is_intraday: bool = False


def get_quote(ticker: str) -> QuoteSnapshot:
    """Fetch current price and market cap from Yahoo Finance."""
    try:
        info = yf.Ticker(ticker).info
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


import json
from pathlib import Path

_YAHOO_CACHE_DIR = Path(".edgar_cache/yahoo")


def _get_cache_path(ticker: str, range_key: str) -> Path:
    _YAHOO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _YAHOO_CACHE_DIR / f"{ticker.upper()}_{range_key}.json"


def _load_cached_history(ticker: str, range_key: PriceRange) -> PriceHistory | None:
    cache_path = _get_cache_path(ticker, range_key)
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        return PriceHistory(**data)
    except Exception:
        logger.warning("Failed to read cached price history for %s (%s)", ticker, range_key, exc_info=True)
        return None


def _save_cached_history(history: PriceHistory) -> None:
    if not history.prices:
        return
    try:
        cache_path = _get_cache_path(history.ticker, history.range_key)
        cache_path.write_text(history.model_dump_json(), encoding="utf-8")
    except Exception:
        logger.warning("Failed to save price history cache for %s (%s)", history.ticker, history.range_key, exc_info=True)


def get_price_history(ticker: str, range_key: PriceRange = "1y") -> PriceHistory:
    """Fetch adjusted price history for a supported chart range.

    Today and 5D use intraday intervals. The 3Y range uses an explicit start
    date because yfinance does not define ``3y`` as a standard period.
    Failures degrade to an empty series so the chart can show its unavailable
    state without taking down the company detail page.
    """
    ticker = ticker.upper()
    history_kwargs: dict[str, object] = {
        "interval": _RANGE_INTERVALS[range_key],
        "auto_adjust": True,
        "actions": False,
        "raise_errors": True,
    }
    if range_key == "3y":
        today = dt.date.today()
        try:
            start = today.replace(year=today.year - 3)
        except ValueError:  # February 29 → February 28
            start = today.replace(year=today.year - 3, day=28)
        history_kwargs["start"] = start.isoformat()
    else:
        history_kwargs["period"] = range_key

    try:
        yahoo_ticker = yf.Ticker(ticker)
        frame = yahoo_ticker.history(**history_kwargs)
        if frame.empty or "Close" not in frame:
            cached = _load_cached_history(ticker, range_key)
            return cached if cached is not None else _empty_price_history(ticker, range_key)

        close = frame["Close"].dropna()
        if close.empty:
            cached = _load_cached_history(ticker, range_key)
            return cached if cached is not None else _empty_price_history(ticker, range_key)

        timestamps = [timestamp.isoformat() for timestamp in close.index]
        prices = [float(value) for value in close.tolist()]
        try:
            metadata = yahoo_ticker.history_metadata or {}
        except Exception:
            logger.warning("Yahoo Finance history metadata failed for %s", ticker, exc_info=True)
            metadata = {}
        currency = metadata.get("currency")

        comparison_price = prices[0]
        if range_key == "1d":
            previous_close = metadata.get("chartPreviousClose") or metadata.get("previousClose")
            if previous_close not in (None, 0):
                comparison_price = float(previous_close)

        change_amount = prices[-1] - comparison_price
        change_pct = (
            change_amount / comparison_price * 100
            if comparison_price not in (0, None)
            else None
        )
        res = PriceHistory(
            ticker=ticker,
            range_key=range_key,
            range_label=_RANGE_LABELS[range_key],
            currency=currency,
            timestamps=timestamps,
            prices=prices,
            change_amount=change_amount,
            change_pct=change_pct,
            is_intraday=range_key in {"1d", "5d"},
        )
        _save_cached_history(res)
        return res
    except Exception:
        logger.warning(
            "Yahoo Finance price history failed for %s (%s)",
            ticker,
            range_key,
            exc_info=True,
        )
        cached = _load_cached_history(ticker, range_key)
        return cached if cached is not None else _empty_price_history(ticker, range_key)


def _empty_price_history(ticker: str, range_key: PriceRange) -> PriceHistory:
    return PriceHistory(
        ticker=ticker,
        range_key=range_key,
        range_label=_RANGE_LABELS[range_key],
        timestamps=[],
        prices=[],
        is_intraday=range_key in {"1d", "5d"},
    )
