import datetime as dt

from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from tickerlens.models.base import Base


class WatchlistEntry(Base):
    """A pinned company on the home screen. CIK is the canonical key."""

    __tablename__ = "watchlist"

    cik: Mapped[str] = mapped_column(String(10), primary_key=True)
    added_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    # Personal reminder of why the company is being watched (PRD §4.6).
    note: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
