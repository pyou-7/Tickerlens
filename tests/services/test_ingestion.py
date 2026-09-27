import datetime as dt
from unittest.mock import MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from tickerlens.models.base import Base
from tickerlens.models.company import Company
from tickerlens.models.quarterly_financial import QuarterlyFinancial
from tickerlens.models.watchlist import WatchlistItem
from tickerlens.services.ingestion import IngestionService, RefreshResult, CURATED_TECH_UNIVERSE


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    return factory()


def _company(
    cik: str = "0000320193",
    ticker: str = "AAPL",
    name: str = "Apple Inc.",
    last_price: float = 220.0,
    market_cap: float = 3_400_000_000_000.0,
) -> Company:
    return Company(
        cik=cik,
        ticker=ticker,
        name=name,
        last_price=last_price,
        market_cap=market_cap,
    )


def _row(
    cik: str = "0000320193",
    period_end: dt.date = dt.date(2025, 6, 30),
    fiscal_year: int = 2025,
    fiscal_period: str = "Q3",
    revenue: float = 120_000.0,
    net_income: float = 35_000.0,
) -> QuarterlyFinancial:
    return QuarterlyFinancial(
        cik=cik,
        period_end=period_end,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        revenue=revenue,
        net_income=net_income,
    )


def test_refresh_ticker_success(session: Session) -> None:
    cik = "0000320193"
    comp = _company(cik=cik, ticker="AAPL")
    row = _row(cik=cik)
    session.add(comp)
    session.add(row)
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik

    mock_fin = MagicMock()
    mock_fin.fetch_and_persist.return_value = [row]
    mock_fin.enrich_company.return_value = None
    mock_fin.enrich_press_releases.return_value = 2

    mock_watch = MagicMock()
    mock_watch.is_pinned.return_value = True

    svc = IngestionService(
        session=session,
        financials_service=mock_fin,
        watchlist_service=mock_watch,
        edgar_client=mock_edgar,
    )

    result = svc.refresh_ticker("AAPL", periods=4, include_disclosures=True, pin=False)

    assert result.success is True
    assert result.ticker == "AAPL"
    assert result.cik == cik
    assert result.name == "Apple Inc."
    assert result.latest_period == "Q3 FY2025"
    assert result.latest_revenue == 120_000.0
    assert result.latest_net_income == 35_000.0
    assert result.latest_price == 220.0
    assert result.disclosures_count == 2
    assert result.is_pinned is True
    assert result.error is None
    assert result.duration_seconds >= 0.0

    mock_fin.fetch_and_persist.assert_called_once_with("AAPL", periods=4, session=session)
    mock_fin.enrich_company.assert_called_once_with("AAPL", session=session)
    mock_fin.enrich_press_releases.assert_called_once_with("AAPL", periods=4, session=session)


def test_refresh_ticker_failure_handling(session: Session) -> None:
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.side_effect = KeyError("Ticker INVALID not found")

    svc = IngestionService(session=session, edgar_client=mock_edgar)
    result = svc.refresh_ticker("INVALID")

    assert result.success is False
    assert result.ticker == "INVALID"
    assert "not found" in (result.error or "")


def test_refresh_tickers_batch(session: Session) -> None:
    cik1 = "0000320193"
    cik2 = "0000789019"
    comp1 = _company(cik=cik1, ticker="AAPL")
    comp2 = _company(cik=cik2, ticker="MSFT", name="Microsoft Corp.")
    session.add(comp1)
    session.add(comp2)
    session.add(_row(cik=cik1))
    session.add(_row(cik=cik2, fiscal_period="Q4", revenue=64_000.0))
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.side_effect = lambda t: cik1 if t == "AAPL" else cik2

    mock_fin = MagicMock()
    mock_fin.fetch_and_persist.return_value = []
    mock_fin.enrich_company.return_value = None

    mock_watch = MagicMock()
    mock_watch.is_pinned.return_value = False

    svc = IngestionService(
        session=session,
        financials_service=mock_fin,
        watchlist_service=mock_watch,
        edgar_client=mock_edgar,
    )

    progress_events: list[tuple[int, int, RefreshResult]] = []

    def callback(idx: int, total: int, res: RefreshResult) -> None:
        progress_events.append((idx, total, res))

    summary = svc.refresh_tickers(
        ["AAPL", "MSFT"],
        periods=8,
        delay=0.0,
        progress_callback=callback,
    )

    assert summary.total_requested == 2
    assert summary.succeeded == 2
    assert summary.failed == 0
    assert len(summary.results) == 2
    assert len(progress_events) == 2
    assert progress_events[0][0] == 1
    assert progress_events[1][0] == 2


def test_refresh_watchlist_and_all_db(session: Session) -> None:
    cik1 = "0000320193"
    comp1 = _company(cik=cik1, ticker="AAPL")
    session.add(comp1)
    session.add(WatchlistItem(cik=cik1, is_pinned=True))
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik1

    mock_fin = MagicMock()
    mock_fin.fetch_and_persist.return_value = []
    mock_fin.enrich_company.return_value = None

    svc = IngestionService(session=session, financials_service=mock_fin, edgar_client=mock_edgar)

    summary_watch = svc.refresh_watchlist(pinned_only=True, delay=0.0)
    assert summary_watch.total_requested == 1
    assert summary_watch.succeeded == 1

    summary_db = svc.refresh_all_db(delay=0.0)
    assert summary_db.total_requested >= 1
    assert summary_db.succeeded >= 1


def test_get_top_universe_tickers() -> None:
    svc = IngestionService(edgar_client=MagicMock())
    top10 = svc.get_top_universe_tickers(10)
    assert len(top10) == 10
    assert "AAPL" in top10
    assert "NVDA" in top10
    assert "MSFT" in top10
