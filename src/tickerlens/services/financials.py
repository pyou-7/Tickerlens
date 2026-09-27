from __future__ import annotations

import csv
import datetime as dt
import io
import logging
import zipfile

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from tickerlens.data.edgar import EdgarClient, normalize_cik
from tickerlens.data.filings import (
    extract_executive_commentary,
    extract_guidance,
    extract_press_release_text,
    extract_risk_factors,
    filing_doc_url,
    latest_annual_filing,
)
from tickerlens.data.sic import sector_for_sic
from tickerlens.data.wikipedia import get_description
from tickerlens.data.xbrl import QuarterlyFinancials, extract_recent_quarterly_financials
from tickerlens.data.yahoo import (
    PriceHistory,
    PriceRange,
    get_earnings_history,
    get_price_history,
    get_quote,
)
from tickerlens.models.company import Company
from tickerlens.models.database import get_session
from tickerlens.models.quarterly_financial import QuarterlyFinancial
from tickerlens.services.ir_download import discover_earnings_filings, er_doc_url

logger = logging.getLogger(__name__)


class CompanyNotFoundError(Exception):
    """Raised by get_overview when no local data exists for a ticker."""


# ── public output models ───────────────────────────────────────────────────────

class KPISnapshot(BaseModel):
    revenue: float | None = None
    net_income: float | None = None
    eps_basic: float | None = None
    eps_diluted: float | None = None
    free_cash_flow: float | None = None
    operating_cash_flow: float | None = None
    capex: float | None = None


class KPIChange(BaseModel):
    """YoY percentage change for each KPI (None = not computable)."""
    revenue: float | None = None
    net_income: float | None = None
    eps_basic: float | None = None
    eps_diluted: float | None = None
    free_cash_flow: float | None = None
    operating_cash_flow: float | None = None
    capex: float | None = None


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
    # Narrative (per-quarter, from the earnings 8-K ex-99; None = not available)
    press_release: str | None = None
    press_release_source: str | None = None
    guidance: str | None = None
    executive_commentary: str | None = None


