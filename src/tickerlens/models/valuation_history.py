import datetime as dt

from sqlalchemy import Date, Float, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from tickerlens.models.base import Base


class ValuationHistory(Base):
    """One valuation snapshot per company per day (PRD §4.11).

    Written by ``FinancialsService.record_valuation_snapshot`` during
    ``enrich_company`` (i.e. on every refresh). Lets the Overview card show
    "Signal changed from X to Y" by comparing the latest snapshot against the
    most recent prior one. CIK — not ticker — is the canonical key.
    """

    __tablename__ = "valuation_history"
    __table_args__ = (UniqueConstraint("cik", "as_of", name="uq_valuation_history_cik_as_of"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cik: Mapped[str] = mapped_column(String(10), index=True)
    as_of: Mapped[dt.date] = mapped_column(Date, index=True)
    price: Mapped[float | None] = mapped_column(Float)
    target_price: Mapped[float | None] = mapped_column(Float)
    upside_pct: Mapped[float | None] = mapped_column(Float)
    signal: Mapped[str] = mapped_column(String(16))
    method: Mapped[str] = mapped_column(String(16))  # "peg" | "sales" | "unavailable"
