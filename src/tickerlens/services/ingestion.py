from __future__ import annotations

import logging
import time
from typing import Callable
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from tickerlens.data.edgar import EdgarClient, normalize_cik
from tickerlens.models.company import Company
from tickerlens.models.database import get_session
from tickerlens.models.quarterly_financial import QuarterlyFinancial
from tickerlens.models.watchlist import WatchlistItem
from tickerlens.services.financials import FinancialsService
from tickerlens.services.watchlist import WatchlistService

logger = logging.getLogger(__name__)

CURATED_TECH_UNIVERSE = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
    "AVGO",
    "ORCL",
    "AMD",
    "INTC",
    "QCOM",
    "CRM",
    "NFLX",
    "ADBE",
    "CSCO",
    "IBM",
    "TXN",
    "NOW",
    "UBER",
    "ABNB",
    "PLTR",
    "SNOW",
    "PANW",
    "MRVL",
]


class RefreshResult(BaseModel):
    ticker: str
    cik: str = ""
    name: str = ""
    quarters_count: int = 0
    latest_period: str = "—"
    latest_period_end: str = "—"
    latest_revenue: float | None = None
    latest_net_income: float | None = None
    latest_price: float | None = None
    market_cap: float | None = None
    disclosures_count: int = 0
    is_pinned: bool = False
    success: bool = True
    error: str | None = None
    duration_seconds: float = 0.0


class BatchSummary(BaseModel):
    total_requested: int = 0
    succeeded: int = 0
    failed: int = 0
    total_quarters: int = 0
    total_disclosures: int = 0
    elapsed_seconds: float = 0.0
    results: list[RefreshResult] = []


