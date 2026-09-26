from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from tickerlens.data.edgar import EdgarClient, normalize_cik
from tickerlens.models.company import Company
from tickerlens.models.database import get_session

logger = logging.getLogger(__name__)


class CompanySearchResult(BaseModel):
    ticker: str
    name: str
    cik: str
    market_cap: float | None = None


@dataclass(slots=True)
class _IndexedCompany:
    cik: str
    ticker: str
    name: str
    ticker_lower: str
    name_lower: str
    name_words_lower: list[str]


class CompanySearchService:
    """Company universe index and search service adhering to PRD §4.10."""

    def __init__(
        self,
        edgar_client: EdgarClient | None = None,
        session: Session | None = None,
    ) -> None:
        self.edgar_client = edgar_client or EdgarClient()
        self._session = session
        self._index: list[_IndexedCompany] | None = None
        self._market_cap_cache: dict[str, float] = {}
        self._market_cap_cached_at: float = 0.0
        self._market_cap_ttl_seconds: float = 60.0

    def _ensure_index(self) -> list[_IndexedCompany]:
        if self._index is not None:
            return self._index

        raw_tickers = self.edgar_client.company_tickers()
        index: list[_IndexedCompany] = []
        for item in raw_tickers.values():
            ticker = str(item.get("ticker", "")).strip()
            name = str(item.get("title", "")).strip()
            cik_raw = item.get("cik_str", "")
            if not ticker or not cik_raw:
                continue

            cik = normalize_cik(cik_raw)
            ticker_lower = ticker.lower()
            name_lower = name.lower()
            name_words_lower = [w for w in name_lower.replace("-", " ").replace(".", " ").split() if w]

            index.append(
                _IndexedCompany(
                    cik=cik,
                    ticker=ticker,
                    name=name,
                    ticker_lower=ticker_lower,
                    name_lower=name_lower,
                    name_words_lower=name_words_lower,
                )
            )

        self._index = index
        return self._index

    def _get_market_caps(self) -> dict[str, float]:
        now = time.monotonic()
        if self._market_cap_cache and (now - self._market_cap_cached_at < self._market_cap_ttl_seconds):
            return self._market_cap_cache

        caps: dict[str, float] = {}
        try:
            session = self._session or get_session()
            close_session = self._session is None
            try:
                stmt = select(Company.cik, Company.market_cap).where(Company.market_cap.is_not(None))
                rows = session.execute(stmt).all()
                for cik, mcap in rows:
                    if mcap is not None:
                        caps[normalize_cik(cik)] = float(mcap)
            finally:
                if close_session:
                    session.close()
        except Exception as exc:
            logger.warning("Failed to fetch market caps for search ranking: %s", exc)

        self._market_cap_cache = caps
        self._market_cap_cached_at = now
        return caps

    def search(self, query: str, limit: int = 8) -> list[CompanySearchResult]:
        """Search the company universe by ticker or name and return ranked matches."""
        q = query.strip().lower()
        if not q:
            return []

        index = self._ensure_index()
        market_caps = self._get_market_caps()

        matched: list[tuple[int, float, str, _IndexedCompany]] = []

        for item in index:
            rank: int | None = None

            # 1. Exact ticker match (e.g. T -> AT&T)
            if item.ticker_lower == q:
                rank = 1
            # 2. Ticker prefix match (e.g. TSL -> TSLA)
            elif item.ticker_lower.startswith(q):
                rank = 2
            # 3. Company name prefix match (e.g. apple -> Apple Inc.)
            elif item.name_lower.startswith(q):
                rank = 3
            # 4. Word-initial prefix in company name (e.g. micro -> Microsoft)
            elif any(w.startswith(q) for w in item.name_words_lower):
                rank = 4
            # 5. Substring contains match in company name (e.g. apple -> Pineapple)
            elif q in item.name_lower:
                rank = 5

            if rank is not None:
                mcap = market_caps.get(item.cik, 0.0)
                # Sort key: rank ASC (1 is best), market_cap DESC (larger first), ticker ASC
                matched.append((rank, -mcap, item.ticker, item))

        matched.sort(key=lambda x: (x[0], x[1], x[2]))

        results: list[CompanySearchResult] = []
        for _, _, _, item in matched[:limit]:
            mcap = market_caps.get(item.cik)
            results.append(
                CompanySearchResult(
                    ticker=item.ticker,
                    name=item.name,
                    cik=item.cik,
                    market_cap=mcap,
                )
            )

        return results
