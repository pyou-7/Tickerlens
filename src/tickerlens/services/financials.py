from __future__ import annotations

import datetime as dt
import logging

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from tickerlens.data.edgar import EdgarClient, normalize_cik
from tickerlens.data.sic import sector_for_sic
from tickerlens.data.wikipedia import get_description
from tickerlens.data.xbrl import QuarterlyFinancials, extract_recent_quarterly_financials
from tickerlens.data.yahoo import get_quote
from tickerlens.models.company import Company
from tickerlens.models.database import get_session
from tickerlens.models.quarterly_financial import QuarterlyFinancial

logger = logging.getLogger(__name__)


class CompanyNotFoundError(Exception):
    """Raised by get_overview when no local data exists for a ticker."""


# ── public output models ───────────────────────────────────────────────────────

class KPISnapshot(BaseModel):
    revenue: float | None = None
    net_income: float | None = None
    eps_basic: float | None = None
    eps_diluted: float | None = None
    free_cash_flow: float | None = None


class KPIChange(BaseModel):
    """YoY percentage change for each KPI (None = not computable)."""
    revenue: float | None = None
    net_income: float | None = None
    eps_basic: float | None = None
    eps_diluted: float | None = None
    free_cash_flow: float | None = None


class CompanyOverview(BaseModel):
    cik: str
    name: str
    ticker: str | None = None
    description: str | None = None
    sector: str | None = None
    last_price: float | None = None
    market_cap: float | None = None
    # latest quarter
    latest_label: str          # e.g. "Q2 FY2025"
    latest_period_end: dt.date
    latest_kpi: KPISnapshot
    yoy: KPIChange
    # TTM
    ttm_kpi: KPISnapshot
    ttm_quarters: int  # number of quarters summed (< 4 means partial)


# ── service ───────────────────────────────────────────────────────────────────

class FinancialsService:
    """Financial statement extraction, persistence, and enrichment service."""

    def __init__(
        self,
        edgar_client: EdgarClient | None = None,
        session: Session | None = None,
    ) -> None:
        self.edgar_client = edgar_client or EdgarClient()
        self._session = session

    def recent_quarterly_financials(
        self,
        cik: str | int,
        periods: int = 4,
    ) -> list[QuarterlyFinancials]:
        normalized_cik = normalize_cik(cik)
        submissions = self.edgar_client.submissions(normalized_cik)
        companyfacts = self.edgar_client.companyfacts(normalized_cik)
        return extract_recent_quarterly_financials(
            companyfacts,
            fiscal_year_end=submissions.get("fiscalYearEnd"),
            periods=periods,
        )

    def fetch_and_persist(
        self,
        ticker: str,
        periods: int = 4,
        session: Session | None = None,
    ) -> list[QuarterlyFinancials]:
        """Fetch XBRL financials from EDGAR and upsert into SQLite."""
        cik = normalize_cik(self.edgar_client.cik_for_ticker(ticker))
        submissions = self.edgar_client.submissions(cik)
        companyfacts = self.edgar_client.companyfacts(cik)

        rows = extract_recent_quarterly_financials(
            companyfacts,
            fiscal_year_end=submissions.get("fiscalYearEnd"),
            periods=periods,
        )

        db = session or self._session or get_session()
        try:
            _upsert_company(db, cik, submissions, ticker)
            for row in rows:
                _upsert_financial(db, cik, row)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            if session is None and self._session is None:
                db.close()

        return rows

    def enrich_company(self, ticker: str, session: Session | None = None) -> None:
        """Update description, price, and market cap for an existing company."""
        cik = normalize_cik(self.edgar_client.cik_for_ticker(ticker))
        db = session or self._session or get_session()
        try:
            company = db.get(Company, cik)
            if company is None:
                raise ValueError(f"Company with CIK {cik} not in DB — run fetch_and_persist first")

            quote = get_quote(ticker)
            description = get_description(company.name)

            company.last_price = quote.last_price
            company.market_cap = quote.market_cap
            company.description = description  # None clears a stale description
            company.updated_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            if session is None and self._session is None:
                db.close()

    def get_overview(self, ticker: str, session: Session | None = None) -> CompanyOverview:
        """Return everything needed to render the Overview page."""
        cik = normalize_cik(self.edgar_client.cik_for_ticker(ticker))
        db = session or self._session or get_session()
        try:
            company = db.get(Company, cik)
            if company is None:
                raise CompanyNotFoundError(f"No data for {ticker} — run fetch_and_persist first")

            rows = (
                db.execute(
                    select(QuarterlyFinancial)
                    .where(QuarterlyFinancial.cik == cik)
                    .order_by(QuarterlyFinancial.period_end.desc())
                    .limit(8)
                )
                .scalars()
                .all()
            )

            if not rows:
                raise CompanyNotFoundError(f"No quarterly data for {ticker}")

            latest = rows[0]
            latest_kpi = _to_kpi(latest)
            ttm_rows = list(rows[:4])
            ttm_kpi = _compute_ttm(ttm_rows)
            yoy = _compute_yoy(latest, list(rows))

            return CompanyOverview(
                cik=cik,
                name=company.name,
                ticker=company.ticker,
                description=company.description,
                sector=sector_for_sic(company.sic),
                last_price=company.last_price,
                market_cap=company.market_cap,
                latest_label=f"{latest.fiscal_period} FY{latest.fiscal_year}",
                latest_period_end=latest.period_end,
                latest_kpi=latest_kpi,
                yoy=yoy,
                ttm_kpi=ttm_kpi,
                ttm_quarters=len(ttm_rows),
            )
        finally:
            if session is None and self._session is None:
                db.close()


