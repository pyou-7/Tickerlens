from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from tickerlens.models.base import Base
from tickerlens.models.company import Company
from tickerlens.models.quarterly_financial import QuarterlyFinancial
from tickerlens.models.watchlist import WatchlistItem
from tickerlens.services.watchlist import WatchlistService


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    return factory()


def test_watchlist_add_and_get(session: Session) -> None:
    # Seed company and quarterly financial
    comp = Company(
        cik="0000320193",
        name="Apple Inc.",
        ticker="AAPL",
        last_price=220.5,
        market_cap=3_400_000_000_000,
        sic="3571",
    )
    session.add(comp)
    q1 = QuarterlyFinancial(
        cik="0000320193",
        period_end=dt.date(2025, 6, 28),
        fiscal_year=2025,
        fiscal_period="Q3",
        revenue=85_777_000_000,
        net_income=21_448_000_000,
        eps_diluted=1.40,
        free_cash_flow=28_000_000_000,
    )
    session.add(q1)
    session.commit()

    svc = WatchlistService(session=session)
    assert not svc.is_pinned("AAPL")
    assert not svc.is_watched("AAPL")

    svc.add("AAPL", pinned=True)
    assert svc.is_pinned("AAPL")
    assert svc.is_watched("AAPL")

    cards = svc.get_watchlist(pinned_only=True)
    assert len(cards) == 1
    card = cards[0]
    assert card.ticker == "AAPL"
    assert card.name == "Apple Inc."
    assert card.last_price == 220.5
    assert card.kpis.revenue == 85_777_000_000
    assert card.latest_period == "Q3 FY2025"


def test_watchlist_toggle_and_remove(session: Session) -> None:
    comp = Company(
        cik="0001045810",
        name="NVIDIA Corporation",
        ticker="NVDA",
        last_price=120.0,
    )
    session.add(comp)
    session.commit()

    svc = WatchlistService(session=session)
    # 1. Toggle on (adds and pins)
    pinned = svc.toggle_pin("NVDA")
    assert pinned is True
    assert svc.is_pinned("NVDA")

    # 2. Toggle off (unpins)
    pinned = svc.toggle_pin("NVDA")
    assert pinned is False
    assert not svc.is_pinned("NVDA")
    assert svc.is_watched("NVDA")  # still in items, just unpinned

    # 3. Toggle on again
    pinned = svc.toggle_pin("NVDA")
    assert pinned is True
    assert svc.is_pinned("NVDA")

    # 4. Remove
    removed = svc.remove("NVDA")
    assert removed is True
    assert not svc.is_watched("NVDA")
    assert not svc.is_pinned("NVDA")
