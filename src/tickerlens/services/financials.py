from __future__ import annotations

import datetime as dt
import logging

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from tickerlens.data.edgar import EdgarClient, normalize_cik
from tickerlens.data.filings import (
    extract_press_release_highlights,
    extract_risk_factors,
    filing_doc_url,
    latest_annual_filing,
)
from tickerlens.data.sic import sector_for_sic
from tickerlens.data.wikipedia import get_description
from tickerlens.data.xbrl import QuarterlyFinancials, extract_recent_quarterly_financials
from tickerlens.data.yahoo import get_quote
from tickerlens.models.company import Company
from tickerlens.models.database import get_session
from tickerlens.models.quarterly_financial import QuarterlyFinancial
from tickerlens.services.ir_download import (
    EarningsPeriod,
    discover_earnings_filings,
    er_doc_url,
)
from tickerlens.services.valuation import ValuationSignal, compute_valuation

logger = logging.getLogger(__name__)


class CompanyNotFoundError(Exception):
    """Raised when no local data exists for a ticker, or when the ticker
    cannot be resolved to a CIK at all (unknown / invalid ticker)."""


def _resolve_cik(edgar_client, ticker: str) -> str:
    """Resolve a ticker to a normalized CIK.

    The EDGAR client raises a bare KeyError for unknown tickers; convert it
    to CompanyNotFoundError so routes can map it to a clean 404 instead of
    a 500.
    """
    try:
        return normalize_cik(edgar_client.cik_for_ticker(ticker))
    except KeyError as exc:
        raise CompanyNotFoundError(f"Unknown ticker: {ticker}") from exc


# ── public output models ───────────────────────────────────────────────────────

class KPISnapshot(BaseModel):
    revenue: float | None = None
    net_income: float | None = None
    eps_basic: float | None = None
    eps_diluted: float | None = None
    free_cash_flow: float | None = None


class KPIChange(BaseModel):
    """YoY percentage change for each KPI (None = not computable)."""
    revenue: float | None = None
    net_income: float | None = None
    eps_basic: float | None = None
    eps_diluted: float | None = None
    free_cash_flow: float | None = None


class BalanceSheet(BaseModel):
    """Point-in-time balance-sheet values as of a period end."""
    total_assets: float | None = None
    total_liabilities: float | None = None
    total_equity: float | None = None
    cash_and_equivalents: float | None = None


class BalanceSheetChange(BaseModel):
    """Percentage change for each balance-sheet line (None = not computable)."""
    total_assets: float | None = None
    total_liabilities: float | None = None
    total_equity: float | None = None
    cash_and_equivalents: float | None = None


class CompanyOverview(BaseModel):
    cik: str
    name: str
    ticker: str | None = None
    description: str | None = None
    sector: str | None = None
    last_price: float | None = None
    market_cap: float | None = None
    # latest quarter
    latest_label: str          # e.g. "Q2 FY2025"
    latest_period_end: dt.date
    latest_kpi: KPISnapshot
    yoy: KPIChange
    # TTM
    ttm_kpi: KPISnapshot
    ttm_quarters: int  # number of quarters summed (< 4 means partial)


class PeriodData(BaseModel):
    """Data for a single selected period (quarterly or yearly aggregate)."""
    label: str                  # "Q2 FY2025" or "FY2025"
    period_end: dt.date | None  # None for yearly aggregates
    fiscal_year: int
    fiscal_period: str | None   # "Q1"–"Q4" for quarterly; None for yearly
    kpi: KPISnapshot
    yoy: KPIChange
    qoq: KPIChange | None       # None for yearly
    balance_sheet: BalanceSheet
    balance_sheet_yoy: BalanceSheetChange
    balance_sheet_qoq: BalanceSheetChange | None  # None for yearly


