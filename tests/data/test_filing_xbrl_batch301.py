"""Batch 301 regression tests: per-class (dimensional) EPS recovery.

Multi-class filers (V, BRK.B, HSY, KKR, STZ, BKR) tag EPS only per share
class — the facts live in StatementClassOfStockAxis contexts that
companyfacts (consolidated-only) never carries, leaving every stored
quarter's EPS NULL. ``parse_class_eps_facts`` reads the traded class's
EPS out of a filing's inline XBRL, ``_eps_missing_for_recent_ends``
gates the recovery to filers whose EPS is actually missing, and
``_augment_with_class_eps`` merges gap-only so consolidated facts
always win. Fixtures model the real class structures probed in
``scripts/batch301_probe2.py`` / ``batch301_probe3.py``.
"""
import sys

sys.path.insert(0, "src")

from tickerlens.data.filing_xbrl import (
    _choose_class_member,
    _class_letter_for_ticker,
    merge_filing_facts,
    merge_filing_facts_gap_only,
    parse_class_eps_facts,
    parse_inline_xbrl,
)
from tickerlens.data.xbrl import extract_recent_quarterly_financials
from tickerlens.services.financials import (
    _augment_with_class_eps,
    _eps_missing_for_recent_ends,
)

AXIS = "us-gaap:StatementClassOfStockAxis"


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


def class_ctx(cid, start, end, member):
    return ctx(cid, start, end, [(AXIS, member)])


Q3 = ("2026-07-01", "2026-09-30")
M9 = ("2026-01-01", "2026-09-30")
Q2 = ("2026-04-01", "2026-06-30")
M6 = ("2026-01-01", "2026-06-30")

HEADER = (
    "<ix:header><ix:resources>"
    + ctx("q2", *Q2)
    + ctx("q3", *Q3)
    + ctx("m6", *M6)
    + ctx("m9", *M9)
    # Visa shape: A / B1 / B2 / C on the class axis.
    + class_ctx("q3A", *Q3, "us-gaap:CommonClassAMember")
    + class_ctx("q3B1", *Q3, "v:CommonClassB1Member")
    + class_ctx("q3C", *Q3, "us-gaap:CommonClassCMember")
    + class_ctx("m9A", *M9, "us-gaap:CommonClassAMember")
    + class_ctx("m9B1", *M9, "v:CommonClassB1Member")
    + class_ctx("m9C", *M9, "us-gaap:CommonClassCMember")
    + class_ctx("q2A", *Q2, "us-gaap:CommonClassAMember")
    + class_ctx("q2B1", *Q2, "v:CommonClassB1Member")
    + class_ctx("q2C", *Q2, "us-gaap:CommonClassCMember")
    # Berkshire shape: equivalent A / B.
    + class_ctx("q3EqA", *Q3, "brka:EquivalentClassAMember")
    + class_ctx("q3EqB", *Q3, "brka:EquivalentClassBMember")
    # Hershey shape: plain common + class B.
    + class_ctx("q3Plain", *Q3, "us-gaap:CommonStockMember")
    + class_ctx("q3B", *Q3, "us-gaap:CommonClassBMember")
    # Subclass-only shape.
    + class_ctx("q3B2", *Q3, "v:CommonClassB2Member")
    # Wrong axis + multi-member contexts (must be ignored).
    + ctx("q3Seg", *Q3, [("srt:ProductOrServiceAxis", "us-gaap:ElectricityMember")])
    + ctx(
        "q3Multi",
        *Q3,
        [(AXIS, "us-gaap:CommonClassAMember"),
         ("srt:ProductOrServiceAxis", "us-gaap:ElectricityMember")],
    )
    + '<xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>'
    + '<xbrli:unit id="usdPerShare"><xbrli:divide><xbrli:unitNumerator>'
      '<xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unitNumerator>'
      '<xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure>'
      "</xbrli:unitDenominator></xbrli:divide></xbrli:unit>"
    + "</ix:resources></ix:header>"
)


def filing(fp, body, fy="2026"):
    return (
        HEADER
        + f'<ix:nonNumeric name="dei:DocumentFiscalYearFocus" contextRef="q3">{fy}</ix:nonNumeric>'
        + f'<ix:nonNumeric name="dei:DocumentFiscalPeriodFocus" contextRef="q3">{fp}</ix:nonNumeric>'
        + body
    )


