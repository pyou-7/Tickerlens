from __future__ import annotations

import datetime as dt
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
    Metric.NET_INCOME: ConceptSpec(tags=("NetIncomeLoss",), unit="USD"),
    Metric.EPS_BASIC: ConceptSpec(tags=("EarningsPerShareBasic",), unit="USD/shares"),
    Metric.EPS_DILUTED: ConceptSpec(tags=("EarningsPerShareDiluted",), unit="USD/shares"),
    Metric.OPERATING_CASH_FLOW: ConceptSpec(
        tags=("NetCashProvidedByUsedInOperatingActivities",),
        unit="USD",
    ),
    Metric.CAPEX: ConceptSpec(
        tags=("PaymentsToAcquirePropertyPlantAndEquipment",),
        unit="USD",
    ),
    Metric.TOTAL_ASSETS: ConceptSpec(tags=("Assets",), unit="USD"),
    Metric.TOTAL_LIABILITIES: ConceptSpec(tags=("Liabilities",), unit="USD"),
    Metric.TOTAL_EQUITY: ConceptSpec(
        tags=(
            "StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
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
) -> list[QuarterlyFinancials]:
    """Extract recent Revenue, Net Income, EPS, and FCF from SEC companyfacts."""

    # Revenue is the canonical anchor — hard failure if missing.
    revenue = quarterly_income_metric(companyfacts, Metric.REVENUE, fiscal_year_end)

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
    opcf        = _safe(quarterly_cash_flow_metric, Metric.OPERATING_CASH_FLOW)
    capex       = _safe(quarterly_cash_flow_metric, Metric.CAPEX)
    balance_sheet = {metric: _safe_bs(metric) for metric in BALANCE_SHEET_METRICS}

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
        free_cash_flow = (
            operating_cash_flow.value - capital_expenditure.value
            if operating_cash_flow and capital_expenditure
            else None
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
    return rows


def quarterly_income_metric(
    companyfacts: dict[str, Any],
    metric: Metric,
    fiscal_year_end: str | None = None,
) -> list[PeriodMetric]:
    source_tag, facts = concept_facts(companyfacts, metric)
    standalone = _dedup_by_end(facts, 70, 100, fiscal_year_end)
    q4 = _derive_q4_income(facts, source_tag, metric, fiscal_year_end)
    return sorted(
        [_period_metric(metric, source_tag, fact) for fact in standalone] + q4,
        key=lambda item: item.end,
    )


def quarterly_cash_flow_metric(
    companyfacts: dict[str, Any],
    metric: Metric,
    fiscal_year_end: str | None = None,
) -> list[PeriodMetric]:
    source_tag, facts = concept_facts(companyfacts, metric)
    q1s = _dedup_by_end(facts, 75, 105, fiscal_year_end)
    h1s = _dedup_by_end(facts, 165, 200, fiscal_year_end)
    m9s = _dedup_by_end(facts, 255, 290, fiscal_year_end)
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


def concept_facts(
    companyfacts: dict[str, Any],
    metric: Metric,
    *,
    instant: bool = False,
) -> tuple[str, list[XbrlFact]]:
    """Return (source_tag, facts) for the first tag in the metric's fallback chain.

    Duration facts (income, cash flow) carry both ``start`` and ``end``; instant
    facts (balance sheet) carry only ``end``. Pass ``instant=True`` to keep the
    latter, which would otherwise be filtered out by the ``start`` requirement.
    """
    spec = CONCEPTS[metric]
    us_gaap = companyfacts["facts"]["us-gaap"]
    for tag in spec.tags:
        units = us_gaap.get(tag, {}).get("units", {})
        raw_facts = units.get(spec.unit, [])
        facts = [
            XbrlFact.model_validate(raw)
            for raw in raw_facts
            if raw.get("form") in {"10-Q", "10-K"}
            and raw.get("end")
            and (instant or raw.get("start"))
        ]
        if facts:
            return tag, facts
    raise KeyError(f"No XBRL facts found for metric {metric.value}")


def balance_sheet_metric(
    companyfacts: dict[str, Any],
    metric: Metric,
    fiscal_year_end: str | None = None,
) -> dict[dt.date, float]:
    """Extract instant balance-sheet values keyed by period-end date.

    Balance-sheet facts are point-in-time, so they join to a quarter by ``end``
    alone. The same ``end`` can appear across filings (a 10-Q value later restated
    in a 10-K); keep the latest-filed one, preferring the fact whose fiscal-year
    label matches the fiscal year inferred for that end date.
    """
    source_tag, facts = concept_facts(companyfacts, metric, instant=True)
    grouped: dict[dt.date, list[XbrlFact]] = {}
    for fact in facts:
        grouped.setdefault(fact.end, []).append(fact)
    return {
        end: _choose_fact_for_end(end, candidates, fiscal_year_end).val
        for end, candidates in grouped.items()
    }


def infer_fiscal_year(end: dt.date, fiscal_year_end: str) -> int:
    """Infer the fiscal-year label from a period end date and SEC MMDD year-end."""

    month = int(fiscal_year_end[:2])
    day = int(fiscal_year_end[2:])
    if month <= 5:
        return end.year
    return end.year if (end.month, end.day) <= (month, day) else end.year + 1


def _derive_q4_income(
    facts: list[XbrlFact],
    source_tag: str,
    metric: Metric,
    fiscal_year_end: str | None,
) -> list[PeriodMetric]:
    annual = _dedup_by_end(facts, 340, 380, fiscal_year_end)
    ytd_9m = _dedup_by_end(facts, 250, 290, fiscal_year_end)
    annual_by_start = _by_start(annual)
    ytd_by_start = _by_start(ytd_9m)

    results: list[PeriodMetric] = []
    for start, annual_fact in annual_by_start.items():
        if start not in ytd_by_start:
            continue
        ytd = ytd_by_start[start]
        fy = _fact_fy(annual_fact)
        results.append(
            _metric_value(
                metric,
                source_tag,
                fy,
                "Q4",
                annual_fact.end,
                annual_fact.val - ytd.val,
            )
        )
    return results


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
    if fiscal_year_end:
        expected_fy = infer_fiscal_year(end, fiscal_year_end)
        matching = [fact for fact in candidates if fact.fy == expected_fy]
        if matching:
            candidates = matching
    return max(candidates, key=lambda fact: fact.filed)


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