class DetailContext(BaseModel):
    """Everything the detail page needs to render."""
    cik: str
    name: str
    ticker: str | None
    sector: str | None
    last_price: float | None
    market_cap: float | None
    # Selector state
    granularity: str            # "quarterly" | "yearly"
    quarter_options: list[str]  # most recent first, e.g. ["Q4 FY2025", ...]
    year_options: list[int]     # most recent first, e.g. [2025, 2024, 2023]
    selected_quarter: str       # e.g. "Q4 FY2025"
    selected_year: int          # e.g. 2025
    # Current period
    current: PeriodData
    # Chart data — all available quarters in chronological order
    chart_labels: list[str]
    chart_revenue: list[float | None]
    chart_eps: list[float | None]
    # Narrative (company-level, from latest 10-K; None = not available)
    risk_factors: str | None = None
    risk_factors_source: str | None = None
    # Press-release highlights for the *selected* period (None = not available)
    press_release_highlights: str | None = None
    press_release_source: str | None = None


# ── service ───────────────────────────────────────────────────────────────────

class FinancialsService:
    """Financial statement extraction, persistence, and enrichment service."""

    def __init__(
        self,
        edgar_client: EdgarClient | None = None,
        session: Session | None = None,
    ) -> None:
        self.edgar_client = edgar_client or EdgarClient()
        self._session = session

    def recent_quarterly_financials(
        self,
        cik: str | int,
        periods: int = 4,
    ) -> list[QuarterlyFinancials]:
        normalized_cik = normalize_cik(cik)
        submissions = self.edgar_client.submissions(normalized_cik)
        companyfacts = self.edgar_client.companyfacts(normalized_cik)
        return extract_recent_quarterly_financials(
            companyfacts,
            fiscal_year_end=submissions.get("fiscalYearEnd"),
            periods=periods,
        )

    def fetch_and_persist(
        self,
        ticker: str,
        periods: int = 4,
        session: Session | None = None,
    ) -> list[QuarterlyFinancials]:
        """Fetch XBRL financials from EDGAR and upsert into SQLite."""
        cik = _resolve_cik(self.edgar_client, ticker)
        submissions = self.edgar_client.submissions(cik)
        companyfacts = self.edgar_client.companyfacts(cik)

        rows = extract_recent_quarterly_financials(
            companyfacts,
            fiscal_year_end=submissions.get("fiscalYearEnd"),
            periods=periods,
        )

        db = session or self._session or get_session()
        try:
            _upsert_company(db, cik, submissions, ticker)
            for row in rows:
                _upsert_financial(db, cik, row)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            if session is None and self._session is None:
                db.close()

        return rows

    def enrich_company(self, ticker: str, session: Session | None = None) -> None:
        """Update description, price, and market cap for an existing company."""
        cik = _resolve_cik(self.edgar_client, ticker)
        db = session or self._session or get_session()
        try:
            company = db.get(Company, cik)
            if company is None:
                raise ValueError(f"Company with CIK {cik} not in DB — run fetch_and_persist first")

            quote = get_quote(ticker)
            description = get_description(company.name)

            company.last_price = quote.last_price
            company.market_cap = quote.market_cap
            company.description = description  # None clears a stale description

            # Risk factors are expensive to fetch and parse; only overwrite when
            # we successfully extract them, so a transient failure never wipes a
            # previously-good value.
            rf_text, rf_source = self._fetch_risk_factors(cik)
            if rf_text is not None:
                company.risk_factors = rf_text
                company.risk_factors_source = rf_source

            # Press-release highlights are per-period and equally expensive; fill
            # only rows that don't have them yet, and never wipe a
            # previously-good value on transient failure.
            self._enrich_press_release_highlights(db, ticker, cik)

            company.updated_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            if session is None and self._session is None:
                db.close()

    def _fetch_risk_factors(self, cik: str) -> tuple[str | None, str | None]:
        """Fetch the latest 10-K and extract Item 1A. Returns (text, source_label).

        Best-effort: any network or parse failure yields (None, None) and is
        logged, never raised — enrichment must not fail on missing narrative.
        """
        try:
            submissions = self.edgar_client.submissions(cik)
            filing = latest_annual_filing(submissions)
            if filing is None:
                # No 10-K in the recent submissions page (SEC paginates older
                # filings into filings.files, which we don't yet traverse).
                logger.warning("No 10-K found in recent submissions for CIK %s", cik)
                return None, None
            html = self.edgar_client.fetch_text(filing_doc_url(cik, filing))
            text = extract_risk_factors(html)
            if text is None:
                return None, None
            return text, f"10-K filed {filing.filing_date.isoformat()}"
        except Exception:
            logger.warning("Risk-factors extraction failed for CIK %s", cik, exc_info=True)
            return None, None

    def _enrich_press_release_highlights(
        self, db: Session, ticker: str, cik: str
    ) -> None:
        """Fill missing per-period press-release highlights from 8-K ex-99 exhibits.

        Matches each stored quarter to its earnings-release 8-K by period-end
        date (the stable period key — not FY/FP labels). Best-effort: rows
        without a matched exhibit keep None and render "Not available for this
        period"; a transient failure never wipes a previously-good value.
        """
        rows: list[QuarterlyFinancial] = (
            db.execute(
                select(QuarterlyFinancial).where(QuarterlyFinancial.cik == cik)
            )
            .scalars()
            .all()
        )
        missing = [r for r in rows if r.press_release_highlights is None]
        if not missing:
            return

        try:
            periods = discover_earnings_filings(ticker, self.edgar_client, n_quarters=len(rows))
        except Exception:
            logger.warning(
                "Earnings-release discovery failed for %s", ticker, exc_info=True
            )
            return
        by_period_end = {p.period_end: p for p in periods}

        for row in missing:
            period = by_period_end.get(row.period_end)
            if period is None:
                continue
            text, source = self._fetch_press_release_highlights(cik, period)
            if text is not None:
                row.press_release_highlights = text
                row.press_release_source = source

    def _fetch_press_release_highlights(
        self, cik: str, period: EarningsPeriod
    ) -> tuple[str | None, str | None]:
        """Fetch an 8-K ex-99 exhibit and extract highlights. Returns (text, source).

        Best-effort: any network or parse failure yields (None, None) and is
        logged, never raised — enrichment must not fail on missing narrative.
        """
        try:
            url = er_doc_url(cik, period)
            if url is None:
                # No ex-99 exhibit found (some companies embed the release in
                # the 8-K primary document, which we don't yet handle).
                logger.info(
                    "No ex-99 exhibit for CIK %s period %s", cik, period.quarter_label
                )
                return None, None
            html = self.edgar_client.fetch_text(url)
            text = extract_press_release_highlights(html)
            if text is None:
                return None, None
            return text, f"Earnings release {period.quarter_label}"
        except Exception:
            logger.warning(
                "Press-release extraction failed for CIK %s period %s",
                cik, period.quarter_label, exc_info=True,
            )
            return None, None

    def get_overview(self, ticker: str, session: Session | None = None) -> CompanyOverview:
        """Return everything needed to render the Overview page."""
        cik = _resolve_cik(self.edgar_client, ticker)
        db = session or self._session or get_session()
        try:
            company = db.get(Company, cik)
            if company is None:
                raise CompanyNotFoundError(f"No data for {ticker} — run fetch_and_persist first")

            rows = (
                db.execute(
                    select(QuarterlyFinancial)
                    .where(QuarterlyFinancial.cik == cik)
                    .order_by(QuarterlyFinancial.period_end.desc())
                    .limit(8)
                )
                .scalars()
                .all()
            )

            if not rows:
                raise CompanyNotFoundError(f"No quarterly data for {ticker}")

            latest = rows[0]
            latest_kpi = _to_kpi(latest)
            ttm_rows = list(rows[:4])
            ttm_kpi = _compute_ttm(ttm_rows)
            yoy = _compute_yoy(latest, list(rows))

            return CompanyOverview(
                cik=cik,
                name=company.name,
                ticker=company.ticker,
                description=company.description,
                sector=sector_for_sic(company.sic),
                last_price=company.last_price,
                market_cap=company.market_cap,
                latest_label=f"{latest.fiscal_period} FY{latest.fiscal_year}",
                latest_period_end=latest.period_end,
                latest_kpi=latest_kpi,
                yoy=yoy,
                ttm_kpi=ttm_kpi,
                ttm_quarters=len(ttm_rows),
            )
        finally:
            if session is None and self._session is None:
                db.close()

    def get_valuation(self, ticker: str, session: Session | None = None) -> ValuationSignal:
        """Compute the rules-based valuation signal for the Overview page.

        Uses stored EDGAR financials plus the last fetched Yahoo quote — no
        network calls, so it is cheap to render on every page view.
        """
        cik = _resolve_cik(self.edgar_client, ticker)
        db = session or self._session or get_session()
        try:
            company = db.get(Company, cik)
            if company is None:
                raise CompanyNotFoundError(f"No data for {ticker} — run fetch_and_persist first")

            rows = (
                db.execute(
                    select(QuarterlyFinancial)
                    .where(QuarterlyFinancial.cik == cik)
                    .order_by(QuarterlyFinancial.period_end.desc())
                )
                .scalars()
                .all()
            )
            if not rows:
                raise CompanyNotFoundError(f"No quarterly data for {ticker}")

            ttm = _compute_ttm(list(rows[:4]))
            prior_ttm = _compute_ttm(list(rows[4:8])) if len(rows) >= 8 else None

            # Growth input, best available first.
            growth_pct: float | None = None
            growth_is_fallback = False
            if prior_ttm is not None:
                growth_pct = _pct_change(ttm.eps_diluted, prior_ttm.eps_diluted)
            if growth_pct is None:
                yoy = _compute_yoy(rows[0], list(rows))
                growth_pct = yoy.eps_diluted
                growth_is_fallback = True
            if growth_pct is None and prior_ttm is not None:
                growth_pct = _pct_change(ttm.net_income, prior_ttm.net_income)
                growth_is_fallback = True

            revenue_growth_pct: float | None = None
            if prior_ttm is not None:
                revenue_growth_pct = _pct_change(ttm.revenue, prior_ttm.revenue)

            shares_outstanding: float | None = None
            if company.market_cap and company.last_price:
                shares_outstanding = company.market_cap / company.last_price

            return compute_valuation(
                ticker=ticker.upper(),
                current_price=company.last_price,
                ttm_eps_diluted=ttm.eps_diluted,
                eps_growth_pct=growth_pct,
                ttm_revenue=ttm.revenue,
                revenue_growth_pct=revenue_growth_pct,
                shares_outstanding=shares_outstanding,
                ttm_quarters=min(4, len(rows)),
                growth_is_fallback=growth_is_fallback,
            )
        finally:
            if session is None and self._session is None:
                db.close()

    def get_detail(
        self,
        ticker: str,
        granularity: str = "quarterly",
        selected_quarter: str | None = None,
        selected_year: int | None = None,
        session: Session | None = None,
    ) -> DetailContext:
        """Return everything the detail / time-slicer page needs."""
        cik = _resolve_cik(self.edgar_client, ticker)
        db = session or self._session or get_session()
        try:
            company = db.get(Company, cik)
            if company is None:
                raise CompanyNotFoundError(f"No data for {ticker} — run fetch_and_persist first")

            all_rows: list[QuarterlyFinancial] = (
                db.execute(
                    select(QuarterlyFinancial)
                    .where(QuarterlyFinancial.cik == cik)
                    .order_by(QuarterlyFinancial.period_end.asc())
                )
                .scalars()
                .all()
            )

            if not all_rows:
                raise CompanyNotFoundError(f"No quarterly data for {ticker}")

            latest = all_rows[-1]

            # Build selector option lists (most recent first)
            quarter_options = [
                f"{r.fiscal_period} FY{r.fiscal_year}" for r in reversed(all_rows)
            ]
            seen_years: set[int] = set()
            year_options: list[int] = []
            for r in reversed(all_rows):
                if r.fiscal_year not in seen_years:
                    year_options.append(r.fiscal_year)
                    seen_years.add(r.fiscal_year)

            # Default selections to latest quarter / latest year
            if selected_quarter is None:
                selected_quarter = f"{latest.fiscal_period} FY{latest.fiscal_year}"
            if selected_year is None:
                selected_year = year_options[0]

            # Build current period data
            if granularity == "yearly":
                current = _build_yearly_period(all_rows, selected_year, year_options[0])
                selected_year = current.fiscal_year  # may have been corrected
            else:
                current, selected_quarter = _build_quarterly_period(
                    all_rows, selected_quarter, latest
                )

            # Chart data — chronological order across all quarters
            chart_labels = [f"{r.fiscal_period} FY{r.fiscal_year}" for r in all_rows]
            chart_revenue = [r.revenue for r in all_rows]
            chart_eps = [r.eps_diluted for r in all_rows]

            # Press-release highlights belong to the selected period. In yearly
            # mode the year's earnings release is the Q4 (annual) one; fall back
            # to the year's latest quarter when no Q4 row exists.
            if granularity == "yearly":
                year_rows = [r for r in all_rows if r.fiscal_year == current.fiscal_year]
                pr_row = next(
                    (r for r in year_rows if r.fiscal_period == "Q4"),
                    year_rows[-1] if year_rows else None,
                )
            else:
                pr_row = next(
                    (
                        r
                        for r in all_rows
                        if r.fiscal_period == current.fiscal_period
                        and r.fiscal_year == current.fiscal_year
                    ),
                    None,
                )

            return DetailContext(
                cik=cik,
                name=company.name,
                ticker=company.ticker,
                sector=sector_for_sic(company.sic),
                last_price=company.last_price,
                market_cap=company.market_cap,
                granularity=granularity,
                quarter_options=quarter_options,
                year_options=year_options,
                selected_quarter=selected_quarter,
                selected_year=selected_year,
                current=current,
                chart_labels=chart_labels,
                chart_revenue=chart_revenue,
                chart_eps=chart_eps,
                risk_factors=company.risk_factors,
                risk_factors_source=company.risk_factors_source,
                press_release_highlights=pr_row.press_release_highlights if pr_row else None,
                press_release_source=pr_row.press_release_source if pr_row else None,
            )
        finally:
            if session is None and self._session is None:
                db.close()


