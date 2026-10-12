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
    FinancialsService,
    _join_and,
    _mdy,
    _pending_filing_candidates,
    _pending_filing_note,
    _quarter_label_for_report_date,
)


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    return factory()


def _company(
    cik: str = "0000896159",
    ticker: str = "CB",
    marker: str | None = "2026-04-28",
    fiscal_year_end: str | None = "1231",
) -> Company:
    c = Company()
    c.cik = cik
    c.name = "Chubb Ltd"
    c.ticker = ticker
    c.fiscal_year_end = fiscal_year_end
    c.xbrl_filings_processed = marker
    c.updated_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    return c


def _row(
    *,
    cik: str = "0000896159",
    period_end: dt.date,
    fiscal_year: int,
    fiscal_period: str,
    revenue: float | None = None,
    net_income: float | None = None,
    eps_diluted: float | None = None,
    free_cash_flow: float | None = None,
) -> QuarterlyFinancial:
    r = QuarterlyFinancial()
    r.cik = cik
    r.period_end = period_end
    r.fiscal_year = fiscal_year
    r.fiscal_period = fiscal_period
    r.revenue = revenue
    r.net_income = net_income
    r.eps_diluted = eps_diluted
    r.free_cash_flow = free_cash_flow
    r.updated_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    return r


def _subs(*triples: tuple[str, str, str]) -> dict:
    """(form, filingDate, reportDate) triples -> submissions feed."""
    return {
        "filings": {
            "recent": {
                "form": [t[0] for t in triples],
                "filingDate": [t[1] for t in triples],
                "reportDate": [t[2] for t in triples],
            }
        }
    }


def _facts(*ends: str) -> dict:
    """companyfacts with 90-day USD Revenues facts at the given end dates."""
    facts = []
    for end in ends:
        start = (dt.date.fromisoformat(end) - dt.timedelta(days=90)).isoformat()
        facts.append({"start": start, "end": end, "val": 1_000_000, "form": "10-Q"})
    return {"facts": {"us-gaap": {"Revenues": {"units": {"USD": facts}}}}}


# ── small formatters ──────────────────────────────────────────────────────────

def test_mdy_formats_iso_date() -> None:
    assert _mdy("2026-07-28") == "Jul 28, 2026"
    assert _mdy("not-a-date") == "not-a-date"


def test_join_and() -> None:
    assert _join_and(["a"]) == "a"
    assert _join_and(["a", "b"]) == "a and b"
    assert _join_and(["a", "b", "c"]) == "a, b and c"


# ── _quarter_label_for_report_date ────────────────────────────────────────────

def test_quarter_label_walks_from_newest_row() -> None:
    # Dec year-end filer; newest stored row Q1 FY2026 ended 2026-03-31.
    label = _quarter_label_for_report_date(
        dt.date(2026, 6, 30), "1231",
        dt.date(2026, 3, 31), (2026, "Q1"),
    )
    assert label == "Q2 FY2026"


def test_quarter_label_falls_back_to_fiscal_year_end() -> None:
    # Sep year-end filer (e.g. Visa): 2026-06-30 is Q3 FY2026.
    label = _quarter_label_for_report_date(
        dt.date(2026, 6, 30), "0930", None, None,
    )
    assert label == "Q3 FY2026"


def test_quarter_label_none_when_unsafe() -> None:
    assert _quarter_label_for_report_date(dt.date(2026, 6, 30), None, None, None) is None


# ── _pending_filing_candidates ────────────────────────────────────────────────

def test_candidates_newer_than_marker_without_quarter() -> None:
    subs = _subs(("10-Q", "2026-07-28", "2026-06-30"), ("10-Q", "2026-04-28", "2026-03-31"))
    out = _pending_filing_candidates(subs, ["2026-03-31"], "2026-04-28", set())
    assert out == [("10-Q", "2026-07-28", "2026-06-30")]


def test_candidates_ignores_stored_and_skipped_quarters() -> None:
    subs = _subs(("10-Q", "2026-07-28", "2026-06-30"))
    assert _pending_filing_candidates(subs, ["2026-06-30"], "2026-04-28", set()) == []
    assert _pending_filing_candidates(subs, ["2026-03-31"], "2026-04-28", {"2026-06-30"}) == []