class IngestionService:
    """Service orchestrating batch ingestion, updates, and watchlist synchronization."""

    def __init__(
        self,
        session: Session | None = None,
        financials_service: FinancialsService | None = None,
        watchlist_service: WatchlistService | None = None,
        edgar_client: EdgarClient | None = None,
    ) -> None:
        self._session = session
        self.edgar = edgar_client or EdgarClient()
        self.financials_svc = financials_service or FinancialsService(
            edgar_client=self.edgar, session=session
        )
        self.watchlist_svc = watchlist_service or WatchlistService(
            session=session, financials_service=self.financials_svc, edgar_client=self.edgar
        )

    def _db_scope(self, session: Session | None = None) -> tuple[Session, bool]:
        """Returns (session, should_close)."""
        if session:
            return session, False
        if self._session:
            return self._session, False
        return get_session(), True

    def refresh_ticker(
        self,
        ticker: str,
        periods: int = 12,
        include_disclosures: bool = False,
        pin: bool = False,
        session: Session | None = None,
    ) -> RefreshResult:
        """Fetch financials, enrich metadata, optionally extract disclosures and pin."""
        t0 = time.monotonic()
        clean_ticker = ticker.strip().upper()
        db, should_close = self._db_scope(session)

        cik = ""
        try:
            cik = normalize_cik(self.edgar.cik_for_ticker(clean_ticker))

            # 1. Fetch & normalize XBRL quarterly financials
            self.financials_svc.fetch_and_persist(clean_ticker, periods=periods, session=db)

            # 2. Enrich company profile (sector, description, live price, market cap, risk factors)
            self.financials_svc.enrich_company(clean_ticker, session=db)

            # 3. Optional primary-source disclosures (press releases, guidance, executive commentary)
            disc_count = 0
            if include_disclosures:
                disc_count = self.financials_svc.enrich_press_releases(
                    clean_ticker, periods=periods, session=db
                )

            # 4. Optional pin to watchlist
            is_pinned = False
            if pin:
                item = self.watchlist_svc.add(clean_ticker, pinned=True, session=db)
                is_pinned = item.is_pinned
            else:
                is_pinned = self.watchlist_svc.is_pinned(clean_ticker, session=db)

            # 5. Query latest persisted data for summary
            company = db.get(Company, cik)
            q_rows = (
                db.execute(
                    select(QuarterlyFinancial)
                    .where(QuarterlyFinancial.cik == cik)
                    .order_by(QuarterlyFinancial.period_end.desc())
                )
                .scalars()
                .all()
            )

            latest_label = "—"
            latest_period_end = "—"
            latest_revenue = None
            latest_net_income = None
            if q_rows:
                latest = q_rows[0]
                latest_label = f"{latest.fiscal_period} FY{latest.fiscal_year}"
                latest_period_end = str(latest.period_end)
                latest_revenue = latest.revenue
                latest_net_income = latest.net_income

            duration = round(time.monotonic() - t0, 2)
            return RefreshResult(
                ticker=clean_ticker,
                cik=cik,
                name=company.name if company else clean_ticker,
                quarters_count=len(q_rows),
                latest_period=latest_label,
                latest_period_end=latest_period_end,
                latest_revenue=latest_revenue,
                latest_net_income=latest_net_income,
                latest_price=company.last_price if company else None,
                market_cap=company.market_cap if company else None,
                disclosures_count=disc_count,
                is_pinned=is_pinned,
                success=True,
                duration_seconds=duration,
            )

        except Exception as e:
            logger.exception("Failed to refresh ticker %s", clean_ticker)
            duration = round(time.monotonic() - t0, 2)
            return RefreshResult(
                ticker=clean_ticker,
                cik=cik,
                success=False,
                error=str(e),
                duration_seconds=duration,
            )
        finally:
            if should_close:
                db.close()

    def refresh_tickers(
        self,
        tickers: list[str],
        periods: int = 12,
        include_disclosures: bool = False,
        pin: bool = False,
        delay: float = 0.2,
        session: Session | None = None,
        progress_callback: Callable[[int, int, RefreshResult], None] | None = None,
    ) -> BatchSummary:
        """Batch refresh a list of tickers with throttling and progress reporting."""
        t0 = time.monotonic()
        results: list[RefreshResult] = []
        unique_tickers = list(dict.fromkeys(t.strip().upper() for t in tickers if t.strip()))
        total = len(unique_tickers)

        for idx, ticker in enumerate(unique_tickers, start=1):
            res = self.refresh_ticker(
                ticker=ticker,
                periods=periods,
                include_disclosures=include_disclosures,
                pin=pin,
                session=session,
            )
            results.append(res)

            if progress_callback:
                progress_callback(idx, total, res)

            # Polite delay to respect SEC rate limit guidelines
            if idx < total and delay > 0:
                time.sleep(delay)

        elapsed = round(time.monotonic() - t0, 2)
        succeeded = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)
        total_quarters = sum(r.quarters_count for r in results)
        total_disc = sum(r.disclosures_count for r in results)

        return BatchSummary(
            total_requested=total,
            succeeded=succeeded,
            failed=failed,
            total_quarters=total_quarters,
            total_disclosures=total_disc,
            elapsed_seconds=elapsed,
            results=results,
        )

    def refresh_watchlist(
        self,
        pinned_only: bool = True,
        periods: int = 12,
        include_disclosures: bool = False,
        delay: float = 0.2,
        session: Session | None = None,
        progress_callback: Callable[[int, int, RefreshResult], None] | None = None,
    ) -> BatchSummary:
        """Refresh all companies on the watchlist."""
        db, should_close = self._db_scope(session)
        try:
            cards = self.watchlist_svc.get_watchlist(pinned_only=pinned_only, session=db)
            tickers = [c.ticker for c in cards if c.ticker]
            return self.refresh_tickers(
                tickers=tickers,
                periods=periods,
                include_disclosures=include_disclosures,
                delay=delay,
                session=db,
                progress_callback=progress_callback,
            )
        finally:
            if should_close:
                db.close()

    def refresh_all_db(
        self,
        periods: int = 12,
        include_disclosures: bool = False,
        delay: float = 0.2,
        session: Session | None = None,
        progress_callback: Callable[[int, int, RefreshResult], None] | None = None,
    ) -> BatchSummary:
        """Refresh all companies currently stored in the database."""
        db, should_close = self._db_scope(session)
        try:
            companies = db.execute(select(Company).order_by(Company.ticker.asc())).scalars().all()
            tickers = [c.ticker for c in companies if c.ticker]
            return self.refresh_tickers(
                tickers=tickers,
                periods=periods,
                include_disclosures=include_disclosures,
                delay=delay,
                session=db,
                progress_callback=progress_callback,
            )
        finally:
            if should_close:
                db.close()

    def get_top_universe_tickers(self, limit: int = 25) -> list[str]:
        """Return top tech/market leaders from the universe."""
        return CURATED_TECH_UNIVERSE[:limit]
