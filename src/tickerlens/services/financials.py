from __future__ import annotations

import datetime as dt

from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from tickerlens.data.edgar import EdgarClient, normalize_cik
from tickerlens.data.xbrl import QuarterlyFinancials, extract_recent_quarterly_financials
from tickerlens.models.company import Company
from tickerlens.models.database import get_session
from tickerlens.models.quarterly_financial import QuarterlyFinancial


class FinancialsService:
    """Financial statement extraction and persistence service."""

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
        """Fetch XBRL financials from EDGAR and upsert into SQLite.

        Returns the list of QuarterlyFinancials that were processed.
        """
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


# ── helpers ───────────────────────────────────────────────────────────────────

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
            updated_at=dt.datetime.utcnow(),
        )
        .on_conflict_do_update(
            index_elements=["cik"],
            set_={
                "name": submissions.get("name", ""),
                "ticker": primary_ticker,
                "fiscal_year_end": submissions.get("fiscalYearEnd"),
                "sic": str(submissions.get("sic", "")) or None,
                "updated_at": dt.datetime.utcnow(),
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
            updated_at=dt.datetime.utcnow(),
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
                "updated_at": dt.datetime.utcnow(),
            },
        )
    )
    session.execute(stmt)