def test_candidates_ignores_non_quarterly_forms() -> None:
    subs = _subs(("8-K", "2026-07-21", "2026-06-30"))
    assert _pending_filing_candidates(subs, ["2026-03-31"], "2026-04-28", set()) == []


def test_candidates_middle_gap_at_or_before_marker() -> None:
    # Batch-44 shape: a 10-Q older than the marker whose quarter never
    # landed, inside the stored window.
    subs = _subs(
        ("10-Q", "2026-07-28", "2026-06-30"),
        ("10-Q", "2026-04-28", "2026-03-31"),
    )
    out = _pending_filing_candidates(
        subs, ["2025-12-31", "2026-06-30"], "2026-07-28", set()
    )
    assert out == [("10-Q", "2026-04-28", "2026-03-31")]


def test_candidates_none_without_marker() -> None:
    subs = _subs(("10-Q", "2026-07-28", "2026-06-30"))
    assert _pending_filing_candidates(subs, ["2026-03-31"], None, set()) == []


# ── _pending_filing_note ──────────────────────────────────────────────────────

def _note_kwargs(**over):
    kw = dict(
        fiscal_year_end="1231",
        newest_end=dt.date(2026, 3, 31),
        newest_label=(2026, "Q1"),
    )
    kw.update(over)
    return kw


def test_note_for_ingestion_lag() -> None:
    # CB shape: Q2'26 10-Q filed 2026-07-28, no revenue facts ingested.
    subs = _subs(("10-Q", "2026-07-28", "2026-06-30"), ("10-Q", "2026-04-28", "2026-03-31"))
    note = _pending_filing_note(
        subs, _facts(), ["2026-03-31"], "2026-04-28", set(), **_note_kwargs()
    )
    assert note is not None
    assert "Q2 FY2026" in note
    assert "10-Q filed Jul 28, 2026" in note
    assert "EDGAR" in note
    assert "Q1 FY2026" in note  # the quarter still shown


def test_note_names_multiple_pending_quarters() -> None:
    # C shape: Q1 and Q2 10-Qs filed, neither ingested.
    subs = _subs(
        ("10-Q", "2026-08-06", "2026-06-30"),
        ("10-Q", "2026-05-07", "2026-03-31"),
        ("10-K", "2026-02-20", "2025-12-31"),
    )
    note = _pending_filing_note(
        subs,
        _facts(),
        ["2025-12-31"],
        "2026-02-20",
        set(),
        fiscal_year_end="1231",
        newest_end=dt.date(2025, 12, 31),
        newest_label=(2025, "Q4"),
    )
    assert note is not None
    assert "Q1 FY2026 and Q2 FY2026" in note
    assert "Q4 FY2025" in note


def test_note_none_when_quarter_present() -> None:
    subs = _subs(("10-Q", "2026-07-28", "2026-06-30"))
    note = _pending_filing_note(
        subs, _facts(), ["2026-03-31", "2026-06-30"], "2026-04-28", set(),
        **_note_kwargs(),
    )
    assert note is None


def test_note_none_when_facts_ingested_but_no_quarter() -> None:
    # Not EDGAR lag — the extractor had its chance; a defect-hunt question.
    subs = _subs(("10-Q", "2026-07-28", "2026-06-30"), ("10-Q", "2026-04-28", "2026-03-31"))
    note = _pending_filing_note(
        subs, _facts("2026-06-30"), ["2026-03-31"], "2026-04-28", set(),
        **_note_kwargs(),
    )
    assert note is None


def test_note_none_for_structural_stub_gap() -> None:
    # Batch-48 shape: 53-day stub revenue fact ingested, no full quarter.
    end = "2026-06-30"
    start = (dt.date.fromisoformat(end) - dt.timedelta(days=53)).isoformat()
    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {"USD": [{"start": start, "end": end, "val": 5, "form": "10-Q"}]}
                }
            }
        }
    }
    subs = _subs(("10-Q", "2026-07-28", "2026-06-30"), ("10-Q", "2026-04-28", "2026-03-31"))
    note = _pending_filing_note(
        subs, facts, ["2026-03-31"], "2026-04-28", set(), **_note_kwargs()
    )
    assert note is None


# ── _update_pending_filing_note ───────────────────────────────────────────────