class RangeSummary(BaseModel):
    """Aggregated financial summary across a multi-period range."""
    start_label: str
    end_label: str
    period_count: int
    total_revenue: float | None = None
    total_net_income: float | None = None
    total_free_cash_flow: float | None = None
    total_operating_cash_flow: float | None = None
    total_capex: float | None = None
    avg_revenue: float | None = None
    cumulative_net_margin: float | None = None
    cumulative_fcf_margin: float | None = None
    revenue_growth_pct: float | None = None
    net_income_growth_pct: float | None = None


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
    mode: str = "single"        # "single" | "range"
    quarter_options: list[str]  # most recent first, e.g. ["Q4 FY2025", ...]
    year_options: list[int]     # most recent first, e.g. [2025, 2024, 2023]
    selected_quarter: str       # e.g. "Q4 FY2025"
    selected_year: int          # e.g. 2025
    range_start: str | None = None
    range_end: str | None = None
    range_summary: RangeSummary | None = None
    range_periods: list[PeriodData] = []
    # Current period (or latest in range)
    current: PeriodData
    # Chart data — unique period-end dates in chronological order. Dates, rather
    # than fiscal labels, prevent duplicate/misreported labels from collapsing
    # multiple quarters onto the same Plotly x position.
    chart_dates: list[str]
    chart_labels: list[str]
    chart_metrics: dict[str, list[float | None]]
    chart_filing_dates: list[str | None] = []
    chart_surprises: list[dict | None] = []
    # Narrative (company-level, from latest 10-K; None = not available)
    risk_factors: str | None = None
    risk_factors_source: str | None = None


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

    def price_history(
        self,
        ticker: str,
        range_key: PriceRange = "1y",
    ) -> PriceHistory:
        """Return normalized adjusted prices for the detail-page stock chart."""
        return get_price_history(ticker, range_key)

    def fetch_and_persist(
        self,
        ticker: str,
        periods: int = 4,
        session: Session | None = None,
    ) -> list[QuarterlyFinancials]:
        """Fetch XBRL financials from EDGAR and upsert into SQLite."""
        cik = normalize_cik(self.edgar_client.cik_for_ticker(ticker))
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
        cik = normalize_cik(self.edgar_client.cik_for_ticker(ticker))
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

    def enrich_press_releases(
        self,
        ticker: str,
        periods: int = 8,
        session: Session | None = None,
    ) -> int:
        """Fetch earnings press releases (8-K ex-99) and store per matching quarter.

        Matches exhibits to quarterly_financials rows by period end date. Best-effort
        throughout: discovery or per-document failures are logged and skipped, and a
        stored value is only overwritten on a successful new extraction. Returns the
        number of quarters updated.
        """
        try:
            cik = normalize_cik(self.edgar_client.cik_for_ticker(ticker))
            earnings = discover_earnings_filings(ticker, self.edgar_client, n_quarters=periods)
        except Exception:
            logger.warning("Earnings-filing discovery failed for %s", ticker, exc_info=True)
            return 0

        db = session or self._session or get_session()
        updated = 0
        try:
            for period in earnings:
                url = er_doc_url(cik, period)
                if url is None:
                    continue  # no ex-99 exhibit found for this quarter
                try:
                    html = self.edgar_client.fetch_text(url)
                    text = extract_press_release_text(html)
                    guidance = extract_guidance(html)
                    commentary = extract_executive_commentary(html)
                except Exception:
                    logger.warning(
                        "Press-release fetch/extract failed for %s %s",
                        ticker, period.quarter_label, exc_info=True,
                    )
                    continue
                if text is None and guidance is None and commentary is None:
                    continue

                row = db.execute(
                    select(QuarterlyFinancial).where(
                        QuarterlyFinancial.cik == cik,
                        QuarterlyFinancial.period_end == period.period_end,
                    )
                ).scalar_one_or_none()
                if row is None:
                    continue  # exhibit for a quarter we don't have financials for

                if text is not None:
                    row.press_release_highlights = text
                if guidance is not None:
                    row.guidance = guidance
                if commentary is not None:
                    row.executive_commentary = commentary
                row.press_release_source = f"8-K ex-99, {period.quarter_label}"
                row.updated_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
                updated += 1

            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            if session is None and self._session is None:
                db.close()
        return updated

    def get_overview(self, ticker: str, session: Session | None = None) -> CompanyOverview:
        """Return everything needed to render the Overview page."""
        cik = normalize_cik(self.edgar_client.cik_for_ticker(ticker))
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

    def get_detail(
        self,
        ticker: str,
        granularity: str = "quarterly",
        selected_quarter: str | None = None,
        selected_year: int | None = None,
        mode: str = "single",
        range_start: str | None = None,
        range_end: str | None = None,
        session: Session | None = None,
    ) -> DetailContext:
        """Return everything the detail / time-slicer page needs."""
        cik = normalize_cik(self.edgar_client.cik_for_ticker(ticker))
        db = session or self._session or get_session()
        try:
            company = db.get(Company, cik)
            if company is None:
                raise CompanyNotFoundError(f"No data for {ticker} — run fetch_and_persist first")

            if company.risk_factors is None:
                rf_text, rf_source = self._fetch_risk_factors(cik)
                if rf_text is not None:
                    company.risk_factors = rf_text
                    company.risk_factors_source = rf_source
                    db.commit()

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

            range_summary: RangeSummary | None = None
            range_periods: list[PeriodData] = []

            if mode == "range":
                (
                    range_summary,
                    range_periods,
                    current,
                    range_start,
                    range_end,
                    chart_dates,
                    chart_labels,
                    chart_metrics,
                    chart_filing_dates,
                    chart_surprises,
                ) = _build_range_data(
                    all_rows,
                    granularity,
                    range_start,
                    range_end,
                    quarter_options,
                    year_options,
                    latest,
                    ticker=company.ticker,
                )
            else:
                # Build current period data
                if granularity == "yearly":
                    current = _build_yearly_period(all_rows, selected_year, year_options[0])
                    selected_year = current.fiscal_year  # may have been corrected
                else:
                    current, selected_quarter = _build_quarterly_period(
                        all_rows, selected_quarter, latest
                    )

                chart_dates = [r.period_end.isoformat() for r in all_rows]
                chart_labels = [r.period_end.strftime("%b '%y") for r in all_rows]
                chart_metrics = {
                    "revenue": [r.revenue for r in all_rows],
                    "net_income": [r.net_income for r in all_rows],
                    "free_cash_flow": [r.free_cash_flow for r in all_rows],
                    "operating_cash_flow": [r.operating_cash_flow for r in all_rows],
                    "capex": [r.capex for r in all_rows],
                    "eps_diluted": [r.eps_diluted for r in all_rows],
                    "eps_basic": [r.eps_basic for r in all_rows],
                    "total_assets": [r.total_assets for r in all_rows],
                    "total_liabilities": [r.total_liabilities for r in all_rows],
                    "total_equity": [r.total_equity for r in all_rows],
                    "cash_and_equivalents": [r.cash_and_equivalents for r in all_rows],
                }
                chart_filing_dates = [_get_filing_date(r) for r in all_rows]
                chart_surprises = _match_surprises_to_dates([r.period_end for r in all_rows], company.ticker)

            return DetailContext(
                cik=cik,
                name=company.name,
                ticker=company.ticker,
                sector=sector_for_sic(company.sic),
                last_price=company.last_price,
                market_cap=company.market_cap,
                granularity=granularity,
                mode=mode,
                quarter_options=quarter_options,
                year_options=year_options,
                selected_quarter=selected_quarter,
                selected_year=selected_year,
                range_start=range_start,
                range_end=range_end,
                range_summary=range_summary,
                range_periods=range_periods,
                current=current,
                chart_dates=chart_dates,
                chart_labels=chart_labels,
                chart_metrics=chart_metrics,
                chart_filing_dates=chart_filing_dates,
                chart_surprises=chart_surprises,
                risk_factors=company.risk_factors,
                risk_factors_source=company.risk_factors_source,
            )
        finally:
            if session is None and self._session is None:
                db.close()

    def export_zip(
        self,
        ticker: str,
        range_start: str | None = None,
        range_end: str | None = None,
        session: Session | None = None,
    ) -> bytes:
        """Generate an in-memory ZIP archive containing formatted financial CSV, press releases, and README."""
        cik = normalize_cik(self.edgar_client.cik_for_ticker(ticker))
        db = session or self._session or get_session()
        try:
            company = db.get(Company, cik)
            if company is None:
                raise CompanyNotFoundError(f"No company found for {ticker}")

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
                raise CompanyNotFoundError(f"No financial data found for {ticker}")

            rows = all_rows
            labels = [f"{r.fiscal_period} FY{r.fiscal_year}" for r in all_rows]
            if range_start and range_start in labels and range_end and range_end in labels:
                s_idx = labels.index(range_start)
                e_idx = labels.index(range_end)
                if s_idx > e_idx:
                    s_idx, e_idx = e_idx, s_idx
                rows = all_rows[s_idx : e_idx + 1]

            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                # 1. Financials CSV
                csv_buf = io.StringIO()
                writer = csv.writer(csv_buf)
                writer.writerow([
                    "Ticker",
                    "CIK",
                    "Fiscal Period",
                    "Fiscal Year",
                    "Period Label",
                    "Period End",
                    "Revenue ($)",
                    "Net Income ($)",
                    "Diluted EPS ($)",
                    "Basic EPS ($)",
                    "Operating Cash Flow ($)",
                    "Capital Expenditures ($)",
                    "Free Cash Flow ($)",
                    "Net Margin (%)",
                    "FCF Margin (%)",
                    "Total Assets ($)",
                    "Total Liabilities ($)",
                    "Total Equity ($)",
                    "Cash & Equivalents ($)",
                ])

                for r in rows:
                    net_margin = (
                        (r.net_income / r.revenue * 100)
                        if (r.net_income is not None and r.revenue and r.revenue > 0)
                        else None
                    )
                    fcf_margin = (
                        (r.free_cash_flow / r.revenue * 100)
                        if (r.free_cash_flow is not None and r.revenue and r.revenue > 0)
                        else None
                    )
                    writer.writerow([
                        ticker.upper(),
                        cik,
                        r.fiscal_period,
                        r.fiscal_year,
                        f"{r.fiscal_period} FY{r.fiscal_year}",
                        r.period_end.isoformat() if r.period_end else "",
                        r.revenue if r.revenue is not None else "",
                        r.net_income if r.net_income is not None else "",
                        f"{r.eps_diluted:.2f}" if r.eps_diluted is not None else "",
                        f"{r.eps_basic:.2f}" if r.eps_basic is not None else "",
                        r.operating_cash_flow if r.operating_cash_flow is not None else "",
                        r.capex if r.capex is not None else "",
                        r.free_cash_flow if r.free_cash_flow is not None else "",
                        f"{net_margin:.2f}" if net_margin is not None else "",
                        f"{fcf_margin:.2f}" if fcf_margin is not None else "",
                        r.total_assets if r.total_assets is not None else "",
                        r.total_liabilities if r.total_liabilities is not None else "",
                        r.total_equity if r.total_equity is not None else "",
                        r.cash_and_equivalents if r.cash_and_equivalents is not None else "",
                    ])

                zf.writestr(f"{ticker.lower()}_financials.csv", csv_buf.getvalue())

                # 2. Press release / earnings disclosures
                seen_disclosures: set[str] = set()
                for r in rows:
                    if r.press_release_highlights or r.guidance or r.executive_commentary:
                        clean_fp = f"{r.fiscal_period}_FY{r.fiscal_year}"
                        if clean_fp in seen_disclosures:
                            clean_fp = f"{clean_fp}_{r.period_end}"
                        seen_disclosures.add(clean_fp)
                        doc_text = (
                            f"================================================================================\n"
                            f"{company.name} ({ticker.upper()}) — {r.fiscal_period} FY{r.fiscal_year} Disclosures\n"
                            f"Period Ended: {r.period_end}\n"
                            f"Source Filing: {r.press_release_source or 'SEC 8-K Ex-99'}\n"
                            f"================================================================================\n\n"
                            f"[MANAGEMENT GUIDANCE]\n"
                            f"{r.guidance or 'No quantitative guidance excerpted for this period.'}\n\n"
                            f"[EXECUTIVE COMMENTARY]\n"
                            f"{r.executive_commentary or 'No executive remarks excerpted for this period.'}\n\n"
                            f"[PRESS RELEASE TEXT]\n"
                            f"{r.press_release_highlights or 'No press release text available.'}\n"
                        )
                        zf.writestr(f"disclosures/{ticker.upper()}_{clean_fp}_disclosure.txt", doc_text)

                # 3. Risk factors if present
                if company.risk_factors:
                    rf_text = (
                        f"================================================================================\n"
                        f"{company.name} ({ticker.upper()}) — 10-K Item 1A Risk Factors\n"
                        f"Source: {company.risk_factors_source or 'SEC 10-K'}\n"
                        f"================================================================================\n\n"
                        f"{company.risk_factors}\n"
                    )
                    zf.writestr(f"{ticker.upper()}_risk_factors.txt", rf_text)

                # 4. README.txt
                readme_text = (
                    f"Tickerlens Financial Data & Filings Export\n"
                    f"==========================================\n"
                    f"Company: {company.name} ({ticker.upper()})\n"
                    f"CIK: {company.cik}\n"
                    f"Sector: {sector_for_sic(company.sic) or 'Unknown'}\n"
                    f"Export Date: {dt.date.today().isoformat()}\n"
                    f"Quarterly Periods Included: {len(rows)}\n\n"
                    f"Files in this Archive:\n"
                    f"- {ticker.lower()}_financials.csv: Comprehensive GAAP financial statement history.\n"
                    f"- disclosures/: Raw text of 8-K Ex-99 earnings press releases, guidance, and executive remarks.\n"
                    f"- {ticker.upper()}_risk_factors.txt: 10-K Item 1A Risk Factors.\n\n"
                    f"Generated by Tickerlens (SEC EDGAR companyfacts & filings engine).\n"
                )
                zf.writestr("README.txt", readme_text)

            return zip_buf.getvalue()
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
        operating_cash_flow=row.operating_cash_flow,
        capex=row.capex,
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
        operating_cash_flow=_sum_nullable(*[r.operating_cash_flow for r in rows]),
        capex=_sum_nullable(*[r.capex for r in rows]),
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
    if prior is None and latest.period_end is not None:
        prior = next(
            (
                r for r in rows
                if r.period_end is not None and 320 <= (latest.period_end - r.period_end).days <= 410
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
        operating_cash_flow=_pct_change(latest.operating_cash_flow, prior.operating_cash_flow),
        capex=_pct_change(latest.capex, prior.capex),
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
    if prior is None and latest.period_end is not None:
        prior = next(
            (
                r for r in rows
                if r.period_end is not None and 320 <= (latest.period_end - r.period_end).days <= 410
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
    if expected_fp is not None and (
        candidate.fiscal_period == expected_fp
        and candidate.fiscal_year == current.fiscal_year + fy_delta
    ):
        return True
    if candidate.period_end is not None and current.period_end is not None:
        days = (current.period_end - candidate.period_end).days
        return 60 <= days <= 130
    return False


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
        operating_cash_flow=_pct_change(current.operating_cash_flow, prior.operating_cash_flow),
        capex=_pct_change(current.capex, prior.capex),
    )


def _compute_kpi_yoy(current_kpi: KPISnapshot, prior_kpi: KPISnapshot) -> KPIChange:
    return KPIChange(
        revenue=_pct_change(current_kpi.revenue, prior_kpi.revenue),
        net_income=_pct_change(current_kpi.net_income, prior_kpi.net_income),
        eps_basic=_pct_change(current_kpi.eps_basic, prior_kpi.eps_basic),
        eps_diluted=_pct_change(current_kpi.eps_diluted, prior_kpi.eps_diluted),
        free_cash_flow=_pct_change(current_kpi.free_cash_flow, prior_kpi.free_cash_flow),
        operating_cash_flow=_pct_change(current_kpi.operating_cash_flow, prior_kpi.operating_cash_flow),
        capex=_pct_change(current_kpi.capex, prior_kpi.capex),
    )


def _get_filing_date(r: QuarterlyFinancial) -> str | None:
    """Best-effort extraction of SEC filing date for a quarterly financial row."""
    val = getattr(r, "filing_date", None)
    if val:
        return val.isoformat() if hasattr(val, "isoformat") else str(val)
    src = getattr(r, "press_release_source", None)
    if src and "filed " in src:
        date_part = src.split("filed ")[-1].strip()
        if len(date_part) >= 10:
            return date_part[:10]
    return None


def _match_surprises_to_dates(
    dates: list[dt.date],
    ticker: str | None,
) -> list[dict | None]:
    """Match quarterly dates to earnings surprises (beats/misses) from Yahoo Finance."""
    if not ticker:
        return [None] * len(dates)

    try:
        surprises = get_earnings_history(ticker)
    except Exception:
        return [None] * len(dates)

    if not surprises:
        return [None] * len(dates)

    result: list[dict | None] = []
    for d in dates:
        matched = None
        min_diff = 40  # within 35-40 days of quarter end
        for s in surprises:
            try:
                s_dt = dt.date.fromisoformat(s.quarter_date)
                diff = abs((d - s_dt).days)
                if diff <= min_diff:
                    min_diff = diff
                    matched = {
                        "quarter_date": s.quarter_date,
                        "eps_actual": s.eps_actual,
                        "eps_estimate": s.eps_estimate,
                        "eps_diff": s.eps_difference,
                        "surprise_pct": s.surprise_pct,
                        "surprise_str": (
                            f"{'+' if s.surprise_pct and s.surprise_pct > 0 else ''}{s.surprise_pct * 100:.1f}%"
                            if s.surprise_pct is not None
                            else None
                        ),
                        "is_beat": s.is_beat,
                    }
            except Exception:
                continue
        result.append(matched)

    return result


def _build_range_data(
    all_rows: list[QuarterlyFinancial],
    granularity: str,
    range_start: str | None,
    range_end: str | None,
    quarter_options: list[str],
    year_options: list[int],
    latest: QuarterlyFinancial,
    ticker: str | None = None,
) -> tuple[
    RangeSummary,
    list[PeriodData],
    PeriodData,
    str,
    str,
    list[str],
    list[str],
    dict[str, list[float | None]],
    list[str | None],
    list[dict | None],
]:
    """Build RangeSummary and list of PeriodData for consecutive multi-period ranges."""
    if granularity == "yearly":
        sorted_years = sorted(year_options)
        start_yr: int | None = None
        end_yr: int | None = None
        if range_start:
            try:
                start_yr = int(range_start.replace("FY", ""))
            except ValueError:
                pass
        if range_end:
            try:
                end_yr = int(range_end.replace("FY", ""))
            except ValueError:
                pass

        if start_yr is None or start_yr not in sorted_years:
            start_yr = sorted_years[max(0, len(sorted_years) - 3)]
        if end_yr is None or end_yr not in sorted_years:
            end_yr = sorted_years[-1]

        if start_yr > end_yr:
            start_yr, end_yr = end_yr, start_yr

        selected_years = [y for y in sorted_years if start_yr <= y <= end_yr]
        range_periods: list[PeriodData] = []
        for yr in selected_years:
            p = _build_yearly_period(all_rows, yr, year_options[0])
            range_periods.append(p)

        total_rev = _sum_nullable(*[p.kpi.revenue for p in range_periods])
        total_ni = _sum_nullable(*[p.kpi.net_income for p in range_periods])
        total_fcf = _sum_nullable(*[p.kpi.free_cash_flow for p in range_periods])
        total_ocf = _sum_nullable(*[p.kpi.operating_cash_flow for p in range_periods])
        total_capex = _sum_nullable(*[p.kpi.capex for p in range_periods])
        p_count = len(range_periods)
        avg_rev = (total_rev / p_count) if (total_rev is not None and p_count > 0) else None
        c_net_margin = (total_ni / total_rev * 100) if (total_ni is not None and total_rev and total_rev > 0) else None
        c_fcf_margin = (total_fcf / total_rev * 100) if (total_fcf is not None and total_rev and total_rev > 0) else None
        rev_growth = _pct_change(range_periods[-1].kpi.revenue, range_periods[0].kpi.revenue)
        ni_growth = _pct_change(range_periods[-1].kpi.net_income, range_periods[0].kpi.net_income)

        start_lbl = f"FY{start_yr}"
        end_lbl = f"FY{end_yr}"
        summary = RangeSummary(
            start_label=start_lbl,
            end_label=end_lbl,
            period_count=p_count,
            total_revenue=total_rev,
            total_net_income=total_ni,
            total_free_cash_flow=total_fcf,
            total_operating_cash_flow=total_ocf,
            total_capex=total_capex,
            avg_revenue=avg_rev,
            cumulative_net_margin=c_net_margin,
            cumulative_fcf_margin=c_fcf_margin,
            revenue_growth_pct=rev_growth,
            net_income_growth_pct=ni_growth,
        )
        current = range_periods[-1]
        chart_dates = [f"{p.fiscal_year}-12-31" for p in range_periods]
        chart_labels = [p.label for p in range_periods]
        chart_metrics = {
            "revenue": [p.kpi.revenue for p in range_periods],
            "net_income": [p.kpi.net_income for p in range_periods],
            "free_cash_flow": [p.kpi.free_cash_flow for p in range_periods],
            "operating_cash_flow": [p.kpi.operating_cash_flow for p in range_periods],
            "capex": [p.kpi.capex for p in range_periods],
            "eps_diluted": [p.kpi.eps_diluted for p in range_periods],
            "eps_basic": [p.kpi.eps_basic for p in range_periods],
            "total_assets": [p.balance_sheet.total_assets for p in range_periods],
            "total_liabilities": [p.balance_sheet.total_liabilities for p in range_periods],
            "total_equity": [p.balance_sheet.total_equity for p in range_periods],
            "cash_and_equivalents": [p.balance_sheet.cash_and_equivalents for p in range_periods],
        }
        chart_filing_dates: list[str | None] = [None] * len(range_periods)
        chart_surprises: list[dict | None] = [None] * len(range_periods)
        return (
            summary,
            range_periods,
            current,
            start_lbl,
            end_lbl,
            chart_dates,
            chart_labels,
            chart_metrics,
            chart_filing_dates,
            chart_surprises,
        )
    else:
        labels = [f"{r.fiscal_period} FY{r.fiscal_year}" for r in all_rows]
        if range_start is None or range_start not in labels:
            start_idx = max(0, len(all_rows) - 4)
        else:
            start_idx = labels.index(range_start)

        if range_end is None or range_end not in labels:
            end_idx = len(all_rows) - 1
        else:
            end_idx = labels.index(range_end)

        if start_idx > end_idx:
            start_idx, end_idx = end_idx, start_idx

        range_rows = all_rows[start_idx : end_idx + 1]
        range_periods = []
        for r in range_rows:
            p, _ = _build_quarterly_period(all_rows, f"{r.fiscal_period} FY{r.fiscal_year}", latest)
            range_periods.append(p)

        total_rev = _sum_nullable(*[r.revenue for r in range_rows])
        total_ni = _sum_nullable(*[r.net_income for r in range_rows])
        total_fcf = _sum_nullable(*[r.free_cash_flow for r in range_rows])
        total_ocf = _sum_nullable(*[r.operating_cash_flow for r in range_rows])
        total_capex = _sum_nullable(*[r.capex for r in range_rows])
        p_count = len(range_rows)
        avg_rev = (total_rev / p_count) if (total_rev is not None and p_count > 0) else None
        c_net_margin = (total_ni / total_rev * 100) if (total_ni is not None and total_rev and total_rev > 0) else None
        c_fcf_margin = (total_fcf / total_rev * 100) if (total_fcf is not None and total_rev and total_rev > 0) else None
        rev_growth = _pct_change(range_rows[-1].revenue, range_rows[0].revenue)
        ni_growth = _pct_change(range_rows[-1].net_income, range_rows[0].net_income)

        start_lbl = labels[start_idx]
        end_lbl = labels[end_idx]
        summary = RangeSummary(
            start_label=start_lbl,
            end_label=end_lbl,
            period_count=p_count,
            total_revenue=total_rev,
            total_net_income=total_ni,
            total_free_cash_flow=total_fcf,
            total_operating_cash_flow=total_ocf,
            total_capex=total_capex,
            avg_revenue=avg_rev,
            cumulative_net_margin=c_net_margin,
            cumulative_fcf_margin=c_fcf_margin,
            revenue_growth_pct=rev_growth,
            net_income_growth_pct=ni_growth,
        )
        current = range_periods[-1]
        chart_dates = [r.period_end.isoformat() for r in range_rows]
        chart_labels = [r.period_end.strftime("%b '%y") for r in range_rows]
        chart_metrics = {
            "revenue": [r.revenue for r in range_rows],
            "net_income": [r.net_income for r in range_rows],
            "free_cash_flow": [r.free_cash_flow for r in range_rows],
            "operating_cash_flow": [r.operating_cash_flow for r in range_rows],
            "capex": [r.capex for r in range_rows],
            "eps_diluted": [r.eps_diluted for r in range_rows],
            "eps_basic": [r.eps_basic for r in range_rows],
            "total_assets": [r.total_assets for r in range_rows],
            "total_liabilities": [r.total_liabilities for r in range_rows],
            "total_equity": [r.total_equity for r in range_rows],
            "cash_and_equivalents": [r.cash_and_equivalents for r in range_rows],
        }
        chart_filing_dates = [_get_filing_date(r) for r in range_rows]
        chart_surprises = _match_surprises_to_dates([r.period_end for r in range_rows], ticker)
        return (
            summary,
            range_periods,
            current,
            start_lbl,
            end_lbl,
            chart_dates,
            chart_labels,
            chart_metrics,
            chart_filing_dates,
            chart_surprises,
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
            press_release=row.press_release_highlights,
            press_release_source=row.press_release_source,
            guidance=row.guidance,
            executive_commentary=row.executive_commentary,
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
            operating_cash_flow=row.operating_cash_flow,
            capex=row.capex,
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
                "operating_cash_flow": row.operating_cash_flow,
                "capex": row.capex,
                "total_assets": row.total_assets,
                "total_liabilities": row.total_liabilities,
                "total_equity": row.total_equity,
                "cash_and_equivalents": row.cash_and_equivalents,
                "updated_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
            },
        )
    )
    session.execute(stmt)