def fact(name, ctx_id, unit, text, **attrs):
    extra = "".join(f' {k}="{v}"' for k, v in attrs.items())
    return (
        f'<ix:nonFraction name="us-gaap:{name}" contextRef="{ctx_id}" '
        f'unitRef="{unit}"{extra}>{text}</ix:nonFraction>'
    )


def eps(ctx_id, basic, diluted=None):
    out = fact("EarningsPerShareBasic", ctx_id, "usdPerShare", str(basic))
    if diluted is not None:
        out += fact("EarningsPerShareDiluted", ctx_id, "usdPerShare", str(diluted))
    return out


def parse(html, ticker):
    return parse_class_eps_facts(
        html, form="10-Q", filed="2026-10-28", accn="A1", ticker=ticker
    )


def facts_of(parsed, tag):
    return parsed.get(tag, {}).get("units", {}).get("USD/shares", [])


# ── class choice ─────────────────────────────────────────────────────────────

def test_class_letter_for_ticker():
    assert _class_letter_for_ticker("BRK.B") == "B"
    assert _class_letter_for_ticker("BF-B") == "B"
    assert _class_letter_for_ticker("V") == "A"
    assert _class_letter_for_ticker("GOOGL") == "A"
    assert _class_letter_for_ticker("") == "A"


def test_choose_agreeing_classes():
    member = _choose_class_member(
        {"CommonClassAMember": 1.00, "CommonClassBMember": 1.004}, "XYZ"
    )
    assert member is not None  # agreement: value is what matters


def test_choose_subclass_only_abstains():
    assert _choose_class_member(
        {"CommonClassB1Member": 4.59, "CommonClassB2Member": 4.47}, "XYZ.B"
    ) is None


def test_choose_no_candidate_abstains():
    # Target A; only B and C present, values differ, no plain member.
    assert _choose_class_member(
        {"CommonClassBMember": 3.0, "CommonClassCMember": 9.0}, "XYZ"
    ) is None


# ── filing parse ─────────────────────────────────────────────────────────────

def test_visa_shape_picks_class_a():
    html = filing("Q3", "".join([
        eps("q3A", "2.97", "2.97"), eps("q3B1", "4.59", "4.59"), eps("q3C", "11.87", "11.86"),
        eps("m9A", "9.15", "9.14"), eps("m9B1", "14.18", "14.17"), eps("m9C", "36.58", "36.55"),
    ]))
    parsed = parse(html, "V")
    basic = {(f["start"], f["end"]): f["val"] for f in facts_of(parsed, "EarningsPerShareBasic")}
    diluted = {(f["start"], f["end"]): f["val"] for f in facts_of(parsed, "EarningsPerShareDiluted")}
    assert basic == {Q3: 2.97, M9: 9.15}
    assert diluted == {Q3: 2.97, M9: 9.14}
    f0 = facts_of(parsed, "EarningsPerShareBasic")[0]
    assert (f0["fy"], f0["fp"], f0["form"], f0["accn"]) == (2026, "Q3", "10-Q", "A1")


def test_berkshire_shape_picks_class_b():
    html = filing("Q3", "".join([eps("q3EqA", "15502"), eps("q3EqB", "10.33")]))
    parsed = parse(html, "BRK.B")
    assert [f["val"] for f in facts_of(parsed, "EarningsPerShareBasic")] == [10.33]
    assert facts_of(parsed, "EarningsPerShareDiluted") == []


def test_hershey_shape_plain_member_wins():
    html = filing("Q3", "".join([eps("q3Plain", "2.96", "2.88"), eps("q3B", "2.69", "2.69")]))
    parsed = parse(html, "HSY")
    assert [f["val"] for f in facts_of(parsed, "EarningsPerShareBasic")] == [2.96]
    assert [f["val"] for f in facts_of(parsed, "EarningsPerShareDiluted")] == [2.88]


def test_single_member_used():
    html = filing("Q3", eps("q3Plain", "1.25", "1.19"))
    parsed = parse(html, "KKR")
    assert [f["val"] for f in facts_of(parsed, "EarningsPerShareBasic")] == [1.25]
    assert [f["val"] for f in facts_of(parsed, "EarningsPerShareDiluted")] == [1.19]


