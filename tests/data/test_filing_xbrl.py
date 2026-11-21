"""Batch 293 regression tests: per-filing inline-XBRL fallback.

SEC's companyfacts aggregation can lag a filing by months — AEP, C, D,
DLR, DUK, ETR, NEE, PLD, PPL, SO and SRE all filed Q2+Q3 2026 10-Qs that
contribute zero facts to the feed. ``parse_inline_xbrl`` reads the
filing's own inline XBRL into companyfacts shape (consolidated facts
only, dei fiscal focus as fy/fp — SEC's own labeling), and
``_augment_with_uningested_filings`` merges it when the filing's
accession is absent from companyfacts, so the existing extractor
recovers the quarters unchanged.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filing_xbrl import (
    companyfacts_accns,
    merge_filing_facts,
    parse_inline_xbrl,
)
from tickerlens.data.xbrl import extract_recent_quarterly_financials
from tickerlens.services.financials import _augment_with_uningested_filings

HEADER = """
<ix:header>
 <ix:references/>
 <ix:resources>
  <xbrli:context id="q1"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000000001</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-01-01</xbrli:startDate><xbrli:endDate>2026-03-31</xbrli:endDate></xbrli:period></xbrli:context>
  <xbrli:context id="q2"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000000001</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period></xbrli:context>
  <xbrli:context id="q3"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000000001</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period></xbrli:context>
  <xbrli:context id="m6"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000000001</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-01-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period></xbrli:context>
  <xbrli:context id="m9"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000000001</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-01-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period></xbrli:context>
  <xbrli:context id="i6"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000000001</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period></xbrli:context>
  <xbrli:context id="i9"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000000001</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period></xbrli:context>
  <xbrli:context id="seg"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000000001</xbrli:identifier><xbrli:segment><xbrldi:explicitMember dimension="srt:ProductOrServiceAxis">us-gaap:ElectricityMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period></xbrli:context>
  <xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
  <xbrli:unit id="usdPerShare"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>
 </ix:resources>
