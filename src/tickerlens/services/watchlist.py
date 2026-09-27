from __future__ import annotations

import datetime as dt
from typing import Generator
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from tickerlens.data.edgar import EdgarClient, normalize_cik
from tickerlens.models.company import Company
from tickerlens.models.database import get_session
from tickerlens.models.quarterly_financial import QuarterlyFinancial
from tickerlens.models.watchlist import WatchlistItem
from tickerlens.services.financials import (
    FinancialsService,
    _compute_yoy,
    _to_kpi,
    KPISnapshot,
    KPIChange,
)


class WatchlistCard(BaseModel):
    cik: str
    ticker: str
    name: str
    last_price: float | None = None
    market_cap: float | None = None
    sector: str | None = None
    is_pinned: bool = True
    display_order: int = 0
    latest_period: str = ""
    latest_period_end: str = ""
    kpis: KPISnapshot
    yoy: KPIChange


class WatchlistService:
    def __init__(
        self,
        session: Session | None = None,
        financials_service: FinancialsService | None = None,
        edgar_client: EdgarClient | None = None,
    ) -> None:
        self._session = session
        self.financials_svc = financials_service or FinancialsService(session=session)
        self.edgar = edgar_client or EdgarClient()

    def _db_scope(self, session: Session | None = None) -> tuple[Session, bool]:
        """Returns (session, should_close)."""
        if session:
            return session, False
        if self._session:
            return self._session, False
        return get_session(), True

    def _resolve_cik(self, ticker_or_cik: str, db: Session) -> tuple[str, str]:
        """Returns (cik, ticker)."""
        raw = ticker_or_cik.strip().upper()
        if raw.isdigit():
            cik = normalize_cik(raw)
            company = db.get(Company, cik)
            ticker = company.ticker if company and company.ticker else raw
            return cik, ticker

        company = db.execute(select(Company).where(Company.ticker == raw)).scalar_one_or_none()
        if company:
            return company.cik, company.ticker or raw

        cik = normalize_cik(self.edgar.cik_for_ticker(raw))
        return cik, raw

    def get_watchlist(
        self,
        pinned_only: bool = True,
        session: Session | None = None,
    ) -> list[WatchlistCard]:
        db, should_close = self._db_scope(session)
        try:
            stmt = select(WatchlistItem).order_by(
                WatchlistItem.display_order.asc(), WatchlistItem.created_at.desc()
            )
            if pinned_only:
                stmt = stmt.where(WatchlistItem.is_pinned.is_(True))

            items = db.execute(stmt).scalars().all()
            cards: list[WatchlistCard] = []

            for item in items:
                company = db.get(Company, item.cik)
                if not company:
                    continue

                rows = (
                    db.execute(
                        select(QuarterlyFinancial)
                        .where(QuarterlyFinancial.cik == item.cik)
                        .order_by(QuarterlyFinancial.period_end.desc())
                        .limit(8)
                    )
                    .scalars()
                    .all()
                )

                if rows:
                    latest = rows[0]
                    latest_label = f"{latest.fiscal_period} FY{latest.fiscal_year}"
                    latest_period_end = str(latest.period_end)
                    latest_kpis = _to_kpi(latest)
                    yoy = _compute_yoy(latest, list(rows))
                else:
                    latest_label = "—"
                    latest_period_end = "—"
                    latest_kpis = KPISnapshot()
                    yoy = KPIChange()

                cards.append(
                    WatchlistCard(
                        cik=company.cik,
                        ticker=company.ticker or "",
                        name=company.name,
                        last_price=company.last_price,
                        market_cap=company.market_cap,
                        sector=company.sic,
                        is_pinned=item.is_pinned,
                        display_order=item.display_order,
                        latest_period=latest_label,
                        latest_period_end=latest_period_end,
                        kpis=latest_kpis,
                        yoy=yoy,
                    )
                )

            return cards
        finally:
            if should_close:
                db.close()

    def is_pinned(self, ticker_or_cik: str, session: Session | None = None) -> bool:
        db, should_close = self._db_scope(session)
        try:
            cik, _ = self._resolve_cik(ticker_or_cik, db)
            item = db.execute(select(WatchlistItem).where(WatchlistItem.cik == cik)).scalar_one_or_none()
            return item is not None and item.is_pinned
        except Exception:
            return False
        finally:
            if should_close:
                db.close()

    def is_watched(self, ticker_or_cik: str, session: Session | None = None) -> bool:
        db, should_close = self._db_scope(session)
        try:
            cik, _ = self._resolve_cik(ticker_or_cik, db)
            item = db.execute(select(WatchlistItem).where(WatchlistItem.cik == cik)).scalar_one_or_none()
            return item is not None
        except Exception:
            return False
        finally:
            if should_close:
                db.close()

    def add(
        self,
        ticker_or_cik: str,
        pinned: bool = True,
        session: Session | None = None,
    ) -> WatchlistItem:
        db, should_close = self._db_scope(session)
        try:
            cik, ticker = self._resolve_cik(ticker_or_cik, db)

            company = db.get(Company, cik)
            if not company:
                self.financials_svc.fetch_and_persist(ticker, periods=8, session=db)
                self.financials_svc.enrich_company(ticker, session=db)
                company = db.get(Company, cik)

            item = db.execute(select(WatchlistItem).where(WatchlistItem.cik == cik)).scalar_one_or_none()
            if item is None:
                item = WatchlistItem(cik=cik, is_pinned=pinned)
                db.add(item)
            else:
                item.is_pinned = pinned
                item.updated_at = dt.datetime.now(dt.timezone.utc)

            db.commit()
            db.refresh(item)
            return item
        finally:
            if should_close:
                db.close()

    def remove(self, ticker_or_cik: str, session: Session | None = None) -> bool:
        db, should_close = self._db_scope(session)
        try:
            cik, _ = self._resolve_cik(ticker_or_cik, db)
            item = db.execute(select(WatchlistItem).where(WatchlistItem.cik == cik)).scalar_one_or_none()
            if item:
                db.delete(item)
                db.commit()
                return True
            return False
        finally:
            if should_close:
                db.close()

    def toggle_pin(self, ticker_or_cik: str, session: Session | None = None) -> bool:
        """Toggles pinned status. Returns True if now pinned, False if unpinned."""
        db, should_close = self._db_scope(session)
        try:
            cik, ticker = self._resolve_cik(ticker_or_cik, db)
            item = db.execute(select(WatchlistItem).where(WatchlistItem.cik == cik)).scalar_one_or_none()
            if item is None:
                # Add and pin
                self.add(ticker, pinned=True, session=db)
                return True
            elif item.is_pinned:
                item.is_pinned = False
                item.updated_at = dt.datetime.now(dt.timezone.utc)
                db.commit()
                return False
            else:
                item.is_pinned = True
                item.updated_at = dt.datetime.now(dt.timezone.utc)
                db.commit()
                return True
        finally:
            if should_close:
                db.close()
