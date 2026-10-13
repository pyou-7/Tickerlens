from __future__ import annotations

import datetime as dt
import json
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from tickerlens.models.base import Base
from tickerlens.models.company import Company
from tickerlens.models.quarterly_financial import QuarterlyFinancial
from tickerlens.services.financials import (
    CompanyNotFoundError,
    FinancialsService,
    _build_quarterly_period,
    _build_yearly_period,
    _compute_qoq,
    _compute_kpi_yoy,
    _compute_ttm,
    _compute_yoy,
    _pct_change,
    KPISnapshot,
)


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    return factory()


def _row(
    *,
    cik: str = "0000320193",
    period_end: dt.date,
    fiscal_year: int,
    fiscal_period: str,
    revenue: float | None = None,
    net_income: float | None = None,
    eps_basic: float | None = None,
    eps_diluted: float | None = None,
    free_cash_flow: float | None = None,
    total_assets: float | None = None,
    total_liabilities: float | None = None,
    total_equity: float | None = None,
    cash_and_equivalents: float | None = None,
    redeemable_nci: float | None = None,
) -> QuarterlyFinancial:
    r = QuarterlyFinancial()
    r.cik = cik
    r.period_end = period_end
    r.fiscal_year = fiscal_year
    r.fiscal_period = fiscal_period
    r.revenue = revenue
    r.net_income = net_income
    r.eps_basic = eps_basic
    r.eps_diluted = eps_diluted
    r.free_cash_flow = free_cash_flow
    r.total_assets = total_assets
    r.total_liabilities = total_liabilities
    r.total_equity = total_equity
    r.cash_and_equivalents = cash_and_equivalents
    r.redeemable_nci = redeemable_nci
    r.updated_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    return r


def _company(cik: str = "0000320193", name: str = "Apple Inc.", ticker: str = "AAPL") -> Company:
    c = Company()
    c.cik = cik
    c.name = name
    c.ticker = ticker
    c.updated_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    return c


# ── _pct_change ───────────────────────────────────────────────────────────────

def test_pct_change_positive() -> None:
    assert _pct_change(110.0, 100.0) == pytest.approx(10.0)


def test_pct_change_negative() -> None:
    assert _pct_change(90.0, 100.0) == pytest.approx(-10.0)


def test_pct_change_none_inputs_return_none() -> None:
    assert _pct_change(None, 100.0) is None
    assert _pct_change(100.0, None) is None
    assert _pct_change(None, None) is None


def test_pct_change_zero_prior_returns_none() -> None:
    assert _pct_change(100.0, 0.0) is None


# ── _compute_ttm ─────────────────────────────────────────────────────────────

def test_compute_ttm_sums_four_quarters() -> None:
    rows = [
        _row(period_end=dt.date(2025, 12, 31), fiscal_year=2025, fiscal_period="Q4", revenue=100),
        _row(period_end=dt.date(2025, 9, 30),  fiscal_year=2025, fiscal_period="Q3", revenue=90),
        _row(period_end=dt.date(2025, 6, 30),  fiscal_year=2025, fiscal_period="Q2", revenue=80),
        _row(period_end=dt.date(2025, 3, 31),  fiscal_year=2025, fiscal_period="Q1", revenue=70),
    ]
    ttm = _compute_ttm(rows)
    assert ttm.revenue == pytest.approx(340.0)


def test_compute_ttm_ignores_nulls_in_partial_data() -> None:
    rows = [
        _row(period_end=dt.date(2025, 12, 31), fiscal_year=2025, fiscal_period="Q4",
             revenue=100, free_cash_flow=None),
        _row(period_end=dt.date(2025, 9, 30),  fiscal_year=2025, fiscal_period="Q3",
             revenue=90,  free_cash_flow=20),
    ]
    ttm = _compute_ttm(rows)
    assert ttm.revenue == pytest.approx(190.0)
    assert ttm.free_cash_flow == pytest.approx(20.0)


def test_compute_ttm_all_null_returns_none() -> None:
    rows = [_row(period_end=dt.date(2025, 12, 31), fiscal_year=2025, fiscal_period="Q4")]
    ttm = _compute_ttm(rows)
    assert ttm.revenue is None


# ── _compute_yoy ─────────────────────────────────────────────────────────────

def test_compute_yoy_matches_same_period_prior_year() -> None:
    latest = _row(period_end=dt.date(2025, 12, 31), fiscal_year=2025, fiscal_period="Q4",
                  revenue=110.0, net_income=55.0)
    prior = _row(period_end=dt.date(2024, 12, 31), fiscal_year=2024, fiscal_period="Q4",
                 revenue=100.0, net_income=50.0)
    yoy = _compute_yoy(latest, [latest, prior])
    assert yoy.revenue == pytest.approx(10.0)
    assert yoy.net_income == pytest.approx(10.0)


def test_compute_yoy_returns_empty_when_no_prior_year_data() -> None:
    latest = _row(period_end=dt.date(2025, 3, 31), fiscal_year=2025, fiscal_period="Q1",
                  revenue=100.0)
    yoy = _compute_yoy(latest, [latest])
    assert yoy.revenue is None


def test_compute_yoy_does_not_match_different_period() -> None:
    latest = _row(period_end=dt.date(2025, 12, 31), fiscal_year=2025, fiscal_period="Q4",
                  revenue=110.0)
    wrong_period = _row(period_end=dt.date(2024, 9, 30), fiscal_year=2024, fiscal_period="Q3",
                        revenue=100.0)
    yoy = _compute_yoy(latest, [latest, wrong_period])
    assert yoy.revenue is None


# ── get_overview ─────────────────────────────────────────────────────────────

def test_get_overview_raises_when_company_not_in_db(session: Session) -> None:
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = "0000320193"
    svc = FinancialsService(edgar_client=mock_edgar, session=session)
    with pytest.raises(CompanyNotFoundError):
        svc.get_overview("AAPL")


def test_get_overview_returns_correct_kpis(session: Session) -> None:
    cik = "0000320193"
    session.add(_company(cik=cik))
    rows = [
        _row(cik=cik, period_end=dt.date(2025, 12, 31), fiscal_year=2025, fiscal_period="Q4",
             revenue=124_300, net_income=36_330, eps_basic=2.41, eps_diluted=2.40, free_cash_flow=30_100),
        _row(cik=cik, period_end=dt.date(2025, 9, 28),  fiscal_year=2025, fiscal_period="Q3",
             revenue=94_930, net_income=23_630, eps_basic=1.57, eps_diluted=1.55, free_cash_flow=26_800),
        _row(cik=cik, period_end=dt.date(2025, 6, 28),  fiscal_year=2025, fiscal_period="Q2",
             revenue=85_777, net_income=21_448, eps_basic=1.43, eps_diluted=1.40, free_cash_flow=22_700),
        _row(cik=cik, period_end=dt.date(2025, 3, 29),  fiscal_year=2025, fiscal_period="Q1",
             revenue=95_359, net_income=24_780, eps_basic=1.65, eps_diluted=1.64, free_cash_flow=30_300),
        _row(cik=cik, period_end=dt.date(2024, 12, 31), fiscal_year=2024, fiscal_period="Q4",
             revenue=119_575, net_income=33_917, eps_basic=2.21, eps_diluted=2.18, free_cash_flow=26_600),
    ]
    for r in rows:
        session.add(r)
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    svc = FinancialsService(edgar_client=mock_edgar, session=session)
    overview = svc.get_overview("AAPL")

    assert overview.cik == cik
    assert overview.ticker == "AAPL"
    assert overview.latest_label == "Q4 FY2025"
    assert overview.latest_kpi.revenue == pytest.approx(124_300)
    assert overview.ttm_quarters == 4
    assert overview.ttm_kpi.revenue == pytest.approx(124_300 + 94_930 + 85_777 + 95_359)
    expected_yoy = (124_300 - 119_575) / 119_575 * 100
    assert overview.yoy.revenue == pytest.approx(expected_yoy)


# ── fetch_and_persist ─────────────────────────────────────────────────────────

_Q1_FACT = {
    "start": "2025-01-01", "end": "2025-03-31",
    "val": 95_000, "fy": 2025, "fp": "Q1",
    "form": "10-Q", "filed": "2025-05-01",
}

_MINIMAL_COMPANYFACTS: dict = {
    "facts": {
        "us-gaap": {
            # concept_facts raises KeyError when a metric has zero facts,
            # so every required metric needs at least one matching entry.
            "RevenueFromContractWithCustomerExcludingAssessedTax": {
                "units": {"USD": [{**_Q1_FACT, "val": 95_000}]}
            },
            "NetIncomeLoss": {
                "units": {"USD": [{**_Q1_FACT, "val": 24_780}]}
            },
            "EarningsPerShareBasic": {
                "units": {"USD/shares": [{**_Q1_FACT, "val": 1.65}]}
            },
            "EarningsPerShareDiluted": {
                "units": {"USD/shares": [{**_Q1_FACT, "val": 1.64}]}
            },
            "NetCashProvidedByUsedInOperatingActivities": {
                "units": {"USD": [{**_Q1_FACT, "val": 30_300}]}
            },
            "PaymentsToAcquirePropertyPlantAndEquipment": {
                "units": {"USD": [{**_Q1_FACT, "val": 800}]}
            },
        }
    }
}

_SUBMISSIONS = {
    "name": "Apple Inc.",
    "tickers": ["AAPL"],
    "fiscalYearEnd": "0928",
    "sic": "3674",
}


def test_fetch_and_persist_upserts_company_and_financials(session: Session) -> None:
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = "0000320193"
    mock_edgar.submissions.return_value = _SUBMISSIONS
    mock_edgar.companyfacts.return_value = _MINIMAL_COMPANYFACTS

    svc = FinancialsService(edgar_client=mock_edgar, session=session)
    rows = svc.fetch_and_persist("AAPL", periods=4, session=session)

    assert len(rows) >= 1

    company = session.get(Company, "0000320193")
    assert company is not None
    assert company.name == "Apple Inc."
    assert company.ticker == "AAPL"
    assert company.sic == "3674"

    financials = session.query(QuarterlyFinancial).all()
    assert any(f.revenue == pytest.approx(95_000) for f in financials)


def test_fetch_and_persist_defaults_to_eight_quarters() -> None:
    # Batch 44: ad-hoc seeds that omitted `periods` silently used the old
    # default of 4 and left thin tickers (LMT, ZTS, PYPL) with NULL freshness
    # markers in the DB. The persisting default must stay 8.
    import inspect

    sig = inspect.signature(FinancialsService.fetch_and_persist)
    assert sig.parameters["periods"].default == 8


# ── _compute_qoq ─────────────────────────────────────────────────────────────

def test_compute_qoq_calculates_change_from_prior_quarter() -> None:
    current = _row(period_end=dt.date(2025, 6, 30), fiscal_year=2025, fiscal_period="Q2",
                   revenue=100.0, eps_diluted=1.0)
    prior   = _row(period_end=dt.date(2025, 3, 31), fiscal_year=2025, fiscal_period="Q1",
                   revenue=80.0, eps_diluted=0.8)
    qoq = _compute_qoq(current, prior)
    assert qoq.revenue    == pytest.approx(25.0)
    assert qoq.eps_diluted == pytest.approx(25.0)


def test_compute_qoq_returns_empty_when_no_prior() -> None:
    current = _row(period_end=dt.date(2025, 3, 31), fiscal_year=2025, fiscal_period="Q1",
                   revenue=100.0)
    qoq = _compute_qoq(current, None)
    assert qoq.revenue is None


# ── _compute_kpi_yoy ─────────────────────────────────────────────────────────

def test_compute_kpi_yoy_computes_pct_change() -> None:
    current_kpi = KPISnapshot(revenue=110.0, net_income=55.0)
    prior_kpi   = KPISnapshot(revenue=100.0, net_income=50.0)
    yoy = _compute_kpi_yoy(current_kpi, prior_kpi)
    assert yoy.revenue    == pytest.approx(10.0)
    assert yoy.net_income == pytest.approx(10.0)


def test_compute_kpi_yoy_handles_null_values() -> None:
    current_kpi = KPISnapshot(revenue=None, net_income=55.0)
    prior_kpi   = KPISnapshot(revenue=100.0, net_income=None)
    yoy = _compute_kpi_yoy(current_kpi, prior_kpi)
    assert yoy.revenue    is None
    assert yoy.net_income is None


# ── _build_quarterly_period ───────────────────────────────────────────────────

def test_build_quarterly_period_selects_correct_row() -> None:
    rows = [
        _row(period_end=dt.date(2024, 9, 30), fiscal_year=2024, fiscal_period="Q3", revenue=91.0),
        _row(period_end=dt.date(2025, 3, 31), fiscal_year=2025, fiscal_period="Q1", revenue=95.0),
        _row(period_end=dt.date(2025, 6, 30), fiscal_year=2025, fiscal_period="Q2", revenue=100.0),
    ]
    data, label = _build_quarterly_period(rows, "Q1 FY2025", rows[-1])
    assert label == "Q1 FY2025"
    assert data.kpi.revenue == pytest.approx(95.0)
    assert data.fiscal_period == "Q1"
    assert data.fiscal_year == 2025


def test_build_quarterly_period_computes_yoy_and_qoq() -> None:
    q3_2024 = _row(period_end=dt.date(2024, 9, 30), fiscal_year=2024, fiscal_period="Q3", revenue=91.0)
    q3_2025 = _row(period_end=dt.date(2025, 9, 28), fiscal_year=2025, fiscal_period="Q3", revenue=100.0)
    q2_2025 = _row(period_end=dt.date(2025, 6, 30), fiscal_year=2025, fiscal_period="Q2", revenue=85.0)
    rows = [q3_2024, q2_2025, q3_2025]

    data, _ = _build_quarterly_period(rows, "Q3 FY2025", q3_2025)
    expected_yoy = (100.0 - 91.0) / 91.0 * 100
    assert data.yoy.revenue == pytest.approx(expected_yoy)
    # QoQ vs Q2 2025 (previous row)
    expected_qoq = (100.0 - 85.0) / 85.0 * 100
    assert data.qoq is not None
    assert data.qoq.revenue == pytest.approx(expected_qoq)


def test_build_quarterly_period_falls_back_to_latest_on_bad_label() -> None:
    rows = [
        _row(period_end=dt.date(2025, 3, 31), fiscal_year=2025, fiscal_period="Q1", revenue=95.0),
        _row(period_end=dt.date(2025, 6, 30), fiscal_year=2025, fiscal_period="Q2", revenue=100.0),
    ]
    data, label = _build_quarterly_period(rows, "INVALID", rows[-1])
    assert data.kpi.revenue == pytest.approx(100.0)   # latest
    assert label == "Q2 FY2025"


def test_build_quarterly_period_no_qoq_when_prior_row_is_not_adjacent_quarter() -> None:
    # DB has Q3 2023 and Q2 2025 — a big gap. QoQ should be None, not Q3 2023.
    rows = [
        _row(period_end=dt.date(2023, 9, 30), fiscal_year=2023, fiscal_period="Q3", revenue=88.0),
        _row(period_end=dt.date(2025, 6, 30), fiscal_year=2025, fiscal_period="Q2", revenue=100.0),
    ]
    data, _ = _build_quarterly_period(rows, "Q2 FY2025", rows[-1])
    assert data.qoq is not None
    assert data.qoq.revenue is None  # gap → _is_prior_quarter returns False → empty KPIChange


def test_build_quarterly_period_no_qoq_for_first_row() -> None:
    rows = [
        _row(period_end=dt.date(2023, 9, 30), fiscal_year=2023, fiscal_period="Q3", revenue=88.0),
        _row(period_end=dt.date(2025, 6, 30), fiscal_year=2025, fiscal_period="Q2", revenue=100.0),
    ]
    # Select earliest row — has no prior QoQ
    data, _ = _build_quarterly_period(rows, "Q3 FY2023", rows[-1])
    assert data.qoq is not None
    assert data.qoq.revenue is None   # prior is None → _compute_qoq returns empty KPIChange