def _svc_with(session: Session, submissions: dict, companyfacts: dict) -> FinancialsService:
    mock_edgar = MagicMock()
    mock_edgar.submissions.return_value = submissions
    mock_edgar.companyfacts.return_value = companyfacts
    return FinancialsService(edgar_client=mock_edgar, session=session)


def test_update_persists_note_for_lagging_filing(session: Session) -> None:
    cik = "0000896159"
    session.add(_company(cik=cik))
    session.add(_row(cik=cik, period_end=dt.date(2026, 3, 31),
                     fiscal_year=2026, fiscal_period="Q1"))
    session.commit()
    subs = _subs(("10-Q", "2026-07-28", "2026-06-30"), ("10-Q", "2026-04-28", "2026-03-31"))
    svc = _svc_with(session, subs, _facts())

    svc._update_pending_filing_note("CB", cik, subs)
    session.refresh(session.get(Company, cik))
    note = session.get(Company, cik).pending_filing_note
    assert note is not None and "Q2 FY2026" in note


def test_update_clears_note_once_quarter_lands(session: Session) -> None:
    cik = "0000896159"
    company = _company(cik=cik, marker="2026-07-28")
    company.pending_filing_note = "stale note"
    session.add(company)
    session.add(_row(cik=cik, period_end=dt.date(2026, 3, 31),
                     fiscal_year=2026, fiscal_period="Q1"))
    session.add(_row(cik=cik, period_end=dt.date(2026, 6, 30),
                     fiscal_year=2026, fiscal_period="Q2"))
    session.commit()
    subs = _subs(("10-Q", "2026-07-28", "2026-06-30"), ("10-Q", "2026-04-28", "2026-03-31"))
    svc = _svc_with(session, subs, _facts("2026-06-30"))

    svc._update_pending_filing_note("CB", cik, subs)
    session.refresh(session.get(Company, cik))
    assert session.get(Company, cik).pending_filing_note is None


def test_update_does_not_rewrite_unchanged_note(session: Session) -> None:
    cik = "0000896159"
    session.add(_company(cik=cik))
    session.add(_row(cik=cik, period_end=dt.date(2026, 3, 31),
                     fiscal_year=2026, fiscal_period="Q1"))
    session.commit()
    subs = _subs(("10-Q", "2026-07-28", "2026-06-30"))
    svc = _svc_with(session, subs, _facts("2026-06-30", "2026-03-31"))

    svc._update_pending_filing_note("CB", cik, subs)
    assert session.get(Company, cik).pending_filing_note is None


def test_update_never_raises(session: Session) -> None:
    mock_edgar = MagicMock()
    mock_edgar.companyfacts.side_effect = RuntimeError("EDGAR down")
    svc = FinancialsService(edgar_client=mock_edgar, session=session)
    svc._update_pending_filing_note("CB", "0000896159", {})  # must not raise


# ── get_overview plumbing + template ──────────────────────────────────────────

def _overview_kwargs(**over):
    import datetime as _dt
    from tickerlens.services.financials import KPIChange, KPISnapshot
    kw = dict(
        cik="0000896159",
        name="Chubb Ltd",
        ticker="CB",
        latest_label="Q1 FY2026",
        latest_period_end=_dt.date(2026, 3, 31),
        latest_kpi=KPISnapshot(),
        yoy=KPIChange(),
        ttm_kpi=KPISnapshot(),
        ttm_quarters=4,
    )
    kw.update(over)
    return kw


def test_get_overview_surfaces_pending_note(session: Session) -> None:
    cik = "0000896159"
    company = _company(cik=cik)
    company.pending_filing_note = "Q2 FY2026 results pending"
    session.add(company)
    session.add(_row(cik=cik, period_end=dt.date(2026, 3, 31),
                     fiscal_year=2026, fiscal_period="Q1",
                     revenue=1_000.0, net_income=100.0,
                     eps_diluted=1.0, free_cash_flow=50.0))
    session.commit()
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    svc = FinancialsService(edgar_client=mock_edgar, session=session)
    overview = svc.get_overview("CB")
    assert overview.pending_filing_note == "Q2 FY2026 results pending"


