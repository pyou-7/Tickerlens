"""Batch 171 regression tests: stale source-label self-heal.

Rows enriched before the batch-52 count-back fix carry a "Q1" source
label for a Q3 (or Q2) quarter — the old labeler counted forward from
Q1 in a mid-cycle window (NFLX Q3 FY2024 stored as "Earnings release
Q1 FY2024"). The live discovery label is correct now, but the backfill
only fills blank fields, so a wrong-but-present label stayed wrong
forever. The backfill now corrects the label while the period is
already re-fetched — but only on a two-against-one vote (live quarter
equals the row's XBRL fiscal_period, fiscal years agree), so only the
quarter moves, never the year.
"""
import datetime as dt
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from tickerlens.models.base import Base
from tickerlens.services.financials import (
    FinancialsService,
    _correct_stale_source_label,
)
from tests.services.test_financials import (
    _company,
    _enrich_mocks,
    _er_period,
    _row,
)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_correct_stale_source_label_fossil_shapes() -> None:
    # The attested fossils: Q1 stored, Q3 live, row is Q3.
    assert (
        _correct_stale_source_label(
            "Earnings release Q1 FY2024",
            "Earnings release Q3 FY2024",
            "Q3",
        )
        == "Earnings release Q3 FY2024"
    )
    assert (
        _correct_stale_source_label(
            "Earnings release Q1 FY2025",
            "Earnings release Q3 FY2025",
            "Q3",
        )
        == "Earnings release Q3 FY2025"
    )
    # XOM: Q1 stored, Q2 live, row is Q2.
    assert (
        _correct_stale_source_label(
            "Earnings release Q1 FY2026",
            "Earnings release Q2 FY2026",
            "Q2",
        )
        == "Earnings release Q2 FY2026"
    )
    # The guidance/transcript label shapes correct the same way.
    assert (
        _correct_stale_source_label(
            "8-K guidance, Q1 FY2024",
            "8-K guidance, Q3 FY2024",
            "Q3",
        )
        == "8-K guidance, Q3 FY2024"
    )


def test_correct_stale_source_label_guards() -> None:
    # Quarters agree — nothing stale, even when the years differ.
    assert (
        _correct_stale_source_label(
            "Earnings release Q3 FY2025",
            "Earnings release Q3 FY2025",
            "Q3",
        )
        is None
    )
    # Fiscal years disagree — the Feb-year-end offset-convention
    # question, not a fossil; leave the label alone.
    assert (
        _correct_stale_source_label(
            "Earnings release Q1 FY2024",
            "Earnings release Q3 FY2025",
            "Q3",
        )
        is None
    )
    # Live quarter does not match the row's own fiscal quarter — the
    # stored label is not the odd one out (e.g. a row whose own
    # fiscal_period is suspect).
    assert (
        _correct_stale_source_label(
            "Earnings release Q1 FY2024",
            "Earnings release Q3 FY2024",
            "Q2",
        )
        is None
    )
    # Unparseable or missing inputs never correct.
    assert (
        _correct_stale_source_label(
            "Earnings release", "Earnings release Q3 FY2024", "Q3"
        )
        is None
    )
    assert (
        _correct_stale_source_label(
            "Earnings release Q1 FY2024", None, "Q3"
        )
        is None
    )
    assert (
        _correct_stale_source_label(
            None, "Earnings release Q3 FY2024", "Q3"
        )
        is None
    )
    assert (
        _correct_stale_source_label(
            "Earnings release Q1 FY2024",
            "Earnings release Q3 FY2024",
            None,
        )
        is None
    )


def test_enrich_corrects_stale_label_while_refilling(session: Session) -> None:
    # The NFLX fossil shape: highlights present with a "Q1" label, guidance
    # blank so the backfill re-fetches the period anyway. The label must
    # correct to the live quarter while the highlights stay untouched and
    # the guidance fills.
    cik = "0000320193"
    session.add(_company(cik=cik))
    row = _row(
        cik=cik,
        period_end=dt.date(2025, 9, 28),
        fiscal_year=2025,
        fiscal_period="Q3",
        revenue=40_100,
    )
    row.press_release_highlights = "existing highlights"
    row.press_release_source = "Earnings release Q1 FY2025"
    session.add(row)
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    p1, p2, p3, _ = _enrich_mocks(
        mock_edgar, [_er_period(period_end=dt.date(2025, 9, 28))]
    )
    try:
        svc = FinancialsService(edgar_client=mock_edgar, session=session)
        svc.enrich_company("AAPL", session=session)
    finally:
        p1.stop()
        p2.stop()
        p3.stop()

    session.refresh(row)
    assert row.press_release_highlights == "existing highlights"
    assert row.press_release_source == "Earnings release Q3 FY2025"
    # The row was visited (guidance blank) and the exhibit re-read — the
    # fixture carries no guidance to extract, so the field stays blank
    # while the label corrects.
    assert mock_edgar.fetch_text.called


def test_enrich_does_not_correct_when_live_disagrees_with_row(
    session: Session,
) -> None:
    # Live says Q3 but the row's own fiscal quarter is Q2: the stored
    # label is not provably stale, so it stays exactly as stored.
    cik = "0000320193"
    session.add(_company(cik=cik))
    row = _row(
        cik=cik,
        period_end=dt.date(2025, 9, 28),
        fiscal_year=2025,
        fiscal_period="Q2",
        revenue=40_100,
    )
    row.press_release_highlights = "existing highlights"
    row.press_release_source = "Earnings release Q1 FY2025"
    session.add(row)
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    p1, p2, p3, _ = _enrich_mocks(
        mock_edgar, [_er_period(period_end=dt.date(2025, 9, 28))]
    )
    try:
        svc = FinancialsService(edgar_client=mock_edgar, session=session)
        svc.enrich_company("AAPL", session=session)
    finally:
        p1.stop()
        p2.stop()
        p3.stop()

    session.refresh(row)
    assert row.press_release_highlights == "existing highlights"
    assert row.press_release_source == "Earnings release Q1 FY2025"