# ── _build_yearly_period ─────────────────────────────────────────────────────

def test_build_yearly_period_sums_all_quarters_in_year() -> None:
    rows = [
        _row(period_end=dt.date(2024, 12, 31), fiscal_year=2024, fiscal_period="Q4", revenue=119.0),
        _row(period_end=dt.date(2025, 3, 31),  fiscal_year=2025, fiscal_period="Q1", revenue=95.0),
        _row(period_end=dt.date(2025, 6, 30),  fiscal_year=2025, fiscal_period="Q2", revenue=85.0),
        _row(period_end=dt.date(2025, 9, 28),  fiscal_year=2025, fiscal_period="Q3", revenue=94.0),
        _row(period_end=dt.date(2025, 12, 31), fiscal_year=2025, fiscal_period="Q4", revenue=124.0),
    ]
    data = _build_yearly_period(rows, selected_year=2025, default_year=2025)
    assert data.label == "FY2025"
    assert data.fiscal_period is None
    assert data.qoq is None
    assert data.kpi.revenue == pytest.approx(95.0 + 85.0 + 94.0 + 124.0)


def test_build_yearly_period_computes_yoy_vs_prior_year() -> None:
    rows = [
        _row(period_end=dt.date(2024, 3, 31),  fiscal_year=2024, fiscal_period="Q1", revenue=90.0),
        _row(period_end=dt.date(2024, 6, 30),  fiscal_year=2024, fiscal_period="Q2", revenue=80.0),
        _row(period_end=dt.date(2024, 9, 30),  fiscal_year=2024, fiscal_period="Q3", revenue=85.0),
        _row(period_end=dt.date(2024, 12, 31), fiscal_year=2024, fiscal_period="Q4", revenue=95.0),
        _row(period_end=dt.date(2025, 3, 31),  fiscal_year=2025, fiscal_period="Q1", revenue=95.0),
        _row(period_end=dt.date(2025, 6, 30),  fiscal_year=2025, fiscal_period="Q2", revenue=85.0),
        _row(period_end=dt.date(2025, 9, 30),  fiscal_year=2025, fiscal_period="Q3", revenue=90.0),
        _row(period_end=dt.date(2025, 12, 31), fiscal_year=2025, fiscal_period="Q4", revenue=100.0),
    ]
    data = _build_yearly_period(rows, selected_year=2025, default_year=2025)
    prior_rev = 90.0 + 80.0 + 85.0 + 95.0
    current_rev = 95.0 + 85.0 + 90.0 + 100.0
    expected_yoy = (current_rev - prior_rev) / prior_rev * 100
    assert data.yoy.revenue == pytest.approx(expected_yoy)


def test_build_yearly_period_falls_back_to_default_when_year_missing() -> None:
    rows = [
        _row(period_end=dt.date(2025, 6, 30), fiscal_year=2025, fiscal_period="Q2", revenue=85.0),
    ]
    data = _build_yearly_period(rows, selected_year=2099, default_year=2025)
    assert data.fiscal_year == 2025


# ── get_detail ────────────────────────────────────────────────────────────────

def test_get_detail_returns_correct_quarterly_context(session: Session) -> None:
    cik = "0000320193"
    session.add(_company(cik=cik))
    rows = [
        _row(cik=cik, period_end=dt.date(2024, 9, 30), fiscal_year=2024, fiscal_period="Q3",
             revenue=91_000, net_income=21_000, eps_basic=1.40, eps_diluted=1.38, free_cash_flow=20_000),
        _row(cik=cik, period_end=dt.date(2024, 12, 31), fiscal_year=2024, fiscal_period="Q4",
             revenue=119_575, net_income=33_917, eps_basic=2.21, eps_diluted=2.18, free_cash_flow=26_600),
        _row(cik=cik, period_end=dt.date(2025, 3, 31), fiscal_year=2025, fiscal_period="Q1",
             revenue=95_359, net_income=24_780, eps_basic=1.65, eps_diluted=1.64, free_cash_flow=30_300),
        _row(cik=cik, period_end=dt.date(2025, 6, 30), fiscal_year=2025, fiscal_period="Q2",
             revenue=85_777, net_income=21_448, eps_basic=1.43, eps_diluted=1.40, free_cash_flow=22_700),
        _row(cik=cik, period_end=dt.date(2025, 9, 28), fiscal_year=2025, fiscal_period="Q3",
             revenue=94_930, net_income=23_630, eps_basic=1.57, eps_diluted=1.55, free_cash_flow=26_800),
    ]
    for r in rows:
        session.add(r)
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    svc = FinancialsService(edgar_client=mock_edgar, session=session)

    ctx = svc.get_detail("AAPL", granularity="quarterly", selected_quarter="Q3 FY2025")

    assert ctx.granularity == "quarterly"
    assert ctx.selected_quarter == "Q3 FY2025"
    assert ctx.current.label == "Q3 FY2025"
    assert ctx.current.kpi.revenue == pytest.approx(94_930)
    # YoY vs Q3 2024
    expected_yoy = (94_930 - 91_000) / 91_000 * 100
    assert ctx.current.yoy.revenue == pytest.approx(expected_yoy)
    # QoQ vs Q2 2025
    expected_qoq = (94_930 - 85_777) / 85_777 * 100
    assert ctx.current.qoq is not None
    assert ctx.current.qoq.revenue == pytest.approx(expected_qoq)


def test_get_detail_exposes_balance_sheet_with_yoy(session: Session) -> None:
    cik = "0000320193"
    session.add(_company(cik=cik))
    rows = [
        _row(cik=cik, period_end=dt.date(2024, 9, 28), fiscal_year=2024, fiscal_period="Q3",
             revenue=94_000, total_assets=352_000, total_liabilities=290_000,
             total_equity=62_000, cash_and_equivalents=29_000),
        _row(cik=cik, period_end=dt.date(2025, 6, 28), fiscal_year=2025, fiscal_period="Q2",
             revenue=85_000, total_assets=331_000, total_liabilities=265_000,
             total_equity=66_000, cash_and_equivalents=28_000),
        _row(cik=cik, period_end=dt.date(2025, 9, 28), fiscal_year=2025, fiscal_period="Q3",
             revenue=94_930, total_assets=364_000, total_liabilities=308_000,
             total_equity=56_000, cash_and_equivalents=30_000),
    ]
    for r in rows:
        session.add(r)
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    svc = FinancialsService(edgar_client=mock_edgar, session=session)

    ctx = svc.get_detail("AAPL", granularity="quarterly", selected_quarter="Q3 FY2025")

    bs = ctx.current.balance_sheet
    assert bs.total_assets == pytest.approx(364_000)
    assert bs.total_equity == pytest.approx(56_000)
    # YoY vs Q3 2024
    expected_yoy = (364_000 - 352_000) / 352_000 * 100
    assert ctx.current.balance_sheet_yoy.total_assets == pytest.approx(expected_yoy)
    # QoQ vs Q2 2025
    assert ctx.current.balance_sheet_qoq is not None
    expected_qoq = (364_000 - 331_000) / 331_000 * 100
    assert ctx.current.balance_sheet_qoq.total_assets == pytest.approx(expected_qoq)


def test_get_detail_returns_correct_yearly_context(session: Session) -> None:
    cik = "0000320193"
    session.add(_company(cik=cik))
    rows = [
        _row(cik=cik, period_end=dt.date(2024, 3, 31), fiscal_year=2024, fiscal_period="Q1", revenue=90_000),
        _row(cik=cik, period_end=dt.date(2025, 3, 31), fiscal_year=2025, fiscal_period="Q1", revenue=95_000),
        _row(cik=cik, period_end=dt.date(2025, 6, 30), fiscal_year=2025, fiscal_period="Q2", revenue=85_000),
    ]
    for r in rows:
        session.add(r)
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    svc = FinancialsService(edgar_client=mock_edgar, session=session)

    ctx = svc.get_detail("AAPL", granularity="yearly", selected_year=2025)

    assert ctx.granularity == "yearly"
    assert ctx.selected_year == 2025
    assert ctx.current.label == "FY2025"
    assert ctx.current.fiscal_period is None
    assert ctx.current.qoq is None
    assert ctx.current.kpi.revenue == pytest.approx(95_000 + 85_000)


def test_get_detail_defaults_to_latest_quarter(session: Session) -> None:
    cik = "0000320193"
    session.add(_company(cik=cik))
    session.add(_row(cik=cik, period_end=dt.date(2025, 9, 28), fiscal_year=2025, fiscal_period="Q3",
                     revenue=94_930))
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    svc = FinancialsService(edgar_client=mock_edgar, session=session)

    ctx = svc.get_detail("AAPL")
    assert ctx.current.label == "Q3 FY2025"


def test_get_detail_raises_when_no_data(session: Session) -> None:
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = "0000320193"
    svc = FinancialsService(edgar_client=mock_edgar, session=session)
    with pytest.raises(CompanyNotFoundError):
        svc.get_detail("AAPL")


def test_get_detail_chart_data_is_chronological(session: Session) -> None:
    cik = "0000320193"
    session.add(_company(cik=cik))
    rows = [
        _row(cik=cik, period_end=dt.date(2024, 3, 31), fiscal_year=2024, fiscal_period="Q1", revenue=90_000),
        _row(cik=cik, period_end=dt.date(2024, 6, 30), fiscal_year=2024, fiscal_period="Q2", revenue=80_000),
        _row(cik=cik, period_end=dt.date(2025, 3, 31), fiscal_year=2025, fiscal_period="Q1", revenue=95_000),
    ]
    for r in rows:
        session.add(r)
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    svc = FinancialsService(edgar_client=mock_edgar, session=session)

    ctx = svc.get_detail("AAPL")
    assert ctx.chart_labels == ["Q1 FY2024", "Q2 FY2024", "Q1 FY2025"]
    assert ctx.chart_revenue == [pytest.approx(90_000), pytest.approx(80_000), pytest.approx(95_000)]


def test_get_detail_quarter_options_most_recent_first(session: Session) -> None:
    cik = "0000320193"
    session.add(_company(cik=cik))
    rows = [
        _row(cik=cik, period_end=dt.date(2024, 3, 31), fiscal_year=2024, fiscal_period="Q1", revenue=90_000),
        _row(cik=cik, period_end=dt.date(2025, 6, 30), fiscal_year=2025, fiscal_period="Q2", revenue=85_000),
    ]
    for r in rows:
        session.add(r)
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    svc = FinancialsService(edgar_client=mock_edgar, session=session)

    ctx = svc.get_detail("AAPL")
    assert ctx.quarter_options[0] == "Q2 FY2025"
    assert ctx.quarter_options[-1] == "Q1 FY2024"


def test_fetch_and_persist_upsert_is_idempotent(session: Session) -> None:
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = "0000320193"
    mock_edgar.submissions.return_value = _SUBMISSIONS
    mock_edgar.companyfacts.return_value = _MINIMAL_COMPANYFACTS

    svc = FinancialsService(edgar_client=mock_edgar, session=session)
    svc.fetch_and_persist("AAPL", periods=4, session=session)
    svc.fetch_and_persist("AAPL", periods=4, session=session)  # must not raise or duplicate

    assert session.query(QuarterlyFinancial).count() == 1


# ── press-release highlights ─────────────────────────────────────────────────

from unittest.mock import patch  # noqa: E402

from tickerlens.services.ir_download import EarningsPeriod  # noqa: E402


def _er_period(*, period_end: dt.date, label: str = "Q3 FY2025") -> EarningsPeriod:
    return EarningsPeriod(
        quarter_label=label,
        fiscal_year=label.rsplit(" FY", 1)[1],
        fp="Q3",
        fy=int(label.rsplit(" FY", 1)[1]),
        period_end=period_end,
        sec_form="10-Q",
        sec_accession="0000320193-25-000010",
        sec_doc="aapl-20250928.htm",
        er_accession="0000320193-25-000011",
        er_doc="ex991.htm",
    )


def _release_html_fixture() -> str:
    lede = (
        "CUPERTINO, California — Acme Corp today announced financial results for its "
        "fiscal 2025 third quarter ended September 28, 2025. The Company posted quarterly "
        "revenue of 40.1 billion dollars, up 5 percent year over year."
    )
    body = ("Additional operating detail and management commentary. " * 30) + lede
    bullets = "".join(
        f"<li>Highlight bullet number {i} with year-over-year comparison detail.</li>"
        for i in range(4)
    )
    return (
        "<html><head><title>EX-99.1</title></head><body>"
        "<h1>Acme Corp Reports Third Quarter 2025 Results</h1>"
        f"<p>{body}</p><h2>Financial Highlights</h2><ul>{bullets}</ul>"
        "<h2>Forward-Looking Statements</h2><p>Safe harbor language.</p>"
        "</body></html>"
    )


def _enrich_mocks(mock_edgar: MagicMock, periods: list[EarningsPeriod]):
    """Patch network-touching helpers; returns the discover mock for assertions."""
    p1 = patch("tickerlens.services.financials.get_quote")
    p2 = patch("tickerlens.services.financials.get_description", return_value="A description")
    p3 = patch(
        "tickerlens.services.financials.discover_earnings_filings", return_value=periods
    )
    q = p1.start()
    q.return_value = MagicMock(last_price=100.0, market_cap=1_000_000.0)
    p2.start()
    discover_mock = p3.start()
    mock_edgar.fetch_text.return_value = _release_html_fixture()
    return p1, p2, p3, discover_mock


def test_enrich_company_fills_highlights_for_matched_period(session: Session) -> None:
    cik = "0000320193"
    session.add(_company(cik=cik))
    matched = _row(cik=cik, period_end=dt.date(2025, 9, 28), fiscal_year=2025,
                   fiscal_period="Q3", revenue=40_100)
    unmatched = _row(cik=cik, period_end=dt.date(2025, 6, 28), fiscal_year=2025,
                     fiscal_period="Q2", revenue=38_000)
    session.add_all([matched, unmatched])
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    p1, p2, p3, _ = _enrich_mocks(mock_edgar, [_er_period(period_end=dt.date(2025, 9, 28))])
    try:
        svc = FinancialsService(edgar_client=mock_edgar, session=session)
        svc.enrich_company("AAPL", session=session)
    finally:
        p1.stop(); p2.stop(); p3.stop()

    session.refresh(matched)
    session.refresh(unmatched)
    assert matched.press_release_highlights is not None
    assert "Acme Corp Reports Third Quarter 2025 Results" in matched.press_release_highlights
    assert matched.press_release_source == "Earnings release Q3 FY2025"
    assert unmatched.press_release_highlights is None
    assert unmatched.press_release_source is None


def test_enrich_company_does_not_overwrite_existing_highlights(session: Session) -> None:
    cik = "0000320193"
    session.add(_company(cik=cik))
    row = _row(cik=cik, period_end=dt.date(2025, 9, 28), fiscal_year=2025,
               fiscal_period="Q3", revenue=40_100)
    row.press_release_highlights = "existing highlights"
    row.press_release_source = "Earnings release Q3 FY2025"
    row.management_guidance = "existing guidance"
    row.management_guidance_source = "8-K guidance, Q3 FY2025"
    row.transcript_excerpts = "existing remarks"
    row.transcript_source = "8-K remarks, Q3 FY2025"
    session.add(row)
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    p1, p2, p3, _ = _enrich_mocks(mock_edgar, [_er_period(period_end=dt.date(2025, 9, 28))])
    try:
        svc = FinancialsService(edgar_client=mock_edgar, session=session)
        svc.enrich_company("AAPL", session=session)
    finally:
        p1.stop(); p2.stop(); p3.stop()

    session.refresh(row)
    assert row.press_release_highlights == "existing highlights"
    assert row.management_guidance == "existing guidance"
    assert row.transcript_excerpts == "existing remarks"
    mock_edgar.fetch_text.assert_not_called()