def _render_overview(note: str | None) -> str:
    from tickerlens.routes.company import templates
    from tickerlens.services.financials import CompanyOverview
    ov = CompanyOverview(**_overview_kwargs(pending_filing_note=note))
    t = templates.get_template("company/overview.html")
    return t.render({
        "request": MagicMock(), "overview": ov, "valuation": None,
        "signal_change": None, "watching": False, "note": None,
        "tags": [], "also_trades_as": [], "peers": [], "ai_analysis": None,
    })


def test_template_renders_pending_note() -> None:
    html = _render_overview("Q2 FY2026 results (10-Q filed Jul 28, 2026) aren't in EDGAR's data feed yet")
    assert "aren&#39;t in EDGAR&#39;s data feed yet" in html or "aren't in EDGAR's data feed yet" in html


def test_template_omits_note_when_none() -> None:
    html = _render_overview(None)
    assert "data feed yet" not in html


# ── get_detail plumbing + detail partial (batch 55) ───────────────────────────

def _detail_ctx_kwargs(**over):
    from tickerlens.services.financials import (
        BalanceSheet,
        BalanceSheetChange,
        KPIChange,
        KPISnapshot,
        PeriodData,
    )
    cur = PeriodData(
        label="Q1 FY2026",
        period_end=dt.date(2026, 3, 31),
        fiscal_year=2026,
        fiscal_period="Q1",
        kpi=KPISnapshot(revenue=1_000.0, net_income=100.0, eps_diluted=1.0,
                        free_cash_flow=50.0),
        yoy=KPIChange(),
        qoq=None,
        balance_sheet=BalanceSheet(),
        balance_sheet_yoy=BalanceSheetChange(),
        balance_sheet_qoq=None,
    )
    kw = dict(
        cik="0000896159", name="Chubb Ltd", ticker="CB", sector="Insurance",
        last_price=295.0, market_cap=68e9,
        granularity="quarterly", quarter_options=["Q1 FY2026"],
        year_options=[2026], selected_quarter="Q1 FY2026", selected_year=2026,
        current=cur, chart_labels=["Q1 FY2026"], chart_revenue=[1_000.0],
        chart_eps=[1.0],
    )
    kw.update(over)
    return kw


def test_get_detail_surfaces_pending_note(session: Session) -> None:
    cik = "0000896159"
    company = _company(cik=cik)
    company.pending_filing_note = "Q2 FY2026 results pending"
    session.add(company)
    session.add(_row(cik=cik, period_end=dt.date(2026, 3, 31),
                     fiscal_year=2026, fiscal_period="Q1",
                     revenue=1_000.0, net_income=100.0,
                     eps_diluted=1.0, free_cash_flow=50.0))
    session.commit()
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    from tickerlens.services.financials import FinancialsService
    svc = FinancialsService(edgar_client=mock_edgar, session=session)
    ctx = svc.get_detail("CB")
    assert ctx.pending_filing_note == "Q2 FY2026 results pending"


def test_get_detail_note_none_by_default(session: Session) -> None:
    cik = "0000896159"
    session.add(_company(cik=cik))
    session.add(_row(cik=cik, period_end=dt.date(2026, 3, 31),
                     fiscal_year=2026, fiscal_period="Q1",
                     revenue=1_000.0, net_income=100.0,
                     eps_diluted=1.0, free_cash_flow=50.0))
    session.commit()
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    from tickerlens.services.financials import FinancialsService
    svc = FinancialsService(edgar_client=mock_edgar, session=session)
    assert svc.get_detail("CB").pending_filing_note is None


def _render_detail_partial(note: str | None) -> str:
    from tickerlens.routes.company import templates
    from tickerlens.services.financials import DetailContext
    ctx = DetailContext(**_detail_ctx_kwargs(pending_filing_note=note))
    t = templates.get_template("partials/detail_data.html")
    return t.render({"request": MagicMock(), "ctx": ctx})


def test_detail_partial_renders_pending_note() -> None:
    html = _render_detail_partial(
        "Q2 FY2026 results (10-Q filed Jul 28, 2026) aren't in EDGAR's data feed yet")
    assert "aren&#39;t in EDGAR&#39;s data feed yet" in html or "aren't in EDGAR's data feed yet" in html
    assert "amber-950/40" in html


def test_detail_partial_omits_note_when_none() -> None:
    html = _render_detail_partial(None)
    assert "data feed yet" not in html
    # The amber note block is the only amber-950/40 in the partial.
    assert "amber-950/40" not in html


