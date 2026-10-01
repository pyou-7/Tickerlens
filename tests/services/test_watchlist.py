"""Tests for the watchlist (PRD §4.6, first slice)."""

from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from tickerlens.models.base import Base
from tickerlens.models.company import Company
from tickerlens.services.financials import CompanyNotFoundError, FinancialsService


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _svc(session: Session, cik: str = "0000320193") -> FinancialsService:
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    return FinancialsService(edgar_client=mock_edgar, session=session)


def _company(cik: str = "0000320193", ticker: str = "AAPL", name: str = "Apple Inc.") -> Company:
    c = Company()
    c.cik = cik
    c.ticker = ticker
    c.name = name
    c.updated_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    return c


def test_watch_and_unwatch_round_trip(session: Session) -> None:
    session.add(_company())
    session.commit()
    svc = _svc(session)
    assert svc.is_watching("AAPL") is False
    assert svc.watch_ticker("AAPL") is True
    assert svc.is_watching("AAPL") is True
    # idempotent
    assert svc.watch_ticker("AAPL") is True
    assert svc.unwatch_ticker("AAPL") is False
    assert svc.is_watching("AAPL") is False


def test_watch_requires_company_data(session: Session) -> None:
    svc = _svc(session)
    with pytest.raises(CompanyNotFoundError):
        svc.watch_ticker("AAPL")


def test_get_watchlist_order_and_signal_none_without_financials(session: Session) -> None:
    session.add(_company(cik="0000320193", ticker="AAPL", name="Apple Inc."))
    session.add(_company(cik="0000789019", ticker="MSFT", name="Microsoft Corp."))
    session.commit()
    svc = _svc(session, cik="0000320193")
    svc.watch_ticker("AAPL")
    # second service with different CIK mapping for MSFT
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = "0000789019"
    svc2 = FinancialsService(edgar_client=mock_edgar, session=session)
    svc2.watch_ticker("MSFT")

    rows = svc.get_watchlist()
    assert [r.ticker for r in rows] == ["MSFT", "AAPL"]  # most recent first
    assert rows[0].name == "Microsoft Corp."
    # no quarterly rows -> valuation not computable -> signal None
    assert rows[0].signal is None


def test_watchlist_note_round_trip(session: Session) -> None:
    session.add(_company())
    session.commit()
    svc = _svc(session)
    assert svc.get_watchlist_note("AAPL") is None
    svc.watch_ticker("AAPL")
    assert svc.set_watchlist_note("AAPL", "Earnings play — check Q3 call") == "Earnings play — check Q3 call"
    assert svc.get_watchlist_note("AAPL") == "Earnings play — check Q3 call"
    # Blank note clears.
    assert svc.set_watchlist_note("AAPL", "   ") is None
    assert svc.get_watchlist_note("AAPL") is None


def test_watchlist_note_capped_at_280_chars(session: Session) -> None:
    session.add(_company())
    session.commit()
    svc = _svc(session)
    svc.watch_ticker("AAPL")
    saved = svc.set_watchlist_note("AAPL", "x" * 500)
    assert saved is not None and len(saved) == 280


def test_watchlist_note_requires_watching(session: Session) -> None:
    session.add(_company())
    session.commit()
    svc = _svc(session)
    with pytest.raises(CompanyNotFoundError):
        svc.set_watchlist_note("AAPL", "hello")


def test_get_watchlist_includes_note(session: Session) -> None:
    session.add(_company())
    session.commit()
    svc = _svc(session)
    svc.watch_ticker("AAPL")
    svc.set_watchlist_note("AAPL", "why: moat")
    rows = svc.get_watchlist()
    assert len(rows) == 1
    assert rows[0].note == "why: moat"


# ── watchlist tags (PRD §4.6, tags slice) ─────────────────────────────────────

def test_watchlist_tags_round_trip(session: Session) -> None:
    session.add(_company())
    session.commit()
    svc = _svc(session)
    assert svc.get_watchlist_tags("AAPL") == []
    svc.watch_ticker("AAPL")
    assert svc.set_watchlist_tags("AAPL", "dividend, ai") == ["dividend", "ai"]
    assert svc.get_watchlist_tags("AAPL") == ["dividend", "ai"]
    # Blank clears.
    assert svc.set_watchlist_tags("AAPL", "  , ") == []
    assert svc.get_watchlist_tags("AAPL") == []


def test_watchlist_tags_normalized(session: Session) -> None:
    session.add(_company())
    session.commit()
    svc = _svc(session)
    svc.watch_ticker("AAPL")
    # Deduped case-insensitively, stripped, capped at 5, each ≤20 chars.
    saved = svc.set_watchlist_tags(
        "AAPL", " AI, ai, Dividend ,x" * 1 + ", extra1, extra2, extra3, extra4,"
        " averylongtagnamethatexceedstwentycharacters"
    )
    assert saved == ["AI", "Dividend", "x", "extra1", "extra2"]
    assert all(len(t) <= 20 for t in saved)


def test_watchlist_tags_require_watching(session: Session) -> None:
    session.add(_company())
    session.commit()
    svc = _svc(session)
    with pytest.raises(CompanyNotFoundError):
        svc.set_watchlist_tags("AAPL", "ai")


def test_get_watchlist_includes_tags(session: Session) -> None:
    session.add(_company())
    session.commit()
    svc = _svc(session)
    svc.watch_ticker("AAPL")
    svc.set_watchlist_tags("AAPL", "dividend, ai")
    rows = svc.get_watchlist()
    assert len(rows) == 1
    assert rows[0].tags == ["dividend", "ai"]


def test_get_benchmarks_returns_stored_benchmarks(session: Session) -> None:
    session.add(_company(cik="0000320193", ticker="AAPL", name="Apple Inc."))
    session.add(_company(cik="0001045810", ticker="NVDA", name="NVIDIA Corp."))
    session.commit()
    svc = _svc(session)
    benchmarks = svc.get_benchmarks()
    assert len(benchmarks) >= 2
    tickers = [b.ticker for b in benchmarks]
    assert "NVDA" in tickers
    assert "AAPL" in tickers