# ── helpers ───────────────────────────────────────────────────────────────────

def _to_kpi(row: QuarterlyFinancial) -> KPISnapshot:
    return KPISnapshot(
        revenue=row.revenue,
        net_income=row.net_income,
        eps_basic=row.eps_basic,
        eps_diluted=row.eps_diluted,
        free_cash_flow=row.free_cash_flow,
    )


def _to_bs(row: QuarterlyFinancial) -> BalanceSheet:
    return BalanceSheet(
        total_assets=row.total_assets,
        total_liabilities=row.total_liabilities,
        total_equity=row.total_equity,
        cash_and_equivalents=row.cash_and_equivalents,
    )


def _bs_change(current: BalanceSheet, prior: BalanceSheet) -> BalanceSheetChange:
    return BalanceSheetChange(
        total_assets=_pct_change(current.total_assets, prior.total_assets),
        total_liabilities=_pct_change(current.total_liabilities, prior.total_liabilities),
        total_equity=_pct_change(current.total_equity, prior.total_equity),
        cash_and_equivalents=_pct_change(current.cash_and_equivalents, prior.cash_and_equivalents),
    )


def _sum_nullable(*values: float | None) -> float | None:
    nums = [v for v in values if v is not None]
    return sum(nums) if nums else None


def _compute_ttm(rows: list[QuarterlyFinancial]) -> KPISnapshot:
    return KPISnapshot(
        revenue=_sum_nullable(*[r.revenue for r in rows]),
        net_income=_sum_nullable(*[r.net_income for r in rows]),
        eps_basic=_sum_nullable(*[r.eps_basic for r in rows]),
        eps_diluted=_sum_nullable(*[r.eps_diluted for r in rows]),
        free_cash_flow=_sum_nullable(*[r.free_cash_flow for r in rows]),
    )


