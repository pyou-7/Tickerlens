import datetime as dt

from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tickerlens.models.base import Base


class Company(Base):
    __tablename__ = "companies"

    cik: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    ticker: Mapped[str | None] = mapped_column(String(20), index=True)
    fiscal_year_end: Mapped[str | None] = mapped_column(String(4))  # MMDD
    sic: Mapped[str | None] = mapped_column(String(10))
    # Latest 10-Q/10-K(/A) filingDate (YYYY-MM-DD) already incorporated into
    # quarterly_financials. Drives refresh_financials_if_stale: a refresh runs
    # only when EDGAR shows a filing newer than this marker, so restarts and
    # repeat visits don't trigger redundant full XBRL re-pulls. NULL for rows
    # that predate the marker (one heuristic pass, then it is set).
    xbrl_filings_processed: Mapped[str | None] = mapped_column(String(10))
    # reportDates (YYYY-MM-DD, JSON array) of in-window quarterly filings
    # whose XBRL facts are ingested but whose quarter the extractor
    # deliberately yields nothing for (e.g. SKYD's merger-era Q3'25: a 53-day
    # stub period the 70–100-day comparability window rejects; its Q4'25,
    # underivable as FY−9M through the merger). Acknowledged gaps stop the
    # middle-gap retry in refresh_financials_if_stale from re-pulling every
    # 6h forever. A future newer filing still re-extracts the full window,
    # so an acknowledged quarter appears then if it ever becomes
    # extractable. NULL/empty = none. Added by ensure_schema on old DBs.
    xbrl_skipped_quarters: Mapped[str | None] = mapped_column(Text)
    # Plain-language note shown on the company page when a 10-Q/10-K has been
    # filed but EDGAR's companyfacts feed hasn't ingested its figures yet
    # (batch-37/APLD ingestion lag — e.g. CB's Q2'26 10-Q filed 2026-07-28
    # with no revenue facts by Oct 2026), so the page still shows the prior
    # quarter with no explanation. Computed by refresh_financials_if_stale
    # (TTL-gated) and cleared automatically once the quarter lands. NULL =
    # nothing pending. Added by ensure_schema on old DBs.
    pending_filing_note: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(String(2000))
    last_price: Mapped[float | None] = mapped_column()
    market_cap: Mapped[float | None] = mapped_column()
    risk_factors: Mapped[str | None] = mapped_column(Text)
    risk_factors_source: Mapped[str | None] = mapped_column(String(64))  # e.g. "10-K filed 2024-11-01"
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    financials: Mapped[list["QuarterlyFinancial"]] = relationship(  # noqa: F821
        back_populates="company", cascade="all, delete-orphan"
    )
