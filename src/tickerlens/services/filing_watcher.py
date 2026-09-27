from __future__ import annotations

import datetime as dt
import logging
from typing import Callable
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from tickerlens.data.edgar import EdgarClient, normalize_cik
from tickerlens.models.company import Company
from tickerlens.models.database import get_session
from tickerlens.models.filing_event import FilingEvent
from tickerlens.models.watchlist import WatchlistItem
from tickerlens.services.financials import FinancialsService
from tickerlens.services.watchlist import WatchlistService

logger = logging.getLogger(__name__)

# Key SEC filing forms that trigger fundamental financial metrics or earnings updates
WATCHED_FORMS = {"10-Q", "10-K", "8-K"}


class DiscoveredFiling(BaseModel):
    ticker: str
    cik: str
    form: str
    accession_number: str
    filing_date: str
    report_date: str | None = None
    description: str | None = None
    refreshed_metrics: bool = False
    is_new: bool = True


class WatcherCheckSummary(BaseModel):
    checked_count: int = 0
    new_filings_count: int = 0
    refreshed_companies_count: int = 0
    new_filings: list[DiscoveredFiling] = []
    checked_at: str = ""


class FilingWatcherService:
    """Service to automatically monitor SEC EDGAR submissions for new filings

    (10-Q, 10-K, 8-K) and trigger automated financial and disclosure refreshes.
    """

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
        if session:
            return session, False
        if self._session:
            return self._session, False
        return get_session(), True

    def check_company_for_new_filings(
        self,
        ticker_or_cik: str,
        auto_refresh: bool = True,
        max_scan_filings: int = 25,
        session: Session | None = None,
    ) -> list[DiscoveredFiling]:
        """Check SEC submissions for a company and record/refresh any newly filed reports."""
        db, should_close = self._db_scope(session)
        clean_input = ticker_or_cik.strip().upper()

        try:
            # Resolve CIK and ticker
            if clean_input.isdigit():
                cik = normalize_cik(clean_input)
                comp = db.get(Company, cik)
                ticker = comp.ticker if comp and comp.ticker else clean_input
            else:
                comp = db.execute(select(Company).where(Company.ticker == clean_input)).scalar_one_or_none()
                if comp:
                    cik = comp.cik
                    ticker = comp.ticker or clean_input
                else:
                    cik = normalize_cik(self.edgar.cik_for_ticker(clean_input))
                    ticker = clean_input

            # Fetch recent submissions from EDGAR
            submissions = self.edgar.submissions(cik)
            recent = submissions.get("filings", {}).get("recent", {})
            if not recent:
                return []

            forms = recent.get("form", [])
            filing_dates = recent.get("filingDate", [])
            report_dates = recent.get("reportDate", [])
            accessions = recent.get("accessionNumber", [])
            descriptions = recent.get("primaryDocDescription", [])

            # Check if this company already has recorded filing events
            has_existing_events = db.execute(
                select(FilingEvent.id).where(FilingEvent.cik == cik).limit(1)
            ).scalar_one_or_none() is not None

            # Collect existing known accession numbers for this CIK
            known_accessions = set(
                db.execute(
                    select(FilingEvent.accession_number).where(FilingEvent.cik == cik)
                ).scalars().all()
            )

            discovered: list[DiscoveredFiling] = []
            should_refresh = False

            # Scan the most recent N filings
            scan_limit = min(max_scan_filings, len(forms))
            for i in range(scan_limit):
                form = forms[i]
                if form not in WATCHED_FORMS:
                    continue

                acc = accessions[i]
                f_date_str = filing_dates[i]
                r_date_str = report_dates[i] if i < len(report_dates) else None
                desc = descriptions[i] if i < len(descriptions) else None

                # For 8-K filings, optionally filter for Item 2.02 earnings announcements
                # or primary press release exhibits
                if form == "8-K":
                    doc_desc = (desc or "").lower()
                    # Keep earnings-related or broad corporate updates
                    if doc_desc and not any(kw in doc_desc for kw in ["earnings", "result", "operation", "financial", "press", "ex-99", "exhibit"]):
                        # Still track if no description is provided, but prioritize earnings
                        pass

                if acc not in known_accessions:
                    try:
                        f_date = dt.date.fromisoformat(f_date_str)
                    except Exception:
                        f_date = dt.date.today()

                    r_date = None
                    if r_date_str:
                        try:
                            r_date = dt.date.fromisoformat(r_date_str)
                        except Exception:
                            r_date = None

                    # If this is the very first time we see this company and it had NO events,
                    # seed existing historical filings as already known so we don't trigger false alerts
                    if not has_existing_events:
                        event = FilingEvent(
                            cik=cik,
                            ticker=ticker,
                            form=form,
                            accession_number=acc,
                            filing_date=f_date,
                            report_date=r_date,
                            description=desc or f"{form} filing",
                            is_processed=True,
                        )
                        db.add(event)
                        known_accessions.add(acc)
                        continue

                    # True NEW filing discovered!
                    event = FilingEvent(
                        cik=cik,
                        ticker=ticker,
                        form=form,
                        accession_number=acc,
                        filing_date=f_date,
                        report_date=r_date,
                        description=desc or f"{form} filing",
                        is_processed=False,
                    )
                    db.add(event)
                    known_accessions.add(acc)

                    discovered.append(
                        DiscoveredFiling(
                            ticker=ticker,
                            cik=cik,
                            form=form,
                            accession_number=acc,
                            filing_date=f_date_str,
                            report_date=r_date_str,
                            description=desc or f"{form} filing",
                            refreshed_metrics=False,
                            is_new=True,
                        )
                    )
                    should_refresh = True

            db.commit()

            # If new filings were discovered and auto_refresh is enabled, trigger refresh
            if should_refresh and auto_refresh:
                logger.info("New filing(s) found for %s (%s). Auto-refreshing metrics...", ticker, cik)
                self.financials_svc.fetch_and_persist(ticker, periods=12, session=db)
                self.financials_svc.enrich_company(ticker, session=db)
                self.financials_svc.enrich_press_releases(ticker, periods=12, session=db)

                # Mark events as processed
                for disc in discovered:
                    db.execute(
                        select(FilingEvent).where(
                            FilingEvent.cik == cik,
                            FilingEvent.accession_number == disc.accession_number,
                        )
                    )
                    ev = db.execute(
                        select(FilingEvent).where(
                            FilingEvent.cik == cik,
                            FilingEvent.accession_number == disc.accession_number,
                        )
                    ).scalar_one_or_none()
                    if ev:
                        ev.is_processed = True
                    disc.refreshed_metrics = True
                db.commit()

            return discovered

        finally:
            if should_close:
                db.close()

    def check_watchlist(
        self,
        pinned_only: bool = True,
        auto_refresh: bool = True,
        session: Session | None = None,
        progress_callback: Callable[[str, list[DiscoveredFiling]], None] | None = None,
    ) -> WatcherCheckSummary:
        """Poll EDGAR for all companies in the watchlist."""
        db, should_close = self._db_scope(session)
        now_str = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        try:
            cards = self.watchlist_svc.get_watchlist(pinned_only=pinned_only, session=db)
            all_discovered: list[DiscoveredFiling] = []
            refreshed_count = 0

            for card in cards:
                if not card.ticker:
                    continue
                try:
                    discovered = self.check_company_for_new_filings(
                        card.ticker,
                        auto_refresh=auto_refresh,
                        session=db,
                    )
                    if discovered:
                        all_discovered.extend(discovered)
                        if any(d.refreshed_metrics for d in discovered):
                            refreshed_count += 1

                    if progress_callback:
                        progress_callback(card.ticker, discovered)
                except Exception:
                    logger.warning("Error polling filings for %s", card.ticker, exc_info=True)

            return WatcherCheckSummary(
                checked_count=len(cards),
                new_filings_count=len(all_discovered),
                refreshed_companies_count=refreshed_count,
                new_filings=all_discovered,
                checked_at=now_str,
            )
        finally:
            if should_close:
                db.close()

    def get_recent_filings(
        self,
        limit: int = 15,
        session: Session | None = None,
    ) -> list[FilingEvent]:
        """Query recent filing events for feeds, alerts, and dashboards."""
        db, should_close = self._db_scope(session)
        try:
            return (
                db.execute(
                    select(FilingEvent)
                    .order_by(FilingEvent.filing_date.desc(), FilingEvent.created_at.desc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
        finally:
            if should_close:
                db.close()
