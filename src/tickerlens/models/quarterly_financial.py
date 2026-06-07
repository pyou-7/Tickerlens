import datetime as dt

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tickerlens.models.base import Base


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
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    company: Mapped["Company"] = relationship(back_populates="financials")  # noqa: F821
