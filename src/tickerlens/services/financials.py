from __future__ import annotations

import datetime as dt
import logging

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from tickerlens.data.edgar import EdgarClient, normalize_cik
from tickerlens.data.filings import (
    extract_management_guidance,
    extract_press_release_highlights,
    extract_risk_factors,
    extract_transcript_excerpts,
    filing_doc_url,
    latest_annual_filing,
)
from tickerlens.data.sic import sector_for_sic
from tickerlens.data.wikipedia import get_description
from tickerlens.data.xbrl import QuarterlyFinancials, extract_recent_quarterly_financials
from tickerlens.data.yahoo import (
    QuoteSnapshot,
    cached_quote,
    get_quote,
    peeked_day_change_pct,
    peeked_quote,
    warm_change_pct_cache,
    warm_quote_cache,
)
from tickerlens.models.company import Company
from tickerlens.models.database import get_session
from tickerlens.models.quarterly_financial import QuarterlyFinancial
from tickerlens.models.valuation_history import ValuationHistory
from tickerlens.models.watchlist import WatchlistEntry
from tickerlens.services.ir_download import (
    EarningsPeriod,
    discover_earnings_filings,
    er_doc_url,
)
from tickerlens.services.search import get_search_entries, sibling_tickers
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


class SignalChange(BaseModel):
    """A valuation-signal flip between two snapshots (PRD §4.11)."""

    previous_signal: str  # e.g. "Hold"
    previous_date: dt.date  # date of the prior snapshot
    current_signal: str  # e.g. "Buy"


class WatchlistRow(BaseModel):
    """One pinned company for the home screen (PRD §4.6)."""

    cik: str
    ticker: str | None
    name: str
    last_price: float | None
    market_cap: float | None
    signal: str | None  # current valuation signal; None when not computable
    note: str | None = None  # personal reminder; None when unset
    tags: list[str] = []  # free-form tags; [] when untagged


class PopularStock(BaseModel):
    """One of the top traded stocks displayed on the home page."""

    ticker: str
    change_pct: float | None = None


# Watchlist tags (PRD §4.6): at most this many tags per company, each this
# long — enough to group ("dividend", "ai", "watch-earnings") without
# turning the tag editor into a second notes field.
_MAX_WATCHLIST_TAGS = 5
_MAX_WATCHLIST_TAG_LEN = 20


def _normalize_tags(raw: str | None) -> str | None:
    """Normalize a comma-separated tag string for storage.

    Splits on commas, strips whitespace, drops empties, dedupes
    case-insensitively (first casing wins), truncates each tag to
    ``_MAX_WATCHLIST_TAG_LEN`` chars and keeps the first
    ``_MAX_WATCHLIST_TAGS``. Returns None when nothing remains (cleared).
    """
    if not raw:
        return None
    seen: set[str] = set()
    tags: list[str] = []
    for part in raw.split(","):
        tag = part.strip()[:_MAX_WATCHLIST_TAG_LEN].strip()
        if not tag or tag.lower() in seen:
            continue
        seen.add(tag.lower())
        tags.append(tag)
        if len(tags) >= _MAX_WATCHLIST_TAGS:
            break
    return ", ".join(tags) if tags else None


def _split_tags(stored: str | None) -> list[str]:
    """Stored comma-separated tags → list (already normalized at write)."""
    return [t for t in (stored or "").split(", ") if t]


class VsCompany(BaseModel):
    """One side of a cross-company comparison (PRD §4.2, compare slice)."""

    ticker: str
    name: str
    sector: str | None
    period_label: str  # latest quarter, e.g. "Q3 FY2025"
    kpi: KPISnapshot  # latest-quarter KPIs
    yoy: KPIChange  # YoY change on the latest quarter
    last_price: float | None
    market_cap: float | None
    signal: str  # valuation signal: Strong Buy … Strong Sell | Watch
    upside_pct: float | None  # implied upside to target, in percent


class CompanyVs(BaseModel):
    """Side-by-side comparison of two companies' latest quarters."""

    a: VsCompany
    b: VsCompany


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


class RangeTableRow(BaseModel):
    """One metric's values across the range window's quarters (chronological)."""
    label: str                  # "Revenue"
    section: str                # "income" | "cashflow" | "balance"
    kind: str                   # "money" | "eps" — picks the template formatter
    values: list[float | None]


class RangeTableData(BaseModel):
    """Metric × quarters grid for a narrowed chart range window.

    Populated only when the detail view's From/To selectors narrow the window
    to 2+ quarters (PRD §4.2, range-mode slice 2); None means the tabbed
    tables keep their single-selected-period view.
    """
    labels: list[str]           # quarter labels, chronological
    rows: list[RangeTableRow]


class RangeKPIData(BaseModel):
    """Window-aggregated hero KPIs for a narrowed chart range (PRD §4.2).

    Populated only when the detail view's From/To selectors narrow the chart
    window to 2+ quarters (same condition as ``range_table``); None keeps the
    hero cards on the selected single period. Flow metrics are summed over
    the window (same nullable-sum convention as TTM — summed EPS is the
    standard approximation); ``change`` compares each sum against the
    immediately preceding equal-length window.
    """
    label: str                   # "Q4 FY2024 → Q2 FY2025"
    quarters: int                # quarters summed in the window
    kpi: KPISnapshot
    change: KPIChange            # vs prior window; all None when no prior quarters
    prior_label: str | None = None   # "Q1 FY2023 → Q3 FY2024"
    prior_quarters: int = 0


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
    # Chart range window (PRD §4.2, range-mode slice 1): From/To quarter labels
    # bounding the trend chart. Chronological option list; None-safe defaults
    # cover the full history.
    chart_range_options: list[str] = []
    selected_chart_from: str | None = None
    selected_chart_to: str | None = None
    # Range tables (PRD §4.2, range-mode slice 2): metric × quarters grid for
    # a narrowed window (2+ quarters); None keeps the single-period tables.
    range_table: RangeTableData | None = None
    # Range KPIs (PRD §4.2, range-mode slice 3): window-aggregated hero cards
    # for a narrowed window; None keeps the cards on the selected period.
    range_kpi: RangeKPIData | None = None
    # Narrative (company-level, from latest 10-K; None = not available)
    risk_factors: str | None = None
    risk_factors_source: str | None = None
    # Press-release highlights for the *selected* period (None = not available)
    press_release_highlights: str | None = None
    press_release_source: str | None = None
    # Management guidance for the *selected* period (None = not available)
    management_guidance: str | None = None
    management_guidance_source: str | None = None
    # Transcript excerpts / prepared remarks for the *selected* period (None = not available)
    transcript_excerpts: str | None = None
    transcript_source: str | None = None


class MetricDelta(BaseModel):
    """Absolute and percentage change from period B to period A (None = not computable)."""
    absolute: float | None = None
    pct: float | None = None


class CompareDeltas(BaseModel):
    """Cross-period deltas for every KPI and balance-sheet metric."""
    revenue: MetricDelta = MetricDelta()
    net_income: MetricDelta = MetricDelta()
    eps_basic: MetricDelta = MetricDelta()
    eps_diluted: MetricDelta = MetricDelta()
    free_cash_flow: MetricDelta = MetricDelta()
    total_assets: MetricDelta = MetricDelta()
    total_liabilities: MetricDelta = MetricDelta()
    total_equity: MetricDelta = MetricDelta()
    cash_and_equivalents: MetricDelta = MetricDelta()


