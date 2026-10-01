from __future__ import annotations

import datetime as dt
import calendar
import logging
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


class Metric(StrEnum):
    REVENUE = "revenue"
    NET_INCOME = "net_income"
    EPS_BASIC = "eps_basic"
    EPS_DILUTED = "eps_diluted"
    OPERATING_CASH_FLOW = "operating_cash_flow"
    CAPEX = "capex"
    # Balance-sheet metrics are *instant* (point-in-time) facts, not durations.
    TOTAL_ASSETS = "total_assets"
    TOTAL_LIABILITIES = "total_liabilities"
    TOTAL_EQUITY = "total_equity"
    CASH_AND_EQUIVALENTS = "cash_and_equivalents"


class ConceptSpec(BaseModel):
    tags: tuple[str, ...]
    unit: str


class XbrlFact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    end: dt.date
    val: float
    filed: dt.date
    form: str
    start: dt.date | None = None
    fy: int | None = None
    fp: str | None = None


class PeriodMetric(BaseModel):
    metric: Metric
    fy: int
    fp: str
    end: dt.date
    value: float
    source_tag: str

    @property
    def period(self) -> str:
        return f"FY{self.fy} {self.fp}"


class QuarterlyFinancials(BaseModel):
    fy: int
    fp: str
    end: dt.date
    revenue: float | None = None
    net_income: float | None = None
    eps_basic: float | None = None
    eps_diluted: float | None = None
    free_cash_flow: float | None = None
    # Balance sheet (instant, as of period end)
    total_assets: float | None = None
    total_liabilities: float | None = None
    total_equity: float | None = None
    cash_and_equivalents: float | None = None

    @property
    def period(self) -> str:
        return f"FY{self.fy} {self.fp}"


CONCEPTS: dict[Metric, ConceptSpec] = {
    Metric.REVENUE: ConceptSpec(
        tags=(
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "Revenues",
            "SalesRevenueNet",
            "SalesRevenueGoodsNet",
        ),
        unit="USD",
    ),
    # Net income: filers sometimes abandon plain ``NetIncomeLoss`` and report
    # only per-common-share net income (e.g. Realty Income stopped filing
    # ``NetIncomeLoss`` quarterly in 2026, filing only
    # ``NetIncomeLossAvailableToCommonStockholdersBasic`` + ``ProfitLoss``).
    # The freshness rule below skips abandoned tags, so these fallbacks only
    # kick in when ``NetIncomeLoss`` is stale or absent.
    Metric.NET_INCOME: ConceptSpec(
        tags=(
            "NetIncomeLoss",
            "NetIncomeLossAvailableToCommonStockholdersBasic",
            "ProfitLoss",
        ),
        unit="USD",
    ),
    Metric.EPS_BASIC: ConceptSpec(tags=("EarningsPerShareBasic",), unit="USD/shares"),
    Metric.EPS_DILUTED: ConceptSpec(tags=("EarningsPerShareDiluted",), unit="USD/shares"),
    Metric.OPERATING_CASH_FLOW: ConceptSpec(
        tags=(
            "NetCashProvidedByUsedInOperatingActivities",
            # AT&T switched its 2026 10-Qs to continuing-operations cash flow
            # (plain tag stops at 2025-12-31) while discontinued-ops cash flow
            # rounds to ~$0; the freshness rule picks whichever is current and
            # the gap-fill below backfills quarters the winner lacks.
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ),
        unit="USD",
    ),
    Metric.CAPEX: ConceptSpec(
        tags=(
            "PaymentsToAcquirePropertyPlantAndEquipment",
            # NVDA abandoned the tag above after 2020 and now files CapEx as
            # "Purchases of property and equipment" under this tag.
            "PaymentsToAcquireProductiveAssets",
            # Eli Lilly never filed the classic tag at all and files CapEx as
            # "Capital expenditures" under this tag (current through 2026).
            "PaymentsToAcquireOtherPropertyPlantAndEquipment",
        ),
        unit="USD",
    ),
    Metric.TOTAL_ASSETS: ConceptSpec(tags=("Assets",), unit="USD"),
    Metric.TOTAL_LIABILITIES: ConceptSpec(tags=("Liabilities",), unit="USD"),
    Metric.TOTAL_EQUITY: ConceptSpec(
        tags=(
            # Total equity includes noncontrolling interests — this tag is the
            # one that satisfies Assets = Liabilities + Equity (e.g. NEE's
            # 2026-03-31: 154.79 + 66.63 = 221.42 exactly; parent-only
            # StockholdersEquity leaves an $11.4B gap). Parent-only stays as
            # the fallback for filers that don't report the total.
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
            "StockholdersEquity",
        ),
        unit="USD",
    ),
    Metric.CASH_AND_EQUIVALENTS: ConceptSpec(
        tags=(
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ),
        unit="USD",
    ),
}

BALANCE_SHEET_METRICS: tuple[Metric, ...] = (
    Metric.TOTAL_ASSETS,
    Metric.TOTAL_LIABILITIES,
    Metric.TOTAL_EQUITY,
    Metric.CASH_AND_EQUIVALENTS,
)