# ── get_compare plumbing + compare page (batch 56) ────────────────────────────

def _seed_two_quarters(session: Session, cik: str = "0000896159") -> None:
    session.add(_row(cik=cik, period_end=dt.date(2026, 3, 31),
                     fiscal_year=2026, fiscal_period="Q1",
                     revenue=1_000.0, net_income=100.0,
                     eps_diluted=1.0, free_cash_flow=50.0))
    session.add(_row(cik=cik, period_end=dt.date(2025, 12, 31),
                     fiscal_year=2025, fiscal_period="Q4",
                     revenue=900.0, net_income=90.0,
                     eps_diluted=0.9, free_cash_flow=45.0))
    session.commit()


def _svc(session: Session, cik: str = "0000896159") -> FinancialsService:
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.return_value = cik
    return FinancialsService(edgar_client=mock_edgar, session=session)


def test_get_compare_surfaces_pending_note(session: Session) -> None:
    cik = "0000896159"
    company = _company(cik=cik)
    company.pending_filing_note = "Q2 FY2026 results pending"
    session.add(company)
    _seed_two_quarters(session, cik)
    ctx = _svc(session).get_compare("CB")
    assert ctx.pending_filing_note == "Q2 FY2026 results pending"


def test_get_compare_note_none_by_default(session: Session) -> None:
    cik = "0000896159"
    session.add(_company(cik=cik))
    _seed_two_quarters(session, cik)
    ctx = _svc(session).get_compare("CB")
    assert ctx.pending_filing_note is None


def _render_compare(note: str | None) -> str:
    from tickerlens.routes.company import templates
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    s = factory()
    cik = "0000896159"
    company = _company(cik=cik)
    company.pending_filing_note = note
    s.add(company)
    _seed_two_quarters(s, cik)
    ctx = _svc(s).get_compare("CB")
    t = templates.get_template("company/compare.html")
    return t.render({"request": MagicMock(), "ctx": ctx, "also_trades_as": []})


def test_compare_page_renders_pending_note() -> None:
    html = _render_compare(
        "Q2 FY2026 results (10-Q filed Jul 28, 2026) aren't in EDGAR's data feed yet")
    assert "aren&#39;t in EDGAR&#39;s data feed yet" in html or "aren't in EDGAR's data feed yet" in html
    assert "amber-950/40" in html


def test_compare_page_omits_note_when_none() -> None:
    html = _render_compare(None)
    assert "data feed yet" not in html
    # The amber note block is the only amber-950/40 on the compare page.
    assert "amber-950/40" not in html


# ── tearsheet page (batch 56) ────────────────────────────────────────────────

def _render_tearsheet(note: str | None) -> str:
    from tickerlens.routes.company import templates
    from tickerlens.services.financials import CompanyOverview, DetailContext
    ov = CompanyOverview(**_overview_kwargs(pending_filing_note=note))
    detail = DetailContext(**_detail_ctx_kwargs())
    t = templates.get_template("company/tearsheet.html")
    return t.render({
        "request": MagicMock(), "overview": ov, "detail": detail,
        "valuation": None, "rows": [], "ai_analysis": None,
        "as_of_date": "October 12, 2026 at 12:00 UTC",
    })


def test_tearsheet_renders_pending_note() -> None:
    html = _render_tearsheet(
        "Q2 FY2026 results (10-Q filed Jul 28, 2026) aren't in EDGAR's data feed yet")
    assert "aren&#39;t in EDGAR&#39;s data feed yet" in html or "aren't in EDGAR's data feed yet" in html
    assert "Latest Quarter Data" in html


def test_tearsheet_omits_note_when_none() -> None:
    html = _render_tearsheet(None)
    assert "data feed yet" not in html
    assert "Latest Quarter Data" not in html


# ── vs page (batch 57) ───────────────────────────────────────────────────────