def test_enrich_company_refills_missing_guidance_without_overwriting(session: Session) -> None:
    """A row with highlights but no guidance/transcript is revisited: the
    missing fields are filled from the exhibit while existing values stay."""
    cik = "0000320193"
    session.add(_company(cik=cik))
    row = _row(cik=cik, period_end=dt.date(2025, 9, 28), fiscal_year=2025,
               fiscal_period="Q3", revenue=40_100)
    row.press_release_highlights = "existing highlights"
    row.press_release_source = "Earnings release Q3 FY2025"
    session.add(row)
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    p1, p2, p3, _ = _enrich_mocks(mock_edgar, [_er_period(period_end=dt.date(2025, 9, 28))])
    try:
        svc = FinancialsService(edgar_client=mock_edgar, session=session)
        svc.enrich_company("AAPL", session=session)
    finally:
        p1.stop(); p2.stop(); p3.stop()

    session.refresh(row)
    assert row.press_release_highlights == "existing highlights"
    assert mock_edgar.fetch_text.called  # exhibit re-read for the missing fields


def test_enrich_company_tolerates_no_matched_8k(session: Session) -> None:
    cik = "0000320193"
    session.add(_company(cik=cik))
    row = _row(cik=cik, period_end=dt.date(2025, 9, 28), fiscal_year=2025,
               fiscal_period="Q3", revenue=40_100)
    session.add(row)
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    p1, p2, p3, _ = _enrich_mocks(mock_edgar, [])  # no earnings releases discovered
    try:
        svc = FinancialsService(edgar_client=mock_edgar, session=session)
        svc.enrich_company("AAPL", session=session)  # must not raise
    finally:
        p1.stop(); p2.stop(); p3.stop()

    session.refresh(row)
    assert row.press_release_highlights is None


def test_get_detail_returns_highlights_for_selected_quarter(session: Session) -> None:
    cik = "0000320193"
    session.add(_company(cik=cik))
    q3 = _row(cik=cik, period_end=dt.date(2025, 9, 28), fiscal_year=2025,
              fiscal_period="Q3", revenue=40_100)
    q3.press_release_highlights = "Q3 highlights"
    q3.press_release_source = "Earnings release Q3 FY2025"
    q4 = _row(cik=cik, period_end=dt.date(2025, 12, 31), fiscal_year=2025,
              fiscal_period="Q4", revenue=50_200)
    q4.press_release_highlights = "Q4 highlights"
    q4.press_release_source = "Earnings release Q4 FY2025"
    q3.management_guidance = "Q3 guidance targets"
    q3.management_guidance_source = "8-K guidance, Q3 FY2025"
    q3.transcript_excerpts = "• Executive remarks from CEO"
    q3.transcript_source = "8-K remarks, Q3 FY2025"
    session.add_all([q3, q4])
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    svc = FinancialsService(edgar_client=mock_edgar, session=session)

    ctx = svc.get_detail("AAPL", selected_quarter="Q3 FY2025")
    assert ctx.press_release_highlights == "Q3 highlights"
    assert ctx.press_release_source == "Earnings release Q3 FY2025"
    assert ctx.management_guidance == "Q3 guidance targets"
    assert ctx.management_guidance_source == "8-K guidance, Q3 FY2025"
    assert ctx.transcript_excerpts == "• Executive remarks from CEO"
    assert ctx.transcript_source == "8-K remarks, Q3 FY2025"

    ctx_latest = svc.get_detail("AAPL")  # defaults to latest = Q4
    assert ctx_latest.press_release_highlights == "Q4 highlights"


def test_get_detail_yearly_uses_q4_highlights(session: Session) -> None:
    cik = "0000320193"
    session.add(_company(cik=cik))
    q3 = _row(cik=cik, period_end=dt.date(2025, 9, 28), fiscal_year=2025,
              fiscal_period="Q3", revenue=40_100)
    q3.press_release_highlights = "Q3 highlights"
    q4 = _row(cik=cik, period_end=dt.date(2025, 12, 31), fiscal_year=2025,
              fiscal_period="Q4", revenue=50_200)
    q4.press_release_highlights = "Q4 annual highlights"
    q4.press_release_source = "Earnings release Q4 FY2025"
    session.add_all([q3, q4])
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    svc = FinancialsService(edgar_client=mock_edgar, session=session)

    ctx = svc.get_detail("AAPL", granularity="yearly", selected_year=2025)
    assert ctx.press_release_highlights == "Q4 annual highlights"
    assert ctx.press_release_source == "Earnings release Q4 FY2025"


def test_get_detail_backfills_missing_disclosures(session: Session) -> None:
    """Companies fetched before the 8-K disclosure feature shipped have NULL
    highlights; the first detail view must fill them lazily (self-healing)."""
    cik = "0000320193"
    session.add(_company(cik=cik))
    q3 = _row(cik=cik, period_end=dt.date(2025, 9, 28), fiscal_year=2025,
              fiscal_period="Q3", revenue=40_100)
    session.add(q3)
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    p1, p2, p3, discover_mock = _enrich_mocks(
        mock_edgar, [_er_period(period_end=dt.date(2025, 9, 28))]
    )
    try:
        svc = FinancialsService(edgar_client=mock_edgar, session=session)
        ctx = svc.get_detail("AAPL", selected_quarter="Q3 FY2025")
    finally:
        p1.stop(); p2.stop(); p3.stop()

    assert discover_mock.called
    assert ctx.press_release_highlights is not None
    assert "Acme Corp Reports Third Quarter 2025 Results" in ctx.press_release_highlights
    assert ctx.press_release_source == "Earnings release Q3 FY2025"
    # The caller's session owns the transaction (as the route does) — commit
    # and the backfilled values must persist.
    session.commit()
    session.refresh(q3)
    assert q3.press_release_highlights == ctx.press_release_highlights


def test_get_detail_backfill_never_raises_on_discovery_failure(session: Session) -> None:
    """A transient SEC failure during the lazy backfill must not break the
    detail page — disclosures stay unavailable and the page still renders."""
    cik = "0000320193"
    session.add(_company(cik=cik))
    q3 = _row(cik=cik, period_end=dt.date(2025, 9, 28), fiscal_year=2025,
              fiscal_period="Q3", revenue=40_100)
    session.add(q3)
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    svc = FinancialsService(edgar_client=mock_edgar, session=session)

    with patch(
        "tickerlens.services.financials.discover_earnings_filings",
        side_effect=RuntimeError("SEC unreachable"),
    ):
        ctx = svc.get_detail("AAPL", selected_quarter="Q3 FY2025")

    assert ctx.press_release_highlights is None
    assert ctx.current.kpi.revenue == pytest.approx(40_100)


def test_enrich_company_keeps_price_on_quote_failure(session: Session) -> None:
    """A transient Yahoo failure (quote fields None) must not wipe a
    previously-good last_price / market_cap — same never-wipe policy as
    risk factors and press-release highlights."""
    from unittest.mock import patch

    cik = "0000320193"
    company = _company(cik=cik)
    company.last_price = 341.07
    company.market_cap = 5_000_000_000_000.0
    session.add(company)
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    svc = FinancialsService(edgar_client=mock_edgar, session=session)

    with patch("tickerlens.services.financials.get_quote") as q, \
         patch("tickerlens.services.financials.get_description", return_value="desc"), \
         patch("tickerlens.services.financials.discover_earnings_filings", return_value=[]):
        q.return_value = MagicMock(last_price=None, market_cap=None)
        svc.enrich_company("AAPL", session=session)

    session.refresh(company)
    assert company.last_price == pytest.approx(341.07)
    assert company.market_cap == pytest.approx(5_000_000_000_000.0)


def test_enrich_company_updates_price_on_quote_success(session: Session) -> None:
    from unittest.mock import patch

    cik = "0000320193"
    company = _company(cik=cik)
    company.last_price = 300.0
    session.add(company)
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    svc = FinancialsService(edgar_client=mock_edgar, session=session)

    with patch("tickerlens.services.financials.get_quote") as q, \
         patch("tickerlens.services.financials.get_description", return_value="desc"), \
         patch("tickerlens.services.financials.discover_earnings_filings", return_value=[]):
        q.return_value = MagicMock(last_price=341.07, market_cap=5_100_000_000_000.0)
        svc.enrich_company("AAPL", session=session)

    session.refresh(company)
    assert company.last_price == pytest.approx(341.07)
    assert company.market_cap == pytest.approx(5_100_000_000_000.0)


def _fy_rows(cik: str, year: int, quarters: int):
    months = [3, 6, 9, 12]
    return [
        _row(cik=cik, period_end=dt.date(year, months[i], 28), fiscal_year=year,
             fiscal_period=f"Q{i + 1}", revenue=100.0 * (i + 1))
        for i in range(quarters)
    ]


def test_yearly_yoy_empty_when_prior_year_incomplete(session: Session) -> None:
    """YoY must not compare a full-year sum against a partial prior year."""
    cik = "0000320193"
    session.add(_company(cik=cik))
    session.add_all(_fy_rows(cik, 2025, 4) + _fy_rows(cik, 2024, 1))
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    svc = FinancialsService(edgar_client=mock_edgar, session=session)

    ctx = svc.get_detail("AAPL", granularity="yearly", selected_year=2025)
    assert ctx.current.kpi.revenue == pytest.approx(1000.0)  # 100+200+300+400
    assert ctx.current.yoy.revenue is None


def test_yearly_yoy_computed_when_both_years_complete(session: Session) -> None:
    cik = "0000320193"
    session.add(_company(cik=cik))
    session.add_all(_fy_rows(cik, 2025, 4) + _fy_rows(cik, 2024, 4))
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    svc = FinancialsService(edgar_client=mock_edgar, session=session)

    ctx = svc.get_detail("AAPL", granularity="yearly", selected_year=2025)
    assert ctx.current.yoy.revenue == pytest.approx(0.0)  # identical sums


# ── valuation history & signal change (PRD §4.11) ─────────────────────────────

def _seed_growing_company(session: Session, cik: str = "0000320193") -> None:
    """8 quarters: TTM diluted EPS 20.0 vs prior TTM 16.0 → +25% growth."""
    c = _company(cik=cik)
    c.last_price = 100.0
    c.market_cap = 1_000_000_000.0
    session.add(c)
    ends = [
        (dt.date(2026, 6, 30), 2026, "Q2", 5.0),
        (dt.date(2026, 3, 31), 2026, "Q1", 5.0),
        (dt.date(2025, 12, 31), 2025, "Q4", 5.0),
        (dt.date(2025, 9, 30), 2025, "Q3", 5.0),
        (dt.date(2025, 6, 30), 2025, "Q2", 4.0),
        (dt.date(2025, 3, 31), 2025, "Q1", 4.0),
        (dt.date(2024, 12, 31), 2024, "Q4", 4.0),
        (dt.date(2024, 9, 30), 2024, "Q3", 4.0),
    ]
    for period_end, fy, fp, eps in ends:
        session.add(_row(cik=cik, period_end=period_end, fiscal_year=fy,
                         fiscal_period=fp, eps_diluted=eps, revenue=100.0))
    session.commit()


def _svc_with_mock(session: Session, cik: str = "0000320193") -> FinancialsService:
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    return FinancialsService(edgar_client=mock_edgar, session=session)


def test_record_valuation_snapshot_writes_todays_signal(session: Session) -> None:
    from tickerlens.models.valuation_history import ValuationHistory

    _seed_growing_company(session)
    snap = _svc_with_mock(session).record_valuation_snapshot("AAPL")

    assert snap.signal == "Strong Buy"
    assert snap.method == "peg"
    assert snap.as_of == dt.date.today()
    assert snap.price == pytest.approx(100.0)
    # Batch 12 rate guardrail: 40x P/E -> 37.0x at the 4.5% default 10y yield.
    assert snap.target_price == pytest.approx(740.7, abs=0.1)
    assert snap.upside_pct == pytest.approx(640.7, abs=0.1)
    rows = session.execute(select(ValuationHistory)).scalars().all()
    assert len(rows) == 1


def test_record_valuation_snapshot_upserts_same_day(session: Session) -> None:
    from tickerlens.models.valuation_history import ValuationHistory

    _seed_growing_company(session)
    svc = _svc_with_mock(session)
    svc.record_valuation_snapshot("AAPL")
    # Refresh later the same day with a new quote → updates, not duplicates.
    session.query(Company).first().last_price = 200.0
    session.commit()
    snap = svc.record_valuation_snapshot("AAPL")

    rows = session.execute(select(ValuationHistory)).scalars().all()
    assert len(rows) == 1
    assert snap.price == pytest.approx(200.0)
    # Batch 12 rate guardrail: target 740.74 vs 200 price.
    assert snap.upside_pct == pytest.approx(270.4, abs=0.1)


def test_get_signal_change_detects_flip(session: Session) -> None:
    from tickerlens.models.valuation_history import ValuationHistory

    _seed_growing_company(session)
    yesterday = dt.date.today() - dt.timedelta(days=1)
    session.add(ValuationHistory(cik="0000320193", as_of=yesterday, price=90.0,
                                target_price=95.0, upside_pct=5.6,
                                signal="Hold", method="peg"))
    session.commit()
    svc = _svc_with_mock(session)
    svc.record_valuation_snapshot("AAPL")

    change = svc.get_signal_change("AAPL")
    assert change is not None
    assert change.previous_signal == "Hold"
    assert change.previous_date == yesterday
    assert change.current_signal == "Strong Buy"


def test_get_signal_change_none_when_unchanged(session: Session) -> None:
    from tickerlens.models.valuation_history import ValuationHistory

    _seed_growing_company(session)
    session.add(ValuationHistory(cik="0000320193",
                                as_of=dt.date.today() - dt.timedelta(days=1),
                                price=100.0, target_price=750.0, upside_pct=650.0,
                                signal="Strong Buy", method="peg"))
    session.commit()
    svc = _svc_with_mock(session)
    svc.record_valuation_snapshot("AAPL")

    assert svc.get_signal_change("AAPL") is None


def test_get_signal_change_none_without_history(session: Session) -> None:
    _seed_growing_company(session)
    assert _svc_with_mock(session).get_signal_change("AAPL") is None


# ── full-history ZIP (PRD §4.8, first slice) ────────────────────────────────────

def test_get_history_zip_entries_one_csv_per_quarter(session: Session) -> None:
    from tickerlens.services.financials import build_history_zip

    session.add(_company())
    session.add(_row(period_end=dt.date(2025, 6, 30), fiscal_year=2025,
                     fiscal_period="Q3", revenue=100.0, net_income=10.0))
    session.add(_row(period_end=dt.date(2025, 9, 30), fiscal_year=2025,
                     fiscal_period="Q4", revenue=120.0, net_income=12.0))
    session.commit()

    ticker, entries = _svc_with_mock(session).get_history_zip_entries("AAPL")

    assert ticker == "AAPL"
    assert [arc for arc, _ in entries] == [
        "AAPL/AAPL_Q3-FY2025.csv",
        "AAPL/AAPL_Q4-FY2025.csv",
    ]
    assert "# Period,Q3 FY2025" in entries[0][1]
    assert "Revenue,100.0" in entries[0][1]
    assert "# Period,Q4 FY2025" in entries[1][1]
    # The Q4 file carries YoY against Q4 of the prior year — none here, so empty.
    assert "None" not in entries[1][1]

    payload = build_history_zip(ticker, entries)
    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        assert sorted(zf.namelist()) == [
            "AAPL/AAPL_Q3-FY2025.csv",
            "AAPL/AAPL_Q4-FY2025.csv",
        ]
        assert zf.read("AAPL/AAPL_Q4-FY2025.csv").decode().startswith("# Company,Apple Inc. (AAPL)")


