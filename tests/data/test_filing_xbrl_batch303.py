"""Batch 303 regression tests: extension-concept CapEx recovery.

LYFT and Dominion tag their cash-flow CapEx line under filer-extension
concepts (``lyft:PaymentsToAcquirePropertyAndEquipmentAndScooterFleet``,
``d:PaymentsToAcquirePropertyPlantAndEquipmentIncludingNuclearFuel``),
which companyfacts (us-gaap only) never carries — every stored quarter's
FCF rendered blank. ``parse_extension_capex_facts`` maps a narrow
signature (tier 1: cash-flow PaymentsToAcquire… property/productive
names; tier 2: bare CapitalExpenditures, only when tier 1 is absent —
Dominion files both and tier 2 is accrual-basis) onto the canonical
CapEx tag, ``_capex_missing_for_recent_ends`` gates the recovery to
filers whose CapEx is actually missing, and
``_augment_with_extension_capex`` merges gap-only so consolidated
us-gaap facts always win. Fixtures model the real shapes probed in
``scripts/batch303_probe*.py`` (LYFT/D/ED/COP/NEE).
"""
import sys

sys.path.insert(0, "src")

from tickerlens.data.filing_xbrl import (
    _extension_capex_tier,
    merge_filing_facts_gap_only,
    parse_extension_capex_facts,
)
from tickerlens.data.xbrl import (
    Metric,
    extract_recent_quarterly_financials,
    quarterly_cash_flow_metric,
)
from tickerlens.services.financials import (
    _augment_with_extension_capex,
    _capex_missing_for_recent_ends,
)


def ctx(cid, start, end, members=()):
    member_xml = "".join(
        f'<xbrldi:explicitMember dimension="{axis}">{member}</xbrldi:explicitMember>'
        for axis, member in members
    )
    segment = f"<xbrli:segment>{member_xml}</xbrli:segment>" if members else ""
    return (
        f'<xbrli:context id="{cid}"><xbrli:entity>'
        f'<xbrli:identifier scheme="http://www.sec.gov/CIK">0000000001</xbrli:identifier>'
        f"{segment}</xbrli:entity>"
        f"<xbrli:period><xbrli:startDate>{start}</xbrli:startDate>"
        f"<xbrli:endDate>{end}</xbrli:endDate></xbrli:period></xbrli:context>"
    )


Q1 = ("2026-01-01", "2026-03-31")
Q2 = ("2026-04-01", "2026-06-30")
Q3 = ("2026-07-01", "2026-09-30")
M9 = ("2026-01-01", "2026-09-30")
M9P = ("2025-01-01", "2025-09-30")

HEADER = (
    "<ix:header><ix:resources>"
    + ctx("q1", *Q1)
    + ctx("q2", *Q2)
    + ctx("q3", *Q3)
    + ctx("m6", "2026-01-01", "2026-06-30")
    + ctx("m9", *M9)
    + ctx("m9p", *M9P)
    # ED shape: dimensional (segment) contexts — must be skipped.
    + ctx("m9seg", *M9, [("srt:ProductOrServiceAxis", "us-gaap:ElectricityMember")])
    + '<xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>'
    + "</ix:resources></ix:header>"
)


def filing(fp, body, fy="2026"):
    return (
        HEADER
        + f'<ix:nonNumeric name="dei:DocumentFiscalYearFocus" contextRef="q3">{fy}</ix:nonNumeric>'
        + f'<ix:nonNumeric name="dei:DocumentFiscalPeriodFocus" contextRef="q3">{fp}</ix:nonNumeric>'
        + body
    )


def xfact(qname, ctx_id, text, **attrs):
    extra = "".join(f' {k}="{v}"' for k, v in attrs.items())
    return (
        f'<ix:nonFraction name="{qname}" contextRef="{ctx_id}" '
        f'unitRef="usd"{extra}>{text}</ix:nonFraction>'
    )


LYFT = "lyft:PaymentsToAcquirePropertyAndEquipmentAndScooterFleet"
D_CASH = "d:PaymentsToAcquirePropertyPlantAndEquipmentIncludingNuclearFuel"
D_ACCRUAL = "d:CapitalExpenditures"
CANON = "PaymentsToAcquirePropertyPlantAndEquipment"


def vals(out):
    return {
        (f["start"], f["end"]): f["val"]
        for f in out[CANON]["units"]["USD"]
    }


# --- signature -------------------------------------------------------