class CompareContext(BaseModel):
    """Side-by-side comparison of two periods (PRD §4.2).

    mode="quarterly" compares two quarters (slice 1); mode="yearly"
    compares two fiscal-year aggregates (slice 2, added 2026-09-29).
    """
    cik: str
    name: str
    ticker: str | None
    sector: str | None
    last_price: float | None
    market_cap: float | None
    mode: str = "quarterly"     # "quarterly" | "yearly"
    # Selector state
    quarter_options: list[str]  # most recent first, e.g. ["Q4 FY2025", ...]
    year_options: list[int] = []  # most recent first, e.g. [2025, 2024]
    period_a_label: str
    period_b_label: str
    preset: str | None          # "yoy" | "qoq" | "5y" | None (free-form); quarterly only
    # The two periods + cross deltas (A minus B)
    a: PeriodData
    b: PeriodData
    deltas: CompareDeltas


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
            sic=submissions.get("sic"),
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
            sic=submissions.get("sic"),
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

            # Price and market cap are point-in-time snapshots; never wipe a
            # previously-good value when a transient quote failure returns None
            # (same policy as risk factors and press-release highlights below).
            if quote.last_price is not None:
                company.last_price = quote.last_price
            if quote.market_cap is not None:
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

            # One valuation snapshot per day — powers the "signal changed"
            # indicator on the Overview card (PRD §4.11).
            self.record_valuation_snapshot(ticker, session=db)

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
            hl, hl_src, gd, gd_src, ex, ex_src = self._fetch_press_release_disclosures(cik, period)
            if hl is not None:
                row.press_release_highlights = hl
                row.press_release_source = hl_src
            if gd is not None:
                row.management_guidance = gd
                row.management_guidance_source = gd_src
            if ex is not None:
                row.transcript_excerpts = ex
                row.transcript_source = ex_src

    def _fetch_press_release_highlights(
        self, cik: str, period: EarningsPeriod
    ) -> tuple[str | None, str | None]:
        """Fetch an 8-K ex-99 exhibit and extract highlights. Returns (text, source)."""
        hl, hl_src, _, _, _, _ = self._fetch_press_release_disclosures(cik, period)
        return hl, hl_src

    def _fetch_press_release_disclosures(
        self, cik: str, period: EarningsPeriod
    ) -> tuple[str | None, str | None, str | None, str | None, str | None, str | None]:
        """Fetch an 8-K ex-99 exhibit and extract highlights, guidance, and transcript excerpts.

        Best-effort: any network or parse failure yields (None, None, ...) and is
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
                return None, None, None, None, None, None
            html = self.edgar_client.fetch_text(url)
            hl = extract_press_release_highlights(html)
            hl_src = f"Earnings release {period.quarter_label}" if hl else None
            gd = extract_management_guidance(html)
            gd_src = f"8-K guidance, {period.quarter_label}" if gd else None
            ex = extract_transcript_excerpts(html)
            ex_src = f"8-K remarks, {period.quarter_label}" if ex else None
            return hl, hl_src, gd, gd_src, ex, ex_src
        except Exception:
            logger.warning(
                "Press-release extraction failed for CIK %s period %s",
                cik, period.quarter_label, exc_info=True,
            )
            return None, None, None, None, None, None

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

            live_quote = peeked_quote(company.ticker or ticker)
            effective_price = (
                live_quote.last_price
                if (live_quote and live_quote.last_price is not None)
                else company.last_price
            )
            effective_market_cap = (
                live_quote.market_cap
                if (live_quote and live_quote.market_cap is not None)
                else company.market_cap
            )

            return CompanyOverview(
                cik=cik,
                name=company.name,
                ticker=company.ticker,
                description=company.description,
                sector=sector_for_sic(company.sic),
                last_price=effective_price,
                market_cap=effective_market_cap,
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

            live_quote = peeked_quote(company.ticker or ticker)
            effective_price = (
                live_quote.last_price
                if (live_quote and live_quote.last_price is not None)
                else company.last_price
            )
            effective_market_cap = (
                live_quote.market_cap
                if (live_quote and live_quote.market_cap is not None)
                else company.market_cap
            )

            shares_outstanding: float | None = None
            if effective_market_cap and effective_price:
                shares_outstanding = effective_market_cap / effective_price

            return compute_valuation(
                ticker=ticker.upper(),
                current_price=effective_price,
                ttm_eps_diluted=ttm.eps_diluted,
                eps_growth_pct=growth_pct,
                ttm_revenue=ttm.revenue,
                revenue_growth_pct=revenue_growth_pct,
                shares_outstanding=shares_outstanding,
                ttm_quarters=min(4, len(rows)),
                growth_is_fallback=growth_is_fallback,
                ttm_free_cash_flow=ttm.free_cash_flow,
                market_cap=effective_market_cap,
            )
        finally:
            if session is None and self._session is None:
                db.close()

    def record_valuation_snapshot(
        self, ticker: str, session: Session | None = None
    ) -> ValuationHistory | None:
        """Persist today's valuation signal for ``ticker`` (PRD §4.11).

        One row per (cik, date) — refreshing twice in a day updates the row
        in place instead of duplicating it. Called from ``enrich_company`` so
        every refresh leaves a trail; cheap enough to also call standalone.
        Returns ``None`` (and logs) when there is no quarterly data to value
        — enrichment must never fail because of a history snapshot.
        """
        cik = _resolve_cik(self.edgar_client, ticker)
        db = session or self._session or get_session()
        try:
            try:
                valuation = self.get_valuation(ticker, session=db)
            except CompanyNotFoundError:
                logger.info("Skipping valuation snapshot for %s: no quarterly data", ticker)
                return None
            today = dt.date.today()
            stmt = (
                insert(ValuationHistory)
                .values(
                    cik=cik,
                    as_of=today,
                    price=valuation.current_price,
                    target_price=valuation.target_price,
                    upside_pct=valuation.upside_pct,
                    signal=valuation.signal,
                    method=valuation.method,
                )
                .on_conflict_do_update(
                    index_elements=["cik", "as_of"],
                    set_={
                        "price": valuation.current_price,
                        "target_price": valuation.target_price,
                        "upside_pct": valuation.upside_pct,
                        "signal": valuation.signal,
                        "method": valuation.method,
                    },
                )
            )
            db.execute(stmt)
            db.flush()
            snapshot = db.execute(
                select(ValuationHistory).where(
                    ValuationHistory.cik == cik, ValuationHistory.as_of == today
                )
            ).scalar_one()
            if session is None and self._session is None:
                db.commit()
            return snapshot
        finally:
            if session is None and self._session is None:
                db.close()

    def get_signal_change(
        self, ticker: str, session: Session | None = None
    ) -> SignalChange | None:
        """Return the signal flip between the two latest snapshots, if any.

        Compares the newest snapshot against the most recent one from an
        earlier date; ``None`` means no history yet or an unchanged signal.
        """
        cik = _resolve_cik(self.edgar_client, ticker)
        db = session or self._session or get_session()
        try:
            snaps = (
                db.execute(
                    select(ValuationHistory)
                    .where(ValuationHistory.cik == cik)
                    .order_by(ValuationHistory.as_of.desc())
                    .limit(2)
                )
                .scalars()
                .all()
            )
            if len(snaps) < 2:
                return None
            latest, previous = snaps[0], snaps[1]
            if latest.as_of == previous.as_of or latest.signal == previous.signal:
                return None
            return SignalChange(
                previous_signal=previous.signal,
                previous_date=previous.as_of,
                current_signal=latest.signal,
            )
        finally:
            if session is None and self._session is None:
                db.close()

    def watch_ticker(self, ticker: str, session: Session | None = None) -> bool:
        """Pin a company to the watchlist. Returns True (now watching)."""
        cik = _resolve_cik(self.edgar_client, ticker)
        db = session or self._session or get_session()
        try:
            if db.get(Company, cik) is None:
                raise CompanyNotFoundError(f"No data for {ticker} — run fetch_and_persist first")
            if db.get(WatchlistEntry, cik) is None:
                db.add(WatchlistEntry(cik=cik))
                db.commit()
            return True
        finally:
            if session is None and self._session is None:
                db.close()

    def unwatch_ticker(self, ticker: str, session: Session | None = None) -> bool:
        """Remove a company from the watchlist. Returns False (not watching)."""
        cik = _resolve_cik(self.edgar_client, ticker)
        db = session or self._session or get_session()
        try:
            entry = db.get(WatchlistEntry, cik)
            if entry is not None:
                db.delete(entry)
                db.commit()
            return False
        finally:
            if session is None and self._session is None:
                db.close()

    def is_watching(self, ticker: str, session: Session | None = None) -> bool:
        """Whether the ticker's company is on the watchlist."""
        cik = _resolve_cik(self.edgar_client, ticker)
        db = session or self._session or get_session()
        try:
            return db.get(WatchlistEntry, cik) is not None
        finally:
            if session is None and self._session is None:
                db.close()

    def get_watchlist_note(
        self, ticker: str, session: Session | None = None
    ) -> str | None:
        """The personal note on a watched company; None when not watching."""
        cik = _resolve_cik(self.edgar_client, ticker)
        db = session or self._session or get_session()
        try:
            entry = db.get(WatchlistEntry, cik)
            return entry.note if entry is not None else None
        finally:
            if session is None and self._session is None:
                db.close()

    def set_watchlist_note(
        self, ticker: str, note: str | None, session: Session | None = None
    ) -> str | None:
        """Save (or clear, when blank) the note on a watched company.

        Raises CompanyNotFoundError when the ticker is not on the watchlist.
        Notes are capped at 280 characters — a reminder, not an essay.
        """
        cik = _resolve_cik(self.edgar_client, ticker)
        db = session or self._session or get_session()
        try:
            entry = db.get(WatchlistEntry, cik)
            if entry is None:
                raise CompanyNotFoundError(f"{ticker} is not on the watchlist")
            entry.note = (note or "").strip()[:280] or None
            db.commit()
            return entry.note
        finally:
            if session is None and self._session is None:
                db.close()

    def get_watchlist_tags(
        self, ticker: str, session: Session | None = None
    ) -> list[str]:
        """The tags on a watched company; [] when not watching or untagged."""
        cik = _resolve_cik(self.edgar_client, ticker)
        db = session or self._session or get_session()
        try:
            entry = db.get(WatchlistEntry, cik)
            return _split_tags(entry.tags) if entry is not None else []
        finally:
            if session is None and self._session is None:
                db.close()

    def set_watchlist_tags(
        self, ticker: str, tags: str | None, session: Session | None = None
    ) -> list[str]:
        """Save (or clear, when blank) the tags on a watched company.

        Raises CompanyNotFoundError when the ticker is not on the watchlist.
        Tags are normalized (comma-separated, max 5 × 20 chars, deduped).
        Returns the stored tag list.
        """
        cik = _resolve_cik(self.edgar_client, ticker)
        db = session or self._session or get_session()
        try:
            entry = db.get(WatchlistEntry, cik)
            if entry is None:
                raise CompanyNotFoundError(f"{ticker} is not on the watchlist")
            entry.tags = _normalize_tags(tags)
            db.commit()
            return _split_tags(entry.tags)
        finally:
            if session is None and self._session is None:
                db.close()

    def get_watchlist(self, session: Session | None = None) -> list[WatchlistRow]:
        """Pinned companies, most recently added first, with live signals."""
        db = session or self._session or get_session()
        try:
            rows = (
                db.execute(
                    select(WatchlistEntry, Company)
                    .join(Company, Company.cik == WatchlistEntry.cik)
                    .order_by(WatchlistEntry.added_at.desc())
                )
                .all()
            )
            result: list[WatchlistRow] = []
            for entry, company in rows:
                try:
                    signal = self.get_valuation(company.ticker or entry.cik, session=db).signal
                except CompanyNotFoundError:
                    signal = None
                live_quote = peeked_quote(company.ticker) if company.ticker else None
                effective_price = (
                    live_quote.last_price
                    if (live_quote and live_quote.last_price is not None)
                    else company.last_price
                )
                effective_market_cap = (
                    live_quote.market_cap
                    if (live_quote and live_quote.market_cap is not None)
                    else company.market_cap
                )
                result.append(
                    WatchlistRow(
                        cik=entry.cik,
                        ticker=company.ticker,
                        name=company.name,
                        last_price=effective_price,
                        market_cap=effective_market_cap,
                        signal=signal,
                        note=entry.note,
                        tags=_split_tags(entry.tags),
                    )
                )
            return result
        finally:
            if session is None and self._session is None:
                db.close()

    def get_benchmarks(self, session: Session | None = None) -> list[WatchlistRow]:
        """Curated list of market leader benchmarks for the home page."""
        db = session or self._session or get_session()
        try:
            benchmark_tickers = ["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "TSLA"]
            comps = (
                db.execute(
                    select(Company).where(Company.ticker.in_(benchmark_tickers))
                )
                .scalars()
                .all()
            )
            comp_map = {c.ticker.upper(): c for c in comps if c.ticker}
            result: list[WatchlistRow] = []
            for t in benchmark_tickers:
                if t in comp_map:
                    c = comp_map[t]
                    try:
                        val = self.get_valuation(c.ticker, session=db)
                        signal = val.signal
                    except Exception:
                        signal = None
                    live_quote = peeked_quote(c.ticker)
                    effective_price = (
                        live_quote.last_price
                        if (live_quote and live_quote.last_price is not None)
                        else c.last_price
                    )
                    effective_market_cap = (
                        live_quote.market_cap
                        if (live_quote and live_quote.market_cap is not None)
                        else c.market_cap
                    )
                    result.append(
                        WatchlistRow(
                            cik=c.cik,
                            ticker=c.ticker,
                            name=c.name,
                            last_price=effective_price,
                            market_cap=effective_market_cap,
                            signal=signal,
                            note=None,
                            tags=[],
                        )
                    )
            return result
        finally:
            if session is None and self._session is None:
                db.close()

    # Fallback day-change percents for the popular bar, used only when a live
    # Yahoo quote is unavailable (network down, ticker delisted). These are a
    # static seed — the live cached value wins whenever one exists — so the
    # home page never blocks on, or blanks from, a transient quote failure.
    _POPULAR_STOCKS_SEED: tuple[tuple[str, float], ...] = (
        ("NVDA", 3.1),
        ("TSLA", -1.8),
        ("AAPL", 0.5),
        ("AMD", 2.4),
        ("AMZN", 1.2),
        ("MSFT", 0.9),
        ("META", 1.7),
        ("GOOGL", 0.4),
        ("PLTR", 4.2),
        ("NFLX", -0.6),
    )

    def get_popular_stocks(self) -> list[PopularStock]:
        """The 10 most actively traded US public companies with price change %.

        The change percent is the live session day-change from Yahoo Finance.
        Values are served from a 5-minute TTL cache that refreshes in a
        background thread — the home page never waits on the network — with
        the static seed below as the fallback when no live value is cached
        yet (or Yahoo is unreachable). This method never raises.
        """
        try:
            tickers = [t for t, _ in self._POPULAR_STOCKS_SEED]
            warm_change_pct_cache(tickers)
            rows = []
            for ticker, fallback in self._POPULAR_STOCKS_SEED:
                live = peeked_day_change_pct(ticker)
                rows.append(PopularStock(
                    ticker=ticker,
                    change_pct=live if live is not None else fallback,
                ))
            return rows
        except Exception:
            logger.warning("Popular stocks fell back to static seed", exc_info=True)
            return [PopularStock(ticker=t, change_pct=p) for t, p in self._POPULAR_STOCKS_SEED]

    def _vs_company(self, ticker: str, db: Session) -> VsCompany:
        """Build one side of a cross-company comparison from stored data."""
        detail = self.get_detail(ticker, session=db)
        val = self.get_valuation(ticker, session=db)
        return VsCompany(
            ticker=detail.ticker or ticker.upper(),
            name=detail.name,
            sector=detail.sector,
            period_label=detail.current.label,
            kpi=detail.current.kpi,
            yoy=detail.current.yoy,
            last_price=detail.last_price,
            market_cap=detail.market_cap,
            signal=val.signal,
            upside_pct=val.upside_pct,
        )

    def get_company_vs(
        self, ticker_a: str, ticker_b: str, session: Session | None = None
    ) -> CompanyVs:
        """Side-by-side latest-quarter comparison of two companies.

        Raises CompanyNotFoundError when either ticker has no stored data.
        Comparing a company with itself returns two identical sides.
        """
        db = session or self._session or get_session()
        try:
            return CompanyVs(
                a=self._vs_company(ticker_a, db),
                b=self._vs_company(ticker_b, db),
            )
        finally:
            if session is None and self._session is None:
                db.close()

    def get_sibling_tickers(self, ticker: str) -> list[str]:
        """Other SEC-listed tickers for the same CIK ("Also trades as", PRD §4.9).

        e.g. GOOG ⇄ GOOGL. Best-effort — never raises; an empty list means
        no sibling share classes in SEC company_tickers.json (or the lookup
        failed, in which case the header simply hides the hint).
        """
        try:
            cik = _resolve_cik(self.edgar_client, ticker)
        except CompanyNotFoundError:
            return []
        try:
            return sibling_tickers(cik, ticker, get_search_entries(self.edgar_client))
        except Exception:
            return []

    def get_peers(self, ticker: str, session: Session | None = None, limit: int = 5) -> list[PeerItem]:
        """Return top industry/sector peers for a given company (PRD §4.2 Peer Intelligence).

        Best-effort — never raises. Combines curated sector leaders and same-SIC
        stored companies.
        """
        from tickerlens.services.peers import PeerItem, get_peers_for_company

        db = session or self._session or get_session()
        try:
            try:
                cik = _resolve_cik(self.edgar_client, ticker)
                company = db.get(Company, cik)
                sic = company.sic if company else None
            except Exception:
                sic = None
            return get_peers_for_company(ticker, sic=sic, session=db, limit=limit)
        except Exception:
            return get_peers_for_company(ticker, limit=limit)
        finally:
            if session is None and self._session is None:
                db.close()

    def _earnings_companies(
        self,
        watchlist_only: bool,
        session: Session | None,
    ) -> tuple[object, list, set]:
        """Shared DB plumbing for the earnings-calendar readers.

        Returns the open session handle, the companies to render, and the set
        of watched CIKs. The caller owns closing the session.
        """
        from tickerlens.models.watchlist import WatchlistEntry

        db = session or self._session or get_session()
        watched_ciks = set(db.scalars(select(WatchlistEntry.cik)).all())
        query = select(Company)
        if watchlist_only:
            if not watched_ciks:
                return db, [], watched_ciks
            query = query.where(Company.cik.in_(watched_ciks))
        companies = db.scalars(query).all()
        return db, list(companies), watched_ciks

    @staticmethod
    def _build_earnings_events(
        companies: list,
        watched_ciks: set,
        fetch_event,
    ) -> list[EarningsEvent]:
        """Build sorted earnings events using ``fetch_event(ticker, name)``."""
        from tickerlens.data.calendar import EarningsEvent

        events: list[EarningsEvent] = []
        for c in companies:
            if not c.ticker:
                continue
            ev = fetch_event(c.ticker, c.name)
            is_watch = c.cik in watched_ciks
            events.append(
                EarningsEvent(
                    ticker=ev.ticker,
                    company_name=c.name,
                    earnings_date=ev.earnings_date,
                    days_until=ev.days_until,
                    eps_estimate_avg=ev.eps_estimate_avg,
                    revenue_estimate_avg=ev.revenue_estimate_avg,
                    dividend_date=ev.dividend_date,
                    ex_dividend_date=ev.ex_dividend_date,
                    is_watchlist=is_watch,
                )
            )

        events.sort(key=lambda x: (x.earnings_date is None, x.earnings_date or "", x.ticker))
        return events

    def get_upcoming_earnings(
        self,
        watchlist_only: bool = False,
        session: Session | None = None,
    ) -> list[EarningsEvent]:
        """Return upcoming earnings and catalyst dates for tracked companies (PRD §4.5).

        Blocking: fetches cold tickers from Yahoo (each bounded by the
        calendar module's 10s timeout). Use :meth:`get_cached_upcoming_earnings`
        on page renders that must not wait on the network.
        """
        from tickerlens.data.calendar import default_calendar_cache, EarningsEvent

        db = session or self._session or get_session()
        try:
            db, companies, watched_ciks = self._earnings_companies(
                watchlist_only, db
            )
            return self._build_earnings_events(
                companies,
                watched_ciks,
                lambda t, n: default_calendar_cache.get(t, n),
            )
        except Exception:
            logger.warning("Failed to retrieve earnings calendar", exc_info=True)
            return []
        finally:
            if session is None and self._session is None:
                db.close()

    def get_cached_upcoming_earnings(
        self,
        watchlist_only: bool = False,
        session: Session | None = None,
    ) -> list[EarningsEvent]:
        """Non-blocking earnings calendar: cached events only, never fetches.

        Cold tickers kick off a background warmer (see
        ``data.calendar.warm_earnings_cache``) and render as date-less events
        until the next render picks up live values. Home-page renders use this
        so a cold calendar cache can never hang the page.
        """
        from tickerlens.data.calendar import (
            EarningsEvent,
            peeked_earnings_event,
            warm_earnings_cache,
        )

        db = session or self._session or get_session()
        try:
            db, companies, watched_ciks = self._earnings_companies(
                watchlist_only, db
            )
            cold = [
                c.ticker
                for c in companies
                if c.ticker and peeked_earnings_event(c.ticker) is None
            ]
            if cold:
                warm_earnings_cache(cold)

            def _peek_or_empty(ticker: str, name: str | None) -> EarningsEvent:
                ev = peeked_earnings_event(ticker)
                if ev is not None:
                    return ev
                return EarningsEvent(
                    ticker=ticker,
                    company_name=name,
                    earnings_date=None,
                    days_until=None,
                    eps_estimate_avg=None,
                    revenue_estimate_avg=None,
                    dividend_date=None,
                    ex_dividend_date=None,
                )

            return self._build_earnings_events(
                companies, watched_ciks, _peek_or_empty
            )
        except Exception:
            logger.warning("Failed to retrieve cached earnings calendar", exc_info=True)
            return []
        finally:
            if session is None and self._session is None:
                db.close()

    def get_stored_quarters(
        self, ticker: str, session: Session | None = None
    ) -> list[QuarterlyFinancial]:
        """Return all stored quarterly financial records for a ticker in chronological order."""
        cik = _resolve_cik(self.edgar_client, ticker)
        db = session or self._session or get_session()
        try:
            return list(
                db.scalars(
                    select(QuarterlyFinancial)
                    .where(QuarterlyFinancial.cik == cik)
                    .order_by(QuarterlyFinancial.period_end.asc())
                ).all()
            )
        finally:
            if session is None and self._session is None:
                db.close()

    def get_ai_analysis(
        self, ticker: str, session: Session | None = None
    ) -> AIAnalysis:
        """Return comprehensive AI fundamental research briefing (PRD §4.4)."""
        from tickerlens.services.ai_analysis import AIAnalysis, generate_ai_analysis

        overview = self.get_overview(ticker, session=session)
        val = self.get_valuation(ticker, session=session)
        try:
            detail = self.get_detail(ticker, session=session)
        except Exception:
            detail = None
        rows = self.get_stored_quarters(ticker, session=session)
        return generate_ai_analysis(
            overview=overview, detail=detail, valuation=val, rows=rows
        )

    def refresh_watchlist_quotes(
        self, session: Session | None = None
    ) -> dict[str, int]:
        """Refresh Yahoo quotes for every watched company (PRD §4.6, slice 2).

        Quote-only (no Wikipedia / risk-factor / press-release work), so home
        pins stay current without opening each company. Quotes go through the
        5-minute TTL cache, so rapid repeat refreshes don't hammer Yahoo.
        Never wipes a stored price on transient failure; records a valuation
        snapshot per company so the signal-change pill can fire on
        quote-driven flips. Per-ticker failures are counted, not raised.
        Returns {"updated": n, "failed": m}.
        """
        db = session or self._session or get_session()
        try:
            rows = (
                db.execute(
                    select(WatchlistEntry, Company).join(
                        Company, Company.cik == WatchlistEntry.cik
                    )
                )
                .all()
            )
            updated = failed = 0
            for entry, company in rows:
                ticker = company.ticker
                if not ticker:
                    failed += 1
                    continue
                try:
                    quote = cached_quote(ticker)
                    if quote.last_price is not None:
                        company.last_price = quote.last_price
                    if quote.market_cap is not None:
                        company.market_cap = quote.market_cap
                    self.record_valuation_snapshot(ticker, session=db)
                    updated += 1
                except Exception:
                    logger.warning("Watchlist quote refresh failed for %s", ticker)
                    failed += 1
            db.commit()
            return {"updated": updated, "failed": failed}
        finally:
            if session is None and self._session is None:
                db.close()

    def refresh_company_quote(
        self, ticker: str, session: Session | None = None
    ) -> QuoteSnapshot:
        """Fetch the latest cached Yahoo quote for ticker and update the DB if changed.

        Reads through the thread-safe QuoteCache (5-min TTL) and persists
        last_price and market_cap to Company. Never raises on failure;
        preserves existing DB values if quote fetch returns None or fails.
        """
        try:
            cik = _resolve_cik(self.edgar_client, ticker)
        except Exception:
            return QuoteSnapshot(ticker=ticker, last_price=None, market_cap=None, currency=None)

        db = session or self._session or get_session()
        try:
            company = db.get(Company, cik)
            if company is None:
                return QuoteSnapshot(ticker=ticker, last_price=None, market_cap=None, currency=None)
            quote = cached_quote(company.ticker or ticker)
            if quote.last_price is not None:
                company.last_price = quote.last_price
            if quote.market_cap is not None:
                company.market_cap = quote.market_cap
            db.commit()
            return quote
        except Exception:
            logger.warning("Quote refresh failed for %s", ticker, exc_info=True)
            return QuoteSnapshot(ticker=ticker, last_price=None, market_cap=None, currency=None)
        finally:
            if session is None and self._session is None:
                db.close()

    def warm_tracked_quotes(self, session: Session | None = None) -> None:
        """Warm quote cache for benchmarks and watchlist in a background thread."""
        db = session or self._session or get_session()
        try:
            benchmark_tickers = ["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "TSLA"]
            watchlist_tickers = [
                row[0]
                for row in db.execute(
                    select(Company.ticker)
                    .join(WatchlistEntry, WatchlistEntry.cik == Company.cik)
                    .where(Company.ticker.is_not(None))
                ).all()
            ]
            all_tickers = list(dict.fromkeys(benchmark_tickers + watchlist_tickers))
            warm_quote_cache(all_tickers)
        except Exception:
            logger.warning("Could not warm tracked quotes", exc_info=True)
        finally:
            if session is None and self._session is None:
                db.close()

    def get_detail(
        self,
        ticker: str,
        granularity: str = "quarterly",
        selected_quarter: str | None = None,
        selected_year: int | None = None,
        chart_from: str | None = None,
        chart_to: str | None = None,
        session: Session | None = None,
    ) -> DetailContext:
        """Return everything the detail / time-slicer page needs.

        ``chart_from``/``chart_to`` are quarter labels (e.g. "Q1 FY2025") that
        bound the trend chart's range window (PRD §4.2, range-mode slice 1)
        and — when narrowed to 2+ quarters — switch the tabbed tables to a
        metric × quarters grid (slice 2); KPI cards, tables, and downloads
        still follow the selected period. Unknown labels fall back to the
        full history; an inverted range is swapped rather than rejected.
        """
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

            # Chart data — chronological order across all quarters, windowed
            # by the range selectors (PRD §4.2, slice 1).
            window_rows, chart_labels = _chart_window(all_rows, chart_from, chart_to)
            chrono_labels = [f"{r.fiscal_period} FY{r.fiscal_year}" for r in all_rows]
            chart_revenue = [r.revenue for r in window_rows]
            chart_eps = [r.eps_diluted for r in window_rows]

            # Range tables (PRD §4.2, slice 2): when the selectors narrow the
            # window to 2+ quarters, the tabbed tables switch from the
            # single-selected-period view to a metric × quarters grid. A
            # one-quarter window keeps the period view (with its YoY/QoQ
            # columns); yearly mode has no range selectors.
            range_table = (
                _build_range_table(window_rows)
                if granularity == "quarterly" and 2 <= len(window_rows) < len(all_rows)
                else None
            )
            # Range KPIs (PRD §4.2, slice 3): same window condition — the hero
            # cards aggregate over the narrowed window instead of showing the
            # selected single period.
            range_kpi = (
                _build_range_kpi(all_rows, window_rows)
                if granularity == "quarterly" and 2 <= len(window_rows) < len(all_rows)
                else None
            )

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

            live_quote = peeked_quote(company.ticker or ticker)
            effective_price = (
                live_quote.last_price
                if (live_quote and live_quote.last_price is not None)
                else company.last_price
            )
            effective_market_cap = (
                live_quote.market_cap
                if (live_quote and live_quote.market_cap is not None)
                else company.market_cap
            )

            return DetailContext(
                cik=cik,
                name=company.name,
                ticker=company.ticker,
                sector=sector_for_sic(company.sic),
                last_price=effective_price,
                market_cap=effective_market_cap,
                granularity=granularity,
                quarter_options=quarter_options,
                year_options=year_options,
                selected_quarter=selected_quarter,
                selected_year=selected_year,
                current=current,
                chart_labels=chart_labels,
                chart_revenue=chart_revenue,
                chart_eps=chart_eps,
                chart_range_options=chrono_labels,
                selected_chart_from=chart_labels[0],
                selected_chart_to=chart_labels[-1],
                range_table=range_table,
                range_kpi=range_kpi,
                risk_factors=company.risk_factors,
                risk_factors_source=company.risk_factors_source,
                press_release_highlights=pr_row.press_release_highlights if pr_row else None,
                press_release_source=pr_row.press_release_source if pr_row else None,
                management_guidance=pr_row.management_guidance if pr_row else None,
                management_guidance_source=pr_row.management_guidance_source if pr_row else None,
                transcript_excerpts=pr_row.transcript_excerpts if pr_row else None,
                transcript_source=pr_row.transcript_source if pr_row else None,
            )
        finally:
            if session is None and self._session is None:
                db.close()

    def get_compare(
        self,
        ticker: str,
        period_a: str | None = None,
        period_b: str | None = None,
        preset: str | None = None,
        mode: str = "quarterly",
        year_a: int | None = None,
        year_b: int | None = None,
        session: Session | None = None,
    ) -> CompareContext:
        """Side-by-side comparison of two periods (PRD §4.2).

        mode="quarterly" (slice 1): two quarters. A defaults to the latest
        quarter. B follows an explicit ``period_b`` label, the ``preset``
        ("yoy" = same quarter prior year, "qoq" = immediately preceding
        quarter, "5y" = same quarter five years ago, else the oldest
        available quarter), or defaults to YoY. Unknown labels fall back to
        the YoY-ago quarter; when no earlier quarter exists at all, B = A
        and deltas are zero.

        mode="yearly" (slice 2): two fiscal-year aggregates (4-quarter sums
        for flow metrics, year-end values for balance sheet). A defaults to
        the latest fiscal year, B to the prior year; unknown years fall back
        the same way; a single year of history compares A to itself.
        """
        ticker = ticker.upper()
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

            quarter_options = [
                f"{r.fiscal_period} FY{r.fiscal_year}" for r in reversed(all_rows)
            ]
            year_options = sorted({r.fiscal_year for r in all_rows}, reverse=True)

            live_quote = peeked_quote(company.ticker or ticker)
            effective_price = (
                live_quote.last_price
                if (live_quote and live_quote.last_price is not None)
                else company.last_price
            )
            effective_market_cap = (
                live_quote.market_cap
                if (live_quote and live_quote.market_cap is not None)
                else company.market_cap
            )

            common = dict(
                cik=cik,
                name=company.name,
                ticker=company.ticker,
                sector=sector_for_sic(company.sic),
                last_price=effective_price,
                market_cap=effective_market_cap,
                quarter_options=quarter_options,
                year_options=year_options,
            )

            if mode == "yearly":
                a_year = year_a if year_a in year_options else year_options[0]
                b_year = year_b if year_b in year_options else a_year - 1
                if b_year not in year_options:
                    earlier = [y for y in year_options if y < a_year]
                    b_year = earlier[0] if earlier else a_year
                a_data = _build_yearly_period(all_rows, a_year, year_options[0])
                b_data = _build_yearly_period(all_rows, b_year, year_options[0])
                return CompareContext(
                    **common,
                    mode="yearly",
                    period_a_label=a_data.label,
                    period_b_label=b_data.label,
                    preset=None,
                    a=a_data,
                    b=b_data,
                    deltas=_compare_periods(a_data, b_data),
                )

            a_data, a_label = _build_quarterly_period(
                all_rows, period_a or quarter_options[0], latest
            )
            a_idx = next(
                (
                    i
                    for i, r in enumerate(all_rows)
                    if r.fiscal_period == a_data.fiscal_period
                    and r.fiscal_year == a_data.fiscal_year
                ),
                len(all_rows) - 1,
            )

            # Resolve B's target (fp, fy).
            target: tuple[str, int] | None = None
            if period_b:
                parsed = _parse_quarter_label(period_b)
                if parsed and any(
                    r.fiscal_period == parsed[0] and r.fiscal_year == parsed[1]
                    for r in all_rows
                ):
                    target = parsed
            if target is None and preset == "qoq" and a_idx > 0:
                prev = all_rows[a_idx - 1]
                target = (prev.fiscal_period, prev.fiscal_year)
            if target is None and preset == "5y":
                # Same quarter five years back. The 3-year history depth
                # means the exact quarter rarely exists, so fall back to the
                # oldest available quarter (maximum span). The B label always
                # shows the real period, so the button never misleads.
                five = (a_data.fiscal_period, a_data.fiscal_year - 5)
                if any(
                    r.fiscal_period == five[0] and r.fiscal_year == five[1]
                    for r in all_rows
                ):
                    target = five
                elif a_idx > 0:
                    oldest = all_rows[0]
                    target = (oldest.fiscal_period, oldest.fiscal_year)
            if target is None:
                # YoY default (also the preset="yoy" path and every fallback).
                target = (a_data.fiscal_period, a_data.fiscal_year - 1)
                if not any(
                    r.fiscal_period == target[0] and r.fiscal_year == target[1]
                    for r in all_rows
                ):
                    # No YoY-ago quarter: nearest earlier quarter, else A itself.
                    earlier = [r for r in all_rows[:a_idx]]
                    target = (
                        (earlier[-1].fiscal_period, earlier[-1].fiscal_year)
                        if earlier
                        else (a_data.fiscal_period, a_data.fiscal_year)
                    )

            b_data, b_label = _build_quarterly_period(
                all_rows, f"{target[0]} FY{target[1]}", latest
            )

            return CompareContext(
                **common,
                period_a_label=a_label,
                period_b_label=b_label,
                preset=preset if preset in ("yoy", "qoq", "5y") else None,
                a=a_data,
                b=b_data,
                deltas=_compare_periods(a_data, b_data),
            )
        finally:
            if session is None and self._session is None:
                db.close()

    def get_history_zip_entries(
        self, ticker: str, session: Session | None = None
    ) -> tuple[str, list[tuple[str, str]]]:
        """Per-period CSVs for every stored quarter: (ticker, [(arcname, csv)]).

        Arcnames are namespaced under ``{TICKER}/`` so the archive unpacks
        into one folder. Raises CompanyNotFoundError for unknown tickers.
        """
        ticker = ticker.upper()
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
            entries: list[tuple[str, str]] = []
            for row in all_rows:
                label = f"{row.fiscal_period} FY{row.fiscal_year}"
                period, _ = _build_quarterly_period(all_rows, label, latest)
                arcname = f"{ticker}/{_period_csv_filename(ticker, period.label)}"
                entries.append((arcname, render_period_csv(company.name, company.ticker, period)))
            return ticker, entries
        finally:
            if session is None and self._session is None:
                db.close()

    def get_compare_zip_entries(
        self,
        ticker: str,
        *,
        period_a: str | None = None,
        period_b: str | None = None,
        preset: str | None = None,
        mode: str = "quarterly",
        year_a: int | None = None,
        year_b: int | None = None,
        session: Session | None = None,
    ) -> tuple[str, list[tuple[str, str]]]:
        """ZIP entries for the compare view (PRD §4.8, second slice).

        ``{TICKER}/{TICKER}_{A}.csv`` + ``{TICKER}/{TICKER}_{B}.csv`` (reusing
        the per-period renderer) + ``{TICKER}/{TICKER}_compare_summary.csv``
        (metric × A | B | Δ | Δ%). Mirrors the compare page's current
        parameters, so the archive matches what's on screen.
        """
        ctx = self.get_compare(
            ticker,
            period_a=period_a,
            period_b=period_b,
            preset=preset,
            mode=mode,
            year_a=year_a,
            year_b=year_b,
            session=session,
        )
        zip_ticker = (ctx.ticker or ticker).upper()
        entries = [
            (
                f"{zip_ticker}/{_period_csv_filename(zip_ticker, ctx.a.label)}",
                render_period_csv(ctx.name, ctx.ticker, ctx.a),
            ),
            (
                f"{zip_ticker}/{_period_csv_filename(zip_ticker, ctx.b.label)}",
                render_period_csv(ctx.name, ctx.ticker, ctx.b),
            ),
            (
                f"{zip_ticker}/{zip_ticker}_compare_summary.csv",
                render_compare_csv(ctx.name, ctx.ticker, ctx),
            ),
        ]
        return zip_ticker, entries

    def get_range_zip_entries(
        self,
        ticker: str,
        *,
        chart_from: str | None = None,
        chart_to: str | None = None,
        session: Session | None = None,
    ) -> tuple[str, list[tuple[str, str]]]:
        """ZIP entries for the detail view's chart range window (PRD §4.8).

        One ``{TICKER}/{TICKER}_{PERIOD}.csv`` per quarter in the resolved
        window (reusing the per-period renderer) +
        ``{TICKER}/{TICKER}_range_summary.csv`` (metric × quarters, raw
        values). Mirrors the chart's ``chart_from``/``chart_to`` parameters,
        including unknown-label fallback and inverted-range swap, so the
        archive matches what's on screen.
        """
        ticker = ticker.upper()
        cik = _resolve_cik(self.edgar_client, ticker)
        db = session or self._session or get_session()
        try:
            company = db.get(Company, cik)
            if company is None:
                raise CompanyNotFoundError(
                    f"No data for {ticker} — run fetch_and_persist first"
                )
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
            window_rows, window_labels = _chart_window(all_rows, chart_from, chart_to)
            entries: list[tuple[str, str]] = []
            periods: list[PeriodData] = []
            for label in window_labels:
                period, _ = _build_quarterly_period(all_rows, label, latest)
                periods.append(period)
                arcname = f"{ticker}/{_period_csv_filename(ticker, period.label)}"
                entries.append(
                    (arcname, render_period_csv(company.name, company.ticker, period))
                )
            entries.append(
                (
                    f"{ticker}/{ticker}_range_summary.csv",
                    render_range_csv(company.name, company.ticker, periods),
                )
            )
            return ticker, entries
        finally:
            if session is None and self._session is None:
                db.close()

    def get_year_zip_entries(
        self,
        ticker: str,
        year: int | None = None,
        session: Session | None = None,
    ) -> tuple[str, int, list[tuple[str, str]]]:
        """ZIP entries for a single fiscal year (PRD §4.8, fourth slice).

        One ``{TICKER}/{TICKER}_{PERIOD}.csv`` per quarter of the fiscal year
        (reusing the per-period renderer) +
        ``{TICKER}/{TICKER}_year_summary.csv`` (metric × quarters, raw
        values — the same shape as the range summary). An unknown ``year``
        falls back to the latest stored fiscal year, mirroring the
        unknown-label fallback convention elsewhere. Returns
        ``(ticker, resolved_year, entries)``.
        """
        ticker = ticker.upper()
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
            year_rows = [r for r in all_rows if r.fiscal_year == year]
            resolved_year = year if year_rows else latest.fiscal_year
            if not year_rows:
                year_rows = [r for r in all_rows if r.fiscal_year == resolved_year]
            entries: list[tuple[str, str]] = []
            periods: list[PeriodData] = []
            for row in year_rows:
                label = f"{row.fiscal_period} FY{row.fiscal_year}"
                period, _ = _build_quarterly_period(all_rows, label, latest)
                periods.append(period)
                arcname = f"{ticker}/{_period_csv_filename(ticker, period.label)}"
                entries.append(
                    (arcname, render_period_csv(company.name, company.ticker, period))
                )
            entries.append(
                (
                    f"{ticker}/{ticker}_year_summary.csv",
                    render_range_csv(company.name, company.ticker, periods),
                )
            )
            return ticker, resolved_year, entries
        finally:
            if session is None and self._session is None:
                db.close()


def _chart_window(
    all_rows: list[QuarterlyFinancial],
    chart_from: str | None,
    chart_to: str | None,
) -> tuple[list[QuarterlyFinancial], list[str]]:
    """Resolve the range-mode chart window (PRD §4.2).

    Returns ``(window_rows, window_labels)`` in chronological order. Unknown
    labels fall back to the full history; an inverted range is swapped rather
    than rejected. Shared by the detail view and the range-view ZIP download
    so the archive always matches the chart on screen.
    """
    chrono_labels = [f"{r.fiscal_period} FY{r.fiscal_year}" for r in all_rows]
    from_idx = chrono_labels.index(chart_from) if chart_from in chrono_labels else 0
    to_idx = (
        chrono_labels.index(chart_to)
        if chart_to in chrono_labels
        else len(chrono_labels) - 1
    )
    if from_idx > to_idx:
        from_idx, to_idx = to_idx, from_idx
    return all_rows[from_idx : to_idx + 1], chrono_labels[from_idx : to_idx + 1]


def _build_range_table(window_rows: list[QuarterlyFinancial]) -> RangeTableData:
    """Build the metric × quarters grid for a narrowed range window.

    One row per metric (grouped by tab section), one value column per quarter
    in the window, chronological. Values come straight off the stored
    quarterly rows — the same numbers the single-period tables show.
    """
    labels = [f"{r.fiscal_period} FY{r.fiscal_year}" for r in window_rows]

    def _row(
        label: str, section: str, kind: str, attr: str
    ) -> RangeTableRow:
        return RangeTableRow(
            label=label,
            section=section,
            kind=kind,
            values=[getattr(r, attr) for r in window_rows],
        )

    return RangeTableData(
        labels=labels,
        rows=[
            _row("Revenue", "income", "money", "revenue"),
            _row("Net Income", "income", "money", "net_income"),
            _row("EPS Basic", "income", "eps", "eps_basic"),
            _row("EPS Diluted", "income", "eps", "eps_diluted"),
            _row("Free Cash Flow", "cashflow", "money", "free_cash_flow"),
            _row("Total Assets", "balance", "money", "total_assets"),
            _row("Total Liabilities", "balance", "money", "total_liabilities"),
            _row("Total Equity", "balance", "money", "total_equity"),
            _row("Cash & Equivalents", "balance", "money", "cash_and_equivalents"),
        ],
    )


def _build_range_kpi(
    all_rows: list[QuarterlyFinancial], window_rows: list[QuarterlyFinancial]
) -> RangeKPIData:
    """Aggregate hero KPIs over a narrowed range window (PRD §4.2, slice 3).

    Sums follow the TTM nullable-sum convention (a metric sums whatever
    quarters have it; None only when every quarter lacks it). The change
    badges compare against the immediately preceding equal-length window;
    when fewer prior quarters exist the prior window is whatever is
    available, and with none the badges stay blank.
    """
    n = len(window_rows)
    window = _compute_ttm(window_rows)
    prior_rows = [r for r in all_rows if r.period_end < window_rows[0].period_end][
        -n:
    ]
    prior = _compute_ttm(prior_rows)
    labels = [f"{r.fiscal_period} FY{r.fiscal_year}" for r in window_rows]
    prior_labels = [f"{r.fiscal_period} FY{r.fiscal_year}" for r in prior_rows]
    return RangeKPIData(
        label=f"{labels[0]} → {labels[-1]}",
        quarters=n,
        kpi=window,
        change=KPIChange(
            revenue=_pct_change(window.revenue, prior.revenue),
            net_income=_pct_change(window.net_income, prior.net_income),
            eps_basic=_pct_change(window.eps_basic, prior.eps_basic),
            eps_diluted=_pct_change(window.eps_diluted, prior.eps_diluted),
            free_cash_flow=_pct_change(window.free_cash_flow, prior.free_cash_flow),
        ),
        prior_label=(
            f"{prior_labels[0]} → {prior_labels[-1]}" if prior_labels else None
        ),
        prior_quarters=len(prior_rows),
    )


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


def _metric_delta(a: float | None, b: float | None) -> MetricDelta:
    if a is None or b is None:
        return MetricDelta()
    return MetricDelta(absolute=a - b, pct=_pct_change(a, b))


def _compare_periods(a: PeriodData, b: PeriodData) -> CompareDeltas:
    """Cross-period deltas (A minus B) for every KPI and balance-sheet metric."""
    return CompareDeltas(
        revenue=_metric_delta(a.kpi.revenue, b.kpi.revenue),
        net_income=_metric_delta(a.kpi.net_income, b.kpi.net_income),
        eps_basic=_metric_delta(a.kpi.eps_basic, b.kpi.eps_basic),
        eps_diluted=_metric_delta(a.kpi.eps_diluted, b.kpi.eps_diluted),
        free_cash_flow=_metric_delta(a.kpi.free_cash_flow, b.kpi.free_cash_flow),
        total_assets=_metric_delta(a.balance_sheet.total_assets, b.balance_sheet.total_assets),
        total_liabilities=_metric_delta(
            a.balance_sheet.total_liabilities, b.balance_sheet.total_liabilities
        ),
        total_equity=_metric_delta(a.balance_sheet.total_equity, b.balance_sheet.total_equity),
        cash_and_equivalents=_metric_delta(
            a.balance_sheet.cash_and_equivalents, b.balance_sheet.cash_and_equivalents
        ),
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
    # A year-over-year % is only meaningful when both years are complete
    # 4-quarter aggregates; otherwise a 4-quarter sum would be compared
    # against a partial-year sum (e.g. 338% "growth" from a single prior
    # quarter). Incomplete comparisons render as "—".
    yoy = (
        _compute_kpi_yoy(kpi, _compute_ttm(prior_rows))
        if len(year_rows) == 4 and len(prior_rows) == 4
        else KPIChange()
    )

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


# ── per-period CSV export (PRD §4.3 #7) ───────────────────────────────────────

_CSV_METRICS: list[tuple[str, str, str, str]] = [
    # (label, KPISnapshot attr, KPIChange attr, BalanceSheet attr)
    ("Revenue", "revenue", "revenue", ""),
    ("Net Income", "net_income", "net_income", ""),
    ("EPS Basic", "eps_basic", "eps_basic", ""),
    ("EPS Diluted", "eps_diluted", "eps_diluted", ""),
    ("Free Cash Flow", "free_cash_flow", "free_cash_flow", ""),
    ("Total Assets", "", "", "total_assets"),
    ("Total Liabilities", "", "", "total_liabilities"),
    ("Total Equity", "", "", "total_equity"),
    ("Cash & Equivalents", "", "", "cash_and_equivalents"),
]


def render_period_csv(name: str, ticker: str | None, period: PeriodData) -> str:
    """Render one period's financials as CSV (raw numbers, no formatting).

    Pure function of (company name, ticker, PeriodData) — used by both the
    per-period download route and the full-history ZIP builder.
    """
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["# Company", f"{name} ({ticker})" if ticker else name])
    w.writerow(["# Period", period.label])
    if period.period_end:
        w.writerow(["# Period end", period.period_end.isoformat()])
    w.writerow(["# Source", "SEC EDGAR XBRL companyfacts (filing-derived)"])
    w.writerow(["metric", "value", "yoy_pct", "qoq_pct"])
    for label, kpi_attr, chg_attr, bs_attr in _CSV_METRICS:
        if bs_attr:
            value = getattr(period.balance_sheet, bs_attr)
            yoy = getattr(period.balance_sheet_yoy, bs_attr)
            qoq = getattr(period.balance_sheet_qoq, bs_attr) if period.balance_sheet_qoq else None
        else:
            value = getattr(period.kpi, kpi_attr)
            yoy = getattr(period.yoy, chg_attr)
            qoq = getattr(period.qoq, chg_attr) if period.qoq else None
        w.writerow([
            label,
            "" if value is None else repr(value),
            "" if yoy is None else repr(round(yoy, 2)),
            "" if qoq is None else repr(round(qoq, 2)),
        ])
    return buf.getvalue()


def render_compare_csv(name: str, ticker: str | None, ctx: CompareContext) -> str:
    """Render the compare view's metric × (A | B | Δ | Δ%) table as CSV.

    Pure function of (company name, ticker, CompareContext) — raw numbers, no
    formatting, so spreadsheets can compute on the values.
    """
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["# Company", f"{name} ({ticker})" if ticker else name])
    w.writerow(["# Period A", ctx.period_a_label])
    w.writerow(["# Period B", ctx.period_b_label])
    w.writerow(["# Mode", ctx.mode])
    w.writerow(["# Source", "SEC EDGAR XBRL companyfacts (filing-derived)"])
    w.writerow(["metric", "period_a", "period_b", "delta", "delta_pct"])
    for label, kpi_attr, _, bs_attr in _CSV_METRICS:
        if bs_attr:
            a_val = getattr(ctx.a.balance_sheet, bs_attr)
            b_val = getattr(ctx.b.balance_sheet, bs_attr)
        else:
            a_val = getattr(ctx.a.kpi, kpi_attr)
            b_val = getattr(ctx.b.kpi, kpi_attr)
        delta = getattr(ctx.deltas, bs_attr or kpi_attr)
        w.writerow([
            label,
            "" if a_val is None else repr(a_val),
            "" if b_val is None else repr(b_val),
            "" if delta.absolute is None else repr(delta.absolute),
            "" if delta.pct is None else repr(round(delta.pct, 2)),
        ])
    return buf.getvalue()


def render_range_csv(
    name: str, ticker: str | None, periods: list[PeriodData]
) -> str:
    """Render a range window's metrics as one CSV: metric × quarters.

    Pure function of (company name, ticker, PeriodData list) — the summary
    file for the range-view ZIP. Raw numbers, no formatting, one column per
    quarter in chronological order.
    """
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["# Company", f"{name} ({ticker})" if ticker else name])
    w.writerow(["# Periods", " → ".join(p.label for p in periods)])
    w.writerow(["# Source", "SEC EDGAR XBRL companyfacts (filing-derived)"])
    w.writerow(["metric", *[p.label for p in periods]])
    for label, kpi_attr, _, bs_attr in _CSV_METRICS:
        values = []
        for p in periods:
            if bs_attr:
                values.append(getattr(p.balance_sheet, bs_attr))
            else:
                values.append(getattr(p.kpi, kpi_attr))
        w.writerow([label, *["" if v is None else repr(v) for v in values]])
    return buf.getvalue()


