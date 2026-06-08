from __future__ import annotations

import logging
from dataclasses import dataclass

import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class QuoteSnapshot:
    ticker: str
    last_price: float | None
    market_cap: float | None
    currency: str | None


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