def test_get_history_zip_entries_unknown_ticker_raises(session: Session) -> None:
    with pytest.raises(CompanyNotFoundError):
        _svc_with_mock(session).get_history_zip_entries("ZZZZ")


# ── watchlist quote refresh (PRD §4.6, slice 2) ─────────────────────────────────

def test_refresh_watchlist_quotes_updates_price_never_wipes(session: Session, monkeypatch) -> None:
    from tickerlens.models.watchlist import WatchlistEntry

    session.add(_company())
    session.add(WatchlistEntry(cik="0000320193"))
    session.commit()

    from tickerlens.services import financials as fin_mod

    class _Quote:
        last_price = 400.0
        market_cap = 6e12

    monkeypatch.setattr(fin_mod, "cached_quote", lambda ticker: _Quote())
    svc = _svc_with_mock(session)
    result = svc.refresh_watchlist_quotes()

    assert result == {"updated": 1, "failed": 0}
    company = session.get(Company, "0000320193")
    assert company.last_price == 400.0
    assert company.market_cap == 6e12


def test_refresh_watchlist_quotes_counts_failures(session: Session, monkeypatch) -> None:
    from tickerlens.models.watchlist import WatchlistEntry

    session.add(_company())
    session.add(WatchlistEntry(cik="0000320193"))
    session.commit()

    from tickerlens.services import financials as fin_mod

    def _boom(ticker: str):
        raise RuntimeError("yahoo down")

    monkeypatch.setattr(fin_mod, "cached_quote", _boom)
    result = _svc_with_mock(session).refresh_watchlist_quotes()

    assert result == {"updated": 0, "failed": 1}


# ── chart range window (PRD §4.2, range-mode slice 1) ───────────────────────────

def _seed_five_quarters(session: Session, cik: str = "0000320193") -> None:
    session.add(_company(cik=cik))
    for end, fy, fp, rev in [
        (dt.date(2024, 9, 30), 2024, "Q3", 91_000),
        (dt.date(2024, 12, 31), 2024, "Q4", 119_575),
        (dt.date(2025, 3, 31), 2025, "Q1", 95_359),
        (dt.date(2025, 6, 30), 2025, "Q2", 85_777),
        (dt.date(2025, 9, 28), 2025, "Q3", 94_930),
    ]:
        session.add(_row(cik=cik, period_end=end, fiscal_year=fy, fiscal_period=fp,
                         revenue=rev, eps_diluted=1.0))
    session.commit()


def test_get_detail_chart_range_windows_trend_chart(session: Session) -> None:
    _seed_five_quarters(session)
    ctx = _svc_with_mock(session).get_detail(
        "AAPL", granularity="quarterly",
        chart_from="Q4 FY2024", chart_to="Q2 FY2025",
    )
    assert ctx.chart_labels == ["Q4 FY2024", "Q1 FY2025", "Q2 FY2025"]
    assert ctx.chart_revenue == [119_575, 95_359, 85_777]
    assert ctx.selected_chart_from == "Q4 FY2024"
    assert ctx.selected_chart_to == "Q2 FY2025"
    assert ctx.chart_range_options == [
        "Q3 FY2024", "Q4 FY2024", "Q1 FY2025", "Q2 FY2025", "Q3 FY2025",
    ]
    # KPI cards and tables still follow the selected period (latest default).
    assert ctx.current.label == "Q3 FY2025"


def test_get_detail_chart_range_inverted_is_swapped(session: Session) -> None:
    _seed_five_quarters(session)
    ctx = _svc_with_mock(session).get_detail(
        "AAPL", chart_from="Q2 FY2025", chart_to="Q4 FY2024"
    )
    assert ctx.chart_labels == ["Q4 FY2024", "Q1 FY2025", "Q2 FY2025"]
    assert ctx.selected_chart_from == "Q4 FY2024"
    assert ctx.selected_chart_to == "Q2 FY2025"


def test_get_detail_chart_range_defaults_to_full_history(session: Session) -> None:
    _seed_five_quarters(session)
    ctx = _svc_with_mock(session).get_detail("AAPL")
    assert ctx.chart_labels == [
        "Q3 FY2024", "Q4 FY2024", "Q1 FY2025", "Q2 FY2025", "Q3 FY2025",
    ]
    assert ctx.selected_chart_from == "Q3 FY2024"
    assert ctx.selected_chart_to == "Q3 FY2025"


def test_get_detail_chart_range_unknown_label_falls_back(session: Session) -> None:
    _seed_five_quarters(session)
    ctx = _svc_with_mock(session).get_detail("AAPL", chart_from="Q9 FY2099")
    assert ctx.chart_labels[0] == "Q3 FY2024"
    assert len(ctx.chart_labels) == 5


# ── range-mode hero KPIs (PRD §4.2, slice 3) ──────────────────────────────────

def _seed_six_quarters_full(session: Session, cik: str = "0000320193") -> None:
    session.add(_company(cik=cik))
    for end, fy, fp, rev, ni, epsd, fcf in [
        (dt.date(2024, 9, 30), 2024, "Q3", 91_000, 21_000, 1.38, 20_000),
        (dt.date(2024, 12, 31), 2024, "Q4", 119_575, 33_917, 2.18, 26_600),
        (dt.date(2025, 3, 31), 2025, "Q1", 95_359, 24_780, 1.64, 30_300),
        (dt.date(2025, 6, 30), 2025, "Q2", 85_777, 21_448, 1.40, 22_700),
        (dt.date(2025, 9, 28), 2025, "Q3", 94_930, 23_630, 1.55, 26_800),
        (dt.date(2025, 12, 31), 2025, "Q4", 120_000, 34_000, 2.20, 27_000),
    ]:
        session.add(_row(cik=cik, period_end=end, fiscal_year=fy, fiscal_period=fp,
                         revenue=rev, net_income=ni, eps_diluted=epsd,
                         free_cash_flow=fcf))
    session.commit()


def test_get_detail_range_kpi_aggregates_window(session: Session) -> None:
    _seed_six_quarters_full(session)
    ctx = _svc_with_mock(session).get_detail(
        "AAPL", chart_from="Q1 FY2025", chart_to="Q2 FY2025"
    )
    rk = ctx.range_kpi
    assert rk is not None
    assert rk.label == "Q1 FY2025 → Q2 FY2025"
    assert rk.quarters == 2
    assert rk.kpi.revenue == pytest.approx(95_359 + 85_777)
    assert rk.kpi.net_income == pytest.approx(24_780 + 21_448)
    assert rk.kpi.eps_diluted == pytest.approx(1.64 + 1.40)
    assert rk.kpi.free_cash_flow == pytest.approx(30_300 + 22_700)
    # Change vs the preceding equal-length window (Q3+Q4 FY2024).
    assert rk.prior_label == "Q3 FY2024 → Q4 FY2024"
    assert rk.prior_quarters == 2
    assert rk.change.revenue == pytest.approx(
        (181_136 - 210_575) / 210_575 * 100
    )
    assert rk.change.free_cash_flow == pytest.approx(
        (53_000 - 46_600) / 46_600 * 100
    )


def test_get_detail_range_kpi_none_for_full_history(session: Session) -> None:
    _seed_six_quarters_full(session)
    ctx = _svc_with_mock(session).get_detail("AAPL")
    assert ctx.range_kpi is None
    assert ctx.current.label == "Q4 FY2025"


def test_get_detail_range_kpi_none_for_single_quarter_window(
    session: Session,
) -> None:
    _seed_six_quarters_full(session)
    ctx = _svc_with_mock(session).get_detail(
        "AAPL", chart_from="Q2 FY2025", chart_to="Q2 FY2025"
    )
    assert ctx.range_kpi is None


def test_get_detail_range_kpi_no_prior_window_blanks_change(
    session: Session,
) -> None:
    _seed_six_quarters_full(session)
    ctx = _svc_with_mock(session).get_detail(
        "AAPL", chart_from="Q3 FY2024", chart_to="Q4 FY2024"
    )
    rk = ctx.range_kpi
    assert rk is not None
    assert rk.kpi.revenue == pytest.approx(91_000 + 119_575)
    assert rk.prior_label is None
    assert rk.prior_quarters == 0
    assert rk.change.revenue is None
    assert rk.change.free_cash_flow is None


def test_get_detail_range_kpi_partial_prior_window(session: Session) -> None:
    # Window of 4 quarters with only 2 prior quarters available: the prior
    # window is whatever exists.
    _seed_six_quarters_full(session)
    ctx = _svc_with_mock(session).get_detail(
        "AAPL", chart_from="Q1 FY2025", chart_to="Q4 FY2025"
    )
    rk = ctx.range_kpi
    assert rk is not None
    assert rk.quarters == 4
    assert rk.prior_quarters == 2
    assert rk.prior_label == "Q3 FY2024 → Q4 FY2024"
    assert rk.change.revenue == pytest.approx(
        (95_359 + 85_777 + 94_930 + 120_000 - 210_575) / 210_575 * 100
    )


# ── get_compare ───────────────────────────────────────────────────────────────

def test_get_compare_defaults_to_latest_vs_yoy(session: Session) -> None:
    _seed_five_quarters(session)
    ctx = _svc_with_mock(session).get_compare("AAPL")
    assert ctx.period_a_label == "Q3 FY2025"
    assert ctx.period_b_label == "Q3 FY2024"
    assert ctx.preset is None
    assert ctx.a.kpi.revenue == pytest.approx(94_930)
    assert ctx.b.kpi.revenue == pytest.approx(91_000)
    assert ctx.deltas.revenue.absolute == pytest.approx(94_930 - 91_000)
    assert ctx.deltas.revenue.pct == pytest.approx((94_930 - 91_000) / 91_000 * 100)


def test_get_compare_qoq_preset(session: Session) -> None:
    _seed_five_quarters(session)
    ctx = _svc_with_mock(session).get_compare("AAPL", preset="qoq")
    assert ctx.period_a_label == "Q3 FY2025"
    assert ctx.period_b_label == "Q2 FY2025"
    assert ctx.preset == "qoq"
    assert ctx.deltas.revenue.absolute == pytest.approx(94_930 - 85_777)


def test_get_compare_5y_preset_exact_quarter(session: Session) -> None:
    """A quarter exactly five years back is used as B."""
    cik = "0000320193"
    session.add(_company(cik=cik))
    for end, fy, fp, rev in [
        (dt.date(2020, 9, 30), 2020, "Q3", 64_000),
        (dt.date(2025, 9, 28), 2025, "Q3", 94_930),
    ]:
        session.add(_row(cik=cik, period_end=end, fiscal_year=fy, fiscal_period=fp,
                         revenue=rev, eps_diluted=1.0))
    session.commit()
    ctx = _svc_with_mock(session).get_compare("AAPL", preset="5y")
    assert ctx.period_a_label == "Q3 FY2025"
    assert ctx.period_b_label == "Q3 FY2020"
    assert ctx.preset == "5y"
    assert ctx.deltas.revenue.absolute == pytest.approx(94_930 - 64_000)


def test_get_compare_5y_preset_falls_back_to_oldest(session: Session) -> None:
    """With the 3-year history depth the exact 5y-ago quarter rarely exists;
    B becomes the oldest available quarter (maximum span), not YoY."""
    _seed_five_quarters(session)
    ctx = _svc_with_mock(session).get_compare("AAPL", preset="5y")
    assert ctx.period_a_label == "Q3 FY2025"
    assert ctx.period_b_label == "Q3 FY2024"  # oldest of the five seeded
    assert ctx.preset == "5y"


def test_get_compare_5y_preset_single_quarter_compares_to_itself(session: Session) -> None:
    cik = "0000320193"
    session.add(_company(cik=cik))
    session.add(_row(cik=cik, period_end=dt.date(2025, 9, 28), fiscal_year=2025,
                     fiscal_period="Q3", revenue=94_930, eps_diluted=1.0))
    session.commit()
    ctx = _svc_with_mock(session).get_compare("AAPL", preset="5y")
    assert ctx.period_b_label == ctx.period_a_label == "Q3 FY2025"
    assert ctx.deltas.revenue.absolute == pytest.approx(0.0)


def test_get_compare_freeform_labels(session: Session) -> None:
    _seed_five_quarters(session)
    ctx = _svc_with_mock(session).get_compare(
        "AAPL", period_a="Q1 FY2025", period_b="Q4 FY2024"
    )
    assert ctx.period_a_label == "Q1 FY2025"
    assert ctx.period_b_label == "Q4 FY2024"
    assert ctx.deltas.revenue.absolute == pytest.approx(95_359 - 119_575)
    assert ctx.deltas.revenue.pct < 0


def test_get_compare_unknown_b_falls_back_to_yoy(session: Session) -> None:
    _seed_five_quarters(session)
    ctx = _svc_with_mock(session).get_compare("AAPL", period_b="Q9 FY2099")
    assert ctx.period_b_label == "Q3 FY2024"


def test_get_compare_unknown_a_falls_back_to_latest(session: Session) -> None:
    _seed_five_quarters(session)
    ctx = _svc_with_mock(session).get_compare("AAPL", period_a="bogus")
    assert ctx.period_a_label == "Q3 FY2025"
    assert ctx.period_b_label == "Q3 FY2024"


def test_get_compare_none_values_yield_none_deltas(session: Session) -> None:
    cik = "0000320193"
    session.add(_company(cik=cik))
    session.add(_row(cik=cik, period_end=dt.date(2024, 9, 30), fiscal_year=2024,
                     fiscal_period="Q3", revenue=91_000, free_cash_flow=None))
    session.add(_row(cik=cik, period_end=dt.date(2025, 9, 28), fiscal_year=2025,
                     fiscal_period="Q3", revenue=94_930, free_cash_flow=26_800))
    session.commit()
    ctx = _svc_with_mock(session).get_compare("AAPL")
    assert ctx.deltas.revenue.pct == pytest.approx((94_930 - 91_000) / 91_000 * 100)
    assert ctx.deltas.free_cash_flow.absolute is None
    assert ctx.deltas.free_cash_flow.pct is None


def test_get_compare_single_quarter_compares_to_itself(session: Session) -> None:
    cik = "0000320193"
    session.add(_company(cik=cik))
    session.add(_row(cik=cik, period_end=dt.date(2025, 9, 28), fiscal_year=2025,
                     fiscal_period="Q3", revenue=94_930))
    session.commit()
    ctx = _svc_with_mock(session).get_compare("AAPL")
    assert ctx.period_a_label == "Q3 FY2025"
    assert ctx.period_b_label == "Q3 FY2025"
    assert ctx.deltas.revenue.absolute == pytest.approx(0)
    assert ctx.deltas.revenue.pct == pytest.approx(0)


def test_get_compare_raises_when_no_data(session: Session) -> None:
    with pytest.raises(CompanyNotFoundError):
        _svc_with_mock(session).get_compare("AAPL")


def test_get_compare_includes_balance_sheet_deltas(session: Session) -> None:
    cik = "0000320193"
    session.add(_company(cik=cik))
    session.add(_row(cik=cik, period_end=dt.date(2024, 9, 30), fiscal_year=2024,
                     fiscal_period="Q3", total_assets=300_000, total_equity=100_000))
    session.add(_row(cik=cik, period_end=dt.date(2025, 9, 28), fiscal_year=2025,
                     fiscal_period="Q3", total_assets=330_000, total_equity=110_000))
    session.commit()
    ctx = _svc_with_mock(session).get_compare("AAPL")
    assert ctx.deltas.total_assets.absolute == pytest.approx(30_000)
    assert ctx.deltas.total_equity.pct == pytest.approx(10.0)


# ── get_compare, yearly mode (PRD §4.2, compare-mode slice 2) ─────────────────