def extract_recent_quarterly_financials(
    companyfacts: dict[str, Any],
    *,
    fiscal_year_end: str | None = None,
    periods: int = 4,
    sic: str | int | None = None,
) -> list[QuarterlyFinancials]:
    """Extract recent Revenue, Net Income, EPS, and FCF from SEC companyfacts.

    ``sic`` selects the revenue concept: finance filers (SIC 6000-6299) report
    revenue as noninterest income + net interest income rather than a single
    ``Revenues`` tag.
    """

    # Revenue is the canonical anchor — hard failure if missing.
    revenue = quarterly_income_metric(
        companyfacts, Metric.REVENUE, fiscal_year_end, sic=sic
    )

    def _safe(fn: Callable, metric: Metric) -> list[PeriodMetric]:
        try:
            return fn(companyfacts, metric, fiscal_year_end)
        except KeyError:
            logger.warning("No XBRL facts for %s — storing None", metric.value)
            return []

    def _safe_bs(metric: Metric) -> dict[dt.date, float]:
        try:
            return balance_sheet_metric(companyfacts, metric, fiscal_year_end)
        except KeyError:
            logger.warning("No XBRL facts for %s — storing None", metric.value)
            return {}

    net_income  = _safe(quarterly_income_metric,    Metric.NET_INCOME)
    eps_basic   = _safe(quarterly_income_metric,    Metric.EPS_BASIC)
    eps_diluted = _safe(quarterly_income_metric,    Metric.EPS_DILUTED)
    # A filing may omit EarningsPerShareBasic for a quarter while filing
    # EarningsPerShareDiluted (Goldman Sachs's Q2 2026 10-Q files diluted
    # only). Basic wins wherever it exists; diluted fills only missing ends,
    # so the displayed "EPS (Basic)" never blanks for a filed quarter.
    eps_basic   = _fill_missing_eps_basic(eps_basic, eps_diluted)
    opcf        = _safe(quarterly_cash_flow_metric, Metric.OPERATING_CASH_FLOW)
    capex       = _safe(quarterly_cash_flow_metric, Metric.CAPEX)
    balance_sheet = {metric: _safe_bs(metric) for metric in BALANCE_SHEET_METRICS}
    # Filers that never report a standalone ``Liabilities`` tag (e.g. Eli
    # Lilly files only LiabilitiesAndStockholdersEquity + StockholdersEquity),
    # or never report an ``Equity`` tag (e.g. Visa files Assets + Liabilities
    # only), get the missing instant from the accounting identity instead of
    # "—".
    _derive_missing_balance_sheet(balance_sheet)

    canonical = sorted(revenue, key=lambda item: item.end)[-periods:]
    by_end = {
        Metric.NET_INCOME: _by_end(net_income),
        Metric.EPS_BASIC: _by_end(eps_basic),
        Metric.EPS_DILUTED: _by_end(eps_diluted),
        Metric.OPERATING_CASH_FLOW: _by_end(opcf),
        Metric.CAPEX: _by_end(capex),
    }

    rows: list[QuarterlyFinancials] = []
    for item in canonical:
        operating_cash_flow = by_end[Metric.OPERATING_CASH_FLOW].get(item.end)
        capital_expenditure = by_end[Metric.CAPEX].get(item.end)
        # FCF is not a meaningful metric for finance filers (SIC 6000-6999):
        # operating cash flow is dominated by balance-sheet flows (loan
        # originations, deposits), so OpCF − CapEx misleads more than it
        # informs. Banks/insurers/REITs already render "—" because they file
        # no CapEx tag; SoFi files one, so suppress explicitly for consistency.
        free_cash_flow = (
            None
            if _is_finance_sic(sic)
            else (
                operating_cash_flow.value - capital_expenditure.value
                if operating_cash_flow and capital_expenditure
                else None
            )
        )
        rows.append(
            QuarterlyFinancials(
                fy=item.fy,
                fp=item.fp,
                end=item.end,
                revenue=item.value,
                net_income=_value_for_end(by_end[Metric.NET_INCOME], item.end),
                eps_basic=_value_for_end(by_end[Metric.EPS_BASIC], item.end),
                eps_diluted=_value_for_end(by_end[Metric.EPS_DILUTED], item.end),
                free_cash_flow=free_cash_flow,
                total_assets=balance_sheet[Metric.TOTAL_ASSETS].get(item.end),
                total_liabilities=balance_sheet[Metric.TOTAL_LIABILITIES].get(item.end),
                total_equity=balance_sheet[Metric.TOTAL_EQUITY].get(item.end),
                cash_and_equivalents=balance_sheet[Metric.CASH_AND_EQUIVALENTS].get(item.end),
            )
        )
    return _dedupe_period_labels(rows)


def _fill_missing_eps_basic(
    basic: list[PeriodMetric], diluted: list[PeriodMetric]
) -> list[PeriodMetric]:
    """Fill per-quarter gaps in basic EPS from diluted EPS.

    Whole-chain tag selection is correct for Goldman Sachs — it still files
    ``EarningsPerShareBasic`` most quarters — but its Q2 2026 10-Q filed
    ``EarningsPerShareDiluted`` only. Basic is preferred wherever present;
    diluted facts fill only ends with no basic fact (basic and diluted EPS
    differ by fractions of a percent, so the merged value stays under the
    EPS_BASIC metric with the diluted fact's source tag).
    """
    by_end = {m.end: m for m in basic}
    for m in diluted:
        if m.end not in by_end:
            by_end[m.end] = PeriodMetric(
                metric=Metric.EPS_BASIC,
                fy=m.fy,
                fp=m.fp,
                end=m.end,
                value=m.value,
                source_tag=m.source_tag,
            )
    return sorted(by_end.values(), key=lambda item: item.end)


def _dedupe_period_labels(rows: list[QuarterlyFinancials]) -> list[QuarterlyFinancials]:
    """Ensure (fy, fp) labels are unique across rows.

    Comparative prior-period columns in a later filing inherit that filing's
    ``fy`` — when the original filing is absent from the CIK's dataset (e.g.
    XOM's new-CIK history holds only the 2026 10-Q), the 2025 comparative
    column is tagged fy=2026 and collides with the real Q2 FY2026, duplicating
    selector options. A fiscal year has exactly one of each quarter, so when
    two period ends share a label the earlier one is the mislabeled
    comparative: walk its year back until the label is free. The later end
    keeps its label because its original filing is the trustworthy source.
    """
    seen: set[tuple[int, str]] = set()
    # Latest end first: its original filing is the trustworthy label source,
    # so it claims the label and earlier (comparative) ends walk back.
    for row in sorted(rows, key=lambda item: item.end, reverse=True):
        while (row.fy, row.fp) in seen:
            row.fy -= 1
        seen.add((row.fy, row.fp))
    return rows


# Stock splits restate per-share facts: the same (start, end) reported at two
# filings whose values differ by an integer split ratio. Restated values are
# exact divisions (7.19 -> 0.72), so a 3% tolerance is generous; anything
# coarser risks mistaking an accounting restatement for a split.
_SPLIT_RATIOS = (2, 3, 4, 5, 10, 20, 100)
_SPLIT_RATIO_TOLERANCE = 0.03
# A lone (start, end) pair at a split-like ratio could be a data correction,
# so an event needs corroboration from a second duration (e.g. the quarterly
# fact and the 6M YTD fact both restated 10x).
_SPLIT_MIN_CORROBORATING_GROUPS = 2

