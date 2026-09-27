import datetime as dt

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tickerlens.models.base import Base


class FilingEvent(Base):
    __tablename__ = "filing_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cik: Mapped[str] = mapped_column(
        String(10), ForeignKey("companies.cik", ondelete="CASCADE"), index=True, nullable=False
    )
    ticker: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    form: Mapped[str] = mapped_column(String(10), nullable=False)  # "10-Q", "10-K", "8-K"
    accession_number: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    filing_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    report_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_processed: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=lambda: dt.datetime.now(dt.timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("cik", "accession_number", name="uq_filing_event_cik_accession"),
    )

    company: Mapped["Company"] = relationship("Company", back_populates="filing_events")  # noqa: F821