def _seed_two_years(session: Session, cik: str = "0000320193") -> None:
    session.add(_company(cik=cik))
    for i, (end, fy, fp, rev, ni) in enumerate([
        (dt.date(2024, 3, 31), 2024, "Q1", 90_000, 20_000),
        (dt.date(2024, 6, 30), 2024, "Q2", 85_000, 19_000),
        (dt.date(2024, 9, 30), 2024, "Q3", 95_000, 21_000),
        (dt.date(2024, 12, 31), 2024, "Q4", 110_000, 25_000),
        (dt.date(2025, 3, 31), 2025, "Q1", 95_000, 22_000),
        (dt.date(2025, 6, 30), 2025, "Q2", 90_000, 21_000),
        (dt.date(2025, 9, 30), 2025, "Q3", 100_000, 23_000),
        (dt.date(2025, 12, 31), 2025, "Q4", 119_575, 27_000),
    ]):
        session.add(_row(cik=cik, period_end=end, fiscal_year=fy, fiscal_period=fp,
                         revenue=rev, net_income=ni, eps_diluted=1.0,
                         total_assets=300_000 + i * 10_000))
    session.commit()


def test_get_compare_yearly_defaults_to_latest_vs_prior_year(session: Session) -> None:
    _seed_two_years(session)
    ctx = _svc_with_mock(session).get_compare("AAPL", mode="yearly")
    assert ctx.mode == "yearly"
    assert ctx.period_a_label == "FY2025"
    assert ctx.period_b_label == "FY2024"
    assert ctx.year_options == [2025, 2024]
    # Flow metrics are 4-quarter sums; balance sheet is year-end point-in-time.
    assert ctx.a.kpi.revenue == pytest.approx(95_000 + 90_000 + 100_000 + 119_575)
    assert ctx.b.kpi.revenue == pytest.approx(90_000 + 85_000 + 95_000 + 110_000)
    assert ctx.deltas.revenue.absolute == pytest.approx(404_575 - 380_000)
    assert ctx.deltas.revenue.pct == pytest.approx((404_575 - 380_000) / 380_000 * 100)
    assert ctx.a.balance_sheet.total_assets == pytest.approx(370_000)
    assert ctx.b.balance_sheet.total_assets == pytest.approx(330_000)


def test_get_compare_yearly_explicit_years(session: Session) -> None:
    _seed_two_years(session)
    ctx = _svc_with_mock(session).get_compare("AAPL", mode="yearly", year_a=2024, year_b=2025)
    assert ctx.period_a_label == "FY2024"
    assert ctx.period_b_label == "FY2025"
    assert ctx.deltas.revenue.absolute == pytest.approx(380_000 - 404_575)


def test_get_compare_yearly_unknown_years_fall_back(session: Session) -> None:
    _seed_two_years(session)
    ctx = _svc_with_mock(session).get_compare("AAPL", mode="yearly", year_a=2099, year_b=1999)
    assert ctx.period_a_label == "FY2025"
    assert ctx.period_b_label == "FY2024"


def test_get_compare_yearly_single_year_compares_to_itself(session: Session) -> None:
    session.add(_company())
    session.add(_row(cik="0000320193", period_end=dt.date(2025, 12, 31),
                     fiscal_year=2025, fiscal_period="Q4", revenue=100_000))
    session.commit()
    ctx = _svc_with_mock(session).get_compare("AAPL", mode="yearly")
    assert ctx.period_a_label == "FY2025"
    assert ctx.period_b_label == "FY2025"
    assert ctx.deltas.revenue.absolute == pytest.approx(0)
    assert ctx.deltas.revenue.pct == pytest.approx(0)


def test_get_compare_quarterly_mode_unchanged(session: Session) -> None:
    _seed_two_years(session)
    ctx = _svc_with_mock(session).get_compare("AAPL", mode="quarterly")
    assert ctx.mode == "quarterly"
    assert ctx.period_a_label == "Q4 FY2025"
    assert ctx.period_b_label == "Q4 FY2024"


# ── range-view ZIP (PRD §4.8, third slice) ──────────────────────────────────────

def test_get_range_zip_entries_windowed_csvs_plus_summary(session: Session) -> None:
    from tickerlens.services.financials import build_history_zip

    session.add(_company())
    session.add(_row(period_end=dt.date(2025, 3, 31), fiscal_year=2025,
                     fiscal_period="Q1", revenue=100.0))
    session.add(_row(period_end=dt.date(2025, 6, 30), fiscal_year=2025,
                     fiscal_period="Q2", revenue=120.0))
    session.add(_row(period_end=dt.date(2025, 9, 30), fiscal_year=2025,
                     fiscal_period="Q3", revenue=140.0))
    session.commit()

    ticker, entries = _svc_with_mock(session).get_range_zip_entries(
        "AAPL", chart_from="Q2 FY2025", chart_to="Q3 FY2025"
    )

    assert ticker == "AAPL"
    assert [arc for arc, _ in entries] == [
        "AAPL/AAPL_Q2-FY2025.csv",
        "AAPL/AAPL_Q3-FY2025.csv",
        "AAPL/AAPL_range_summary.csv",
    ]
    assert "# Period,Q2 FY2025" in entries[0][1]
    assert "Revenue,120.0" in entries[0][1]
    summary = entries[2][1]
    assert "# Periods,Q2 FY2025 → Q3 FY2025" in summary
    assert "metric,Q2 FY2025,Q3 FY2025" in summary
    assert "Revenue,120.0,140.0" in summary

    payload = build_history_zip(ticker, entries)
    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        assert sorted(zf.namelist()) == [
            "AAPL/AAPL_Q2-FY2025.csv",
            "AAPL/AAPL_Q3-FY2025.csv",
            "AAPL/AAPL_range_summary.csv",
        ]


def test_get_range_zip_entries_unknown_labels_fall_back_to_full_history(
    session: Session,
) -> None:
    session.add(_company())
    session.add(_row(period_end=dt.date(2025, 3, 31), fiscal_year=2025,
                     fiscal_period="Q1", revenue=100.0))
    session.add(_row(period_end=dt.date(2025, 6, 30), fiscal_year=2025,
                     fiscal_period="Q2", revenue=120.0))
    session.commit()

    _, entries = _svc_with_mock(session).get_range_zip_entries(
        "AAPL", chart_from="bogus", chart_to="also-bogus"
    )
    assert [arc for arc, _ in entries] == [
        "AAPL/AAPL_Q1-FY2025.csv",
        "AAPL/AAPL_Q2-FY2025.csv",
        "AAPL/AAPL_range_summary.csv",
    ]


def test_get_range_zip_entries_inverted_range_swaps(session: Session) -> None:
    session.add(_company())
    session.add(_row(period_end=dt.date(2025, 3, 31), fiscal_year=2025,
                     fiscal_period="Q1", revenue=100.0))
    session.add(_row(period_end=dt.date(2025, 6, 30), fiscal_year=2025,
                     fiscal_period="Q2", revenue=120.0))
    session.commit()

    _, entries = _svc_with_mock(session).get_range_zip_entries(
        "AAPL", chart_from="Q2 FY2025", chart_to="Q1 FY2025"
    )
    assert entries[0][0] == "AAPL/AAPL_Q1-FY2025.csv"
    assert entries[1][0] == "AAPL/AAPL_Q2-FY2025.csv"


def test_get_range_zip_entries_unknown_ticker_raises(session: Session) -> None:
    with pytest.raises(CompanyNotFoundError):
        _svc_with_mock(session).get_range_zip_entries("ZZZZ")


# ── single-year ZIP (PRD §4.8, fourth slice) ────────────────────────────────────

def test_get_year_zip_entries_quarterly_csvs_plus_summary(session: Session) -> None:
    session.add(_company())
    session.add(_row(period_end=dt.date(2025, 3, 31), fiscal_year=2025,
                     fiscal_period="Q1", revenue=100.0))
    session.add(_row(period_end=dt.date(2025, 6, 30), fiscal_year=2025,
                     fiscal_period="Q2", revenue=120.0))
    session.add(_row(period_end=dt.date(2026, 3, 31), fiscal_year=2026,
                     fiscal_period="Q1", revenue=140.0))
    session.commit()

    ticker, resolved_year, entries = _svc_with_mock(session).get_year_zip_entries(
        "AAPL", year=2025
    )

    assert ticker == "AAPL"
    assert resolved_year == 2025
    assert [arc for arc, _ in entries] == [
        "AAPL/AAPL_Q1-FY2025.csv",
        "AAPL/AAPL_Q2-FY2025.csv",
        "AAPL/AAPL_year_summary.csv",
    ]
    assert "# Period,Q1 FY2025" in entries[0][1]
    assert "Revenue,100.0" in entries[0][1]
    summary = entries[2][1]
    assert "metric,Q1 FY2025,Q2 FY2025" in summary
    assert "Revenue,100.0,120.0" in summary


def test_get_year_zip_entries_unknown_year_falls_back_to_latest(session: Session) -> None:
    session.add(_company())
    session.add(_row(period_end=dt.date(2025, 3, 31), fiscal_year=2025,
                     fiscal_period="Q1", revenue=100.0))
    session.add(_row(period_end=dt.date(2026, 3, 31), fiscal_year=2026,
                     fiscal_period="Q1", revenue=140.0))
    session.commit()

    _, resolved_year, entries = _svc_with_mock(session).get_year_zip_entries(
        "AAPL", year=2099
    )

    assert resolved_year == 2026
    assert [arc for arc, _ in entries] == [
        "AAPL/AAPL_Q1-FY2026.csv",
        "AAPL/AAPL_year_summary.csv",
    ]


def test_get_year_zip_entries_unknown_ticker_raises(session: Session) -> None:
    with pytest.raises(CompanyNotFoundError):
        _svc_with_mock(session).get_year_zip_entries("ZZZZ")


# ── range tables (PRD §4.2, range-mode slice 2) ────────────────────────────────

def test_get_detail_range_table_for_narrowed_window(session: Session) -> None:
    _seed_five_quarters(session)
    ctx = _svc_with_mock(session).get_detail(
        "AAPL", granularity="quarterly",
        chart_from="Q4 FY2024", chart_to="Q2 FY2025",
    )
    rt = ctx.range_table
    assert rt is not None
    assert rt.labels == ["Q4 FY2024", "Q1 FY2025", "Q2 FY2025"]
    income = [r for r in rt.rows if r.section == "income"]
    assert [r.label for r in income] == [
        "Revenue", "Net Income", "EPS Basic", "EPS Diluted",
    ]
    assert income[0].values == [119_575, 95_359, 85_777]
    assert income[0].kind == "money"
    assert income[2].kind == "eps"
    assert len([r for r in rt.rows if r.section == "cashflow"]) == 1
    assert len([r for r in rt.rows if r.section == "balance"]) == 4
    # KPI cards and the selected period still follow the period selector.
    assert ctx.current.label == "Q3 FY2025"


def test_get_detail_no_range_table_for_full_history(session: Session) -> None:
    _seed_five_quarters(session)
    ctx = _svc_with_mock(session).get_detail("AAPL")
    assert ctx.range_table is None


def test_get_detail_no_range_table_for_single_quarter_window(session: Session) -> None:
    # A one-quarter window keeps the single-period view (with YoY/QoQ).
    _seed_five_quarters(session)
    ctx = _svc_with_mock(session).get_detail(
        "AAPL", chart_from="Q1 FY2025", chart_to="Q1 FY2025",
    )
    assert ctx.chart_labels == ["Q1 FY2025"]
    assert ctx.range_table is None


def test_get_detail_no_range_table_in_yearly_mode(session: Session) -> None:
    _seed_five_quarters(session)
    ctx = _svc_with_mock(session).get_detail("AAPL", granularity="yearly")
    assert ctx.range_table is None


# ── cross-company compare (PRD §4.2, compare slice) ────────────────────────────

def _svc_two_tickers(session: Session) -> "FinancialsService":
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.side_effect = lambda t: {
        "AAPL": "0000320193", "MSFT": "0000789019",
    }[t.upper()]
    return FinancialsService(edgar_client=mock_edgar, session=session)


def _seed_vs_pair(session: Session) -> None:
    def rows(cik, revs, nis, epss, fcfs):
        ends = [dt.date(2024, 6, 30), dt.date(2024, 9, 30), dt.date(2024, 12, 31),
                dt.date(2025, 3, 31), dt.date(2025, 6, 30)]
        fps = ["Q2", "Q3", "Q4", "Q1", "Q2"]
        fys = [2024, 2024, 2024, 2025, 2025]
        for end, fy, fp, rev, ni, eps, fcf in zip(ends, fys, fps, revs, nis, epss, fcfs):
            session.add(_row(cik=cik, period_end=end, fiscal_year=fy, fiscal_period=fp,
                             revenue=rev, net_income=ni, eps_diluted=eps,
                             free_cash_flow=fcf))

    aapl = _company(cik="0000320193", name="Apple Inc.", ticker="AAPL")
    aapl.last_price = 200.0
    aapl.market_cap = 3e12
    msft = _company(cik="0000789019", name="Microsoft Corp.", ticker="MSFT")
    msft.last_price = 500.0
    msft.market_cap = 3.7e12
    session.add(aapl)
    session.add(msft)
    rows("0000320193",
         [80_000, 91_000, 119_575, 95_359, 85_777],
         [20_000, 21_000, 33_917, 24_780, 21_448],
         [1.30, 1.38, 2.18, 1.64, 1.40],
         [20_000, 20_000, 26_600, 30_300, 22_700])
    rows("0000789019",
         [60_000, 65_585, 69_632, 61_858, 64_000],
         [21_000, 24_667, 24_108, 25_824, 27_000],
         [2.80, 3.30, 3.23, 3.46, 3.60],
         [23_000, 24_000, 22_000, 25_000, 26_000])
    session.commit()


def test_get_company_vs_returns_both_sides(session: Session) -> None:
    _seed_vs_pair(session)
    vs = _svc_two_tickers(session).get_company_vs("AAPL", "MSFT")
    assert vs.a.ticker == "AAPL"
    assert vs.b.ticker == "MSFT"
    assert vs.a.name == "Apple Inc."
    assert vs.b.name == "Microsoft Corp."
    assert vs.a.period_label == "Q2 FY2025"
    assert vs.b.period_label == "Q2 FY2025"
    assert vs.a.kpi.revenue == pytest.approx(85_777)
    assert vs.b.kpi.eps_diluted == pytest.approx(3.60)
    # YoY badges come from each company's own latest quarter.
    assert vs.a.yoy.revenue == pytest.approx((85_777 - 80_000) / 80_000 * 100)
    assert vs.b.yoy.revenue == pytest.approx((64_000 - 60_000) / 60_000 * 100)
    assert vs.a.last_price == pytest.approx(200.0)
    assert vs.b.market_cap == pytest.approx(3.7e12)
    assert isinstance(vs.a.signal, str) and vs.a.signal
    assert isinstance(vs.b.signal, str) and vs.b.signal


def test_get_company_vs_missing_ticker_raises(session: Session) -> None:
    _seed_vs_pair(session)
    with pytest.raises(CompanyNotFoundError):
        _svc_two_tickers(session).get_company_vs("AAPL", "ZZZZ")


def test_get_company_vs_same_ticker_twice(session: Session) -> None:
    _seed_vs_pair(session)
    vs = _svc_two_tickers(session).get_company_vs("AAPL", "AAPL")
    assert vs.a.ticker == vs.b.ticker == "AAPL"
    assert vs.a.kpi.revenue == vs.b.kpi.revenue


# ── earnings calendar: non-blocking cached variant ────────────────────────────

def _seed_earnings_companies(session: Session) -> None:
    for cik, ticker, name in [
        ("0000320193", "AAPL", "Apple Inc."),
        ("0000789019", "MSFT", "Microsoft Corp"),
    ]:
        c = Company()
        c.cik = cik
        c.ticker = ticker
        c.name = name
        session.add(c)
    session.commit()


