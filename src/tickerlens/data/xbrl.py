from __future__ import annotations

import datetime as dt
import calendar
import logging
import math
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

from tickerlens.models.quarterly_financial import (
    identity_tolerance as _identity_tolerance,
)

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
    # Redeemable noncontrolling interest sits in *mezzanine* equity — between
    # liabilities and permanent equity on the balance sheet, part of neither.
    # Filers that carry it (e.g. S&P Global's $4.9B, AT&T's $2.0B) otherwise
    # render Assets != Liabilities + Equity.
    REDEEMABLE_NCI = "redeemable_nci"


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
    # SEC accession number of the filing the fact came from (e.g.
    # "0000940944-25-000071"). Lets the balance-sheet identity guard tell
    # whether the three legs of one period end share a filing basis.
    accn: str | None = None


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
    # Mezzanine equity (redeemable NCI) — between liabilities and equity,
    # part of neither. Rendered as its own balance-sheet line; subtracted
    # when the accounting identity derives a missing leg.
    redeemable_nci: float | None = None

    @property
    def period(self) -> str:
        return f"FY{self.fy} {self.fp}"


CONCEPTS: dict[Metric, ConceptSpec] = {
    # Revenue: prefer the total top-line ``Revenues`` tag when the filer
    # provides it. The ``...ExcludingAssessedTax`` variant is ASC-606-only
    # revenue and silently drops non-contract revenue such as leases —
    # Applied Digital's Q1 FY2027 10-Q filed 2026-10-07 reports $341.9M under
    # ``Revenues`` (matching its earnings release) but only $262.8M under
    # the narrower tag, which the old order picked. Staleness skipping still
    # protects filers whose ``Revenues`` tag is abandoned.
    Metric.REVENUE: ConceptSpec(
        tags=(
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
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
            # Partnership-structure filers (MLPs such as Energy Transfer)
            # report equity as PartnersCapital, not StockholdersEquity —
            # without these, total_equity rendered "—" for every quarter (and
            # the newest quarter also lost total_liabilities, since the
            # Assets = Liabilities + Equity derivation needs equity). Same
            # total-then-parent ordering as the corporate pair.
            "PartnersCapitalIncludingPortionAttributableToNoncontrollingInterest",
            "PartnersCapital",
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
    # Redeemable NCI is filed under the carrying-amount tag on every live
    # filer checked (SPGI, T, UNH, APLD, OTIS, ICE, CI, SNPS — 2026-10-12);
    # the bare tag has no facts on any of them, so the chain is one tag.
    Metric.REDEEMABLE_NCI: ConceptSpec(
        tags=("RedeemableNoncontrollingInterestEquityCarryingAmount",),
        unit="USD",
    ),
}

BALANCE_SHEET_METRICS: tuple[Metric, ...] = (
    Metric.TOTAL_ASSETS,
    Metric.TOTAL_LIABILITIES,
    Metric.TOTAL_EQUITY,
    Metric.CASH_AND_EQUIVALENTS,
    Metric.REDEEMABLE_NCI,
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
    ``Revenues`` tag; mortgage REITs (SIC 6798) report net interest income
    only.
    """

    # Revenue is the canonical anchor — hard failure if missing.
    try:
        revenue = quarterly_income_metric(
            companyfacts, Metric.REVENUE, fiscal_year_end, sic=sic
        )
    except KeyError:
        # No usable revenue facts: the filer is outside Tickerlens' coverage
        # (e.g. ASML reports in EUR and files Form 20-F — the USD-only unit
        # filter and the 10-Q/10-K form filter reject every fact). Surface a
        # plain-language reason instead of the bare KeyError so the company
        # routes can render an honest "not covered" page.
        raise UnsupportedFilerError(_revenue_unsupported_reason(companyfacts)) from None

    def _safe(fn: Callable, metric: Metric) -> list[PeriodMetric]:
        try:
            return fn(companyfacts, metric, fiscal_year_end)
        except KeyError:
            logger.warning("No XBRL facts for %s — storing None", metric.value)
            return []

    def _safe_bs_facts(metric: Metric) -> dict[dt.date, XbrlFact]:
        try:
            return _balance_sheet_facts(companyfacts, metric, fiscal_year_end)
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
    bs_facts = {metric: _safe_bs_facts(metric) for metric in BALANCE_SHEET_METRICS}
    # Latest-filed-wins is per metric, so one quarter's legs can come from
    # different filings (Darden's segment note misdates its consolidated
    # total-assets context); repair the basis before the identity is used to
    # derive missing legs below.
    _reconcile_balance_sheet_identity(bs_facts, companyfacts, fiscal_year_end)
    balance_sheet = {
        metric: {end: fact.val for end, fact in facts.items()}
        for metric, facts in bs_facts.items()
    }
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
                redeemable_nci=balance_sheet[Metric.REDEEMABLE_NCI].get(item.end),
            )
        )
    rows = _dedupe_period_labels(rows)
    return _repair_sequence_breaks(rows)


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


def _successor_label(fy: int, fp: str) -> tuple[int, str] | None:
    """The (fy, fp) label the quarter after ``(fy, fp)`` should carry.

    Returns None for non-quarterly period labels (e.g. "FY"), where no
    sequence expectation exists.
    """
    order = {"Q1": "Q2", "Q2": "Q3", "Q3": "Q4", "Q4": "Q1"}
    nxt = order.get(fp)
    if nxt is None:
        return None
    return (fy + 1, nxt) if fp == "Q4" else (fy, nxt)


def _dedupe_period_labels(rows: list[QuarterlyFinancials]) -> list[QuarterlyFinancials]:
    """Ensure (fy, fp) labels are unique across rows.

    Comparative prior-period columns in a later filing inherit that filing's
    ``fy`` — when the original filing is absent from the CIK's dataset (e.g.
    XOM's new-CIK history holds only the 2026 10-Q), the 2025 comparative
    column is tagged fy=2026 and collides with the real Q2 FY2026, duplicating
    selector options. A fiscal year has exactly one of each quarter, so when
    two period ends share a label one of them is mislabeled.

    Which one is mislabeled is decided by sequence consistency, not recency:
    a filer's *newest* filing can itself mislabel the current quarter's fy
    (Oracle's Sep-2026 10-Q tags Q1 FY2027 as fy=2026; Salesforce's Jan 10-K
    tags Q4 FY2026 as fy=2025), colliding with the correctly labeled year-ago
    quarter. The old "later end keeps its label" rule then walked the *correct*
    row back a year (ORCL's Q1 FY2026 rendered "FY2025 Q1"). Now, when two
    ends collide, the earlier end keeps the label if its claim matches the
    sequence expectation from its predecessor, and the later end is relabeled
    to its own expectation. When there is no sequence context to arbitrate
    (the earlier end is the first row, or a quarter is missing), the legacy
    behavior applies: the later end keeps its label and the earlier walks
    back. Rows without a collision are never touched.
    """
    holder: dict[tuple[int, str], QuarterlyFinancials] = {}
    # id(row) -> the row's claim matched the sequence expectation derived
    # from its predecessor's final label (a first row or a row after a gap
    # has no expectation, so it is never "grounded").
    grounded: dict[int, bool] = {}
    prev: tuple[int, str] | None = None
    for row in sorted(rows, key=lambda item: item.end):
        expected = _successor_label(*prev) if prev is not None else None
        claim = (row.fy, row.fp)
        if claim in holder:
            earlier = holder[claim]
            if (
                expected is not None
                and expected != claim
                and expected not in holder
                and grounded.get(id(earlier), False)
            ):
                # The earlier end's label is sequence-consistent, so the
                # later end's original filing mislabeled the year — relabel
                # the later end to its expectation instead of corrupting the
                # correct row.
                row.fy, row.fp = expected
                holder[expected] = row
            else:
                # Legacy: the earlier end is the mislabeled comparative
                # column; it vacates the collided label (the later end keeps
                # it) and walks its year back until the label is free.
                del holder[claim]
                earlier.fy -= 1
                while (earlier.fy, earlier.fp) in holder:
                    earlier.fy -= 1
                holder[(earlier.fy, earlier.fp)] = earlier
                holder[claim] = row
        else:
            holder[claim] = row
        grounded[id(row)] = expected is not None and (row.fy, row.fp) == expected
        prev = (row.fy, row.fp)
    return rows


def _predecessor_label(fy: int, fp: str) -> tuple[int, str] | None:
    """The (fy, fp) label the quarter before ``(fy, fp)`` should carry."""
    order = {"Q1": "Q4", "Q2": "Q1", "Q3": "Q2", "Q4": "Q3"}
    prev = order.get(fp)
    if prev is None:
        return None
    return (fy - 1, prev) if fp == "Q1" else (fy, prev)


def _walk_label(label: tuple[int, str], steps: int) -> tuple[int, str] | None:
    """Apply ``steps`` signed quarter-steps to a (fy, fp) label."""
    fy, fp = label
    for _ in range(abs(steps)):
        nxt = _successor_label(fy, fp) if steps > 0 else _predecessor_label(fy, fp)
        if nxt is None:
            return None
        fy, fp = nxt
    return fy, fp


def _quarter_steps(earlier: dt.date, later: dt.date) -> int:
    """Whole quarter-steps between two period ends, for label walking.

    The step count comes from the calendar distance so a genuine coverage gap
    does not shift the walk: a missing year walks back to the row's own claim
    and is never "repaired".
    """
    return max(1, round((later - earlier).days / 91.3125))


def _repair_sequence_breaks(rows: list[QuarterlyFinancials]) -> list[QuarterlyFinancials]:
    """Relabel filer-mislabeled fiscal years that break the quarter sequence.

    ``_dedupe_period_labels`` only arbitrates *collisions* (two ends sharing
    one label). Some filers tag a consistent-but-wrong ``fy`` on their own
    filings with no collision — CrowdStrike's FY2025 10-K and Q1-FY2026 10-Q
    label their periods by the calendar year the fiscal year *began*
    (fy=2024/2025) while later filings' comparative columns use the standard
    ending-year convention (fy=2026/2027). The stored series then reads
    FY2025Q3 → FY2024Q4 → FY2025Q1 → FY2026Q2: ``fy`` *decreases* across
    consecutive quarters, which a fiscal calendar can never do.

    Repair: the longest run of rows whose labels are mutual successors is the
    backbone (ties broken toward the run holding the latest row, whose filing
    carries the filer's most current convention). Only when the backbone is a
    strict majority of rows and at least 3 long, every other row's expected
    label is walked from the nearest backbone row by calendar quarter-steps —
    so a missing quarter or year resolves to the row's own claim. A row is
    relabeled only when it is a pure year shift (the walked expectation's fp
    matches its claimed fp) and the target label is unheld. A missing quarter
    changes fp, so it can never be "repaired" into a wrong label; two rows
    whose walked expectations coincide keep the first and the second is left
    alone via the unheld-target guard.
    """
    ordered = sorted(rows, key=lambda r: r.end)
    n = len(ordered)
    if n < 4:
        return rows
    runs: list[tuple[int, int]] = []  # (start index, length)
    cur_start = 0
    for i in range(1, n):
        if _successor_label(ordered[i - 1].fy, ordered[i - 1].fp) != (
            ordered[i].fy,
            ordered[i].fp,
        ):
            runs.append((cur_start, i - cur_start))
            cur_start = i
    runs.append((cur_start, n - cur_start))

    def _run_key(run: tuple[int, int]) -> tuple[int, bool]:
        start, length = run
        return (length, start + length == n)

    bstart, blen = max(runs, key=_run_key)
    if blen < 3 or blen * 2 <= n:
        return rows

    bend = bstart + blen  # exclusive
    held = {(r.fy, r.fp) for r in ordered[bstart:bend]}
    for i, row in enumerate(ordered):
        if bstart <= i < bend:
            continue
        if i < bstart:
            ref = ordered[bstart]
            steps = -_quarter_steps(row.end, ref.end)
        else:
            ref = ordered[bend - 1]
            steps = _quarter_steps(ref.end, row.end)
        expected = _walk_label((ref.fy, ref.fp), steps)
        claim = (row.fy, row.fp)
        if (
            expected is not None
            and expected != claim
            and expected[1] == claim[1]
            and expected not in held
        ):
            row.fy, row.fp = expected
        held.add((row.fy, row.fp))
    return rows


# Stock splits restate per-share facts: the same (start, end) reported at two
# filings whose values differ by an integer split ratio. Restated values are
# exact divisions (7.19 -> 0.72), so a 3% tolerance is generous; anything
# coarser risks mistaking an accounting restatement for a split.
# 8: GE's 1-for-8 reverse split (2021-07-30); 25: BKNG's 25-for-1 split
# (2026-04) — both multi-corroborated in live companyfacts (batch 51).
_SPLIT_RATIOS = (2, 3, 4, 5, 8, 10, 20, 25, 100)
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
      since) → rescale only if the rescaled value is clearly closer, in
      ratio terms, to some post-split reference than the original is to
      any (see `_is_pre_split_basis`), so genuinely post-split facts
      (NFLX's Q1-2026, filed 2026-04-17, before the restating 10-Q) are
      left alone.
    """
    events = _detect_split_events(facts)
    if not events:
        return
    min_event_date = min(event.date for event in events)
    # Post-split reference values: restated comparatives (latest filed wins)
    # and any fact filed on/after the first restating filing. Keyed by
    # (start, end) — not by end alone — because one end date can carry both
    # a quarterly and a YTD fact (HON's 2025-06-30: Q2 4.90 and 6M 9.34,
    # both filed 2026-07-23); collapsing by end let the YTD value win the
    # tie and poison the quarterly neighbor check, silently skipping the
    # rescale of genuinely pre-split quarters (HON FY2025Q1 stayed 2.22
    # instead of 4.44 — batch 51).
    latest_by_period: dict[tuple[dt.date | None, dt.date], XbrlFact] = {}
    for fact in facts:
        key = (fact.start, fact.end)
        prev = latest_by_period.get(key)
        if prev is None or fact.filed > prev.filed:
            latest_by_period[key] = fact
    certain: dict[tuple[dt.date | None, dt.date], float] = {}
    for (start, end), fact in latest_by_period.items():
        if end in {e for event in events for e in event.period_ends} or fact.filed >= min_event_date:
            certain[(start, end)] = fact.val

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
        if _is_pre_split_basis(fact, scale, certain):
            fact.val *= scale


# The basis check must only compare like duration classes: a quarterly fact
# against quarterly references, a YTD fact against YTD references. One end
# date can carry both (HON's 2025-06-30: Q2 4.90 and 6M 9.34, both filed
# 2026-07-23), and cross-comparing let the YTD value poison the quarterly
# check. 120 days separates the classes cleanly (quarterly 70–100d,
# 6M ~182d, 9M ~273d, FY ~365d).
_QUARTERLY_MAX_DAYS = 120
# The rescaled value must be at least this much closer (in log-ratio terms)
# to guard against borderline flip-flops.
_BASIS_CHECK_MARGIN = math.log(1.2)


def _is_pre_split_basis(
    fact: XbrlFact,
    scale: float,
    certain: dict[tuple[dt.date | None, dt.date], float],
) -> bool:
    """Decide whether a pre-event filing's fact is on the pre-split basis.

    Compares the original and rescaled values against the post-split
    references (same duration class) in *ratio* terms: a pre-split fact's
    rescaled value lands near the post-split neighborhood, while an
    already-post-split fact's rescaled value flies far away from it. Ratio
    distance (not absolute) is what makes this work across the 25x range of
    split factors — and across loss quarters and outlier-polluted
    neighborhoods, where absolute interpolation breaks down (HON's
    FY2025Q4 −0.18 kept its pre-split basis because the interpolated
    +11.42 neighborhood had the opposite sign; FY2026Q1 1.29 because the
    neighborhood was inflated by a gain quarter — batch 51).
    """
    if fact.start is None:
        return False
    quarterly = (fact.end - fact.start).days <= _QUARTERLY_MAX_DAYS
    refs = [
        abs(val)
        for (start, end), val in certain.items()
        if start is not None
        and ((end - start).days <= _QUARTERLY_MAX_DAYS) == quarterly
        and val != 0
    ]
    if not refs or fact.val == 0:
        # No reference to judge by: stay conservative. (A zero fact rescales
        # to zero anyway.)
        return fact.val == 0
    mag = abs(fact.val)
    orig = min(abs(math.log(mag / ref)) for ref in refs)
    new = min(abs(math.log(mag * scale / ref)) for ref in refs)
    return new < orig - _BASIS_CHECK_MARGIN


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
    # file Revenues only annually fall through to the component composite;
    # mortgage REITs (SIC 6798, e.g. NLY) whose top line is net interest
    # income fall through to the mREIT composite. Business development
    # companies (no SIC, e.g. ARCC) whose top line is gross investment income
    # are tag-detected on the generic-chain KeyError below. Falls back to the
    # generic chain when none is available (e.g. insurers without quarterly
    # Revenues).
    if metric is Metric.REVENUE and _is_finance_sic(sic):
        total = _finance_total_revenue(companyfacts, fiscal_year_end)
        if total:
            return total
        if _is_bank_sic(sic):
            composite = _bank_quarterly_revenue(companyfacts, fiscal_year_end)
            if composite:
                return composite
        if _is_mreit_sic(sic):
            composite = _mreit_quarterly_revenue(companyfacts, fiscal_year_end)
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
    try:
        candidates = _chain_candidates(
            companyfacts,
            spec.tags,
            spec.unit,
            staleness_window=(70, 100),
            metric_name=metric.value,
        )
    except KeyError:
        # No revenue facts on the generic chain: tag-detected BDC coverage
        # (ARCC — no SIC, no ``Revenues``, top line is gross investment
        # income). Runs only when nothing else applies, so the unsupported-
        # filer path is preserved for genuinely uncovered filers.
        if metric is Metric.REVENUE:
            bdc = _bdc_quarterly_revenue(companyfacts, fiscal_year_end)
            if bdc:
                return bdc
        raise
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

    A 70–100-day fact is quarterly by duration, so any non-"Q4" fp label on
    one that coincides with a derivable Q4 is a filer mislabeling of its 10-K
    Q4 stub (ABBV's 10-K tags the 91-day Q4 Revenues fact fp="FY"; BNY's
    2024 10-K tags its 92-day Q4 NoninterestIncome/InterestIncomeExpenseNet
    stubs fp="Q1" — both verified against raw SEC JSON). The filer's own
    quarterly fact is authoritative over the derived Q4 row, so relabel it
    and let it supersede the duplicate — otherwise the phantom row steals a
    slot in the recent-periods slice and collides on (cik, period_end) at
    upsert (and in the bank composite it would be *summed* with the derived
    Q4, roughly doubling the quarter, as BNY's Q4 2024 revenue was).
    """
    derived_q4_ends = {item.end for item in q4}
    metrics: list[PeriodMetric] = []
    superseded_q4: set[dt.date] = set()
    for fact in standalone:
        pm = _period_metric(metric, source_tag, fact)
        if pm.fp != "Q4" and pm.end in derived_q4_ends:
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


def _revenue_unsupported_reason(companyfacts: dict[str, Any]) -> str:
    """Plain-language reason why no revenue facts were usable.

    Inspects the revenue concept chain for facts rejected by the USD-only
    unit filter or the 10-Q/10-K form filter, so the message names the
    actual blocker (currency, form, or both).
    """
    tags = CONCEPTS[Metric.REVENUE].tags
    us_gaap = companyfacts.get("facts", {}).get("us-gaap", {})
    currencies: set[str] = set()
    forms: set[str] = set()
    for tag in tags:
        for unit, facts in us_gaap.get(tag, {}).get("units", {}).items():
            if facts:
                currencies.add(unit)
                forms.update(f.get("form") for f in facts if f.get("form"))
    bits = []
    non_usd = sorted(c for c in currencies if c != "USD")
    if non_usd:
        bits.append(f"reports in {', '.join(non_usd)}")
    foreign_forms = sorted(f for f in forms if f not in {"10-Q", "10-K"})
    if foreign_forms:
        bits.append(f"files {', '.join(foreign_forms)} instead of 10-Q/10-K")
    detail = "; ".join(bits) if bits else "has no usable revenue facts"
    return (
        f"This company {detail} — Tickerlens covers US-GAAP filers reporting "
        "in USD with quarterly 10-Q/10-K filings."
    )


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


# Business development companies (e.g. ARCC) report no SIC at all and file no
# ``Revenues`` — their top line is gross investment income. This composite is
# tag-detected rather than SIC-dispatched: it only fires when the generic
# chain finds no revenue facts, so operating companies are unaffected; when
# the filer has no gross-investment-income facts either it returns [] and
# the KeyError propagates to the honest unsupported-filer path.
_BDC_REVENUE_TAGS: tuple[str, ...] = (
    "GrossInvestmentIncomeOperating",
)


# Mortgage REITs (SIC 6798) file no ``Revenues`` and no ``NoninterestIncome`` —
# their top line is net interest income (NLY files 85 quarterly
# ``InterestIncomeExpenseNet`` facts and no quarterly ``Revenues``). Equity
# REITs share SIC 6798 but file current quarterly ``Revenues`` and take the
# finance preference above, so this composite only ever fires when ``Revenues``
# is absent; when the filer has no net-interest-income facts either it
# returns [] and the generic chain applies unchanged.
_MREIT_SIC = 6798
_MREIT_REVENUE_TAGS: tuple[str, ...] = (
    "InterestIncomeExpenseNet",
    "NetInterestIncome",
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


def _bdc_quarterly_revenue(
    companyfacts: dict[str, Any],
    fiscal_year_end: str | None = None,
) -> list[PeriodMetric]:
    """Quarterly revenue for business development companies as gross
    investment income.

    BDCs (e.g. ARCC) report no SIC and file no ``Revenues`` — their top line
    is ``GrossInvestmentIncomeOperating`` (Q2'26: $768M standalone, clean
    framed quarterly facts). Same tag selection, standalone-quarter
    extraction, and Q4-from-annual derivation as a regular income metric.
    Returns [] when the filer has no gross-investment-income facts so the
    caller keeps the unsupported-filer path.
    """
    try:
        source_tag, facts = _select_tag_facts(
            companyfacts, _BDC_REVENUE_TAGS, "USD", staleness_window=(70, 100)
        )
    except KeyError:
        logger.warning(
            "BDC revenue tag %s missing — composite skipped", _BDC_REVENUE_TAGS[0]
        )
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


def _is_mreit_sic(sic: str | int | None) -> bool:
    """True for SIC 6798 (real estate investment trusts, incl. mortgage REITs)."""
    if sic is None:
        return False
    try:
        return int(str(sic).strip()) == _MREIT_SIC
    except (TypeError, ValueError):
        return False


def _mreit_quarterly_revenue(
    companyfacts: dict[str, Any],
    fiscal_year_end: str | None = None,
) -> list[PeriodMetric]:
    """Quarterly revenue for mortgage REITs as net interest income.

    A single-component series (no summation needed, unlike the bank
    composite): the same tag selection, standalone-quarter extraction, and
    Q4-from-annual derivation as a regular income metric. Returns [] when the
    filer has no net-interest-income facts so the caller falls back to the
    generic chain.
    """
    try:
        source_tag, facts = _select_tag_facts(
            companyfacts, _MREIT_REVENUE_TAGS, "USD", staleness_window=(70, 100)
        )
    except KeyError:
        logger.warning(
            "mREIT revenue component %s missing — composite skipped",
            _MREIT_REVENUE_TAGS[0],
        )
        return []
    standalone = _dedup_by_end(facts, 70, 100, fiscal_year_end)
    q4 = _derive_q4_income(facts, source_tag, Metric.REVENUE, fiscal_year_end)
    return _merge_standalone_with_q4(Metric.REVENUE, source_tag, standalone, q4)


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


def _balance_sheet_facts(
    companyfacts: dict[str, Any],
    metric: Metric,
    fiscal_year_end: str | None = None,
) -> dict[dt.date, XbrlFact]:
    """Chosen balance-sheet fact per period-end date, provenance-preserving.

    Same selection as :func:`balance_sheet_metric`, but keeps the winning
    :class:`XbrlFact` (including its filing ``accn``) instead of just the
    value, so :func:`_reconcile_balance_sheet_identity` can detect legs of
    one quarter drawn from different filings and repair the basis.
    """
    spec = CONCEPTS[metric]
    candidates = _chain_candidates(
        companyfacts, spec.tags, spec.unit, instant=True, metric_name=metric.value
    )
    chosen: dict[dt.date, XbrlFact] = {}
    for tag, facts in candidates:
        grouped: dict[dt.date, list[XbrlFact]] = {}
        for fact in facts:
            grouped.setdefault(fact.end, []).append(fact)
        for end, end_candidates in grouped.items():
            if end not in chosen:
                chosen[end] = _choose_fact_for_end(
                    end, end_candidates, fiscal_year_end
                )
    return chosen


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

    Thin wrapper over :func:`_balance_sheet_facts`; the identity guard in
    ``extract_recent_quarterly_financials`` works on the facts directly.
    """
    return {
        end: fact.val
        for end, fact in _balance_sheet_facts(
            companyfacts, metric, fiscal_year_end
        ).items()
    }


# A single filing's balance sheet always satisfies the accounting identity
# (double-entry bookkeeping), but the per-metric latest-filed-wins assembly
# can mix legs from different filings. Darden's Q2 FY2026 10-Q tags its
# segment-note "Consolidated" total-assets column (Nov 23, 2025: $12,940.2M)
# with a stale 2024-11-24 context, so the 2024-11-24 Assets leg came from the
# FY2026-Q2 filing while Liabilities/Equity came from the original FY2025-Q2
# filing - a $421M phantom gap no mezzanine line could explain. When the
# identity is violated beyond tolerance and the legs span more than one
# filing, fall back to the earliest-filed single filing whose own legs close
# the identity (tolerance: models.quarterly_financial.identity_tolerance,
# shared with the mezzanine render gate).


def _reconcile_balance_sheet_identity(
    chosen: dict[Metric, dict[dt.date, XbrlFact]],
    companyfacts: dict[str, Any],
    fiscal_year_end: str | None,
) -> None:
    """Repair mixed-filing balance-sheet bases via the accounting identity.

    For each period end where Assets, Liabilities and Equity are all present,
    checks ``|A - L - mezz - E|`` against the tolerance. On violation with
    legs drawn from two or more filings, replaces the quarter's legs with the
    earliest-filed single filing whose own facts for that end close the
    identity. A no-op when the identity already holds, when every leg shares
    one filing (the filer's own books genuinely don't close - nothing to
    reconcile), or when no single filing's legs close (keeps latest-wins).
    Never invents values: every candidate comes from a filed fact.
    """
    need = (Metric.TOTAL_ASSETS, Metric.TOTAL_LIABILITIES, Metric.TOTAL_EQUITY)
    if not all(m in chosen for m in need):
        return
    mezz_by_end = chosen.get(Metric.REDEEMABLE_NCI, {})
    ends = (
        set(chosen[Metric.TOTAL_ASSETS])
        & set(chosen[Metric.TOTAL_LIABILITIES])
        & set(chosen[Metric.TOTAL_EQUITY])
    )
    for end in sorted(ends):
        a = chosen[Metric.TOTAL_ASSETS][end].val
        l = chosen[Metric.TOTAL_LIABILITIES][end].val  # noqa: E741
        e = chosen[Metric.TOTAL_EQUITY][end].val
        mezz_fact = mezz_by_end.get(end)
        mezz = mezz_fact.val if mezz_fact is not None else 0.0
        if abs(a - l - mezz - e) <= _identity_tolerance(a):
            continue
        accns = {
            chosen[m][end].accn for m in need if chosen[m][end].accn is not None
        }
        if mezz_fact is not None and mezz_fact.accn is not None:
            accns.add(mezz_fact.accn)
        if len(accns) < 2:
            continue
        # All candidate facts for this end, grouped by filing.
        per_accn: dict[str, dict[Metric, XbrlFact]] = {}
        metrics = need + (
            (Metric.REDEEMABLE_NCI,) if Metric.REDEEMABLE_NCI in chosen else ()
        )
        for m in metrics:
            spec = CONCEPTS[m]
            try:
                tag_facts = _chain_candidates(
                    companyfacts, spec.tags, spec.unit,
                    instant=True, metric_name=m.value,
                )
            except KeyError:
                continue
            for _tag, facts in tag_facts:
                for fact in facts:
                    if fact.end != end or fact.accn is None:
                        continue
                    slot = per_accn.setdefault(fact.accn, {})
                    if m not in slot or fact.filed > slot[m].filed:
                        slot[m] = fact
        for accn in sorted(
            per_accn, key=lambda a_: min(f.filed for f in per_accn[a_].values())
        ):
            legs = per_accn[accn]
            if not all(m in legs for m in need):
                continue
            mz = (
                legs[Metric.REDEEMABLE_NCI].val
                if Metric.REDEEMABLE_NCI in legs
                else 0.0
            )
            a2 = legs[Metric.TOTAL_ASSETS].val
            if (
                abs(
                    a2
                    - legs[Metric.TOTAL_LIABILITIES].val
                    - mz
                    - legs[Metric.TOTAL_EQUITY].val
                )
                <= _identity_tolerance(a2)
            ):
                for m in need:
                    chosen[m][end] = legs[m]
                if Metric.REDEEMABLE_NCI in chosen:
                    if Metric.REDEEMABLE_NCI in legs:
                        chosen[Metric.REDEEMABLE_NCI][end] = legs[
                            Metric.REDEEMABLE_NCI
                        ]
                    else:
                        chosen[Metric.REDEEMABLE_NCI].pop(end, None)
                logger.info(
                    "Balance-sheet basis reconciled for %s: mixed filings %s "
                    "violated A=L+mezz+E by %.1fM; using %s",
                    end, sorted(accns), (a - l - mezz - e) / 1e6, accn,
                )
                break


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

    The identity is really Assets = Liabilities + Mezzanine + Equity:
    redeemable noncontrolling interest sits between liabilities and equity,
    part of neither. When the mezzanine instant is known for an end it is
    subtracted from the derived leg — otherwise a filer carrying mezzanine
    (e.g. S&P Global's $4.9B) would get a derived leg overstated by exactly
    the mezzanine amount. Unknown mezzanine keeps the old two-leg formula.
    """
    liabilities = balance_sheet[Metric.TOTAL_LIABILITIES]
    assets = balance_sheet[Metric.TOTAL_ASSETS]
    equity = balance_sheet[Metric.TOTAL_EQUITY]
    mezz = balance_sheet.get(Metric.REDEEMABLE_NCI, {})
    for end in sorted(set(assets) & set(equity)):
        liabilities.setdefault(end, assets[end] - equity[end] - mezz.get(end, 0.0))
    for end in sorted(set(assets) & set(liabilities)):
        equity.setdefault(end, assets[end] - liabilities[end] - mezz.get(end, 0.0))


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