def test_tier_signature():
    assert _extension_capex_tier(
        "PaymentsToAcquirePropertyAndEquipmentAndScooterFleet") == 1
    assert _extension_capex_tier(
        "PaymentsToAcquirePropertyPlantAndEquipmentIncludingNuclearFuel") == 1
    assert _extension_capex_tier("PaymentsToAcquireProductiveAssets") == 1
    assert _extension_capex_tier("CapitalExpenditures") == 2
    # Lookalikes never match.
    assert _extension_capex_tier(
        "SegmentReportingInformationCapitalExpendituresAndInvestments") is None
    assert _extension_capex_tier("CapitalExpendituresOfFPL") is None
    assert _extension_capex_tier("PlannedCapitalExpendituresFifthYear") is None
    assert _extension_capex_tier(
        "ProceedsPaymentsFromOtherCapitalExpenditures") is None
    assert _extension_capex_tier("PaymentsToAcquireBusinesses") is None
    assert _extension_capex_tier("PaymentsToAcquireMarketableSecurities") is None
    assert _extension_capex_tier("CapitalExpendituresIncurredButNotYetPaid") is None


# --- parser ----------------------------------------------------------

def test_lyft_shape_parses_to_canonical_tag():
    html = filing("Q3",
                  xfact(LYFT, "m9", "84,476", scale="3")
                  + xfact(LYFT, "m9p", "34,220", scale="3"))
    out = parse_extension_capex_facts(
        html, form="10-Q", filed="2026-11-05", accn="0001")
    assert set(out) == {CANON}
    assert vals(out) == {M9: 84_476_000.0, M9P: 34_220_000.0}
    fact = out[CANON]["units"]["USD"][0]
    assert fact["fy"] == 2026 and fact["fp"] == "Q3"
    assert fact["form"] == "10-Q" and fact["accn"] == "0001"


def test_tier1_cash_line_wins_over_tier2_accrual():
    # Dominion shape: both concepts consolidated, values differ by the
    # accrual-vs-cash gap — the cash line (tier 1) must win.
    html = filing("Q3",
                  xfact(D_ACCRUAL, "m9", "8,593", scale="6")
                  + xfact(D_CASH, "m9", "8,576", scale="6")
                  + xfact(D_ACCRUAL, "m9p", "9,267", scale="6")
                  + xfact(D_CASH, "m9p", "9,255", scale="6"))
    out = parse_extension_capex_facts(
        html, form="10-Q", filed="2026-11-05", accn="0002")
    assert vals(out) == {M9: 8_576_000_000.0, M9P: 9_255_000_000.0}


def test_tier2_used_when_tier1_absent():
    html = filing("Q3", xfact("acme:CapitalExpenditures", "m9", "100", scale="6"))
    out = parse_extension_capex_facts(
        html, form="10-Q", filed="2026-11-05", accn="0003")
    assert vals(out) == {M9: 100_000_000.0}


def test_dimensional_tier2_skipped():
    # ED shape: CapitalExpenditures only in segment contexts.
    html = filing("Q3",
                  xfact("ed:CapitalExpenditures", "m9seg", "143", scale="6"))
    out = parse_extension_capex_facts(
        html, form="10-Q", filed="2026-11-05", accn="0004")
    assert out == {}


def test_lookalike_concepts_ignored():
    html = filing(
        "Q3",
        xfact("cop:SegmentReportingInformationCapitalExpendituresAndInvestments",
              "m9", "500", scale="6")
        + xfact("nee:CapitalExpendituresOfFPL", "m9", "600", scale="6")
        + xfact("nee:PlannedCapitalExpendituresFifthYear", "m9", "700", scale="6")
        + xfact("acme:PaymentsToAcquireBusinesses", "m9", "800", scale="6"))
    out = parse_extension_capex_facts(
        html, form="10-Q", filed="2026-11-05", accn="0005")
    assert out == {}


def test_us_gaap_facts_ignored():
    html = filing(
        "Q3",
        xfact(f"us-gaap:{CANON}", "m9", "999", scale="6"))
    out = parse_extension_capex_facts(
        html, form="10-Q", filed="2026-11-05", accn="0006")
    assert out == {}


def test_conflicting_tier1_concepts_abstain():
    html = filing(
        "Q3",
        xfact("acme:PaymentsToAcquirePropertyPlantAndEquipment", "m9", "100",
              scale="6")
        + xfact("acme:PaymentsToAcquireOtherPropertyAssets", "m9", "40",
                scale="6"))
    out = parse_extension_capex_facts(
        html, form="10-Q", filed="2026-11-05", accn="0007")
    assert out == {}