</ix:header>
"""


def filing(fp, body):
    return (
        HEADER
        + f'<ix:nonNumeric name="dei:DocumentFiscalYearFocus" contextRef="q1">2026</ix:nonNumeric>'
        + f'<ix:nonNumeric name="dei:DocumentFiscalPeriodFocus" contextRef="q1">{fp}</ix:nonNumeric>'
        + body
    )


def fact(name, ctx, unit, text, **attrs):
    extra = "".join(f' {k}="{v}"' for k, v in attrs.items())
    return (
        f'<ix:nonFraction name="us-gaap:{name}" contextRef="{ctx}" '
        f'unitRef="{unit}"{extra}>{text}</ix:nonFraction>'
    )


REV = "RevenueFromContractWithCustomerExcludingAssessedTax"

Q2_HTML = filing("Q2", "".join([
    fact(REV, "q2", "usd", "200", scale="0"),
    fact(REV, "m6", "usd", "300", scale="0"),
    fact("NetIncomeLoss", "q2", "usd", "20"),
    fact("NetIncomeLoss", "m6", "usd", "30"),
    fact("EarningsPerShareBasic", "q2", "usdPerShare", "2.00"),
    fact("EarningsPerShareDiluted", "q2", "usdPerShare", "1.90"),
    fact("Assets", "i6", "usd", "5", scale="3"),
]))

Q3_HTML = filing("Q3", "".join([
    fact(REV, "q3", "usd", "300"),
    fact(REV, "m9", "usd", "600"),
    fact("NetIncomeLoss", "q3", "usd", "30"),
    fact("NetIncomeLoss", "m9", "usd", "60"),
    fact("EarningsPerShareBasic", "q3", "usdPerShare", "3.00"),
    fact("EarningsPerShareDiluted", "q3", "usdPerShare", "2.90"),
    fact("Assets", "i9", "usd", "5500"),
]))


def cf_fact(start, end, val, fy, fp, filed="2026-05-05", accn="0000000001-26-000001"):
    return {"start": start, "end": end, "val": val, "fy": fy, "fp": fp,
            "form": "10-Q", "filed": filed, "accn": accn}


def q1_companyfacts():
    return {"facts": {"us-gaap": {
        REV: {"units": {"USD": [cf_fact("2026-01-01", "2026-03-31", 100.0, 2026, "Q1")]}},
        "NetIncomeLoss": {"units": {"USD": [cf_fact("2026-01-01", "2026-03-31", 10.0, 2026, "Q1")]}},
        "EarningsPerShareBasic": {"units": {"USD/shares": [cf_fact("2026-01-01", "2026-03-31", 1.0, 2026, "Q1")]}},
        "EarningsPerShareDiluted": {"units": {"USD/shares": [cf_fact("2026-01-01", "2026-03-31", 0.95, 2026, "Q1")]}},
        "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": []}},
        "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": []}},
    }}}


# ── parser units ─────────────────────────────────────────────────────────────

def test_duration_fact_with_scale_and_labels():
    facts = parse_inline_xbrl(Q2_HTML, form="10-Q", filed="2026-07-30", accn="A2")
    rev = facts[REV]["units"]["USD"]
    q2 = [f for f in rev if f["end"] == "2026-06-30" and f["start"] == "2026-04-01"][0]
    assert q2["val"] == 200.0 and q2["fy"] == 2026 and q2["fp"] == "Q2"
    assert q2["form"] == "10-Q" and q2["filed"] == "2026-07-30" and q2["accn"] == "A2"
    assets = facts["Assets"]["units"]["USD"][0]
    assert assets["val"] == 5000.0 and "start" not in assets  # instant, scale 3


def test_sign_parens_fixed_zero_and_comma_decimal():
    html = filing("Q3", "".join([
        fact("NetIncomeLoss", "q3", "usd", "1,234", sign="-"),
        fact("OperatingIncomeLoss", "q3", "usd", "(567)"),
        fact("CashAndCashEquivalentsAtCarryingValue", "i9", "usd", "—", format="ixt:fixed-zero"),
        fact("Assets", "i9", "usd", "1.234,5", format="ixt:num-comma-decimal"),
    ]))
    facts = parse_inline_xbrl(html, form="10-Q", filed="2026-10-28", accn="A3")
    assert facts["NetIncomeLoss"]["units"]["USD"][0]["val"] == -1234.0
    assert facts["OperatingIncomeLoss"]["units"]["USD"][0]["val"] == -567.0
    assert facts["CashAndCashEquivalentsAtCarryingValue"]["units"]["USD"][0]["val"] == 0.0
    assert facts["Assets"]["units"]["USD"][0]["val"] == 1234.5


def test_skips_dimensional_nil_nongaap_and_words():
    html = filing("Q3", "".join([
        fact(REV, "seg", "usd", "999"),                      # dimensional
        fact(REV, "q3", "usd", "300"),                       # consolidated
        '<ix:nonFraction name="us-gaap:NetIncomeLoss" contextRef="q3" unitRef="usd" nil="true"></ix:nonFraction>',
        '<ix:nonFraction name="aep:CustomThing" contextRef="q3" unitRef="usd">5</ix:nonFraction>',
        fact("Assets", "i9", "usd", "five", format="ixt-sec:numwordsen"),
    ]))
    facts = parse_inline_xbrl(html, form="10-Q", filed="2026-10-28", accn="A3")
    assert [f["val"] for f in facts[REV]["units"]["USD"]] == [300.0]
    assert "NetIncomeLoss" not in facts
    assert "Assets" not in facts
    assert len(facts) == 1


def test_dedupes_identical_facts():
    html = filing("Q3", fact(REV, "q3", "usd", "300") + fact(REV, "q3", "usd", "300"))
    facts = parse_inline_xbrl(html, form="10-Q", filed="2026-10-28", accn="A3")
    assert len(facts[REV]["units"]["USD"]) == 1


def test_dei_focus_wrapped_in_styled_markup():
    # D/PLD cover pages wrap the dei focus value in a styled <span>.
    html = (
        HEADER
        + '<ix:nonNumeric name="dei:DocumentFiscalYearFocus" contextRef="q3">'
        + '<span style="font-weight:bold">2026</span></ix:nonNumeric>'
        + '<ix:nonNumeric name="dei:DocumentFiscalPeriodFocus" contextRef="q3">Q3</ix:nonNumeric>'
        + fact(REV, "q3", "usd", "300")
    )
    facts = parse_inline_xbrl(html, form="10-Q", filed="2026-10-30", accn="A3")
    assert facts[REV]["units"]["USD"][0]["fy"] == 2026


def test_missing_dei_focus_abstains():
    facts = parse_inline_xbrl(HEADER + fact(REV, "q3", "usd", "300"),
                              form="10-Q", filed="2026-10-28", accn="A3")
    assert facts == {}


def test_per_share_unit_normalizes():
    facts = parse_inline_xbrl(Q3_HTML, form="10-Q", filed="2026-10-28", accn="A3")
    assert facts["EarningsPerShareBasic"]["units"]["USD/shares"][0]["val"] == 3.0


# ── end-to-end extraction ────────────────────────────────────────────────────

def test_merged_filings_recover_missing_quarters():
    cf = q1_companyfacts()
    merge_filing_facts(cf, parse_inline_xbrl(Q2_HTML, form="10-Q", filed="2026-07-30", accn="A2"))
    merge_filing_facts(cf, parse_inline_xbrl(Q3_HTML, form="10-Q", filed="2026-10-28", accn="A3"))
    rows = extract_recent_quarterly_financials(cf, fiscal_year_end="1231", periods=8)
    by_end = {r.end.isoformat(): r for r in rows}
    assert sorted(by_end) == ["2026-03-31", "2026-06-30", "2026-09-30"]
    assert (by_end["2026-06-30"].fy, by_end["2026-06-30"].fp) == (2026, "Q2")
    assert (by_end["2026-09-30"].fy, by_end["2026-09-30"].fp) == (2026, "Q3")
    assert by_end["2026-06-30"].revenue == 200.0
    assert by_end["2026-09-30"].revenue == 300.0
    assert by_end["2026-09-30"].net_income == 30.0
    assert by_end["2026-06-30"].total_assets == 5000.0
    assert by_end["2026-09-30"].total_assets == 5500.0


# ── augment wiring ───────────────────────────────────────────────────────────

class FakeClient:
    def __init__(self, html_by_accn):
        self.html_by_accn = html_by_accn
        self.fetched = []

    def fetch_text(self, url):
        self.fetched.append(url)
        for accn, html in self.html_by_accn.items():
            if accn.replace("-", "") in url:
                if isinstance(html, Exception):
                    raise html
                return html
        raise AssertionError(f"unexpected fetch: {url}")


def submissions(rows):
    return {"filings": {"recent": {
        "form": [r[0] for r in rows],
        "filingDate": [r[1] for r in rows],
        "accessionNumber": [r[2] for r in rows],
        "primaryDocument": [r[3] for r in rows],
    }}}


def test_augment_merges_only_uningested():
    cf = q1_companyfacts()
    subs = submissions([
        ("10-Q", "2026-10-28", "0000000001-26-000003", "q3.htm"),
        ("10-Q", "2026-07-30", "0000000001-26-000002", "q2.htm"),
        ("10-Q", "2026-05-05", "0000000001-26-000001", "q1.htm"),  # ingested
    ])
    client = FakeClient({"0000000001-26-000003": Q3_HTML,
                         "0000000001-26-000002": Q2_HTML})
    merged = _augment_with_uningested_filings(client, "0000000001", subs, cf)
    assert merged == 2
    assert len(client.fetched) == 2
    assert "0000000001-26-000003" in companyfacts_accns(cf)


def test_augment_noop_when_all_ingested():
    cf = q1_companyfacts()
    subs = submissions([("10-Q", "2026-05-05", "0000000001-26-000001", "q1.htm")])
    client = FakeClient({})
    assert _augment_with_uningested_filings(client, "0000000001", subs, cf) == 0
    assert client.fetched == []


def test_augment_never_raises():
    cf = q1_companyfacts()
    subs = submissions([("10-Q", "2026-10-28", "0000000001-26-000003", "q3.htm")])
    client = FakeClient({"0000000001-26-000003": RuntimeError("boom")})
    assert _augment_with_uningested_filings(client, "0000000001", subs, cf) == 0
    assert cf == q1_companyfacts()
