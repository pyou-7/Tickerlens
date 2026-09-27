import datetime as dt
from unittest.mock import MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from tickerlens.models.base import Base
from tickerlens.models.company import Company
from tickerlens.models.filing_event import FilingEvent
from tickerlens.models.watchlist import WatchlistItem
from tickerlens.services.filing_watcher import FilingWatcherService, DiscoveredFiling


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    return factory()


def _mock_submissions(accessions: list[str], forms: list[str]) -> dict:
    return {
        "filings": {
            "recent": {
                "accessionNumber": accessions,
                "form": forms,
                "filingDate": ["2026-08-20"] * len(accessions),
                "reportDate": ["2026-07-26"] * len(accessions),
                "primaryDocDescription": ["Quarterly Report"] * len(accessions),
            }
        }
    }


def test_pending_filings_retry_after_refresh_failure(session):
    cik = "0001045810"
    session.add(Company(cik=cik, ticker="NVDA", name="NVIDIA"))
    session.add(FilingEvent(cik=cik, ticker="NVDA", form="10-Q",
                           accession_number="pending", filing_date=dt.date(2026, 8, 20),
                           is_processed=False))
    session.commit()
    edgar = MagicMock()
    edgar.submissions.return_value = _mock_submissions(["pending"], ["10-Q"])
    financials = MagicMock()
    financials.fetch_and_persist.side_effect = [RuntimeError("temporary outage"), None]
    watcher = FilingWatcherService(session=session, edgar_client=edgar, financials_service=financials)
    with pytest.raises(RuntimeError):
        watcher.check_company_for_new_filings("NVDA")
    assert not session.query(FilingEvent).one().is_processed
    retried = watcher.check_company_for_new_filings("NVDA")
    assert len(retried) == 1 and not retried[0].is_new
    assert retried[0].refreshed_metrics
    assert session.query(FilingEvent).one().is_processed
    edgar.submissions.assert_called_with(cik, force_refresh=True)


def test_check_company_initial_seeding(session: Session) -> None:
    cik = "0001045810"
    comp = Company(cik=cik, ticker="NVDA", name="NVIDIA CORP")
    session.add(comp)
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    mock_edgar.submissions.return_value = _mock_submissions(
        ["0001045810-26-000001", "0001045810-26-000002"],
        ["10-Q", "8-K"],
    )

    mock_fin = MagicMock()
    svc = FilingWatcherService(session=session, financials_service=mock_fin, edgar_client=mock_edgar)

    discovered = svc.check_company_for_new_filings("NVDA", auto_refresh=True, session=session)

    # Initial run seeds historical filings without triggering false-positive "new" alerts
    assert len(discovered) == 0

    # But events should be seeded in DB
    events = session.query(FilingEvent).filter_by(cik=cik).all()
    assert len(events) == 2
    mock_fin.fetch_and_persist.assert_not_called()


def test_check_company_new_filing_detection_and_refresh(session: Session) -> None:
    cik = "0001045810"
    comp = Company(cik=cik, ticker="NVDA", name="NVIDIA CORP")
    session.add(comp)
    # Pre-seed one known event
    session.add(
        FilingEvent(
            cik=cik,
            ticker="NVDA",
            form="10-Q",
            accession_number="0001045810-26-000001",
            filing_date=dt.date(2026, 5, 20),
            is_processed=True,
        )
    )
    session.commit()

    # Now EDGAR returns an additional new filing!
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    mock_edgar.submissions.return_value = _mock_submissions(
        ["0001045810-26-000099", "0001045810-26-000001"],
        ["10-Q", "10-Q"],
    )

    mock_fin = MagicMock()
    mock_fin.fetch_and_persist.return_value = []
    mock_fin.enrich_company.return_value = None
    mock_fin.enrich_press_releases.return_value = 1

    svc = FilingWatcherService(session=session, financials_service=mock_fin, edgar_client=mock_edgar)

    discovered = svc.check_company_for_new_filings("NVDA", auto_refresh=True, session=session)

    assert len(discovered) == 1
    assert discovered[0].accession_number == "0001045810-26-000099"
    assert discovered[0].form == "10-Q"
    assert discovered[0].refreshed_metrics is True

    # Check auto-refreshes were triggered
    mock_fin.fetch_and_persist.assert_called_once_with("NVDA", periods=12, session=session)
    mock_fin.enrich_company.assert_called_once_with("NVDA", session=session)
    mock_fin.enrich_press_releases.assert_called_once_with("NVDA", periods=12, session=session)

    # Check event persisted in DB
    new_ev = session.query(FilingEvent).filter_by(accession_number="0001045810-26-000099").one()
    assert new_ev.is_processed is True


def test_check_watchlist_and_get_recent_filings(session: Session) -> None:
    cik = "0000320193"
    comp = Company(cik=cik, ticker="AAPL", name="Apple Inc.")
    session.add(comp)
    session.add(WatchlistItem(cik=cik, is_pinned=True))
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    mock_edgar.submissions.return_value = _mock_submissions(
        ["0000320193-26-000010"],
        ["10-Q"],
    )

    svc = FilingWatcherService(session=session, edgar_client=mock_edgar)

    summary = svc.check_watchlist(pinned_only=True, auto_refresh=False, session=session)
    assert summary.checked_count == 1

    recent = svc.get_recent_filings(limit=5, session=session)
    assert len(recent) >= 1
    assert recent[0].ticker == "AAPL"