def test_wrong_axis_and_multi_member_ignored():
    html = filing("Q3", "".join([
        eps("q3Seg", "5.00", "5.00"), eps("q3Multi", "6.00", "6.00"),
        eps("q3", "7.00", "7.00"),  # consolidated: parse_inline_xbrl's job
    ]))
    assert parse(html, "V") == {}


def test_inconsistent_members_abstain_filing():
    # Basic group picks Class A; diluted group would pick the plain
    # member — two different winners in one filing abstain wholesale.
    html = filing("Q3", "".join([
        fact("EarningsPerShareBasic", "q3A", "usdPerShare", "2.00"),
        fact("EarningsPerShareBasic", "q3B", "usdPerShare", "3.00"),
        fact("EarningsPerShareDiluted", "q3Plain", "usdPerShare", "1.90"),
        fact("EarningsPerShareDiluted", "q3B", "usdPerShare", "2.90"),
    ]))
    assert parse(html, "V") == {}


def test_missing_dei_focus_abstains():
    html = HEADER + eps("q3A", "2.97")
    assert parse(html, "V") == {}


def test_conflicting_same_member_values_abstain_group():
    html = filing("Q3", "".join([eps("q3A", "2.97"), eps("q3A", "2.98")]))
    assert parse(html, "V") == {}


# ── gap-only merge ───────────────────────────────────────────────────────────

def test_gap_only_merge_never_displaces():
    cf = {"facts": {"us-gaap": {"EarningsPerShareBasic": {"units": {"USD/shares": [
        {"start": Q3[0], "end": Q3[1], "val": 7.77, "accn": "OLD"},
    ]}}}}}
    filing_facts = {"EarningsPerShareBasic": {"units": {"USD/shares": [
        {"start": Q3[0], "end": Q3[1], "val": 2.97, "accn": "NEW"},
        {"start": M9[0], "end": M9[1], "val": 9.15, "accn": "NEW"},
    ]}}}
    assert merge_filing_facts_gap_only(cf, filing_facts) == 1
    vals = {(f["start"], f["end"]): f["val"]
            for f in cf["facts"]["us-gaap"]["EarningsPerShareBasic"]["units"]["USD/shares"]}
    assert vals == {Q3: 7.77, M9: 9.15}


# ── trigger predicate ────────────────────────────────────────────────────────

def _cf(rev_end=None, eps_end=None):
    gaap = {}
    if rev_end:
        gaap["Revenues"] = {"units": {"USD": [{"end": rev_end, "val": 1}]}}
    if eps_end:
        gaap["EarningsPerShareDiluted"] = {"units": {"USD/shares": [{"end": eps_end, "val": 1}]}}
    return {"facts": {"us-gaap": gaap}}


def test_eps_missing_predicate():
    assert _eps_missing_for_recent_ends(_cf("2026-09-30", "2026-09-30")) is False
    assert _eps_missing_for_recent_ends(_cf("2026-09-30", "2026-06-30")) is False  # 92d lag
    assert _eps_missing_for_recent_ends(_cf("2026-09-30", "2024-12-31")) is True   # BKR shape
    assert _eps_missing_for_recent_ends(_cf("2026-09-30", None)) is True           # V shape
    assert _eps_missing_for_recent_ends(_cf(None, "2026-09-30")) is False          # no anchor
    assert _eps_missing_for_recent_ends({}) is False
    assert _eps_missing_for_recent_ends({"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [{"end": "not-a-date"}]}},
    }}}) is False


# ── augment wiring + end-to-end ──────────────────────────────────────────────

class FakeClient:
    def __init__(self, html_by_accn):
        self.html_by_accn = html_by_accn
        self.fetched = []

    def fetch_text(self, url):
        self.fetched.append(url)
        if "_d" in url.rsplit("/", 1)[-1]:
            raise FileNotFoundError(f"no sibling document: {url}")
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


REV = "RevenueFromContractWithCustomerExcludingAssessedTax"