def _period_csv_filename(ticker: str | None, label: str) -> str:
    """Safe `{TICKER}_{PERIOD}.csv` filename shared by both download routes."""
    ticker = (ticker or "company").upper()
    safe_label = "".join(c if c.isalnum() else "-" for c in label)
    return f"{ticker}_{safe_label}.csv"


def build_period_csv(ctx: DetailContext) -> str:
    """Render the selected period's financials as CSV.

    Thin wrapper kept for the per-period download route and existing tests.
    """
    return render_period_csv(ctx.name, ctx.ticker, ctx.current)


def download_filename(ctx: DetailContext) -> str:
    """Safe attachment filename for the per-period CSV export."""
    return _period_csv_filename(ctx.ticker, ctx.current.label)


def build_history_zip(ticker: str, entries: list[tuple[str, str]]) -> bytes:
    """Pack per-period CSVs into a ZIP archive (PRD §4.8 first slice).

    ``entries`` are ``(arcname, csv_text)`` pairs; arcnames are namespaced
    under ``{TICKER}/`` so the archive unpacks into one folder. Synchronous,
    in-memory — fine at personal-use scale (8 quarters ≈ tens of KB).
    """
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, csv_text in entries:
            zf.writestr(arcname, csv_text.encode("utf-8"))
    return buf.getvalue()