def _swap_calendar_cache(monkeypatch, cache) -> None:
    import tickerlens.data.calendar as cal_mod

    monkeypatch.setattr(cal_mod, "default_calendar_cache", cache)


def test_get_cached_upcoming_earnings_never_fetches(session: Session, monkeypatch) -> None:
    """Cold cache: no network call, empty events, warmer kicked off."""
    from tickerlens.data.calendar import CalendarCache, EarningsEvent

    _seed_earnings_companies(session)
    calls: list[str] = []

    def fetch(ticker: str, name: str | None = None) -> EarningsEvent:
        calls.append(ticker)
        raise AssertionError("network fetch must not happen on the cached path")

    cache = CalendarCache(ttl_seconds=3600, fetch_fn=fetch)
    _swap_calendar_cache(monkeypatch, cache)
    warmed: list[list[str]] = []
    monkeypatch.setattr(
        "tickerlens.data.calendar.warm_earnings_cache",
        lambda tickers: warmed.append(list(tickers)),
    )

    svc = FinancialsService(session=session)
    events = svc.get_cached_upcoming_earnings()

    assert calls == []  # nothing fetched
    assert len(events) == 2
    assert all(e.earnings_date is None for e in events)
    assert {e.ticker for e in events} == {"AAPL", "MSFT"}
    assert {e.company_name for e in events} == {"Apple Inc.", "Microsoft Corp"}
    # Both tickers were cold, so the warmer was kicked off once with both.
    assert warmed == [["AAPL", "MSFT"]] or warmed == [["MSFT", "AAPL"]]


def test_get_cached_upcoming_earnings_serves_cached(session: Session, monkeypatch) -> None:
    """Warm cache: returns live cached events without fetching, no warmer."""
    from tickerlens.data.calendar import CalendarCache, EarningsEvent

    _seed_earnings_companies(session)
    calls: list[str] = []

    def fetch(ticker: str, name: str | None = None) -> EarningsEvent:
        calls.append(ticker)
        return EarningsEvent(
            ticker=ticker,
            company_name=name,
            earnings_date="2026-10-29",
            days_until=24,
            eps_estimate_avg=1.65,
            revenue_estimate_avg=95000000000.0,
            dividend_date=None,
            ex_dividend_date=None,
        )

    cache = CalendarCache(ttl_seconds=3600, fetch_fn=fetch)
    cache.get("AAPL")  # pre-warm only AAPL
    assert calls == ["AAPL"]
    _swap_calendar_cache(monkeypatch, cache)
    warmed: list[list[str]] = []
    monkeypatch.setattr(
        "tickerlens.data.calendar.warm_earnings_cache",
        lambda tickers: warmed.append(list(tickers)),
    )

    svc = FinancialsService(session=session)
    events = svc.get_cached_upcoming_earnings()

    assert calls == ["AAPL"]  # no new fetches
    by_ticker = {e.ticker: e for e in events}
    assert by_ticker["AAPL"].earnings_date == "2026-10-29"
    assert by_ticker["MSFT"].earnings_date is None
    # Dated events sort before date-less ones.
    assert events[0].ticker == "AAPL"
    # Only the cold ticker went to the warmer.
    assert warmed == [["MSFT"]]


def test_get_upcoming_earnings_still_fetches(session: Session, monkeypatch) -> None:
    """Blocking variant unchanged: cold tickers are fetched synchronously."""
    from tickerlens.data.calendar import CalendarCache, EarningsEvent

    _seed_earnings_companies(session)
    calls: list[str] = []

    def fetch(ticker: str, name: str | None = None) -> EarningsEvent:
        calls.append(ticker)
        return EarningsEvent(
            ticker=ticker,
            company_name=name,
            earnings_date="2026-10-29",
            days_until=24,
            eps_estimate_avg=None,
            revenue_estimate_avg=None,
            dividend_date=None,
            ex_dividend_date=None,
        )

    _swap_calendar_cache(monkeypatch, CalendarCache(ttl_seconds=3600, fetch_fn=fetch))

    svc = FinancialsService(session=session)
    events = svc.get_upcoming_earnings()

    assert sorted(calls) == ["AAPL", "MSFT"]
    assert all(e.earnings_date == "2026-10-29" for e in events)


def test_refresh_company_quote_updates_price_and_market_cap(session: Session, monkeypatch) -> None:
    from tickerlens.data.yahoo import QuoteSnapshot
    from tickerlens.services import financials as fin_mod

    cik = "0000320193"
    company = _company(cik=cik)
    company.last_price = 100.0
    company.market_cap = 1e12
    session.add(company)
    session.commit()

    monkeypatch.setattr(
        fin_mod,
        "cached_quote",
        lambda t: QuoteSnapshot(ticker=t, last_price=150.0, market_cap=2e12, currency="USD"),
    )

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    svc = FinancialsService(edgar_client=mock_edgar, session=session)

    quote = svc.refresh_company_quote("AAPL", session=session)
    assert quote.last_price == 150.0

    session.refresh(company)
    assert company.last_price == 150.0
    assert company.market_cap == 2e12


def test_refresh_company_quote_preserves_price_on_failure(session: Session, monkeypatch) -> None:
    from tickerlens.data.yahoo import QuoteSnapshot
    from tickerlens.services import financials as fin_mod

    cik = "0000320193"
    company = _company(cik=cik)
    company.last_price = 100.0
    company.market_cap = 1e12
    session.add(company)
    session.commit()

    monkeypatch.setattr(
        fin_mod,
        "cached_quote",
        lambda t: QuoteSnapshot(ticker=t, last_price=None, market_cap=None, currency=None),
    )

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    svc = FinancialsService(edgar_client=mock_edgar, session=session)

    quote = svc.refresh_company_quote("AAPL", session=session)
    assert quote.last_price is None

    session.refresh(company)
    assert company.last_price == 100.0
    assert company.market_cap == 1e12


def test_refresh_company_quote_unknown_ticker_never_raises(session: Session) -> None:
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.side_effect = KeyError("not found")
    svc = FinancialsService(edgar_client=mock_edgar, session=session)

    quote = svc.refresh_company_quote("ZZZZ", session=session)
    assert quote.last_price is None



def test_refresh_company_quote_fast_path_skips_lookup_when_fresh(session: Session, monkeypatch) -> None:
    """A fresh cached quote short-circuits: no EDGAR lookup, no DB session work."""
    from tickerlens.data.yahoo import QuoteSnapshot
    from tickerlens.services import financials as fin_mod

    snap = QuoteSnapshot(ticker="AAPL", last_price=150.0, market_cap=2e12, currency="USD")
    monkeypatch.setattr(fin_mod, "peeked_quote", lambda t: snap)

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.side_effect = AssertionError("must not resolve CIK on fast path")
    svc = FinancialsService(edgar_client=mock_edgar, session=session)

    assert svc.refresh_company_quote("AAPL") is snap
    mock_edgar.cik_for_ticker.assert_not_called()


def test_refresh_company_quote_skips_commit_when_unchanged(session: Session, monkeypatch) -> None:
    """No write transaction when the cached quote matches the stored values."""
    from tickerlens.data.yahoo import QuoteSnapshot
    from tickerlens.services import financials as fin_mod

    cik = "0000320193"
    company = _company(cik=cik)
    company.last_price = 150.0
    company.market_cap = 2e12
    session.add(company)
    session.commit()

    monkeypatch.setattr(fin_mod, "peeked_quote", lambda t: None)  # force slow path
    monkeypatch.setattr(
        fin_mod,
        "cached_quote",
        lambda t: QuoteSnapshot(ticker=t, last_price=150.0, market_cap=2e12, currency="USD"),
    )
    commits: list[int] = []
    monkeypatch.setattr(session, "commit", lambda: commits.append(1))

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    svc = FinancialsService(edgar_client=mock_edgar, session=session)

    quote = svc.refresh_company_quote("AAPL", session=session)
    assert quote.last_price == 150.0
    assert commits == []


# ── earnings-calendar event build (batch 23) ─────────────────────────────────

from types import SimpleNamespace

from tickerlens.data.calendar import EarningsEvent


def _cal_company(ticker: str) -> SimpleNamespace:
    return SimpleNamespace(ticker=ticker, name=f"{ticker} Inc.", cik=f"CIK-{ticker}")


def _cal_fetch_event(ticker: str, name: str | None) -> EarningsEvent:
    # Mimics Yahoo normalization: the fetch form is hyphenated even when the
    # DB ticker is dotted.
    return EarningsEvent(
        ticker=ticker.replace(".", "-"),
        company_name=name,
        earnings_date="2026-11-07",
        days_until=32,
        eps_estimate_avg=None,
        revenue_estimate_avg=None,
        dividend_date=None,
        ex_dividend_date=None,
    )


def test_build_earnings_events_uses_db_display_ticker() -> None:
    events = FinancialsService._build_earnings_events(
        [_cal_company("BRK.B"), _cal_company("AAPL")], set(), _cal_fetch_event
    )
    by = {e.ticker: e for e in events}
    assert set(by) == {"BRK.B", "AAPL"}
    assert by["BRK.B"].company_name == "BRK.B Inc."
    assert by["BRK.B"].is_watchlist is False


def test_build_earnings_events_marks_watchlist() -> None:
    events = FinancialsService._build_earnings_events(
        [_cal_company("AAPL")], {"CIK-AAPL"}, _cal_fetch_event
    )
    assert events[0].is_watchlist is True


def test_earnings_sort_key_upcoming_before_reported_before_tbd() -> None:
    def ev(days: int | None) -> EarningsEvent:
        return EarningsEvent(
            ticker="X",
            company_name=None,
            earnings_date=None,
            days_until=days,
            eps_estimate_avg=None,
            revenue_estimate_avg=None,
            dividend_date=None,
            ex_dividend_date=None,
        )

    ordered = sorted(
        [ev(None), ev(-30), ev(10), ev(-1), ev(2)],
        key=FinancialsService._earnings_sort_key,
    )
    assert [e.days_until for e in ordered] == [2, 10, -1, -30, None]


# ── refresh_financials_if_stale ───────────────────────────────────────────────

def _submissions_forms(*forms_dates: tuple[str, str]) -> dict:
    forms = [f for f, _ in forms_dates]
    dates = [d for _, d in forms_dates]
    return {"filings": {"recent": {"form": forms, "filingDate": dates}}}


@pytest.fixture
def _fresh_filings_state():
    """Reset the module-level filings-check cache around each test."""
    from tickerlens.services import financials as fin_mod
    with fin_mod._filings_check_lock:
        fin_mod._filings_check_state.clear()
    yield
    with fin_mod._filings_check_lock:
        fin_mod._filings_check_state.clear()


def test_refresh_runs_when_newer_10q_filed(session: Session, _fresh_filings_state) -> None:
    cik = "0000320193"
    session.add(_company(cik=cik))
    session.add(_row(cik=cik, period_end=dt.date(2026, 6, 27), fiscal_year=2026,
                     fiscal_period="Q3", revenue=94_930.0))
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    # 10-Q filed after the newest stored quarter-end -> stale
    mock_edgar.submissions.return_value = _submissions_forms(("10-Q", "2026-09-25"))
    svc = FinancialsService(edgar_client=mock_edgar, session=session)
    svc.fetch_and_persist = MagicMock()
    svc._enrich_press_release_highlights = MagicMock()

    assert svc.refresh_financials_if_stale("AAPL") is True
    svc.fetch_and_persist.assert_called_once_with("AAPL", periods=8)


def test_refresh_skipped_when_filings_not_newer(session: Session, _fresh_filings_state) -> None:
    cik = "0000320193"
    session.add(_company(cik=cik))
    session.add(_row(cik=cik, period_end=dt.date(2026, 9, 27), fiscal_year=2026,
                     fiscal_period="Q4", revenue=100_000.0))
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    # Latest 10-Q predates the newest stored quarter-end -> fresh
    mock_edgar.submissions.return_value = _submissions_forms(("10-Q", "2026-07-30"))
    svc = FinancialsService(edgar_client=mock_edgar, session=session)
    svc.fetch_and_persist = MagicMock()

    assert svc.refresh_financials_if_stale("AAPL") is False
    svc.fetch_and_persist.assert_not_called()


def test_refresh_respects_ttl(session: Session, _fresh_filings_state) -> None:
    cik = "0000320193"
    session.add(_company(cik=cik))
    session.add(_row(cik=cik, period_end=dt.date(2026, 6, 27), fiscal_year=2026,
                     fiscal_period="Q3", revenue=94_930.0))
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    # Latest 10-Q predates the stored quarter-end: nothing to do.
    mock_edgar.submissions.return_value = _submissions_forms(("10-Q", "2026-06-01"))
    svc = FinancialsService(edgar_client=mock_edgar, session=session)
    svc.fetch_and_persist = MagicMock()

    assert svc.refresh_financials_if_stale("AAPL") is False
    assert svc.refresh_financials_if_stale("AAPL") is False
    # Second call is served from the TTL cache: submissions fetched once.
    assert mock_edgar.submissions.call_count == 1


def test_refresh_never_raises_on_edgar_failure(session: Session, _fresh_filings_state) -> None:
    cik = "0000320193"
    session.add(_company(cik=cik))
    session.add(_row(cik=cik, period_end=dt.date(2026, 6, 27), fiscal_year=2026,
                     fiscal_period="Q3", revenue=94_930.0))
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    mock_edgar.submissions.side_effect = RuntimeError("EDGAR down")
    svc = FinancialsService(edgar_client=mock_edgar, session=session)

    assert svc.refresh_financials_if_stale("AAPL") is False


def test_refresh_skips_unknown_ticker(_fresh_filings_state) -> None:
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.side_effect = KeyError("ZZZZ")
    svc = FinancialsService(edgar_client=mock_edgar)
    assert svc.refresh_financials_if_stale("ZZZZ") is False


def test_refresh_skips_pull_when_filing_already_processed(
    session: Session, _fresh_filings_state
) -> None:
    """Regression (batch 31): a filing date always postdates the quarter's
    period end, so the old ``latest > max_period_end`` check fired a full
    re-pull after every server restart even when the latest 10-Q was already
    ingested. The persisted ``xbrl_filings_processed`` marker must suppress it.

    Mirrors the real AAPL shape: 10-Q filed 2026-07-31 for the quarter ended
    2026-06-27 — filing date > period end, but the quarter is already in the DB.
    """
    cik = "0000320193"
    company = _company(cik=cik)
    company.xbrl_filings_processed = "2026-07-31"
    session.add(company)
    session.add(_row(cik=cik, period_end=dt.date(2026, 6, 27), fiscal_year=2026,
                     fiscal_period="Q3", revenue=94_930.0))
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    mock_edgar.submissions.return_value = _submissions_forms(("10-Q", "2026-07-31"))
    svc = FinancialsService(edgar_client=mock_edgar, session=session)
    svc.fetch_and_persist = MagicMock()

    assert svc.refresh_financials_if_stale("AAPL") is False
    svc.fetch_and_persist.assert_not_called()


def test_refresh_runs_when_filing_newer_than_processed_marker(
    session: Session, _fresh_filings_state
) -> None:
    """A genuinely newer 10-Q (past the persisted marker) still triggers."""
    cik = "0000320193"
    company = _company(cik=cik)
    company.xbrl_filings_processed = "2026-05-01"
    session.add(company)
    session.add(_row(cik=cik, period_end=dt.date(2026, 3, 28), fiscal_year=2026,
                     fiscal_period="Q2", revenue=95_000.0))
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    mock_edgar.submissions.return_value = _submissions_forms(("10-Q", "2026-07-31"))
    svc = FinancialsService(edgar_client=mock_edgar, session=session)
    svc.fetch_and_persist = MagicMock()
    svc._enrich_press_release_highlights = MagicMock()

    assert svc.refresh_financials_if_stale("AAPL") is True
    svc.fetch_and_persist.assert_called_once_with("AAPL", periods=8)


