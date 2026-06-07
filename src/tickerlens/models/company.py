import datetime as dt

from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tickerlens.models.base import Base


class Company(Base):
    __tablename__ = "companies"

    cik: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    ticker: Mapped[str | None] = mapped_column(String(20), index=True)
    fiscal_year_end: Mapped[str | None] = mapped_column(String(4))  # MMDD
    sic: Mapped[str | None] = mapped_column(String(10))
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    financials: Mapped[list["QuarterlyFinancial"]] = relationship(  # noqa: F821
        back_populates="company", cascade="all, delete-orphan"
    )