# Two restating filings can observe the same split (NFLX's FY2025 10-K and
# Q2-2026 10-Q each restated pre-split comparatives ~10x, six months apart).
# Without merging, pre-split facts would be rescaled twice. Events with
# near-identical scales close in time are one split; genuinely repeated
# splits (same ratio, well separated in time) stay distinct.
_SPLIT_MERGE_MAX_DAYS = 400


def _split_adjust_facts(facts: list[XbrlFact]) -> None:
    """Rescale pre-split per-share facts to the latest filing's share basis.

    After a stock split the filer restates comparative per-share facts in
    later filings (NFLX's 10-for-1 split restated Q2-2025 diluted EPS from
    7.19 to 0.72 in the 2026 10-Q), but facts filed before the restating
    filing stay on the old basis — mixing them produced a bogus -87%
    "trend" and a -13.58 derived Q4. Facts are mutated in place; callers
    pass freshly built lists.

    Classification per fact:
    - its period was demonstrably restated at a split ratio → pre-split,
      rescale unconditionally;
    - otherwise (e.g. NFLX's Q3-2025, filed pre-split but never restated
      since) → rescale only if the rescaled value is clearly closer to the
      post-split neighborhood (nearest certain-basis quarters) than the
      original, so genuinely post-split facts (NFLX's Q1-2026, filed
      2026-04-17, before the restating 10-Q) are left alone.
    """
    events = _detect_split_events(facts)
    if not events:
        return
    min_event_date = min(event.date for event in events)
    # Post-split reference values: restated comparatives (latest filed wins)
    # and any fact filed on/after the first restating filing.
    latest_by_end: dict[dt.date, XbrlFact] = {}
    for fact in facts:
        prev = latest_by_end.get(fact.end)
        if prev is None or fact.filed > prev.filed:
            latest_by_end[fact.end] = fact
    certain: dict[dt.date, float] = {}
    for end, fact in latest_by_end.items():
        if end in {e for event in events for e in event.period_ends} or fact.filed >= min_event_date:
            certain[end] = fact.val
    certain_ends = sorted(certain)

    for fact in facts:
        scale = 1.0
        for event in events:
            if event.date > fact.filed:
                scale *= event.scale
        if scale == 1.0:
            continue
        if fact.end in {e for event in events for e in event.period_ends}:
            fact.val *= scale
            continue
        expected = _neighbor_value(fact.end, certain_ends, certain)
        if expected is not None and abs(fact.val * scale - expected) < 0.5 * abs(fact.val - expected):
            fact.val *= scale


def _neighbor_value(
    end: dt.date, certain_ends: list[dt.date], certain: dict[dt.date, float]
) -> float | None:
    """Interpolate the expected post-split value from certain-basis neighbors."""
    below = [e for e in certain_ends if e < end]
    above = [e for e in certain_ends if e > end]
    if below and above:
        lo, hi = below[-1], above[0]
        span = (hi - lo).days or 1
        w = (end - lo).days / span
        return certain[lo] * (1 - w) + certain[hi] * w
    if below:
        return certain[below[-1]]
    if above:
        return certain[above[0]]
    return None


class _SplitEvent:
    """A detected stock split: the restating filing's date, the rescale
    factor for pre-split facts, and the period ends whose restatement
    corroborated it (those periods are certainly pre-split)."""

    def __init__(self, date: dt.date, scale: float, period_ends: set[dt.date]) -> None:
        self.date = date
        self.scale = scale
        self.period_ends = period_ends