def _pct_change(current: float | None, prior: float | None) -> float | None:
    if current is None or prior is None or prior == 0:
        return None
    return (current - prior) / abs(prior) * 100


def _compute_yoy(latest: QuarterlyFinancial, rows: list[QuarterlyFinancial]) -> KPIChange:
    prior = next(
        (
            r for r in rows
            if r.fiscal_period == latest.fiscal_period
            and r.fiscal_year == latest.fiscal_year - 1
        ),
        None,
    )
    if prior is None:
        return KPIChange()
    return KPIChange(
        revenue=_pct_change(latest.revenue, prior.revenue),
        net_income=_pct_change(latest.net_income, prior.net_income),
        eps_basic=_pct_change(latest.eps_basic, prior.eps_basic),
        eps_diluted=_pct_change(latest.eps_diluted, prior.eps_diluted),
        free_cash_flow=_pct_change(latest.free_cash_flow, prior.free_cash_flow),
    )


def _compute_bs_yoy(
    latest: QuarterlyFinancial, rows: list[QuarterlyFinancial]
) -> BalanceSheetChange:
    prior = next(
        (
            r for r in rows
            if r.fiscal_period == latest.fiscal_period
            and r.fiscal_year == latest.fiscal_year - 1
        ),
        None,
    )
    if prior is None:
        return BalanceSheetChange()
    return _bs_change(_to_bs(latest), _to_bs(prior))