def test_agreeing_tier1_concepts_dedupe():
    html = filing(
        "Q3",
        xfact("acme:PaymentsToAcquirePropertyPlantAndEquipment", "m9", "100",
              scale="6")
        + xfact("acme:PaymentsToAcquirePropertyAssets", "m9", "100", scale="6"))
    out = parse_extension_capex_facts(
        html, form="10-Q", filed="2026-11-05", accn="0008")
    assert vals(out) == {M9: 100_000_000.0}


def test_same_concept_two_values_abstains():
    html = filing(
        "Q3",
        xfact(LYFT, "m9", "100", scale="6")
        + xfact(LYFT, "m9", "101", scale="6"))
    out = parse_extension_capex_facts(
        html, form="10-Q", filed="2026-11-05", accn="0009")
    assert out == {}


def test_missing_dei_focus_abstains():
    html = HEADER + xfact(LYFT, "m9", "100", scale="6")
    out = parse_extension_capex_facts(
        html, form="10-Q", filed="2026-11-05", accn="0010")
    assert out == {}


def test_instant_and_nil_facts_skipped():
    instant = (
        '<xbrli:context id="inst"><xbrli:entity>'
        '<xbrli:identifier scheme="http://www.sec.gov/CIK">0000000001</xbrli:identifier>'
        "</xbrli:entity><xbrli:period>"
        "<xbrli:instant>2026-09-30</xbrli:instant>"
        "</xbrli:period></xbrli:context>"
    )
    html = (
        "<ix:header><ix:resources>" + ctx("q3", *Q3) + instant
        + '<xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>'
        + "</ix:resources></ix:header>"
        + '<ix:nonNumeric name="dei:DocumentFiscalYearFocus" contextRef="q3">2026</ix:nonNumeric>'
        + '<ix:nonNumeric name="dei:DocumentFiscalPeriodFocus" contextRef="q3">Q3</ix:nonNumeric>'
        + xfact(LYFT, "inst", "100", scale="6")
        + xfact(LYFT, "q3", "", **{"nil": "true"})
    )
    out = parse_extension_capex_facts(
        html, form="10-Q", filed="2026-11-05", accn="0011")
    assert out == {}


# --- trigger ---------------------------------------------------------

def _cf(capex_end=None, opcf_end="2026-09-30"):
    gaap = {}
    if opcf_end:
        gaap["NetCashProvidedByUsedInOperatingActivities"] = {
            "units": {"USD": [
                {"start": "2026-01-01", "end": opcf_end, "val": 1.0,
                 "filed": "2026-11-01", "form": "10-Q", "fy": 2026, "fp": "Q3"},
            ]}}
    if capex_end:
        gaap[CANON] = {
            "units": {"USD": [
                {"start": "2026-01-01", "end": capex_end, "val": 1.0,
                 "filed": "2026-11-01", "form": "10-Q", "fy": 2026, "fp": "Q3"},
            ]}}
    return {"facts": {"us-gaap": gaap}}


def test_trigger_fires_when_capex_absent():
    assert _capex_missing_for_recent_ends(_cf()) is True


def test_trigger_fires_when_capex_stale():
    assert _capex_missing_for_recent_ends(_cf(capex_end="2025-12-31")) is True


def test_trigger_quiet_when_capex_current():
    assert _capex_missing_for_recent_ends(_cf(capex_end="2026-06-30")) is False
    assert _capex_missing_for_recent_ends(_cf(capex_end="2026-09-30")) is False


def test_trigger_abstains_without_opcf_anchor():
    assert _capex_missing_for_recent_ends(_cf(opcf_end=None)) is False
    assert _capex_missing_for_recent_ends({}) is False
    assert _capex_missing_for_recent_ends({"facts": None}) is False


# --- end-to-end ------------------------------------------------------