def _detect_split_events(facts: list[XbrlFact]) -> list[_SplitEvent]:
    """Detect stock splits from restated comparatives.

    Groups facts by ``(start, end)``; a group whose consecutive filings
    report values differing by ~a split ratio casts one vote for the later
    filing's date. An event fires only with enough corroborating groups (a
    lone split-like ratio could be a data correction), and duplicate events
    on the same filing date collapse to their median scale.
    """
    by_period: dict[tuple[dt.date | None, dt.date], dict[dt.date, set[float]]] = {}
    for fact in facts:
        by_period.setdefault((fact.start, fact.end), {}).setdefault(fact.filed, set()).add(fact.val)

    votes: dict[dt.date, list[tuple[float, dt.date]]] = {}
    for (start, end), by_filed in by_period.items():
        if start is None:
            continue
        # One filing reporting two values for the same period is ambiguous
        # (or a data error) — it can't corroborate anything.
        if any(len(vals) != 1 for vals in by_filed.values()):
            continue
        ordered = sorted((filed, next(iter(vals))) for filed, vals in by_filed.items())
        for (filed_a, val_a), (filed_b, val_b) in zip(ordered, ordered[1:]):
            if val_a == 0:
                continue
            ratio = val_b / val_a
            if any(
                abs(ratio - r) / r <= _SPLIT_RATIO_TOLERANCE
                or abs(ratio - 1 / r) / (1 / r) <= _SPLIT_RATIO_TOLERANCE
                for r in _SPLIT_RATIOS
            ):
                votes.setdefault(filed_b, []).append((ratio, end))

    events = []
    for event_date, corroborated in votes.items():
        if len(corroborated) < _SPLIT_MIN_CORROBORATING_GROUPS:
            logger.info(
                "skipping lone split-like ratio on %s (needs %d corroborating groups)",
                event_date, _SPLIT_MIN_CORROBORATING_GROUPS,
            )
            continue
        ratios = sorted(ratio for ratio, _ in corroborated)
        scale = ratios[len(ratios) // 2]
        period_ends = {end for _, end in corroborated}
        logger.warning(
            "stock split detected: restated %s, rescaling earlier per-share facts by %s",
            event_date, scale,
        )
        events.append(_SplitEvent(event_date, scale, period_ends))
    return _merge_duplicate_events(events)


def _merge_duplicate_events(events: list[_SplitEvent]) -> list[_SplitEvent]:
    """Collapse multiple observations of one split into a single event."""
    merged: list[_SplitEvent] = []
    for event in sorted(events, key=lambda e: e.date):
        for kept in merged:
            same_scale = abs(kept.scale - event.scale) / kept.scale <= _SPLIT_RATIO_TOLERANCE
            if same_scale and abs((kept.date - event.date).days) <= _SPLIT_MERGE_MAX_DAYS:
                kept.period_ends |= event.period_ends
                break
        else:
            merged.append(event)
    return merged


def quarterly_income_metric(
    companyfacts: dict[str, Any],
    metric: Metric,
    fiscal_year_end: str | None = None,
    sic: str | int | None = None,
) -> list[PeriodMetric]:
    # Finance filers (SIC Division H) report revenue differently: prefer the
    # filer's own total-revenue tag when current (MET's contract-revenue tag
    # is a $0.7B fee-income sub-component vs $19B total Revenues); banks that
    # file Revenues only annually fall through to the component composite.
    # Falls back to the generic chain when neither is available (e.g.
    # insurers without quarterly Revenues).
    if metric is Metric.REVENUE and _is_finance_sic(sic):
        total = _finance_total_revenue(companyfacts, fiscal_year_end)
        if total:
            return total
        if _is_bank_sic(sic):
            composite = _bank_quarterly_revenue(companyfacts, fiscal_year_end)
            if composite:
                return composite
        logger.warning(
            "finance revenue preference unavailable — falling back to generic chain"
        )
    # Q4 EPS can't be derived by subtracting per-share values (the annual and
    # 9M figures divide by different share counts), so pass the net-income
    # facts for the share-implied derivation. Dollar metrics need nothing.
    ni_facts: list[XbrlFact] | None = None
    if metric in (Metric.EPS_BASIC, Metric.EPS_DILUTED):
        try:
            _, ni_facts = concept_facts(
                companyfacts, Metric.NET_INCOME, staleness_window=(70, 100)
            )
        except KeyError:
            ni_facts = None
    spec = CONCEPTS[metric]
    candidates = _chain_candidates(
        companyfacts,
        spec.tags,
        spec.unit,
        staleness_window=(70, 100),
        metric_name=metric.value,
    )
    # Per-share metrics must share one share basis: after a stock split the
    # filer restates comparative per-share facts in later filings (NFLX's
    # 10-for-1 split restated Q2-2025 diluted EPS from 7.19 to 0.72 in the
    # 2026 10-Q), but facts filed before the restating filing stay on the
    # old basis — mixing them produced a bogus -87% "trend" and a -13.58
    # derived Q4. Rescale pre-split facts to the latest basis first so the
    # Q4 share-implied derivation below also sees consistent NI/EPS pairs.
    if metric in (Metric.EPS_BASIC, Metric.EPS_DILUTED):
        _split_adjust_facts([fact for _, facts in candidates for fact in facts])
    return _merge_gap_fill(
        [
            _income_series_for_tag(metric, tag, facts, fiscal_year_end, ni_facts)
            for tag, facts in candidates
        ]
    )


def _income_series_for_tag(
    metric: Metric,
    source_tag: str,
    facts: list[XbrlFact],
    fiscal_year_end: str | None,
    ni_facts: list[XbrlFact] | None = None,
) -> list[PeriodMetric]:
    """Quarterly series from one tag: standalone quarters + derived Q4s."""
    standalone = _dedup_by_end(facts, 70, 100, fiscal_year_end)
    q4 = _derive_q4_income(facts, source_tag, metric, fiscal_year_end, ni_facts=ni_facts)
    return _merge_standalone_with_q4(metric, source_tag, standalone, q4)


def _merge_gap_fill(series_list: list[list[PeriodMetric]]) -> list[PeriodMetric]:
    """Merge per-tag quarterly series, gap-filling ends earlier tags lack.

    Earlier series win every end they cover; later series contribute only
    ends absent from all earlier ones. This backfills quarters a filer's
    mid-history tag switch left blank (AT&T OpCF, Intel cash) without
    changing any value the winning tag already supplied.
    """
    by_end: dict[dt.date, PeriodMetric] = {}
    for series in series_list:
        for item in series:
            by_end.setdefault(item.end, item)
    return sorted(by_end.values(), key=lambda item: item.end)


def _merge_standalone_with_q4(
    metric: Metric,
    source_tag: str,
    standalone: list[XbrlFact],
    q4: list[PeriodMetric],
) -> list[PeriodMetric]:
    """Merge quarterly facts with derived Q4 rows, fixing mislabeled Q4 stubs.

    A 70–100-day fact is quarterly by duration, so an fp="FY" label on one is
    a filer mislabeling of its 10-K Q4 stub (ABBV's 10-K tags the 91-day Q4
    Revenues fact fp="FY"; verified against raw SEC JSON). The filer's own
    quarterly fact is authoritative over the derived Q4 row, so relabel it
    and let it supersede the duplicate — otherwise the phantom FY row steals
    a slot in the recent-periods slice and collides on (cik, period_end) at
    upsert (and in the bank composite it would be *summed* with the derived
    Q4, roughly doubling the quarter).
    """
    derived_q4_ends = {item.end for item in q4}
    metrics: list[PeriodMetric] = []
    superseded_q4: set[dt.date] = set()
    for fact in standalone:
        pm = _period_metric(metric, source_tag, fact)
        if pm.fp == "FY" and pm.end in derived_q4_ends:
            pm = pm.model_copy(update={"fp": "Q4"})
            superseded_q4.add(pm.end)
        metrics.append(pm)
    metrics.extend(item for item in q4 if item.end not in superseded_q4)
    return sorted(metrics, key=lambda item: item.end)


def quarterly_cash_flow_metric(
    companyfacts: dict[str, Any],
    metric: Metric,
    fiscal_year_end: str | None = None,
) -> list[PeriodMetric]:
    spec = CONCEPTS[metric]
    candidates = _chain_candidates(
        companyfacts, spec.tags, spec.unit, metric_name=metric.value
    )
    return _merge_gap_fill(
        [
            _cash_flow_series_for_tag(metric, tag, facts, fiscal_year_end)
            for tag, facts in candidates
        ]
    )


def _cash_flow_series_for_tag(
    metric: Metric,
    source_tag: str,
    facts: list[XbrlFact],
    fiscal_year_end: str | None,
) -> list[PeriodMetric]:
    """Uncumulative quarterly cash-flow series from one tag's YTD facts."""
    q1s = _dedup_by_end(facts, 75, 105, fiscal_year_end)
    h1s = _dedup_by_end(facts, 165, 200, fiscal_year_end)
    # 52/53-week filers (e.g. Costco's 36-week 9M = 251 days) run shorter than
    # a nominal 273-day 9M; the 240-day floor covers them without touching the
    # H1 (≤200d) or full-year (≥340d) windows. Keep in sync with _derive_q4_income.
    m9s = _dedup_by_end(facts, 240, 290, fiscal_year_end)
    years = _dedup_by_end(facts, 340, 380, fiscal_year_end)

    q1_by_start = _by_start(q1s)
    h1_by_start = _by_start(h1s)
    m9_by_start = _by_start(m9s)
    year_by_start = _by_start(years)

    results: list[PeriodMetric] = []
    for start in set(q1_by_start) | set(h1_by_start) | set(m9_by_start) | set(year_by_start):
        q1 = q1_by_start.get(start)
        h1 = h1_by_start.get(start)
        m9 = m9_by_start.get(start)
        year = year_by_start.get(start)
        label_fact = year or m9 or h1 or q1
        if label_fact is None:
            continue
        fy = _fact_fy(label_fact)

        if q1:
            results.append(_metric_value(metric, source_tag, fy, "Q1", q1.end, q1.val))
        if h1 and q1:
            results.append(_metric_value(metric, source_tag, fy, "Q2", h1.end, h1.val - q1.val))
        if m9 and h1:
            results.append(_metric_value(metric, source_tag, fy, "Q3", m9.end, m9.val - h1.val))
        if year and m9:
            results.append(
                _metric_value(metric, source_tag, fy, "Q4", year.end, year.val - m9.val)
            )

    return sorted(results, key=lambda item: item.end)


# A tag whose newest fact is more than this far behind the freshest tag in the
# chain is considered abandoned by the filer. Two full filing cycles (~180
# days): the relative rule compares tags from the *same* filer, so a slow
# filer is never penalized (all its tags lag together); a tag missing for two
# consecutive quarters while a sibling tag stays current is abandonment, even
# when the switch is recent (Realty Income dropped quarterly ``NetIncomeLoss``
# only ~273 days before the replacement tag's newest fact; PLUG's stale tag
# lagged by 5+ years).
_MAX_TAG_STALENESS_DAYS = 180


def concept_facts(
    companyfacts: dict[str, Any],
    metric: Metric,
    *,
    instant: bool = False,
    staleness_window: tuple[int, int] | None = None,
) -> tuple[str, list[XbrlFact]]:
    """Return (source_tag, facts) for the best tag in the metric's fallback chain.

    Duration facts (income, cash flow) carry both ``start`` and ``end``; instant
    facts (balance sheet) carry only ``end``. Pass ``instant=True`` to keep the
    latter, which would otherwise be filtered out by the ``start`` requirement.

    Chain order expresses semantic preference, but a tag whose newest fact is
    far older than the newest fact across the whole chain has been abandoned
    by the filer (e.g. PLUG's ``...IncludingAssessedTax`` quarterly facts end
    in 2020 while ``Revenues`` runs through 2026). Such stale tags are skipped
    so the tool never presents years-old data as current. ``staleness_window``
    optionally restricts which facts count toward a tag's "newest" to a
    duration range in days — the quarterly path passes its 70–100 day window
    so a tag kept alive only by half-year facts still counts as abandoned.
    If no tag is fresh enough, falls back to the first non-empty tag
    (previous behavior).
    """
    spec = CONCEPTS[metric]
    return _select_tag_facts(
        companyfacts,
        spec.tags,
        spec.unit,
        instant=instant,
        staleness_window=staleness_window,
        metric_name=metric.value,
    )


def _select_tag_facts(
    companyfacts: dict[str, Any],
    tags: tuple[str, ...],
    unit: str,
    *,
    instant: bool = False,
    staleness_window: tuple[int, int] | None = None,
    metric_name: str = "",
) -> tuple[str, list[XbrlFact]]:
    """Return (source_tag, facts) for the best tag among ``tags``.

    Same semantics as :func:`concept_facts`, but takes an explicit tag chain
    instead of a :class:`Metric` — used for the bank revenue composite, whose
    components (e.g. ``NoninterestIncome``) are not full ``Metric`` entries.
    """
    return _chain_candidates(
        companyfacts,
        tags,
        unit,
        instant=instant,
        staleness_window=staleness_window,
        metric_name=metric_name,
    )[0]


# A gap-fill tag whose newest fact is more than this far behind the freshest
# tag in the chain is too abandoned to backfill from — its old facts would
# pollute the recent window rather than repair a recent tag switch. Four
# quarters is the bar: a tag that filed within the last year is plausibly
# part of current history (AT&T's plain OpCF tag, 181 days behind the
# continuing-operations tag, still backfills 2024-2025 quarters), while a tag
# dead for over a year (an insurer's absolutely-stale ``Revenues``, 640 days
# behind) stays out. Gap-fill never overrides the winner, so this is
# deliberately laxer than the 180-day winner-take-all abandonment rule.
_GAP_FILL_MAX_STALENESS_DAYS = 365


class UnsupportedFilerError(Exception):
    """Raised when a filer's companyfacts carry no US-GAAP taxonomy.

    Foreign private issuers (e.g. TSM) report under IFRS (``ifrs-full``);
    the concept chains in this module are US-GAAP tags, so there is nothing
    to extract. Callers surface this as "not supported" instead of letting
    a bare ``KeyError: 'us-gaap'`` through.
    """


def _chain_candidates(
    companyfacts: dict[str, Any],
    tags: tuple[str, ...],
    unit: str,
    *,
    instant: bool = False,
    staleness_window: tuple[int, int] | None = None,
    metric_name: str = "",
) -> list[tuple[str, list[XbrlFact]]]:
    """All non-empty ``(tag, facts)`` pairs for a chain, winner first.

    The first pair is exactly what :func:`_select_tag_facts` returns (chain
    order + freshness rule); the rest follow in chain order. Callers use the
    tail to gap-fill quarter-ends the winner lacks — a filer can switch tags
    mid-history (AT&T's 2026 10-Qs file continuing-operations OpCF while the
    plain tag stops at 2025-12-31; Intel's plain cash tag skips isolated
    quarters the composite cash tag has), and the winner-take-all selection
    would otherwise blank those quarters. Gap-fill only *adds* ends the
    winner lacks; it never changes a value the winner supplied.

    The tail excludes abandoned tags (newest fact more than
    ``_GAP_FILL_MAX_STALENESS_DAYS`` behind the overall newest), so ancient
    facts can't pollute the recent window — e.g. an insurer's absolutely
    stale ``Revenues`` (640 days behind) stays out while AT&T's recently
    superseded plain OpCF tag (181 days behind) still backfills.
    """
    us_gaap_root = companyfacts.get("facts", {})
    if "us-gaap" not in us_gaap_root:
        have = ", ".join(sorted(us_gaap_root)) or "none"
        raise UnsupportedFilerError(
            f"no US-GAAP facts (reports under {have}); "
            "Tickerlens supports US-GAAP filers only"
        )
    us_gaap = us_gaap_root["us-gaap"]
    candidates: list[tuple[str, list[XbrlFact], dt.date | None]] = []
    for tag in tags:
        units = us_gaap.get(tag, {}).get("units", {})
        raw_facts = units.get(unit, [])
        facts = [
            XbrlFact.model_validate(raw)
            for raw in raw_facts
            if raw.get("form") in {"10-Q", "10-K"}
            and raw.get("end")
            and (instant or raw.get("start"))
        ]
        if facts:
            newest = _newest_in_window(facts, staleness_window)
            candidates.append((tag, facts, newest))
    if not candidates:
        raise KeyError(f"No XBRL facts found for metric {metric_name or 'composite'}")
    dated = [(t, f, n) for t, f, n in candidates if n is not None]
    winner: tuple[str, list[XbrlFact]] | None = None
    tail: list[tuple[str, list[XbrlFact]]]
    if dated:
        newest_overall = max(n for _, _, n in dated)
        for tag, facts, newest in dated:
            if (newest_overall - newest).days <= _MAX_TAG_STALENESS_DAYS:
                winner = (tag, facts)
                break
        assert winner is not None  # the overall-newest tag is 0 days behind
        tail = [
            (t, f)
            for t, f, n in candidates
            if t != winner[0]
            and n is not None
            and (newest_overall - n).days <= _GAP_FILL_MAX_STALENESS_DAYS
        ]
    else:
        winner = (candidates[0][0], candidates[0][1])
        tail = [(t, f) for t, f, _ in candidates if t != winner[0]]
    return [winner] + tail


# Banks and broker-dealers (SIC Division H, 6000-6299) report revenue as two
# components — noninterest income plus net interest income — and the generic
# ``Revenues`` fallback chain often holds only *annual* facts for them (JPM's
# quarterly ``Revenues`` facts stop in 2014; GS files none at all), which
# pinned the revenue anchor — and therefore every joined metric — a decade in
# the past. The components sum exactly to quarterly ``Revenues`` (verified on
# BAC 2026 Q1/Q2: diff 0), so finance filers use this composite. Insurers
# (6300s) have a different revenue structure and fall through to the generic
# chain when their components are absent.
_BANK_SIC_LO, _BANK_SIC_HI = 6000, 6300
_BANK_REVENUE_COMPONENTS: tuple[tuple[str, ...], ...] = (
    ("NoninterestIncome",),
    ("InterestIncomeExpenseNet", "NetInterestIncome"),
)


# Finance filers (SIC Division H, 6000-6999) report revenue differently from
# operating companies: the contract-revenue tags the generic chain prefers
# are often small sub-components (MET: $0.7B fee income) while the filer's own
# total-revenue tag ``Revenues`` is the true top line ($19B). Prefer
# ``Revenues`` when its quarterly facts are current; banks that file it only
# annually (JPM's quarterly ``Revenues`` stops in 2014) fall through to the
# component composite below.
_FINANCE_SIC_LO, _FINANCE_SIC_HI = 6000, 7000


def _is_finance_sic(sic: str | int | None) -> bool:
    """True for finance SICs (Division H: banks, insurers, real estate)."""
    if sic is None:
        return False
    try:
        return _FINANCE_SIC_LO <= int(str(sic).strip()) < _FINANCE_SIC_HI
    except (TypeError, ValueError):
        return False


def _finance_total_revenue(
    companyfacts: dict[str, Any],
    fiscal_year_end: str | None = None,
) -> list[PeriodMetric]:
    """Quarterly ``Revenues`` for finance filers, when it is actually current.

    Unlike the generic chain's *relative* staleness rule (a tag is fresh if it
    is within ``_MAX_TAG_STALENESS_DAYS`` of the freshest tag in the chain), this needs an
    *absolute* check: JPM files nothing else quarterly in the chain, so its
    2014 ``Revenues`` would look "fresh" relative to itself. Facts older than
    ``_MAX_TAG_STALENESS_DAYS`` from today count as abandoned and yield [],
    letting bank-SIC filers fall through to the component composite.
    """
    try:
        source_tag, facts = _select_tag_facts(
            companyfacts, ("Revenues",), "USD", staleness_window=(70, 100)
        )
    except KeyError:
        return []
    newest = _newest_in_window(facts, (70, 100))
    if newest is None or (dt.date.today() - newest).days > _MAX_TAG_STALENESS_DAYS:
        return []
    standalone = _dedup_by_end(facts, 70, 100, fiscal_year_end)
    q4 = _derive_q4_income(facts, source_tag, Metric.REVENUE, fiscal_year_end)
    return _merge_standalone_with_q4(Metric.REVENUE, source_tag, standalone, q4)


def _is_bank_sic(sic: str | int | None) -> bool:
    """True for finance SICs (Division H: banks, brokers) with bank revenue tags."""
    if sic is None:
        return False
    try:
        return _BANK_SIC_LO <= int(str(sic).strip()) < _BANK_SIC_HI
    except (TypeError, ValueError):
        return False


def _bank_quarterly_revenue(
    companyfacts: dict[str, Any],
    fiscal_year_end: str | None = None,
) -> list[PeriodMetric]:
    """Quarterly revenue for banks as NoninterestIncome + net interest income.

    Each component goes through the same tag selection (with the same
    quarterly-freshness staleness rule), standalone-quarter extraction, and
    Q4-from-annual derivation as a regular income metric; the component
    series are then summed by period-end date. A missing component (no facts
    at all) aborts the composite so the caller can fall back to the generic
    chain. Ends where only one component is present use that component alone —
    in practice both are filed in the same 10-Q.
    """
    component_series: list[list[PeriodMetric]] = []
    for tags in _BANK_REVENUE_COMPONENTS:
        try:
            source_tag, facts = _select_tag_facts(
                companyfacts, tags, "USD", staleness_window=(70, 100)
            )
        except KeyError:
            logger.warning(
                "bank revenue component %s missing — composite skipped", tags[0]
            )
            return []
        standalone = _dedup_by_end(facts, 70, 100, fiscal_year_end)
        q4 = _derive_q4_income(facts, source_tag, Metric.REVENUE, fiscal_year_end)
        component_series.append(
            _merge_standalone_with_q4(Metric.REVENUE, source_tag, standalone, q4)
        )
    by_end: dict[dt.date, list[PeriodMetric]] = {}
    for series in component_series:
        for item in series:
            by_end.setdefault(item.end, []).append(item)
    return sorted(
        (
            _metric_value(
                Metric.REVENUE,
                "+".join(item.source_tag for item in items),
                items[0].fy,
                items[0].fp,
                end,
                sum(item.value for item in items),
            )
            for end, items in by_end.items()
        ),
        key=lambda item: item.end,
    )


def _newest_in_window(
    facts: list[XbrlFact], window: tuple[int, int] | None
) -> dt.date | None:
    """Newest end date among facts whose duration falls in ``window``.

    A ``None`` window means facts of any duration — including instant
    (point-in-time) facts, which carry no ``start``. Balance-sheet tag
    selection passes ``None``, so instant facts must still count: without
    them the staleness check never engages for balance-sheet metrics and the
    first tag always wins even when abandoned (UNH's ``StockholdersEquity``
    ended in 2015 while ``StockholdersEquityIncludingPortionAttributableTo-
    NoncontrollingInterest`` is current; PG's
    ``CashAndCashEquivalentsAtCarryingValue`` ended in 2019 while
    ``CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents`` is
    current — both metrics rendered "—" for every quarter).
    """
    if window is None:
        ends = [f.end for f in facts]
    else:
        ends = [
            f.end
            for f in facts
            if f.start is not None
            and window[0] <= (f.end - f.start).days <= window[1]
        ]
    return max(ends) if ends else None


def balance_sheet_metric(
    companyfacts: dict[str, Any],
    metric: Metric,
    fiscal_year_end: str | None = None,
) -> dict[dt.date, float]:
    """Extract instant balance-sheet values keyed by period-end date.

    Balance-sheet facts are point-in-time, so they join to a quarter by ``end``
    alone. The same ``end`` can appear across filings (a 10-Q value later restated
    in a 10-K); keep the latest-filed one, preferring the fact whose fiscal-year
    label matches the fiscal year inferred for that end date. Quarter-ends the
    winning tag lacks are gap-filled from later chain tags (Intel's plain cash
    tag skips quarters the composite cash tag has) without changing any value
    the winner supplied.
    """
    spec = CONCEPTS[metric]
    candidates = _chain_candidates(
        companyfacts, spec.tags, spec.unit, instant=True, metric_name=metric.value
    )
    merged: dict[dt.date, float] = {}
    for tag, facts in candidates:
        grouped: dict[dt.date, list[XbrlFact]] = {}
        for fact in facts:
            grouped.setdefault(fact.end, []).append(fact)
        for end, end_candidates in grouped.items():
            if end not in merged:
                merged[end] = _choose_fact_for_end(
                    end, end_candidates, fiscal_year_end
                ).val
    return merged


def _derive_missing_balance_sheet(
    balance_sheet: dict[Metric, dict[dt.date, float]],
) -> None:
    """Fill missing balance-sheet instants via the accounting identity.

    Some filers (e.g. Eli Lilly) never report a standalone ``Liabilities``
    tag — only ``LiabilitiesAndStockholdersEquity`` alongside
    ``StockholdersEquity`` — and others (e.g. Visa) never report a standalone
    equity tag, so the balance-sheet tab and compare table showed "—".
    Assets = Liabilities + Equity recovers the exact value from the same
    filing's other two instants; only ends where both components exist are
    filled, and an explicitly filed value is never overwritten. Assets is
    never derived (it is the anchor the identity is checked against).
    """
    liabilities = balance_sheet[Metric.TOTAL_LIABILITIES]
    assets = balance_sheet[Metric.TOTAL_ASSETS]
    equity = balance_sheet[Metric.TOTAL_EQUITY]
    for end in sorted(set(assets) & set(equity)):
        liabilities.setdefault(end, assets[end] - equity[end])
    for end in sorted(set(assets) & set(liabilities)):
        equity.setdefault(end, assets[end] - liabilities[end])


# SEC's fiscalYearEnd is a fixed MMDD, but 52/53-week filers use floating
# year-ends that can land up to about a week after the nominal date.
_FLOATING_YEAR_END_GRACE_DAYS = 7


def infer_fiscal_year(end: dt.date, fiscal_year_end: str) -> int:
    """Infer the fiscal-year label from a period end date and SEC MMDD year-end.

    US filers label the fiscal year by the calendar year in which it ends, so
    the label is the year of the first nominal year-end on or after the period
    end. SEC's ``fiscalYearEnd`` is a fixed MMDD, but many filers (e.g. Apple:
    "the last Saturday of September") use a floating year-end that can land a
    few days after the nominal date, so a short grace window is applied —
    without it, Apple's 2024-09-28 year-end (nominal 0926) was mislabeled
    FY2025, duplicating the "Q4 FY2025" selector option.
    """
    month = int(fiscal_year_end[:2])
    day = int(fiscal_year_end[2:])
    anchor = end - dt.timedelta(days=_FLOATING_YEAR_END_GRACE_DAYS)
    for year in (anchor.year - 1, anchor.year, anchor.year + 1, anchor.year + 2):
        month_len = calendar.monthrange(year, month)[1]
        if dt.date(year, month, min(day, month_len)) >= anchor:
            return year
    raise AssertionError("unreachable: a year-end always falls after the anchor")


def _derive_q4_income(
    facts: list[XbrlFact],
    source_tag: str,
    metric: Metric,
    fiscal_year_end: str | None,
    ni_facts: list[XbrlFact] | None = None,
) -> list[PeriodMetric]:
    annual = _dedup_by_end(facts, 340, 380, fiscal_year_end)
    # Same 240-day floor as quarterly_cash_flow_metric's m9 window (52/53-week
    # filers like Costco file a 251-day 9M fact).
    ytd_9m = _dedup_by_end(facts, 240, 290, fiscal_year_end)
    annual_by_start = _by_start(annual)
    ytd_by_start = _by_start(ytd_9m)
    ni_lookup: dict[dt.date, tuple[XbrlFact, XbrlFact]] = {}
    if ni_facts:
        ni_annual = _by_start(_dedup_by_end(ni_facts, 340, 380, fiscal_year_end))
        ni_ytd = _by_start(_dedup_by_end(ni_facts, 240, 290, fiscal_year_end))
        ni_lookup = {
            start: (fact, ni_ytd[start])
            for start, fact in ni_annual.items()
            if start in ni_ytd
        }

    results: list[PeriodMetric] = []
    for start, annual_fact in annual_by_start.items():
        if start not in ytd_by_start:
            continue
        ytd = ytd_by_start[start]
        fy = _fact_fy(annual_fact)
        value = annual_fact.val - ytd.val
        if metric in (Metric.EPS_BASIC, Metric.EPS_DILUTED):
            # Per-share values must not be un-cumulated by subtraction: the
            # annual and 9M figures divide by different share counts, so
            # FY_EPS − 9M_EPS misstates Q4 — and can even invert the
            # basic/diluted ranking, as it did for DUOL's FY2025 Q4
            # ($0.94 diluted vs $0.88 basic, arithmetically impossible).
            # Derive Q4 from net income and implied share counts instead.
            implied = _implied_q4_eps(annual_fact, ytd, ni_lookup.get(start))
            value = implied if implied is not None else _round_like_inputs(
                annual_fact.val, ytd.val, value
            )
        results.append(
            _metric_value(
                metric,
                source_tag,
                fy,
                "Q4",
                annual_fact.end,
                value,
            )
        )
    return results


def _implied_q4_eps(
    annual_eps: XbrlFact,
    ytd_eps: XbrlFact,
    ni_pair: tuple[XbrlFact, XbrlFact] | None,
) -> float | None:
    """Derive Q4 EPS as Q4 net income over the implied Q4 share count.

    EPS = NI / weighted-average shares, so the share counts are implied from
    the filed NI and EPS pairs; Q4's average share count is the share-month
    residual (12·FY_avg − 9·9M_avg)/3. Returns None when the inputs can't
    support the derivation (missing or zero EPS/NI facts, non-positive
    implied shares) so the caller can fall back to plain subtraction.
    """
    if ni_pair is None:
        return None
    annual_ni, ytd_ni = ni_pair
    if not annual_eps.val or not ytd_eps.val:
        return None
    fy_shares = annual_ni.val / annual_eps.val
    ytd_shares = ytd_ni.val / ytd_eps.val
    if fy_shares <= 0 or ytd_shares <= 0:
        return None
    q4_shares = (12 * fy_shares - 9 * ytd_shares) / 3
    if q4_shares <= 0:
        return None
    return round((annual_ni.val - ytd_ni.val) / q4_shares, 4)


def _decimals(value: float) -> int:
    text = repr(value)
    if "e" in text or "E" in text:
        return 0
    _, _, frac = text.partition(".")
    return len(frac)


def _round_like_inputs(a: float, b: float, value: float) -> float:
    """Round a derived value to the precision of its inputs.

    Float subtraction of filing decimals (e.g. 9.05 − 8.17) leaves binary
    noise (0.8800000000000008) that leaks into CSV exports; the inputs are
    only ever as precise as the filing's own decimals.
    """
    return round(value, max(_decimals(a), _decimals(b)))


def _dedup_by_end(
    facts: list[XbrlFact],
    min_days: int,
    max_days: int,
    fiscal_year_end: str | None,
) -> list[XbrlFact]:
    grouped: dict[dt.date, list[XbrlFact]] = {}
    for fact in facts:
        if fact.start is None:
            continue
        days = (fact.end - fact.start).days
        if min_days <= days <= max_days:
            grouped.setdefault(fact.end, []).append(fact)

    return sorted(
        (_choose_fact_for_end(end, candidates, fiscal_year_end) for end, candidates in grouped.items()),
        key=lambda fact: fact.end,
    )


def _choose_fact_for_end(
    end: dt.date,
    candidates: list[XbrlFact],
    fiscal_year_end: str | None,
) -> XbrlFact:
    """Pick one fact per period end, keeping labels honest.

    The same quarter often appears in several filings: the original 10-Q plus
    comparative prior-period columns in later 10-Qs/10-Ks. Those comparative
    facts inherit the *later* filing's ``fy`` label (e.g. JNJ's Q3-2024 quarter
    re-tagged ``fy=2025`` inside the Q3-2025 10-Q), and SEC's nominal
    ``fiscalYearEnd`` is not always trustworthy either (JNJ reports "0103"
    while its own filings label the Dec-2025-ended year FY2025). Trusting
    either source mislabels rows and duplicates selector options.

    The original filing is authoritative for *what the period is called*,
    while a later amendment may restate the *number*, so: labels (``fy``,
    ``fp``) come from the earliest-filed candidate and the value from the
    latest-filed one.
    """
    _ = fiscal_year_end  # kept for signature compatibility; labels come from filings
    earliest = min(candidates, key=lambda fact: fact.filed)
    latest = max(candidates, key=lambda fact: fact.filed)
    if earliest is latest:
        return latest
    return latest.model_copy(update={"fy": earliest.fy, "fp": earliest.fp})


def _period_metric(metric: Metric, source_tag: str, fact: XbrlFact) -> PeriodMetric:
    return _metric_value(metric, source_tag, _fact_fy(fact), _fact_fp(fact), fact.end, fact.val)


def _metric_value(
    metric: Metric,
    source_tag: str,
    fy: int,
    fp: str,
    end: dt.date,
    value: float,
) -> PeriodMetric:
    return PeriodMetric(metric=metric, source_tag=source_tag, fy=fy, fp=fp, end=end, value=value)


def _by_end(items: list[PeriodMetric]) -> dict[dt.date, PeriodMetric]:
    return {item.end: item for item in items}


def _by_start(facts: list[XbrlFact]) -> dict[dt.date, XbrlFact]:
    return {fact.start: fact for fact in facts if fact.start is not None}


def _value_for_end(items: dict[dt.date, PeriodMetric], end: dt.date) -> float | None:
    item = items.get(end)
    return item.value if item else None


def _fact_fy(fact: XbrlFact) -> int:
    if fact.fy is None:
        raise ValueError(f"XBRL fact has no fiscal year label: {fact}")
    return fact.fy


def _fact_fp(fact: XbrlFact) -> str:
    if fact.fp is None:
        raise ValueError(f"XBRL fact has no fiscal period label: {fact}")
    return fact.fp
