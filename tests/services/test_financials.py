from __future__ import annotations

import datetime as dt
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
    mock_edgar.fetch_text.assert_not_called()


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
    session.add_all([q3, q4])
    session.commit()

    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    svc = FinancialsService(edgar_client=mock_edgar, session=session)

    ctx = svc.get_detail("AAPL", selected_quarter="Q3 FY2025")
    assert ctx.press_release_highlights == "Q3 highlights"
    assert ctx.press_release_source == "Earnings release Q3 FY2025"

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