def _compute_bs_qoq(
    current: QuarterlyFinancial, prior: QuarterlyFinancial | None
) -> BalanceSheetChange:
    if prior is None:
        return BalanceSheetChange()
    return _bs_change(_to_bs(current), _to_bs(prior))


def _is_prior_quarter(
    candidate: QuarterlyFinancial | None, current: QuarterlyFinancial
) -> bool:
    """True only when candidate is the quarter immediately before current."""
    if candidate is None:
        return False
    _prev = {"Q2": ("Q1", 0), "Q3": ("Q2", 0), "Q4": ("Q3", 0), "Q1": ("Q4", -1)}
    expected_fp, fy_delta = _prev.get(current.fiscal_period, (None, None))
    if expected_fp is None:
        return False
    return (
        candidate.fiscal_period == expected_fp
        and candidate.fiscal_year == current.fiscal_year + fy_delta
    )


def _compute_qoq(
    current: QuarterlyFinancial, prior: QuarterlyFinancial | None
) -> KPIChange:
    if prior is None:
        return KPIChange()
    return KPIChange(
        revenue=_pct_change(current.revenue, prior.revenue),
        net_income=_pct_change(current.net_income, prior.net_income),
        eps_basic=_pct_change(current.eps_basic, prior.eps_basic),
        eps_diluted=_pct_change(current.eps_diluted, prior.eps_diluted),
        free_cash_flow=_pct_change(current.free_cash_flow, prior.free_cash_flow),
    )