# ── helpers ───────────────────────────────────────────────────────────────────

def _to_kpi(row: QuarterlyFinancial) -> KPISnapshot:
    return KPISnapshot(
        revenue=row.revenue,
        net_income=row.net_income,
        eps_basic=row.eps_basic,
        eps_diluted=row.eps_diluted,
        free_cash_flow=row.free_cash_flow,
    )


def _sum_nullable(*values: float | None) -> float | None:
    nums = [v for v in values if v is not None]
    return sum(nums) if nums else None


def _compute_ttm(rows: list[QuarterlyFinancial]) -> KPISnapshot:
    return KPISnapshot(
        revenue=_sum_nullable(*[r.revenue for r in rows]),
        net_income=_sum_nullable(*[r.net_income for r in rows]),
        eps_basic=_sum_nullable(*[r.eps_basic for r in rows]),
        eps_diluted=_sum_nullable(*[r.eps_diluted for r in rows]),
        free_cash_flow=_sum_nullable(*[r.free_cash_flow for r in rows]),
    )


def _pct_change(current: float | None, prior: float | None) -> float | None:
    if current is None or prior is None or prior == 0:
        return None
    return (current - prior) / abs(prior) * 100


def _compute_yoy(latest: QuarterlyFinancial, rows: list[QuarterlyFinancial]) -> KPIChange:
    prior = next(
        (
            r for r in rows
            if r.fiscal_period == latest.fiscal_period
            and r.fiscal_year == latest.fiscal_year - 1
        ),
        None,
    )
    if prior is None:
        return KPIChange()
    return KPIChange(
        revenue=_pct_change(latest.revenue, prior.revenue),
        net_income=_pct_change(latest.net_income, prior.net_income),
        eps_basic=_pct_change(latest.eps_basic, prior.eps_basic),
        eps_diluted=_pct_change(latest.eps_diluted, prior.eps_diluted),
        free_cash_flow=_pct_change(latest.free_cash_flow, prior.free_cash_flow),
    )


def _upsert_company(session: Session, cik: str, submissions: dict, ticker: str) -> None:
    tickers = submissions.get("tickers") or []
    primary_ticker = ticker.upper() if ticker else (tickers[0] if tickers else None)

    stmt = (
        insert(Company)
        .values(
            cik=cik,
            name=submissions.get("name", ""),
            ticker=primary_ticker,
            fiscal_year_end=submissions.get("fiscalYearEnd"),
            sic=str(submissions.get("sic", "")) or None,
            updated_at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
        )
        .on_conflict_do_update(
            index_elements=["cik"],
            set_={
                "name": submissions.get("name", ""),
                "ticker": primary_ticker,
                "fiscal_year_end": submissions.get("fiscalYearEnd"),
                "sic": str(submissions.get("sic", "")) or None,
                "updated_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
            },
        )
    )
    session.execute(stmt)


def _upsert_financial(session: Session, cik: str, row: QuarterlyFinancials) -> None:
    stmt = (
        insert(QuarterlyFinancial)
        .values(
            cik=cik,
            period_end=row.end,
            fiscal_year=row.fy,
            fiscal_period=row.fp,
            revenue=row.revenue,
            net_income=row.net_income,
            eps_basic=row.eps_basic,
            eps_diluted=row.eps_diluted,
            free_cash_flow=row.free_cash_flow,
            updated_at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
        )
        .on_conflict_do_update(
            index_elements=["cik", "period_end"],
            set_={
                "fiscal_year": row.fy,
                "fiscal_period": row.fp,
                "revenue": row.revenue,
                "net_income": row.net_income,
                "eps_basic": row.eps_basic,
                "eps_diluted": row.eps_diluted,
                "free_cash_flow": row.free_cash_flow,
                "updated_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
            },
        )
    )
    session.execute(stmt)
