"""Batch 193: the guidance collector skips footnote blocks in-loop and ends
the section at the next section heading.

Batch 192 left the guidance collector as the one path with no footnote
handling at all — APD's "#" per-share definition and "* Certain results"
legend were served as guidance, and the collector ran 30 lines past the
guidance section into results narrative (its 4000-char cap truncating
mid-segment-table), so the served "guidance" was mostly results prose.
The fix, all in extract_management_guidance:
  - footnote-definition / rounding-note / asterisk-note blocks are skipped
    whole in-loop (the section collector's block machinery), so the 30-line
    budget is spent only on kept lines — never post-collection, which batch
    192 showed refills the freed char budget with next-section content;
  - a next-section heading ends the section (title-case, unterminated,
    heading a bullet/prose/dateline block), gated on the section having
    delivered guidance already (Crown Castle's OUTLOOK opens with a
    safe-harbor intro and a Restructuring Plan Update before its table);
  - the anchor tolerates an attached footnote digit on compound headings
    ("Financial Guidance1" — DAL) but not on bare words ("Guidance5" —
    CRM's table column header), and rejects quote fragments;
  - "-more-" and repeated release-title lines are skipped; all-caps period
    labels ("Q4 FY25") no longer break collection; paren-word table headers
    ("(Prior)", "(Updated)") are not footnote keys; call/webcast notices
    break the section.
  - Repair spot-check (before the DB repair) caught two more tail shapes
    the blast's junk check missed: Applied Materials' guidance section is
    followed by its results segment table ("First Quarter Reportable
    Segment Information" — a table-start break now) and General Mills'
    notice shape ("pre-recorded management remarks ... webcasted
    question and answer session" — a guarded call-notice break now).
Blast (1,699 exhibits, base vs new9): 796 vs 765 guidance texts, 0 lost,
31 gained (APH, CI, CSCO, DAL, DASH — all genuine guidance tables/prose),
446 diffs, 2,244 removed lines (all footnote lines, "-more-", teleconference
/ call notices, and next-section results narrative — verified line by line),
673 added lines (guidance bullets, outlook prose, outlook-table rows freed
by the skipped footnotes), 0 added junk lines. The 162 flagged removed
lines are all correct removals: the 160 from the new8 classification
(results narrative, metric glossaries, Business Highlights, supplemental
pointers, segment-table rows, disclaimers) plus 2 GIS safe-harbor
disclaimer lines that sat after the call notice.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _CALL_QA_SESSION_RE,
    _FINANCIAL_TABLE_START_RE,
    _guidance_has_signal,
    _is_guidance_heading,
    _is_guidance_next_section_heading,
    _is_guidance_period_label,
    extract_management_guidance,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _live(ticker_period: str) -> str:
    html = open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ).read()
    out = extract_management_guidance(html)
    assert out is not None, f"{ticker_period} extracted None"
    return out


# --- unit: the next-section heading rule ----------------------------------

def test_next_section_apd_news_and_highlights():
    lines = [
        "Guidance",
        "•Raising fiscal 2026 full-year adjusted EPS guidance* to $13.00 to $13.25",
        "News and Highlights",
        "•Electronics growth: Selected by Samsung to build facilities",
    ]
    assert _is_guidance_next_section_heading(lines, 2)


def test_next_section_apd_results_heading_paren_dateline():
    lines = [
        "Guidance",
        "•Expect fiscal year 2026 capital expenditures* of approximately $4.0 billion",
        "Fiscal 2025 Full-Year Consolidated Results",
        "LEHIGH VALLEY, Pa. (November 6, 2025) - Air Products (NYSE:APD) today reported",
    ]
    assert _is_guidance_next_section_heading(lines, 2)


def test_next_section_apd_teleconference():
    lines = [
        "Guidance",
        "•Expect fiscal year 2026 capital expenditures* of approximately $4.0 billion",
        "Earnings Teleconference",
        "Access the fiscal 2026 second quarter earnings teleconference scheduled for 8:00 a.m.",
    ]
    assert _is_guidance_next_section_heading(lines, 2)


def test_next_section_exempts_guidance_vocab_headings():
    # ADP's outlook sub-sections end in Outlook/Guidance — never a break.
    for head in [
        "Consolidated Fiscal 2024 Outlook",
        "Long-Term Outlook",
        "Employer Services Segment Fiscal 2024 Outlook",
        "AbbVie Raises 2024 EPS Guidance Floor",
    ]:
        lines = ["Guidance", head, "•Revenue growth of 6% to 7%"]
        assert not _is_guidance_next_section_heading(lines, 1), head


def test_next_section_exempts_period_label():
    lines = [
        "Business Outlook",
        "Second Quarter Fiscal 2024",
        "Revenue growth is expected to be 6% to 7% for the quarter.",
    ]
    assert not _is_guidance_next_section_heading(lines, 1)


def test_next_section_exempts_dateline_and_split_dateline():
    lines = [
        "Financial Guidance for Fiscal Year 2026",
        "GOODLETTSVILLE, Tenn.--(BUSINESS WIRE)--",
        "Dollar General Corporation (NYSE: DG) today reported financial results",
    ]
    # The split dateline is not a heading; the joined form matches.
    assert not _is_guidance_next_section_heading(lines, 1)


def test_next_section_exempts_bullet_item_after_lone_marker():
    lines = [
        "Outlook",
        "For 2024, management is anticipating the following:",
        "·",
        "Full year comparable restaurant sales growth in the mid-single digit range",
        "Restaurant level operating margin in the range of 15.5% to 16.5%",
    ]
    assert not _is_guidance_next_section_heading(lines, 3)


def test_next_section_exempts_sentence_case_metric_labels():
    # DUOL's outlook metric sub-headings are sentence-case, not headings.
    for head in ["Bookings and revenue", "Gross margin", "Share count"]:
        lines = [
            "2025 Outlook",
            head,
            "Based on our Q2 results and what we’re seeing so far in the third quarter, we’re raising our full-year bookings guidance",
        ]
        assert not _is_guidance_next_section_heading(lines, 1), head


def test_next_section_exempts_table_headers_and_domain_footer():
    # EQIX's "Prior" column label is followed by a figure row, not prose.
    lines = ["Business Outlook", "2025 Guidance", "(in millions, except per share data)", "Prior", "FY 2025 Guidance Guidance Adjustment Foreign Exchange Impact Revised"]
    assert not _is_guidance_next_section_heading(lines, 3)
    # CCI's "CrownCastle.com" page footer is not a heading.
    lines = ["OUTLOOK", "The pathway to possible.", "CrownCastle.com", "News Release continued: Page 4", "•Additionally, a $15 million decrease in site rental costs"]
    assert not _is_guidance_next_section_heading(lines, 2)


def test_next_section_wrapped_prose_fragment_is_not_a_heading():
    # GIS: a wrapped guidance sentence's first fragment looks heading-shaped
    # but its continuation starts lowercase, so it never breaks.
    lines = [
        "Fiscal 2024 Outlook",
        "General Mills continues to expect the largest",
        "contribution to growth to come from its North America Retail segment.",
    ]
    assert not _is_guidance_next_section_heading(lines, 1)


# --- unit: the anchor ------------------------------------------------------

def test_anchor_attached_footnote_digit_compound_heading():
    assert _is_guidance_heading("Financial Guidance1")
    assert _is_guidance_heading("2023 OUTLOOK2")


def test_anchor_bare_word_plus_digit_is_not_a_heading():
    # Batch 196 supersedes this: a bare word + digit IS a heading when
    # it is the section heading — Cigna's outlook section is headed
    # "OUTLOOK2" (OUTLOOK<sup>2</sup> in the HTML), and the 1,699-
    # exhibit census shows CRM's "Guidance5" column header can never
    # become the anchor (an earlier "Guidance" heading always precedes
    # it). See tests/data/test_filings_batch196.py.
    assert _is_guidance_heading("Guidance5")
    assert _is_guidance_heading("OUTLOOK2")


def test_anchor_quote_fragment_is_not_a_heading():
    assert not _is_guidance_heading("outlook at the start of the year.”")
    assert _is_guidance_heading("Full-year 2026 guidance:")
    assert _is_guidance_heading("Business Outlook")


def test_anchor_wrapped_prose_fragment_stays_an_anchor():
    # GEV's wrapped "guidance of similar segment EBITDA losses to 2025."
    # is the (accidental but working) entry to its segment-outlook section.
    assert _is_guidance_heading("guidance of similar segment EBITDA losses to 2025.")


# --- unit: period labels and the signal gate -------------------------------

def test_period_label_shapes():
    assert _is_guidance_period_label("Second Quarter Fiscal 2024")
    assert _is_guidance_period_label("Q4 FY25")
    assert _is_guidance_period_label("FY25")
    assert _is_guidance_period_label("Full Year Fiscal 2026")
    assert not _is_guidance_period_label("Fiscal 2025 Third Quarter Consolidated Results")
    assert not _is_guidance_period_label("CONSOLIDATED STATEMENTS OF INCOME")


def test_signal_gate_safe_harbor_has_no_signal():
    assert not _guidance_has_signal(
        [
            "OUTLOOK",
            "This Outlook section contains forward-looking statements, and actual results may differ materially.",
        ]
    )
    assert _guidance_has_signal(["Guidance", "•Revenue growth of 6% to 7%"])
    assert _guidance_has_signal(
        ["Guidance", "In the second quarter, Applied expects net revenue to be approximately $6.50 billion."]
    )


# --- end to end: real exhibits ---------------------------------------------

def test_apd_guidance_is_just_the_two_bullets():
    out = _live("APD_2025-09-30")
    assert "Fiscal 2026 full-year adjusted EPS guidance* of $12.85 to $13.15" in out
    assert "Expect fiscal year 2026 capital expenditures* of approximately $4 billion" in out
    assert "Consolidated Results" not in out
    assert "LEHIGH VALLEY" not in out
    assert "Chief Executive Officer Eduardo Menezes said" not in out
    assert "#" not in out and "Certain results" not in out
    assert len(out) < 400


def test_apd_2026_q2_no_footnote_lines_or_more():
    out = _live("APD_2026-03-31")
    assert "Raising fiscal 2026 full-year adjusted EPS guidance*" in out
    assert "# Per share amounts" not in out
    assert "Certain results" not in out
    assert "-more-" not in out


def test_afl_asterisk_pointer_dropped():
    out = _live("AFL_2025-06-30")
    assert "*See Non-U.S. GAAP Financial Measures" not in out


def test_dal_real_guidance_heading_found():
    out = _live("DAL_2024-09-30")
    assert out.startswith("Financial Guidance 1")  # batch 218: footnote key now spaced
    assert "Total Revenue YoY" in out
    assert "$1.60 - $1.85" in out
    assert "Cost Performance" not in out


def test_crm_revenue_table_served():
    out = _live("CRM_2024-10-31")
    assert "Total Revenue" in out
    assert "$9.90 - $10.10 Billion" in out


def test_ci_gained_guidance():
    out = _live("CI_2023-09-30")
    assert "at least $192.0 billion" in out
    assert "at least $24.75 per share" in out


def test_csco_gained_guidance():
    out = _live("CSCO_2024-01-27")
    assert "Cisco expects to achieve the following results for the third quarter of fiscal 2024" in out
    assert "$12.1 billion - $12.3 billion" in out


def test_bmy_table_headers_kept_footnote_rows_dropped():
    out = _live("BMY_2026-06-30")
    assert "2026 WW Revenue Growth*" in out
    assert "(Prior) July" in out or "Total Revenues" in out
    assert "Conference Call Information" not in out


def test_biib_fx_line_kept():
    out = _live("BIIB_2023-12-31")
    assert "This guidance also assumes that foreign exchange rates as of February 9, 2024" in out
    assert "Biogen does not provide guidance for GAAP reported financial measures" in out


def test_carr_guidance_header_not_swallowed_by_footnote_block():
    out = _live("CARR_2025-12-31")
    assert "2026 Guidance" in out
    assert "1 Excludes NORESCO" not in out
    assert "Adjusted EPS* of ~$2.80" in out


def test_axon_call_notice_dropped_definitions_dropped():
    out = _live("AXON_2025-09-30")
    assert "We expect 2025 CapEx to be in the range of $170 million to $180 million" in out
    assert "Quarterly conference call and webcast" not in out
    assert "will host our Q3 2025 earnings conference call" not in out


def test_chd_webcast_notice_dropped():
    out = _live("CHD_2025-06-30")
    assert "will host a webcast" not in out


def test_dg_split_dateline_regained():
    out = _live("DG_2026-05-01")
    assert "Financial Guidance for Fiscal Year 2026" in out


def test_cci_table_survives_restructuring_subsection():
    out = _live("CCI_2023-09-30")
    assert "The following table sets forth Crown Castle's current full year 2023 and 2024 Outlook" in out


# --- repair spot-check: segment-table and Q&A-notice tails ----------------

def test_segment_information_heading_is_a_table_start():
    assert _FINANCIAL_TABLE_START_RE.match("First Quarter Reportable Segment Information")
    assert _FINANCIAL_TABLE_START_RE.match("Fourth Quarter and Fiscal 2025 Reportable Segment Information")
    assert _FINANCIAL_TABLE_START_RE.match("Reportable Segment Information")
    assert not _FINANCIAL_TABLE_START_RE.match("Outlook by Segment")
    assert not _FINANCIAL_TABLE_START_RE.match("Segment Operating Income")


def test_qa_session_notice_regex():
    ln = (
        "General Mills will issue pre-recorded management remarks today, December 17, 2025, "
        "at approximately 6:30 a.m. Central time (7:30 a.m. Eastern time) and will hold a live, "
        "webcasted question and answer session beginning at 8:00 a.m. Central time."
    )
    m = _CALL_QA_SESSION_RE.search(ln)
    assert m is not None and m.start() <= 120
    # The notice's continuation line (no "management") matches too.
    m2 = _CALL_QA_SESSION_RE.search(
        "The pre-recorded remarks and the webcast will be made available at www.generalmills.com/investors."
    )
    assert m2 is not None and m2.start() <= 120
    assert _CALL_QA_SESSION_RE.search("We expect fiscal 2026 adjusted EPS of $5.00 to $5.20.") is None


def test_amat_guidance_stops_before_segment_table():
    out = _live("AMAT_2025-01-26")
    assert "Total net revenue $ 7,100 +/- $ 400" in out
    assert "Non-GAAP diluted EPS $ 2.30 +/- $ 0.18" in out
    assert "Reportable Segment Information" not in out
    assert "Net revenue $ 5,356 $ 4,909" not in out
    assert "Foundry, logic and other" not in out


def test_gis_call_notice_dropped():
    out = _live("GIS_2025-11-23")
    assert "The net impact of divestitures, acquisitions, foreign currency exchange" in out
    assert "pre-recorded" not in out
    assert "webcasted question and answer" not in out
    assert "generalmills.com/investors" not in out


def test_qa_session_tail_pointer_kept():
    # The 120-char start guard: a guidance sentence that merely points
    # at the pre-recorded remarks in its tail (past char 120) is kept,
    # the same shape as Biogen's FX line for the conference-call notice.
    html = (
        "<html><body><p>Business Outlook</p>"
        "<p>We expect fiscal 2026 adjusted EPS of $5.00 to $5.20, with revenue growth of "
        "4% to 6% and operating margin expansion of 50 basis points, and further details on "
        "the outlook will be provided in our pre-recorded remarks.</p>"
        "<p>General Mills will issue pre-recorded management remarks today at 6:30 a.m.</p>"
        "</body></html>"
    )
    out = extract_management_guidance(html)
    assert out is not None
    assert "pre-recorded remarks" in out
    assert "General Mills will issue" not in out
