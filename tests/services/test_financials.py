from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
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
        _row(period_end=dt.date(2025, 3, 31),  fiscal_year=2025, fiscal_period="Q1", revenue=95.0),
        _row(period_end=dt.date(2025, 6, 30),  fiscal_year=2025, fiscal_period="Q2", revenue=85.0),
    ]
    data = _build_yearly_period(rows, selected_year=2025, default_year=2025)
    prior_rev = 90.0 + 80.0
    current_rev = 95.0 + 85.0
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