def _seed_vs_company(session: Session, cik: str, ticker: str, name: str,
                     note: str | None) -> None:
    c = _company(cik=cik, ticker=ticker)
    c.name = name
    c.last_price = 200.0
    c.market_cap = 3e12
    c.pending_filing_note = note
    session.add(c)
    ends = [dt.date(2024, 6, 30), dt.date(2024, 9, 30), dt.date(2024, 12, 31),
            dt.date(2025, 3, 31), dt.date(2025, 6, 30)]
    fps = ["Q2", "Q3", "Q4", "Q1", "Q2"]
    fys = [2024, 2024, 2024, 2025, 2025]
    revs = [80_000, 91_000, 119_575, 95_359, 85_777]
    nis = [20_000, 21_000, 33_917, 24_780, 21_448]
    epss = [1.30, 1.38, 2.18, 1.64, 1.40]
    fcfs = [20_000, 20_000, 26_600, 30_300, 22_700]
    for end, fy, fp, rev, ni, eps, fcf in zip(ends, fys, fps, revs, nis, epss, fcfs):
        session.add(_row(cik=cik, period_end=end, fiscal_year=fy, fiscal_period=fp,
                         revenue=rev, net_income=ni, eps_diluted=eps,
                         free_cash_flow=fcf))
    session.commit()


def _svc_two(session: Session) -> FinancialsService:
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.side_effect = lambda t: {
        "AAPL": "0000320193", "MSFT": "0000789019",
    }[t.upper()]
    return FinancialsService(edgar_client=mock_edgar, session=session)


def test_get_company_vs_surfaces_pending_notes(session: Session) -> None:
    _seed_vs_company(session, "0000320193", "AAPL", "Apple Inc.",
                     "Q2 FY2026 results (10-Q filed Jul 28, 2026) aren't in EDGAR's data feed yet")
    _seed_vs_company(session, "0000789019", "MSFT", "Microsoft Corp.", None)
    vs = _svc_two(session).get_company_vs("AAPL", "MSFT")
    assert vs.a.pending_filing_note == (
        "Q2 FY2026 results (10-Q filed Jul 28, 2026) aren't in EDGAR's data feed yet")
    assert vs.b.pending_filing_note is None


def test_get_company_vs_note_none_by_default(session: Session) -> None:
    _seed_vs_company(session, "0000320193", "AAPL", "Apple Inc.", None)
    _seed_vs_company(session, "0000789019", "MSFT", "Microsoft Corp.", None)
    vs = _svc_two(session).get_company_vs("AAPL", "MSFT")
    assert vs.a.pending_filing_note is None
    assert vs.b.pending_filing_note is None


def _render_vs(a_note: str | None, b_note: str | None) -> str:
    from tickerlens.routes.company import templates
    from tickerlens.services.financials import (
        CompanyVs, KPIChange, KPISnapshot, VsCompany,
    )

    def side(ticker: str, name: str, note: str | None) -> VsCompany:
        return VsCompany(
            ticker=ticker, name=name, sector="Technology",
            period_label="Q2 FY2025",
            kpi=KPISnapshot(revenue=85_777.0, net_income=21_448.0,
                            eps_basic=1.40, eps_diluted=1.40,
                            free_cash_flow=22_700.0),
            yoy=KPIChange(revenue=7.2, net_income=None, eps_basic=None,
                          eps_diluted=None, free_cash_flow=None),
            last_price=200.0, market_cap=3e12,
            signal="Buy", upside_pct=12.5,
            pending_filing_note=note,
        )

    vs = CompanyVs(a=side("AAPL", "Apple Inc.", a_note),
                   b=side("MSFT", "Microsoft Corp.", b_note))
    t = templates.get_template("company/vs.html")
    return t.render({"request": MagicMock(), "vs": vs})


def test_vs_page_renders_pending_note_for_one_side() -> None:
    html = _render_vs(
        "Q2 FY2026 results (10-Q filed Jul 28, 2026) aren't in EDGAR's data feed yet",
        None)
    assert "aren&#39;t in EDGAR&#39;s data feed yet" in html or "aren't in EDGAR's data feed yet" in html
    assert "amber-950/40" in html
    # The ticker label disambiguates which side the note belongs to.
    assert ">AAPL:</span>" in html


def test_vs_page_renders_notes_for_both_sides() -> None:
    html = _render_vs("A note", "B note")
    assert ">AAPL:</span> A note" in html
    assert ">MSFT:</span> B note" in html
    assert "amber-950/40" in html


def test_vs_page_omits_note_when_none() -> None:
    html = _render_vs(None, None)
    assert "data feed yet" not in html
    # The amber note block is the only amber-950/40 on the vs page (the Hold
    # signal badge uses amber-950/50).
    assert "amber-950/40" not in html