def test_fetch_and_persist_records_processed_filing_date(
    session: Session, _fresh_filings_state
) -> None:
    """fetch_and_persist stores the latest quarterly filing date it
    incorporated, so a later freshness check doesn't re-pull the same filing."""
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = "0000320193"
    mock_edgar.submissions.return_value = {
        **_SUBMISSIONS,
        "filings": {"recent": {"form": ["10-Q", "8-K"], "filingDate": ["2025-05-01", "2025-05-02"]}},
    }
    mock_edgar.companyfacts.return_value = _MINIMAL_COMPANYFACTS

    svc = FinancialsService(edgar_client=mock_edgar, session=session)
    svc.fetch_and_persist("AAPL", periods=4, session=session)

    company = session.get(Company, "0000320193")
    assert company is not None
    assert company.xbrl_filings_processed == "2025-05-01"

    # And the in-memory fast path agrees: an immediate freshness check is a no-op.
    svc.fetch_and_persist = MagicMock()
    assert svc.refresh_financials_if_stale("AAPL") is False
    svc.fetch_and_persist.assert_not_called()


def test_fetch_and_persist_does_not_wipe_marker_without_quarterly_forms(
    session: Session,
) -> None:
    """A submissions feed with no 10-Q/10-K forms must not clear a marker set
    by an earlier pull."""
    company = _company(cik="0000320193")
    company.xbrl_filings_processed = "2025-05-01"
    session.add(company)
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = "0000320193"
    mock_edgar.submissions.return_value = _SUBMISSIONS  # no "filings" key
    mock_edgar.companyfacts.return_value = _MINIMAL_COMPANYFACTS

    svc = FinancialsService(edgar_client=mock_edgar, session=session)
    svc.fetch_and_persist("AAPL", periods=4, session=session)

    assert session.get(Company, "0000320193").xbrl_filings_processed == "2025-05-01"


def test_fetch_and_persist_marks_only_processed_filings(
    session: Session, _fresh_filings_state
) -> None:
    """Regression (batch 37): the ``xbrl_filings_processed`` marker must not
    advance to a filing whose quarter isn't in the extracted rows. Mirrors
    DUK: the 10-Q covering Q2 was filed, but companyfacts had no facts for
    it, so the marker stays at the older processed 10-Q and the freshness
    check keeps retrying instead of skipping the quarter forever."""
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = "0001326160"
    mock_edgar.submissions.return_value = {
        **_SUBMISSIONS,
        "filings": {"recent": {
            "form": ["10-Q", "10-Q"],
            "filingDate": ["2025-08-04", "2025-05-01"],
            "reportDate": ["2025-06-30", "2025-03-31"],
        }},
    }
    # _MINIMAL_COMPANYFACTS only has facts through 2025-03-31: the Q2
    # 10-Q's quarter is missing from the extracted rows.
    mock_edgar.companyfacts.return_value = _MINIMAL_COMPANYFACTS

    svc = FinancialsService(edgar_client=mock_edgar, session=session)
    svc.fetch_and_persist("DUK", periods=4, session=session)

    company = session.get(Company, "0001326160")
    assert company is not None
    assert company.xbrl_filings_processed == "2025-05-01"


def test_refresh_refires_after_pull_with_unprocessed_filing(
    session: Session, _fresh_filings_state
) -> None:
    """End-to-end of the batch-37 loop: a pull that ingests nothing new
    (companyfacts lags the filing) leaves the marker behind the latest
    filing, so the next freshness check fires again instead of treating the
    quarter as handled."""
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = "0001326160"
    mock_edgar.submissions.return_value = {
        **_SUBMISSIONS,
        "filings": {"recent": {
            "form": ["10-Q", "10-Q"],
            "filingDate": ["2025-08-04", "2025-05-01"],
            "reportDate": ["2025-06-30", "2025-03-31"],
        }},
    }
    mock_edgar.companyfacts.return_value = _MINIMAL_COMPANYFACTS

    svc = FinancialsService(edgar_client=mock_edgar, session=session)
    svc.fetch_and_persist("DUK", periods=4, session=session)
    assert session.get(Company, "0001326160").xbrl_filings_processed == "2025-05-01"

    # Simulate a later check (fresh in-memory state, as after a restart).
    from tickerlens.services import financials as fin_mod
    with fin_mod._filings_check_lock:
        fin_mod._filings_check_state.clear()
    svc.fetch_and_persist = MagicMock()
    svc._enrich_press_release_highlights = MagicMock()

    assert svc.refresh_financials_if_stale("DUK") is True
    svc.fetch_and_persist.assert_called_once_with("DUK", periods=8)


def _middle_gap_submissions() -> dict:
    """SKYD shape (batch 44): the Q3'25 10-Q was filed 2025-11-10 but SEC
    never ingested its facts; the marker sits at 2026-08-04 on newer
    processed filings."""
    return {"filings": {"recent": {
        "form": ["10-Q", "10-Q", "10-K", "10-Q"],
        "filingDate": ["2026-08-04", "2026-05-04", "2026-02-25", "2025-11-10"],
        "reportDate": ["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30"],
    }}}


def test_middle_gap_helper_detects_unprocessed_filing() -> None:
    from tickerlens.services.financials import _has_unprocessed_quarter_in_window

    stored = [  # 2025-09-30 missing from inside the window
        "2024-09-30", "2024-12-31", "2025-03-31", "2025-06-30",
        "2025-12-31", "2026-03-31", "2026-06-30",
    ]
    assert _has_unprocessed_quarter_in_window(
        _middle_gap_submissions(), stored, "2026-08-04"
    ) is True


def test_middle_gap_helper_quiet_when_no_gap() -> None:
    from tickerlens.services.financials import _has_unprocessed_quarter_in_window

    stored = ["2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]
    assert _has_unprocessed_quarter_in_window(
        _middle_gap_submissions(), stored, "2026-08-04"
    ) is False


def test_middle_gap_helper_ignores_out_of_window_filing() -> None:
    """A filing older than the stored window is legitimately unstored —
    must not false-positive into perpetual re-pulls."""
    from tickerlens.services.financials import _has_unprocessed_quarter_in_window

    submissions = {"filings": {"recent": {
        "form": ["10-Q", "10-Q"],
        "filingDate": ["2026-08-04", "2024-05-01"],
        "reportDate": ["2026-06-30", "2024-03-31"],
    }}}
    stored = ["2026-03-31", "2026-06-30"]  # 2024-03-31 outside the window
    assert _has_unprocessed_quarter_in_window(submissions, stored, "2026-08-04") is False


def test_middle_gap_helper_ignores_filing_newer_than_marker() -> None:
    """A filing newer than the marker is the latest>marker path's
    responsibility, not the middle-gap check's."""
    from tickerlens.services.financials import _has_unprocessed_quarter_in_window

    submissions = {"filings": {"recent": {
        "form": ["10-Q"],
        "filingDate": ["2026-08-04"],
        "reportDate": ["2026-06-30"],
    }}}
    assert _has_unprocessed_quarter_in_window(submissions, ["2026-03-31"], "2026-05-01") is False


def test_refresh_fires_on_middle_gap(
    session: Session, _fresh_filings_state
) -> None:
    """End-to-end of the batch-44 middle-gap check: the marker is ahead of an
    un-ingested middle filing, so the refresh fires instead of treating the
    missing quarter as handled."""
    cik = "0002041610"
    company = _company(cik=cik, name="Skydance Corp", ticker="SKYD")
    company.xbrl_filings_processed = "2026-08-04"
    session.add(company)
    for end, fy, fp in [
        (dt.date(2024, 9, 30), 2025, "Q3"),
        (dt.date(2024, 12, 31), 2025, "Q4"),
        (dt.date(2025, 3, 31), 2025, "Q1"),
        (dt.date(2025, 6, 30), 2025, "Q2"),
        # 2025-09-30 (Q3) missing: filed 2025-11-10, never ingested by SEC
        (dt.date(2025, 12, 31), 2025, "Q4"),
        (dt.date(2026, 3, 31), 2026, "Q1"),
        (dt.date(2026, 6, 30), 2026, "Q2"),
    ]:
        session.add(_row(cik=cik, period_end=end, fiscal_year=fy,
                         fiscal_period=fp, revenue=1.0))
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    mock_edgar.submissions.return_value = _middle_gap_submissions()

    svc = FinancialsService(edgar_client=mock_edgar, session=session)
    svc.fetch_and_persist = MagicMock()
    svc._enrich_press_release_highlights = MagicMock()

    assert svc.refresh_financials_if_stale("SKYD") is True
    svc.fetch_and_persist.assert_called_once_with("SKYD", periods=8)


def test_refresh_skips_when_middle_gap_closed(
    session: Session, _fresh_filings_state
) -> None:
    """Same shape but every in-window filing has its quarter stored —
    the middle-gap check must not fire."""
    cik = "0002041610"
    company = _company(cik=cik, name="Skydance Corp", ticker="SKYD")
    company.xbrl_filings_processed = "2026-08-04"
    session.add(company)
    for end, fy, fp in [
        (dt.date(2025, 9, 30), 2025, "Q3"),
        (dt.date(2025, 12, 31), 2025, "Q4"),
        (dt.date(2026, 3, 31), 2026, "Q1"),
        (dt.date(2026, 6, 30), 2026, "Q2"),
    ]:
        session.add(_row(cik=cik, period_end=end, fiscal_year=fy,
                         fiscal_period=fp, revenue=1.0))
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    mock_edgar.submissions.return_value = _middle_gap_submissions()

    svc = FinancialsService(edgar_client=mock_edgar, session=session)
    svc.fetch_and_persist = MagicMock()

    assert svc.refresh_financials_if_stale("SKYD") is False
    svc.fetch_and_persist.assert_not_called()


# ── ingested-but-unextractable gap acknowledgment (batch 48) ─────────────────

def test_missing_in_window_quarters_lists_gaps() -> None:
    from tickerlens.services.financials import _missing_in_window_quarters

    stored = [  # 2025-09-30 missing from inside the window
        "2024-09-30", "2024-12-31", "2025-03-31", "2025-06-30",
        "2025-12-31", "2026-03-31", "2026-06-30",
    ]
    assert _missing_in_window_quarters(
        _middle_gap_submissions(), stored, "2026-08-04"
    ) == ["2025-09-30"]


def test_missing_in_window_quarters_dedupes_amendments() -> None:
    """A 10-K and its 10-K/A share a reportDate — one gap, not two."""
    from tickerlens.services.financials import _missing_in_window_quarters

    submissions = {"filings": {"recent": {
        "form": ["10-K/A", "10-K", "10-Q"],
        "filingDate": ["2026-04-24", "2026-02-25", "2026-08-04"],
        "reportDate": ["2025-12-31", "2025-12-31", "2026-06-30"],
    }}}
    stored = ["2025-06-30", "2025-09-30", "2026-03-31", "2026-06-30"]
    assert _missing_in_window_quarters(
        submissions, stored, "2026-08-04"
    ) == ["2025-12-31"]


def test_missing_in_window_quarters_honors_skip_list() -> None:
    from tickerlens.services.financials import (
        _has_unprocessed_quarter_in_window,
        _missing_in_window_quarters,
    )

    stored = [
        "2024-09-30", "2024-12-31", "2025-03-31", "2025-06-30",
        "2025-12-31", "2026-03-31", "2026-06-30",
    ]
    subs = _middle_gap_submissions()
    assert _missing_in_window_quarters(
        subs, stored, "2026-08-04", {"2025-09-30"}
    ) == []
    assert _has_unprocessed_quarter_in_window(
        subs, stored, "2026-08-04", {"2025-09-30"}
    ) is False
    # ...but an un-acknowledged gap still fires
    assert _has_unprocessed_quarter_in_window(subs, stored, "2026-08-04") is True


def test_read_skipped_quarters_tolerant() -> None:
    from tickerlens.services.financials import _read_skipped_quarters

    assert _read_skipped_quarters(None) == set()
    assert _read_skipped_quarters("") == set()
    assert _read_skipped_quarters("not-json{{{") == set()
    assert _read_skipped_quarters("42") == set()
    assert _read_skipped_quarters('["2025-09-30", 7, null]') == {"2025-09-30"}


def test_revenue_duration_facts_scoped_to_revenue_chain() -> None:
    """Only USD duration facts on the generic revenue chain count — a filing
    can be partially ingested (APLD's FY2026 10-K: 153 duration facts, no
    annual revenue fact), so any-tag facts must not read as "the extractor
    had its chance"."""
    from tickerlens.services.financials import _revenue_duration_facts

    companyfacts = {"facts": {"us-gaap": {
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
            {"start": "2025-08-08", "end": "2025-09-30", "val": 4121000000},
            {"start": None, "end": "2025-09-30", "val": 999},  # instant: ignored
        ]}},
        "CostOfRevenue": {"units": {"USD": [
            {"start": "2025-06-01", "end": "2026-05-31", "val": 396858000},
        ]}},
    }, "dei": {}}}
    assert _revenue_duration_facts(companyfacts) == {"2025-09-30": [(53, "RevenueFromContractWithCustomerExcludingAssessedTax")]}
    assert _revenue_duration_facts({"facts": {}}) == {}
    assert _revenue_duration_facts({}) == {}


def _skyd_structural_companyfacts() -> dict:
    """SKYD shape: 53-day stub Q3'25 + FY2025 annual with stubbed 9M."""
    rev = "RevenueFromContractWithCustomerExcludingAssessedTax"
    return {"facts": {"us-gaap": {rev: {"units": {"USD": [
        {"start": "2025-08-08", "end": "2025-09-30", "val": 4121000000},   # 53d stub
        {"start": "2025-01-01", "end": "2025-12-31", "val": 12269000000},  # 364d annual
        {"start": "2026-04-01", "end": "2026-06-30", "val": 6913000000},   # 90d quarter
    ]}}}, "dei": {}}}


def test_is_structural_gap_stub_quarter() -> None:
    from tickerlens.services.financials import _is_structural_gap, _revenue_duration_facts

    rf = _revenue_duration_facts(_skyd_structural_companyfacts())
    assert _is_structural_gap(rf, _middle_gap_submissions(), "2025-09-30") is True
    # a proper quarter-length fact is extractable, not structural
    assert _is_structural_gap(rf, _middle_gap_submissions(), "2026-06-30") is False


def test_is_structural_gap_annual_with_stub_9m() -> None:
    """SKYD's 10-K gap: annual fact ingested, 9M window holds only the 53-day
    stub — FY−9M can never derive Q4."""
    from tickerlens.services.financials import _is_structural_gap, _revenue_duration_facts

    rf = _revenue_duration_facts(_skyd_structural_companyfacts())
    assert _is_structural_gap(rf, _middle_gap_submissions(), "2025-12-31") is True


def test_is_structural_gap_false_when_revenue_missing() -> None:
    """APLD shape: 153 non-revenue duration facts ingested, but the annual
    revenue fact still missing — the retry loop must stay alive."""
    from tickerlens.services.financials import _is_structural_gap, _revenue_duration_facts

    companyfacts = {"facts": {"us-gaap": {
        "CostOfRevenue": {"units": {"USD": [
            {"start": "2025-06-01", "end": "2026-05-31", "val": 396858000},
        ]}},
    }, "dei": {}}}
    rf = _revenue_duration_facts(companyfacts)
    assert _is_structural_gap(rf, _middle_gap_submissions(), "2026-05-31") is False


