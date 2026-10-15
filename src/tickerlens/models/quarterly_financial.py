import datetime as dt

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tickerlens.models.base import Base


# Tolerance for the balance-sheet accounting identity, shared with the
# extraction guard in tickerlens.data.xbrl (which imports it from here).
# $2M floor covers worst-case rounding across the three legs (filers report
# in millions); 0.1% relative keeps the check meaningful for large balance
# sheets.
_IDENTITY_TOLERANCE_FLOOR = 2_000_000.0
_IDENTITY_TOLERANCE_REL = 0.001


def identity_tolerance(total_assets: float) -> float:
    """Materiality threshold for Assets vs Liabilities + Mezzanine + Equity."""
    return max(_IDENTITY_TOLERANCE_FLOOR, abs(total_assets) * _IDENTITY_TOLERANCE_REL)


def mezzanine_is_third_leg(
    total_assets: float | None,
    total_liabilities: float | None,
    total_equity: float | None,
    redeemable_nci: float | None,
) -> bool:
    """Whether the filed redeemable-NCI value is a genuine third balance-sheet leg.

    Some filers (AT&T, Thermo Fisher, Accenture, Walmart, Energy Transfer)
    file a redeemable-NCI tag while their extracted total equity already
    includes it — Assets minus Liabilities minus Equity closes to the dollar
    — so rendering the mezzanine row as an additional leg would double-count
    it. The row is only a real third leg when there is an identity gap for it
    to explain: the gap is material, runs in the same direction as the
    mezzanine value, and the mezzanine does not overshoot the gap.
    """
    if redeemable_nci is None:
        return False
    if total_assets is None or total_liabilities is None or total_equity is None:
        # Can't evaluate the identity; show the filed value (legacy behavior).
        return True
    gap = total_assets - total_liabilities - total_equity
    tol = identity_tolerance(total_assets)
    if abs(gap) <= tol:
        return False
    return (gap > 0) == (redeemable_nci > 0) and abs(redeemable_nci) <= abs(gap) + tol


class QuarterlyFinancial(Base):
    __tablename__ = "quarterly_financials"
    __table_args__ = (UniqueConstraint("cik", "period_end", name="uq_cik_period_end"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cik: Mapped[str] = mapped_column(String(10), ForeignKey("companies.cik"), index=True)
    period_end: Mapped[dt.date] = mapped_column(Date, index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer)
    fiscal_period: Mapped[str] = mapped_column(String(4))   # Q1 | Q2 | Q3 | Q4
    revenue: Mapped[float | None] = mapped_column(Float)
    net_income: Mapped[float | None] = mapped_column(Float)
    eps_basic: Mapped[float | None] = mapped_column(Float)
    eps_diluted: Mapped[float | None] = mapped_column(Float)
    free_cash_flow: Mapped[float | None] = mapped_column(Float)
    # Funds from operations (batch 72): net income + depreciation −
    # property-disposition gains (+ real-estate impairments), computed at
    # extraction time. Only the REIT valuation path reads it. Auto-migrated
    # by ensure_schema(); backfilled by batch 72.
    ffo: Mapped[float | None] = mapped_column(Float)
    # Balance sheet (instant, as of period_end)
    total_assets: Mapped[float | None] = mapped_column(Float)
    total_liabilities: Mapped[float | None] = mapped_column(Float)
    total_equity: Mapped[float | None] = mapped_column(Float)
    cash_and_equivalents: Mapped[float | None] = mapped_column(Float)
    # Mezzanine equity: redeemable noncontrolling interest (between
    # liabilities and equity, part of neither). Auto-migrated by
    # ensure_schema(); backfilled by batch 59.
    redeemable_nci: Mapped[float | None] = mapped_column(Float)
    # Earnings-release highlights, extracted from the period's 8-K ex-99 exhibit.
    # Owned by enrich_company (best-effort); never wiped on transient failure.
    press_release_highlights: Mapped[str | None] = mapped_column(Text)
    press_release_source: Mapped[str | None] = mapped_column(String(64))  # e.g. "Earnings release Q4 FY2025"
    management_guidance: Mapped[str | None] = mapped_column(Text)
    management_guidance_source: Mapped[str | None] = mapped_column(String(64))
    transcript_excerpts: Mapped[str | None] = mapped_column(Text)
    transcript_source: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    company: Mapped["Company"] = relationship(back_populates="financials")  # noqa: F821

    @property
    def quarter_label(self) -> str:
        return f"{self.fiscal_period} FY{self.fiscal_year}"

    @property
    def mezzanine_is_third_leg(self) -> bool:
        """Whether this quarter's redeemable-NCI value renders as its own
        balance-sheet row (see :func:`mezzanine_is_third_leg`)."""
        return mezzanine_is_third_leg(
            self.total_assets,
            self.total_liabilities,
            self.total_equity,
            self.redeemable_nci,
        )