# NI figures are EPS x 10 shares throughout, so the extractor's
# share-implied derivation sees one consistent share basis.
Q3_FILING = filing("Q3", "".join([
    fact(REV, "q3", "usd", "300"), fact(REV, "m9", "usd", "600"),
    fact("NetIncomeLoss", "q3", "usd", "29.7"), fact("NetIncomeLoss", "m9", "usd", "91.5"),
    eps("q3A", "2.97", "2.90"), eps("q3B1", "4.59", "4.50"), eps("q3C", "11.87", "11.86"),
    eps("m9A", "9.15", "9.14"), eps("m9B1", "14.18", "14.17"), eps("m9C", "36.58", "36.55"),
]))

Q2_FILING = filing("Q2", "".join([
    fact(REV, "q2", "usd", "200"), fact(REV, "m6", "usd", "300"),
    fact("NetIncomeLoss", "q2", "usd", "25"), fact("NetIncomeLoss", "m6", "usd", "61.8"),
    eps("q2A", "2.50", "2.45"), eps("q2B1", "3.90", "3.80"), eps("q2C", "9.90", "9.80"),
]))


def _q1_companyfacts():
    def f(start, end, val):
        return {"start": start, "end": end, "val": val, "filed": "2026-05-05",
                "form": "10-Q", "accn": "0000000001-26-000001", "fy": 2026, "fp": "Q1"}
    return {"facts": {"us-gaap": {
        REV: {"units": {"USD": [f("2026-01-01", "2026-03-31", 100.0)]}},
        "NetIncomeLoss": {"units": {"USD": [f("2026-01-01", "2026-03-31", 36.8)]}},
    }}}


def test_augment_recovers_class_eps_end_to_end():
    cf = _q1_companyfacts()
    # Consolidated Q2/Q3 revenue+NI arrive via the batch-293 path shape.
    merge_filing_facts(cf, parse_inline_xbrl(Q2_FILING, form="10-Q", filed="2026-07-30", accn="0000000001-26-000002"))
    merge_filing_facts(cf, parse_inline_xbrl(Q3_FILING, form="10-Q", filed="2026-10-28", accn="0000000001-26-000003"))
    assert _eps_missing_for_recent_ends(cf) is True  # no consolidated EPS anywhere

    subs = submissions([
        ("10-Q", "2026-10-28", "0000000001-26-000003", "q3.htm"),
        ("10-Q", "2026-07-30", "0000000001-26-000002", "q2.htm"),
        ("10-Q", "2026-05-05", "0000000001-26-000001", "q1.htm"),
    ])
    client = FakeClient({
        "0000000001-26-000003": Q3_FILING,
        "0000000001-26-000002": Q2_FILING,
        # Q1 filing carries no class EPS (parse abstains, not counted).
        "0000000001-26-000001": filing("Q1", fact(REV, "q2", "usd", "100")),
    })
    merged = _augment_with_class_eps(
        client, "0000000001", "V", subs, cf, lookback_days=100000
    )
    assert merged == 2

    rows = extract_recent_quarterly_financials(cf, fiscal_year_end="1231", periods=8)
    by_end = {r.end.isoformat(): r for r in rows}
    assert by_end["2026-09-30"].eps_basic == 2.97     # Class A, not C's 11.87
    assert by_end["2026-09-30"].eps_diluted == 2.90
    assert by_end["2026-06-30"].eps_basic == 2.50
    assert by_end["2026-06-30"].eps_diluted == 2.45
    # Q1 has no filed EPS fact; the extractor derives it share-implied
    # from the merged Class A M9/Q2/Q3 facts (36.8 / 10 shares = 3.68).
    assert by_end["2026-03-31"].eps_basic is not None
    assert abs(by_end["2026-03-31"].eps_basic - 3.68) < 0.1


def test_augment_never_raises():
    cf = _q1_companyfacts()
    subs = submissions([("10-Q", "2026-10-28", "0000000001-26-000003", "q3.htm")])
    client = FakeClient({"0000000001-26-000003": RuntimeError("boom")})
    assert _augment_with_class_eps(
        client, "0000000001", "V", subs, cf, lookback_days=100000
    ) == 0
    assert cf == _q1_companyfacts()


def test_augment_respects_lookback():
    cf = _q1_companyfacts()
    subs = submissions([("10-Q", "2020-01-15", "0000000001-20-000003", "q3.htm")])
    client = FakeClient({})
    assert _augment_with_class_eps(
        client, "0000000001", "V", subs, cf, lookback_days=1100
    ) == 0
    assert client.fetched == []