def _compute_kpi_yoy(current_kpi: KPISnapshot, prior_kpi: KPISnapshot) -> KPIChange:
    return KPIChange(
        revenue=_pct_change(current_kpi.revenue, prior_kpi.revenue),
        net_income=_pct_change(current_kpi.net_income, prior_kpi.net_income),
        eps_basic=_pct_change(current_kpi.eps_basic, prior_kpi.eps_basic),
        eps_diluted=_pct_change(current_kpi.eps_diluted, prior_kpi.eps_diluted),
        free_cash_flow=_pct_change(current_kpi.free_cash_flow, prior_kpi.free_cash_flow),
    )


def _parse_quarter_label(label: str) -> tuple[str, int] | None:
    """Parse "Q2 FY2025" → ("Q2", 2025). Returns None on invalid input."""
    try:
        fp, fy_str = label.split(" FY")
        return fp, int(fy_str)
    except (ValueError, AttributeError):
        return None


def _build_quarterly_period(
    all_rows: list[QuarterlyFinancial],
    selected_quarter: str,
    latest: QuarterlyFinancial,
) -> tuple[PeriodData, str]:
    """Build PeriodData for a single quarter selection. Returns (data, corrected_label)."""
    parsed = _parse_quarter_label(selected_quarter)
    if parsed is None:
        fp, fy = latest.fiscal_period, latest.fiscal_year
    else:
        fp, fy = parsed

    row = next(
        (r for r in all_rows if r.fiscal_period == fp and r.fiscal_year == fy),
        latest,
    )
    corrected_label = f"{row.fiscal_period} FY{row.fiscal_year}"

    row_idx = next((i for i, r in enumerate(all_rows) if r is row), len(all_rows) - 1)
    _candidate = all_rows[row_idx - 1] if row_idx > 0 else None
    # Only treat the candidate as QoQ if it is truly the immediately preceding quarter
    # (handles gaps in DB history — e.g. Q3 2023 followed by Q2 2025).
    prior_qoq = _candidate if _is_prior_quarter(_candidate, row) else None

    return (
        PeriodData(
            label=corrected_label,
            period_end=row.period_end,
            fiscal_year=row.fiscal_year,
            fiscal_period=row.fiscal_period,
            kpi=_to_kpi(row),
            yoy=_compute_yoy(row, list(all_rows)),
            qoq=_compute_qoq(row, prior_qoq),
            balance_sheet=_to_bs(row),
            balance_sheet_yoy=_compute_bs_yoy(row, list(all_rows)),
            balance_sheet_qoq=_compute_bs_qoq(row, prior_qoq),
        ),
        corrected_label,
    )