def test_is_structural_gap_false_when_9m_proper() -> None:
    """Annual ingested and a proper 240–290d 9M fact present — Q4 should
    derive, so a missing quarter here is not structural (keep retrying)."""
    from tickerlens.services.financials import _is_structural_gap, _revenue_duration_facts

    rev = "RevenueFromContractWithCustomerExcludingAssessedTax"
    companyfacts = {"facts": {"us-gaap": {rev: {"units": {"USD": [
        {"start": "2025-01-01", "end": "2025-12-31", "val": 12269000000},  # 364d
        {"start": "2025-01-01", "end": "2025-09-30", "val": 8000000000},   # 272d 9M
    ]}}}, "dei": {}}}
    rf = _revenue_duration_facts(companyfacts)
    assert _is_structural_gap(rf, _middle_gap_submissions(), "2025-12-31") is False


def test_prior_quarter_report_date() -> None:
    from tickerlens.services.financials import _prior_quarter_report_date

    assert _prior_quarter_report_date(_middle_gap_submissions(), "2025-12-31") == "2025-09-30"
    assert _prior_quarter_report_date(_middle_gap_submissions(), "2024-01-01") is None
    assert _prior_quarter_report_date({}, "2025-12-31") is None


def _stub_companyfacts() -> dict:
    """SKYD shape: the merger-stub quarter's facts ARE ingested."""
    return {"facts": {"us-gaap": {"RevenueFromContractWithCustomerExcludingAssessedTax": {
        "units": {"USD": [
            {"start": "2025-08-08", "end": "2025-09-30", "val": 4121000000,
             "filed": "2025-11-10", "form": "10-Q"},
        ]}}}, "dei": {}}}


def _unsubmitted_companyfacts() -> dict:
    """Batch-37 shape: the missing quarter's facts are NOT ingested yet."""
    return {"facts": {"us-gaap": {"RevenueFromContractWithCustomerExcludingAssessedTax": {
        "units": {"USD": [
            {"start": "2026-04-01", "end": "2026-06-30", "val": 6913000000,
             "filed": "2026-08-04", "form": "10-Q"},
        ]}}}, "dei": {}}}


def _gap_company(session: Session, cik: str = "0002041610") -> None:
    company = _company(cik=cik, name="Skydance Corp", ticker="SKYD")
    company.xbrl_filings_processed = "2026-08-04"
    session.add(company)
    for end, fy, fp in [
        (dt.date(2024, 9, 30), 2025, "Q3"),
        (dt.date(2024, 12, 31), 2025, "Q4"),
        (dt.date(2025, 3, 31), 2025, "Q1"),
        (dt.date(2025, 6, 30), 2025, "Q2"),
        # 2025-09-30 (Q3) missing: filed 2025-11-10
        (dt.date(2025, 12, 31), 2025, "Q4"),
        (dt.date(2026, 3, 31), 2026, "Q1"),
        (dt.date(2026, 6, 30), 2026, "Q2"),
    ]:
        session.add(_row(cik=cik, period_end=end, fiscal_year=fy,
                         fiscal_period=fp, revenue=1.0))
    session.commit()


def test_refresh_acknowledges_ingested_stub_then_stays_quiet(
    session: Session, _fresh_filings_state
) -> None:
    """The batch-48 futility fix: a middle-gap refire that still yields no
    quarter — while the filing's facts ARE ingested (stub period) — records
    the reportDate as acknowledged; the next check stays quiet instead of
    re-pulling every 6h forever."""
    _gap_company(session)
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = "0002041610"
    mock_edgar.submissions.return_value = _middle_gap_submissions()
    mock_edgar.companyfacts.return_value = _stub_companyfacts()

    svc = FinancialsService(edgar_client=mock_edgar, session=session)
    svc.fetch_and_persist = MagicMock()  # refire yields no new quarter
    svc._enrich_press_release_highlights = MagicMock()

    assert svc.refresh_financials_if_stale("SKYD") is True
    assert set(json.loads(
        session.get(Company, "0002041610").xbrl_skipped_quarters
    )) == {"2025-09-30"}

    # Simulate the next 6h check (fresh in-memory state, as after a restart).
    from tickerlens.services import financials as fin_mod
    with fin_mod._filings_check_lock:
        fin_mod._filings_check_state.clear()
    svc.fetch_and_persist.reset_mock()

    assert svc.refresh_financials_if_stale("SKYD") is False
    svc.fetch_and_persist.assert_not_called()


def test_refresh_keeps_retrying_when_facts_not_ingested(
    session: Session, _fresh_filings_state
) -> None:
    """The batch-37 ingestion lag must NOT be acknowledged: with no facts at
    the missing reportDate, the retry loop stays alive."""
    _gap_company(session)
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = "0002041610"
    mock_edgar.submissions.return_value = _middle_gap_submissions()
    mock_edgar.companyfacts.return_value = _unsubmitted_companyfacts()

    svc = FinancialsService(edgar_client=mock_edgar, session=session)
    svc.fetch_and_persist = MagicMock()
    svc._enrich_press_release_highlights = MagicMock()

    assert svc.refresh_financials_if_stale("SKYD") is True
    assert session.get(Company, "0002041610").xbrl_skipped_quarters is None

    from tickerlens.services import financials as fin_mod
    with fin_mod._filings_check_lock:
        fin_mod._filings_check_state.clear()

    assert svc.refresh_financials_if_stale("SKYD") is True
    assert svc.fetch_and_persist.call_count == 2


def test_refresh_keeps_retrying_on_partial_ingestion(
    session: Session, _fresh_filings_state
) -> None:
    """APLD shape: the 10-K's facts are partially ingested (153 non-revenue
    duration facts) but the annual revenue fact is still missing. The
    revenue-chain-scoped check must NOT acknowledge — the retry loop stays
    alive until SEC finishes ingesting."""
    _gap_company(session)
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = "0002041610"
    mock_edgar.submissions.return_value = _middle_gap_submissions()
    mock_edgar.companyfacts.return_value = {"facts": {"us-gaap": {
        "CostOfRevenue": {"units": {"USD": [
            {"start": "2025-07-01", "end": "2025-09-30", "val": 1000},
        ]}},
    }, "dei": {}}}

    svc = FinancialsService(edgar_client=mock_edgar, session=session)
    svc.fetch_and_persist = MagicMock()
    svc._enrich_press_release_highlights = MagicMock()

    assert svc.refresh_financials_if_stale("SKYD") is True
    assert session.get(Company, "0002041610").xbrl_skipped_quarters is None

    from tickerlens.services import financials as fin_mod
    with fin_mod._filings_check_lock:
        fin_mod._filings_check_state.clear()

    assert svc.refresh_financials_if_stale("SKYD") is True
    assert svc.fetch_and_persist.call_count == 2


def test_fetch_and_persist_pull_uses_live_edgar(
    session: Session, _fresh_filings_state
) -> None:
    """A deliberate pull must bypass the disk cache: it runs precisely
    because the freshness check suspects new data, so a cached snapshot
    would make the pull a no-op."""
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = "0000320193"
    mock_edgar.submissions.return_value = _SUBMISSIONS
    mock_edgar.companyfacts.return_value = _MINIMAL_COMPANYFACTS

    svc = FinancialsService(edgar_client=mock_edgar, session=session)
    svc.fetch_and_persist("AAPL", periods=4, session=session)

    mock_edgar.submissions.assert_called_with("0000320193", fresh=True)
    mock_edgar.companyfacts.assert_called_with("0000320193", fresh=True)


# ── quarters_count / partial-year disclosure (batch 39) ───────────────────────

def test_build_yearly_period_counts_stored_quarters() -> None:
    rows = [
        _row(period_end=dt.date(2025, 3, 31), fiscal_year=2025, fiscal_period="Q1", revenue=95.0),
        _row(period_end=dt.date(2025, 6, 30), fiscal_year=2025, fiscal_period="Q2", revenue=85.0),
        _row(period_end=dt.date(2024, 12, 31), fiscal_year=2024, fiscal_period="Q4", revenue=119.0),
        _row(period_end=dt.date(2024, 9, 30), fiscal_year=2024, fiscal_period="Q3", revenue=111.0),
        _row(period_end=dt.date(2024, 6, 30), fiscal_year=2024, fiscal_period="Q2", revenue=100.0),
        _row(period_end=dt.date(2024, 3, 31), fiscal_year=2024, fiscal_period="Q1", revenue=90.0),
    ]
    partial = _build_yearly_period(rows, selected_year=2025, default_year=2025)
    assert partial.quarters_count == 2  # only Q1+Q2 reported — the honesty signal
    full = _build_yearly_period(rows, selected_year=2024, default_year=2024)
    assert full.quarters_count == 4


def test_build_quarterly_period_counts_one_quarter() -> None:
    rows = [
        _row(period_end=dt.date(2025, 3, 31), fiscal_year=2025, fiscal_period="Q1", revenue=95.0),
        _row(period_end=dt.date(2025, 6, 30), fiscal_year=2025, fiscal_period="Q2", revenue=100.0),
    ]
    data, _ = _build_quarterly_period(rows, "Q2 FY2025", rows[-1])
    assert data.quarters_count == 1


def test_render_period_csv_partial_year_note() -> None:
    from tickerlens.services.financials import (
        BalanceSheet,
        BalanceSheetChange,
        KPIChange,
        KPISnapshot,
        PeriodData,
        render_period_csv,
    )

    def period(**kw) -> PeriodData:
        base = dict(
            label="FY2025", period_end=dt.date(2025, 6, 30), fiscal_year=2025,
            fiscal_period=None, kpi=KPISnapshot(), yoy=KPIChange(), qoq=None,
            balance_sheet=BalanceSheet(), balance_sheet_yoy=BalanceSheetChange(),
            balance_sheet_qoq=None,
        )
        base.update(kw)
        return PeriodData(**base)

    partial_csv = render_period_csv("ARCC", "ARCC", period(quarters_count=2))
    assert "# Period note,partial year — 2 of 4 quarters reported" in partial_csv

    full_csv = render_period_csv("ARCC", "ARCC", period(quarters_count=4))
    assert "# Period note" not in full_csv

    # Quarterly periods never get the note (they are single quarters by definition).
    quarterly_csv = render_period_csv(
        "Apple Inc.", "AAPL",
        period(label="Q2 FY2025", fiscal_period="Q2", quarters_count=1),
    )
    assert "# Period note" not in quarterly_csv


def test_get_detail_backfill_triggers_when_only_guidance_missing(session: Session) -> None:
    """Batch-50 regression: the lazy disclosure backfill trigger covered only
    press_release_highlights, so rows with highlights filled but guidance NULL
    (AVGO/INTU in the wild) never got their guidance backfilled."""
    from unittest.mock import MagicMock, patch

    cik = "0000320193"
    session.add(_company(cik=cik))
    q3 = _row(cik=cik, period_end=dt.date(2025, 9, 28), fiscal_year=2025,
              fiscal_period="Q3", revenue=40_100)
    q3.press_release_highlights = "Highlights already filled."
    q3.press_release_source = "Earnings release Q3 FY2025"
    session.add(q3)
    session.commit()

    html_with_guidance = (
        "<html><head><title>EX-99.1</title></head><body>"
        "<h1>Acme Corp Reports Third Quarter 2025 Results</h1>"
        "<h2>Full Year Fiscal 2026 Guidance</h2>"
        "<p>Revenue is expected to be between $45.0 billion and $46.5 billion for fiscal 2026, "
        "with operating margin expansion across every segment of the business portfolio.</p>"
        "<p>GAAP gross margin is expected to be approximately 47.0 percent for the full year.</p>"
        "<h2>Condensed Consolidated Statements of Operations</h2>"
        "<p>Revenue: $40,100</p>"
        "</body></html>"
    )
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    p1, p2, p3, discover_mock = _enrich_mocks(
        mock_edgar, [_er_period(period_end=dt.date(2025, 9, 28))]
    )
    # _enrich_mocks sets a highlights-only fixture; override with a release
    # that also carries a guidance section.
    mock_edgar.fetch_text.return_value = html_with_guidance
    try:
        svc = FinancialsService(edgar_client=mock_edgar, session=session)
        ctx = svc.get_detail("AAPL", selected_quarter="Q3 FY2025")
    finally:
        p1.stop(); p2.stop(); p3.stop()

    assert discover_mock.called, "backfill must trigger when guidance is missing"
    assert ctx.management_guidance is not None
    assert "$45.0 billion" in ctx.management_guidance
    # Previously-good highlights must not be wiped or overwritten.
    assert ctx.press_release_highlights == "Highlights already filled."


# ── redeemable NCI mezzanine row (batch 59) ───────────────────────────────────

def test_range_table_includes_mezzanine_row_when_any_quarter_has_value(session: Session) -> None:
    session.add(_company())
    for end, fy, fp, rev, mezz in [
        (dt.date(2024, 9, 30), 2024, "Q3", 91_000, None),
        (dt.date(2024, 12, 31), 2024, "Q4", 119_575, None),
        (dt.date(2025, 3, 31), 2025, "Q1", 95_359, 4_917.0),
        (dt.date(2025, 6, 30), 2025, "Q2", 85_777, 4_920.0),
    ]:
        session.add(_row(period_end=end, fiscal_year=fy, fiscal_period=fp,
                         revenue=rev, redeemable_nci=mezz))
    session.commit()
    ctx = _svc_with_mock(session).get_detail(
        "AAPL", granularity="quarterly",
        chart_from="Q4 FY2024", chart_to="Q2 FY2025",
    )
    rt = ctx.range_table
    assert rt is not None
    mezz_rows = [r for r in rt.rows if r.label == "Redeemable NCI (mezzanine)"]
    assert len(mezz_rows) == 1
    assert mezz_rows[0].values == [None, 4_917.0, 4_920.0]
    # Mezzanine sits between liabilities and equity, like the balance sheet.
    labels = [r.label for r in rt.rows if r.section == "balance"]
    assert labels.index("Redeemable NCI (mezzanine)") == labels.index("Total Liabilities") + 1


def test_range_table_drops_mezzanine_row_when_all_none(session: Session) -> None:
    _seed_five_quarters(session)
    ctx = _svc_with_mock(session).get_detail(
        "AAPL", granularity="quarterly",
        chart_from="Q4 FY2024", chart_to="Q2 FY2025",
    )
    rt = ctx.range_table
    assert rt is not None
    assert all(r.label != "Redeemable NCI (mezzanine)" for r in rt.rows)
    assert len([r for r in rt.rows if r.section == "balance"]) == 4


def test_to_bs_carries_redeemable_nci(session: Session) -> None:
    from tickerlens.services.financials import _to_bs
    # Realistic dollar magnitudes: the third-leg gate's $2M rounding floor
    # is calibrated for real filings (values in dollars), not toy scales.
    r = _row(period_end=dt.date(2025, 3, 31), fiscal_year=2025, fiscal_period="Q1",
             total_assets=60_792_000_000.0, total_liabilities=24_587_000_000.0,
             total_equity=31_288_000_000.0, redeemable_nci=4_917_000_000.0)
    bs = _to_bs(r)
    assert bs.redeemable_nci == 4_917_000_000.0
    assert bs.total_liabilities + bs.redeemable_nci + bs.total_equity == bs.total_assets


def test_compare_deltas_include_redeemable_nci() -> None:
    from tickerlens.services.financials import (
        BalanceSheet,
        BalanceSheetChange,
        KPISnapshot,
        KPIChange,
        PeriodData,
        _compare_periods,
    )

    def _pd(mezz: float | None) -> PeriodData:
        return PeriodData(
            label="Q1 FY2026", period_end=dt.date(2026, 3, 31),
            fiscal_year=2026, fiscal_period="Q1",
            kpi=KPISnapshot(), yoy=KPIChange(), qoq=None,
            balance_sheet=BalanceSheet(redeemable_nci=mezz),
            balance_sheet_yoy=BalanceSheetChange(), balance_sheet_qoq=None,
        )

    deltas = _compare_periods(_pd(4_917.0), _pd(4_000.0))
    assert deltas.redeemable_nci.absolute == 917.0
    # None on either side -> empty delta, never a crash.
    assert _compare_periods(_pd(None), _pd(4_000.0)).redeemable_nci.absolute is None