def _full_facts(with_capex=False):
    def rows(pairs, fp="Q3"):
        return [{"start": s, "end": e, "val": v, "filed": "2026-11-05",
                 "form": "10-Q", "fy": 2026, "fp": fp} for s, e, v in pairs]

    gaap = {
        "Revenues": {"units": {"USD": rows([
            ("2026-01-01", "2026-03-31", 1000.0),
            ("2026-04-01", "2026-06-30", 1100.0),
            ("2026-07-01", "2026-09-30", 1200.0),
        ])}},
        "NetIncomeLoss": {"units": {"USD": rows([
            ("2026-01-01", "2026-03-31", 100.0),
            ("2026-04-01", "2026-06-30", 110.0),
            ("2026-07-01", "2026-09-30", 120.0),
        ])}},
        "EarningsPerShareBasic": {"units": {"USD/shares": rows([
            ("2026-01-01", "2026-03-31", 1.0),
            ("2026-04-01", "2026-06-30", 1.1),
            ("2026-07-01", "2026-09-30", 1.2),
        ])}},
        "EarningsPerShareDiluted": {"units": {"USD/shares": rows([
            ("2026-01-01", "2026-03-31", 0.9),
            ("2026-04-01", "2026-06-30", 1.0),
            ("2026-07-01", "2026-09-30", 1.1),
        ])}},
        "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": rows([
            ("2026-01-01", "2026-03-31", 300.0),
            ("2026-01-01", "2026-06-30", 650.0),
            ("2026-01-01", "2026-09-30", 1000.0),
        ])}},
    }
    if with_capex:
        gaap[CANON] = {"units": {"USD": rows([
            ("2026-01-01", "2026-03-31", 50.0),
            ("2026-01-01", "2026-06-30", 110.0),
            ("2026-01-01", "2026-09-30", 180.0),
        ])}}
    return {"facts": {"us-gaap": gaap}}


class FakeClient:
    def __init__(self, html):
        self.html = html

    def fetch_text(self, url):
        if "_d" in url:
            raise RuntimeError("no sibling")
        return self.html


SUBS = {"filings": {"recent": {
    "form": ["10-Q"], "filingDate": ["2026-11-05"],
    "accessionNumber": ["0000000001-26-000001"],
    "primaryDocument": ["acme-20260930.htm"],
}}}


def test_augment_recovers_fcf_end_to_end():
    facts = _full_facts()
    assert _capex_missing_for_recent_ends(facts) is True
    rows = extract_recent_quarterly_financials(facts, periods=3)
    assert all(r.free_cash_flow is None for r in rows)

    html = filing("Q3",
                  xfact(LYFT, "q1", "50")
                  + xfact(LYFT, "m6", "110")
                  + xfact(LYFT, "m9", "180"))
    merged = _augment_with_extension_capex(
        FakeClient(html), "0000000001", SUBS, facts)
    assert merged == 1
    rows = extract_recent_quarterly_financials(facts, periods=3)
    fcf = {str(r.end): r.free_cash_flow for r in rows}
    assert fcf == {
        "2026-03-31": 250.0,   # 300 - 50
        "2026-06-30": 290.0,   # (650-300) - (110-50)
        "2026-09-30": 280.0,   # (1000-650) - (180-110)
    }


def test_augment_gap_only_consolidated_wins():
    facts = _full_facts(with_capex=True)
    html = filing("Q3", xfact(LYFT, "m9", "999"))
    merged = _augment_with_extension_capex(
        FakeClient(html), "0000000001", SUBS, facts)
    assert merged == 0
    rows = extract_recent_quarterly_financials(facts, periods=3)
    fcf = {str(r.end): r.free_cash_flow for r in rows}
    assert fcf["2026-09-30"] == 280.0  # consolidated 180, not extension 999


# --- VZ chain tag ------------------------------------------------------

def test_other_productive_assets_tag_wins_by_freshness():
    # Verizon shape: ProductiveAssets stops in 2019, the total capex
    # line lives under OtherProductiveAssets (current).
    def rows(pairs):
        return [{"start": s, "end": e, "val": v, "filed": "2026-11-05",
                 "form": "10-Q", "fy": 2026, "fp": "Q3"} for s, e, v in pairs]

    facts = {"facts": {"us-gaap": {
        "PaymentsToAcquireProductiveAssets": {"units": {"USD": rows([
            ("2019-01-01", "2019-09-30", 999.0),
        ])}},
        "PaymentsToAcquireOtherProductiveAssets": {"units": {"USD": rows([
            ("2026-01-01", "2026-03-31", 4201.0),
            ("2026-01-01", "2026-06-30", 8210.0),
            ("2026-01-01", "2026-09-30", 11926.0),
        ])}},
    }}}
    series = {str(m.end): m.value
              for m in quarterly_cash_flow_metric(facts, Metric.CAPEX)}
    assert series["2026-03-31"] == 4201.0
    assert series["2026-06-30"] == 4009.0
    assert series["2026-09-30"] == 3716.0


def test_augment_never_raises():
    class Boom:
        def fetch_text(self, url):
            raise RuntimeError("boom")

    facts = _full_facts()
    assert _augment_with_extension_capex(
        Boom(), "0000000001", SUBS, facts) == 0
    assert _augment_with_extension_capex(
        Boom(), "0000000001", {}, facts) == 0