def _build_yearly_period(
    all_rows: list[QuarterlyFinancial],
    selected_year: int,
    default_year: int,
) -> PeriodData:
    """Build PeriodData for a fiscal-year aggregate."""
    year_rows = [r for r in all_rows if r.fiscal_year == selected_year]
    if not year_rows:
        selected_year = default_year
        year_rows = [r for r in all_rows if r.fiscal_year == selected_year]

    kpi = _compute_ttm(year_rows)

    prior_rows = [r for r in all_rows if r.fiscal_year == selected_year - 1]
    yoy = _compute_kpi_yoy(kpi, _compute_ttm(prior_rows)) if prior_rows else KPIChange()

    # Balance sheet is a point-in-time value — use the year's last quarter (year end),
    # not a sum, and compare against the prior year's last quarter.
    balance_sheet = _to_bs(year_rows[-1]) if year_rows else BalanceSheet()
    balance_sheet_yoy = (
        _bs_change(balance_sheet, _to_bs(prior_rows[-1]))
        if year_rows and prior_rows
        else BalanceSheetChange()
    )

    return PeriodData(
        label=f"FY{selected_year}",
        period_end=year_rows[-1].period_end if year_rows else None,
        fiscal_year=selected_year,
        fiscal_period=None,
        kpi=kpi,
        yoy=yoy,
        qoq=None,
        balance_sheet=balance_sheet,
        balance_sheet_yoy=balance_sheet_yoy,
        balance_sheet_qoq=None,
    )


def _upsert_company(session: Session, cik: str, submissions: dict, ticker: str) -> None:
    tickers = submissions.get("tickers") or []
    primary_ticker = ticker.upper() if ticker else (tickers[0] if tickers else None)

    stmt = (
        insert(Company)
        .values(
            cik=cik,
            name=submissions.get("name", ""),
            ticker=primary_ticker,
            fiscal_year_end=submissions.get("fiscalYearEnd"),
            sic=str(submissions.get("sic", "")) or None,
            updated_at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
        )
        .on_conflict_do_update(
            index_elements=["cik"],
            set_={
                "name": submissions.get("name", ""),
                "ticker": primary_ticker,
                "fiscal_year_end": submissions.get("fiscalYearEnd"),
                "sic": str(submissions.get("sic", "")) or None,
                "updated_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
            },
        )
    )
    session.execute(stmt)


def _upsert_financial(session: Session, cik: str, row: QuarterlyFinancials) -> None:
    stmt = (
        insert(QuarterlyFinancial)
        .values(
            cik=cik,
            period_end=row.end,
            fiscal_year=row.fy,
            fiscal_period=row.fp,
            revenue=row.revenue,
            net_income=row.net_income,
            eps_basic=row.eps_basic,
            eps_diluted=row.eps_diluted,
            free_cash_flow=row.free_cash_flow,
            total_assets=row.total_assets,
            total_liabilities=row.total_liabilities,
            total_equity=row.total_equity,
            cash_and_equivalents=row.cash_and_equivalents,
            updated_at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
        )
        .on_conflict_do_update(
            index_elements=["cik", "period_end"],
            set_={
                "fiscal_year": row.fy,
                "fiscal_period": row.fp,
                "revenue": row.revenue,
                "net_income": row.net_income,
                "eps_basic": row.eps_basic,
                "eps_diluted": row.eps_diluted,
                "free_cash_flow": row.free_cash_flow,
                "total_assets": row.total_assets,
                "total_liabilities": row.total_liabilities,
                "total_equity": row.total_equity,
                "cash_and_equivalents": row.cash_and_equivalents,
                "updated_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
            },
        )
    )
    session.execute(stmt)
