"""Batch 182: table-section heading/intro leak — the batch-178 blast washes
(GPC segment-label lines, CEG reconciliation intro, CSX header+value line).

Twelve extractor changes, one cluster: a reconciliation table's heading
and its boilerplate intro, a business-segment heading, a split units
declaration, and a split conference-call notice all leak into highlights
as lede lines or section content — and the CEG/EQIX intro + notice tails
inflate a section's financial density, so the wrong section wins the
batch-102 ranking. The last three (8–10) are follow-ons found on the
batch-182 blast's own diffs: freeing the budget past BRO's recon table
exposed its "See information" pointer, its dash-joined adjusted-EPS
header, and Amex's "# # #" separator tail.

1. Reconciliation heading: "GAAP/Adjusted (non-GAAP) Operating Earnings
   Reconciliation" (Constellation, 5 cache quarters), "Reconciliation of
   Commissions and Fees" (Brown & Brown, 7), "Reconciliation of GAAP to
   Non-GAAP Measures1" (CSX). Fix: _is_lede_recon_heading — a heading
   shape carrying "reconcil". It BREAKS Highlights-section collection
   (the table starts where the highlights end) and is SKIPPED in the
   lede loop (not a break — CSX's CEO quote and volume paragraph follow
   its recon table, and a break would lose them).
2. Wrapped recon heading: Brown & Brown splits its heading across two
   lines ("Reconciliation of Commissions and Fees" / "to Organic
   Revenue"). Fix: _is_recon_heading_wrap, consulted only right after a
   skipped recon heading — the position is the evidence.
3. Segment heading: "North America Automotive Parts Group (\"North
   America Automotive\")" (Genuine Parts, 2 cache quarters) is served as
   a dangling lede line when the 6-line budget runs out on it. Fix:
   _is_lede_segment_heading — skipped in the lede loop; the segment
   paragraph below it is real content and is kept, so the freed budget
   serves the paragraph instead.
4. Split units declaration: CSX's recon table heads with "Dollars in
   millions," on one line and "except per share amounts Operating Income
   Operating Margin Net" on the next. Fix: _LEDE_BARE_UNITS_DOLLARS_RE
   (a line that IS just the declaration) and
   _is_lede_split_units_continuation (the "except per share amounts"
   continuation glued to column labels), both wired into
   _is_lede_table_line before the termination gate.
5. Split conference-call notice: CSX's notice splits across two lines —
   the announcement ("CSX executives will conduct a conference call ...
   at 4:30 p.m. ... dialing 1-888-510-2008") carries no webcast/replay,
   and the webcast line ("In conjunction with the call, a live webcast
   ...") carries no "conference call", so the batch-166 regex misses
   both (6 quarters). Fix: _is_lede_call_announcement (future-tense
   scheduling verb + time/dial-in) with its webcast continuation, and
   the same notice shapes break Highlights-section collection — the
   batch-181 carried follow-up (AXP's notice "needs its collection path
   found") was the section collector, which has no notice handling.
6. Report pointer: "This earnings announcement ... is contained in the
   CSX Quarterly Financial Report ..." (CSX, 12 quarters) and "This
   earnings release should be read in conjunction with the company's
   statistical tables ..." (American Express, 12 quarters) are
   document-tail pointers served once the notice above them drops.
   Fix: _is_lede_report_pointer, skipped in the lede loop and filtered
   from Highlights sections.
7. Glued footnote pointer: CSX's recon-table footnote "1See the
   Non-GAAP Measures section ..." has no space after the number and no
   trailing period, so neither the batch-173 pointer regex nor the
   bare-numbered-footnote predicate caught it. Fix: _FOOTNOTE_POINTER_RE
   takes the space as optional (the batch-178 glued-number precedent).
8. Dash-joined table header: Brown & Brown's next table heads with
   "Diluted Net Income Per Share - Adjusted", and _is_lede_table_header
   missed it because the bare "-" token fails the capital-led loop
   ("-".isupper() is False). Fix: pure-punctuation dash tokens are
   skipped in that loop. The AJG "Summary of Financial Results - Third
   Quarter" lines and the ELV dateline (both served, both carrying
   " - ") stay out — neither carries a metric word.
9. "See information" pointer: Brown & Brown closes every recon table
   with "See information regarding non-GAAP measures presented later in
   this press release." (12 quarters, served in 7). Fix: the second
   form of _is_lede_report_pointer, which needs the "presented later in
   this press release" tail — a bare "See information regarding X"
   without it is not a pointer.
10. Hash separator: Amex flattens its "###" end-of-release marker as
    the line "# # #" (5 quarters), the tail of every Amex highlights
    block. Fix: _RULE_LINE_RE takes a second alternative — a line of
    nothing but "#" (spaced or not) — stripped by the final-assembly
    filter for both paths.

Still open after this batch: BRO's live still ends with two table-row
label lines ("Diluted net income per share", "Change in estimated
acquisition earn-out payables") — orphaned labels whose $-value rows
the fragment-run dropper already ate, so the label predicate cannot see
them. Fixing them in the dropper exposes the definitions prose and the
"###" tail, so it needs a combined fix in a future batch.

The pin is behavioral: on stashed old code the new predicates do not
exist (collection error) and the end-to-end tests serve the defect
lines / lose the quote and the segment paragraph.
"""
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _FOOTNOTE_POINTER_RE,
    _LEDE_BARE_UNITS_DOLLARS_RE,
    _RULE_LINE_RE,
    _extract_highlights_sections,
    _is_lede_call_announcement,
    _is_lede_recon_heading,
    _is_lede_report_pointer,
    _is_lede_segment_heading,
    _is_lede_split_units_continuation,
    _is_lede_table_header,
    _is_lede_table_line,
    _is_lede_webcast_continuation,
    _is_recon_heading_wrap,
    _opens_footnote_def,
    extract_press_release_highlights,
)

CEG_HEADING = "GAAP/Adjusted (non-GAAP) Operating Earnings Reconciliation"
CEG_HEADING_EBITDA = "GAAP/Adjusted EBITDA (non-GAAP) Reconciliation"
BRO_HEADING = "Reconciliation of Commissions and Fees"
CSX_HEADING = "Reconciliation of GAAP to Non-GAAP Measures1"
CEG_INTRO = (
    "Unless otherwise noted, the income tax impact of each reconciling "
    "adjustment between GAAP Net Income (Loss) Attributable to Common "
    "Shareholders and Adjusted (non-GAAP) Operating Earnings is based on "
    "the marginal statutory federal and state income tax rates, taking "
    "into account whether the income or expense item is taxable or "
    "deductible, respectively, in whole or in part."
)
GPC_SEGMENT = 'North America Automotive Parts Group ("North America Automotive")'
GPC_SEGMENT_SHORT = 'Automotive Parts Group ("Automotive")'
CSX_NOTICE = (
    "CSX executives will conduct a conference call with the investment "
    "community this afternoon, October 16, at 4:30 p.m. Eastern Time. "
    "Investors, media and the public may listen to the conference call "
    "by dialing 1-888-510-2008. For callers outside the U.S., dial "
    "1-646-960-0306. Participants should dial in 10 minutes prior to "
    "the call and enter 3368220 as the passcode."
)
CSX_WEBCAST = (
    "In conjunction with the call, a live webcast will be accessible and "
    "presentation materials will be posted on the company's website at "
    "http://investors.csx.com. Following the earnings call, a webcast "
    "replay of the presentation will be archived on the company website."
)
CSX_POINTER = (
    "This earnings announcement, as well as additional detailed financial "
    "information, is contained in the CSX Quarterly Financial Report "
    "available through the company's website at http://investors.csx.com "
    "and on Form 8-K with the Securities and Exchange Commission."
)
AXP_POINTER = (
    "This earnings release should be read in conjunction with the "
    "company's statistical tables for the second quarter 2025, which "
    "include information regarding our reportable operating segments, "
    "available on the American Express Investor Relations website at "
    "http://ir.americanexpress.com and in a Form 8-K furnished today "
    "with the Securities and Exchange Commission."
)


def test_recon_heading_attested_lines():
    assert _is_lede_recon_heading(CEG_HEADING)
    assert _is_lede_recon_heading(CEG_HEADING_EBITDA)
    assert _is_lede_recon_heading(BRO_HEADING)
    assert _is_lede_recon_heading(CSX_HEADING)
    assert _is_lede_recon_heading("Non-GAAP Reconciliations")
    assert _is_lede_recon_heading("Guidance Reconciliation")
    # A prose mention is terminated, so it never qualifies.
    assert not _is_lede_recon_heading(
        "Please see a reconciliation of GAAP to non-GAAP financial "
        "measures in the appendix on pages 12 and 13."
    )
    assert not _is_lede_recon_heading(
        "A reconciliation of non-GAAP financial measures to the most "
        "directly comparable GAAP measures is provided at the end of "
        "this release."
    )
    # A sub-headline naming a reconciliation is kept by the verb veto.
    assert not _is_lede_recon_heading(
        "Company Provides Reconciliation of Non-GAAP Measures"
    )
    # A colon-ended table caption is terminated, so it never qualifies.
    assert not _is_lede_recon_heading(
        "Reconciliation of NOI of consolidated entities:"
    )
    assert not _is_lede_recon_heading(
        "Reconciliations (continued) (dollars in millions):"
    )
    # A bullet is narrative, never a heading.
    assert not _is_lede_recon_heading(
        "•Reconciliation of GAAP to Non-GAAP Measures"
    )
    # A long prose line carrying the word is not heading-shaped.
    assert not _is_lede_recon_heading(
        "Reconciliation of the company's non-GAAP financial measures to "
        "their most directly comparable GAAP measures has been provided "
        "in the tables below for reference by investors."
    )
    # A lowercase-worded heading ("Reconciliation of net income
    # attributable to Eaton ordinary shareholders" — raw HTML only,
    # never served in live) stays out: the capital-led guard is what
    # keeps a prose fragment out, and the shape is unattested in live.
    assert not _is_lede_recon_heading(
        "Reconciliation of net income attributable to Eaton ordinary shareholders"
    )


def test_recon_heading_wrap_attested_lines():
    assert _is_recon_heading_wrap("to Organic Revenue")
    # A capital-led line is a new heading, not a wrap tail.
    assert not _is_recon_heading_wrap("Organic Revenue")
    assert not _is_recon_heading_wrap(
        "The table below provides a reconciliation of GAAP Net Income"
    )
    # A terminated line is a sentence, not a wrap tail.
    assert not _is_recon_heading_wrap("to Organic Revenue.")
    # A figure-carrying line is a data row, not a wrap tail.
    assert not _is_recon_heading_wrap("to $1.2 billion in revenue")


def test_segment_heading_attested_lines():
    assert _is_lede_segment_heading(GPC_SEGMENT)
    assert _is_lede_segment_heading(GPC_SEGMENT_SHORT)
    assert _is_lede_segment_heading(
        'International Automotive Parts Group ("International Automotive")'
    )
    # Terminated prose mentioning a segment is content, not a heading.
    assert not _is_lede_segment_heading(
        'The Automotive Parts Group ("Automotive") reported sales of '
        "$2.4 billion."
    )
    # A lowercase-led line is a wrap fragment, not a heading.
    assert not _is_lede_segment_heading(
        'automotive parts group ("Automotive")'
    )
    # No parenthesized alias, no heading signature.
    assert not _is_lede_segment_heading("North America Automotive Parts Group")
    # A $ figure means a value line, not a heading.
    assert not _is_lede_segment_heading(
        'North America Automotive Parts Group ("North America Automotive") $2.4 billion'
    )


def test_split_units_continuation_attested_lines():
    assert _is_lede_split_units_continuation(
        "except per share amounts Operating Income Operating Margin Net"
    )
    # The bare continuation without column labels is not this shape.
    assert not _is_lede_split_units_continuation("except per share amounts")
    # A prose fragment starting "except ..." carries no metric word.
    assert not _is_lede_split_units_continuation(
        "except per share amounts were higher in the quarter."
    )
    # The units line itself is the other predicate's job.
    assert not _is_lede_split_units_continuation("Dollars in millions,")


def test_bare_units_dollars_attested_lines():
    assert _LEDE_BARE_UNITS_DOLLARS_RE.match("Dollars in millions,")
    assert _LEDE_BARE_UNITS_DOLLARS_RE.match("Dollars in millions")
    assert _LEDE_BARE_UNITS_DOLLARS_RE.match("Dollar in billions,")
    assert _is_lede_table_line("Dollars in millions,")
    # The "except" tail belongs to the older bare-units regex, not this one.
    assert not _LEDE_BARE_UNITS_DOLLARS_RE.match(
        "Dollars in millions, except per share data"
    )
    # A prose sentence that merely opens with the words is not a bare line.
    assert not _LEDE_BARE_UNITS_DOLLARS_RE.match(
        "Dollars in millions were up 10% in the quarter."
    )
    assert not _LEDE_BARE_UNITS_DOLLARS_RE.match("In millions, except per share data")


def test_call_announcement_attested_lines():
    assert _is_lede_call_announcement(CSX_NOTICE)
    # A prose mention of a past call has no scheduling verb or time.
    assert not _is_lede_call_announcement(
        "we discussed the results on the conference call"
    )
    # "will be held" is not one of the scheduling verbs — Amex's line is
    # the batch-166 regex's job (it carries "replay" on the same line).
    assert not _is_lede_call_announcement(
        "An investor conference call will be held at 8:30 a.m. (ET) today "
        "to discuss second-quarter results."
    )
    # A bare heading-shaped announcement has no time or dial-in, so it
    # stays for the conf-call-heading guard's kept announcements.
    assert not _is_lede_call_announcement(
        "Company to Host Conference Call to Discuss Q3 Results"
    )
    # A scheduling verb with no time or dial-in is not a notice line.
    assert not _is_lede_call_announcement(
        "Management will host a conference call tomorrow to discuss the quarter."
    )


def test_webcast_continuation_attested_lines():
    assert _is_lede_webcast_continuation(CSX_WEBCAST)
    assert not _is_lede_webcast_continuation(
        "A replay of the call will be available one hour after the call."
    )
    assert not _is_lede_webcast_continuation(
        "In conjunction with the call, management raised guidance."
    )


def test_report_pointer_attested_lines():
    assert _is_lede_report_pointer(CSX_POINTER)
    assert _is_lede_report_pointer(AXP_POINTER)
    # The opener is load-bearing: a mid-paragraph "should be read"
    # (Charter) never qualifies.
    assert not _is_lede_report_pointer(
        "The information in this press release should be read in "
        "conjunction with the financial statements and footnotes."
    )
    # A highlights sentence opening the same way but pointing nowhere.
    assert not _is_lede_report_pointer(
        "This earnings announcement includes a reconciliation of GAAP measures."
    )
    assert not _is_lede_report_pointer(
        "This press release contains forward-looking statements."
    )


BRO_POINTER = (
    "See information regarding non-GAAP measures presented later in "
    "this press release."
)


def test_table_header_dash_token_attested_lines():
    assert _is_lede_table_header("Diluted Net Income Per Share - Adjusted")
    # Without the qualifier there is no repeat and no qualifier, so the
    # bare label is not a header by this predicate.
    assert not _is_lede_table_header("Diluted Net Income Per Share")
    assert _is_lede_table_header("Adjusted EBITDA - Reconciliation")
    # AJG's section heading carries " - " but no metric word.
    assert not _is_lede_table_header(
        "Summary of Financial Results - Third Quarter"
    )
    assert not _is_lede_table_header(
        "Summary of Financial Results - Nine Months"
    )
    # The ELV dateline carries " - " and a year but no metric word.
    assert not _is_lede_table_header(
        "Indianapolis, IN - October 21, 2025 - Elevance"
    )
    # A headline with a verb is a sub-headline, not a column header.
    assert not _is_lede_table_header("Revenue Growth - Exceeds Expectations")


def test_report_pointer_see_information_form():
    assert _is_lede_report_pointer(BRO_POINTER)
    # Without the "presented later in this press release" tail it is
    # not a pointer — it could be a real cross-reference sentence.
    assert not _is_lede_report_pointer(
        "See information regarding the dividend on our investor website."
    )
    # A bare "See ..." sentence is not this form either.
    assert not _is_lede_report_pointer(
        "See the Non-GAAP Measures section for additional information."
    )


def test_hash_rule_line_attested_lines():
    assert _RULE_LINE_RE.match("# # #")
    assert _RULE_LINE_RE.match("###")
    assert _RULE_LINE_RE.match("# ## #")
    # The underscore rule still matches.
    assert _RULE_LINE_RE.match("____________________________________")
    # A prose line that merely contains "#" is not a rule line.
    assert not _RULE_LINE_RE.match(
        "American Express ranked #4 on the 2025 Best Companies list."
    )
    assert not _RULE_LINE_RE.match("#1 in customer satisfaction")


def test_footnote_pointer_glued_form():
    assert _FOOTNOTE_POINTER_RE.match(
        "1See the Non-GAAP Measures section of the quarterly financial "
        "report for additional information"
    )
    assert _FOOTNOTE_POINTER_RE.match(
        "1Refer to previously defined adjusted earnings."
    )
    # The spaced form still matches.
    assert _FOOTNOTE_POINTER_RE.match("1 See Table A for the reconciliation.")
    assert _FOOTNOTE_POINTER_RE.match("2) Refer to the notes below.")
    # A digit glued to anything but See/Refer to is not a pointer.
    assert not _FOOTNOTE_POINTER_RE.match("3M reports third-quarter results.")
    assert not _FOOTNOTE_POINTER_RE.match(
        "12 million shares were repurchased in the quarter."
    )
    # The glued pointer opens a footnote block (the CSX "1See" line is
    # unterminated, so the bare-numbered predicate alone misses it).
    assert _opens_footnote_def(
        "1See the Non-GAAP Measures section of the quarterly financial "
        "report for additional information",
        "About CSX and its Disclosures",
    )


def _extract(body_lines):
    body = "".join(f"<p>{ln}</p>" for ln in body_lines)
    return extract_press_release_highlights(
        f"<html><body>{body}<h2>About Acme</h2><p>Boilerplate.</p></body></html>"
    )


def test_ceg_style_section_ends_at_recon_heading():
    out = _extract(
        [
            "Constellation Reports Third Quarter 2024 Results",
            "Baltimore (Nov. 4, 2024) — Constellation Energy Corporation (Nasdaq: CEG) today reported its financial results for the third quarter of 2024.",
            "Recent Developments and Third Quarter Highlights",
            "•Announcing Crane Clean Energy Center: During the third quarter of 2024, we executed a 20-year PPA with Microsoft that will support the restart of Three Mile Island Unit 1, renamed as the Crane Clean Energy Center, which was retired in 2019 for economic reasons.",
            "•Nuclear Operations: Our nuclear fleet produced 45,510 gigawatt-hours (GWhs) in the third quarter of 2024, compared with 44,125 GWhs in the third quarter of 2023, and achieved a 95.0% capacity factor for the quarter.",
            "•Natural Gas, Oil, and Renewables Operations: The dispatch match rate for our fleet was 98.2% in the third quarter of 2024, compared with 98.5% in the third quarter of 2023.",
            CEG_HEADING,
            CEG_INTRO,
            "(In millions, except per share data)",
            "Three Months Ended September 30, 2024 Earnings Per Share(1)",
            "GAAP Net Income (Loss) Attributable to Common Shareholders $ 1,200 $ 3.82",
        ]
    )
    assert out is not None
    assert "Announcing Crane Clean Energy Center" in out
    assert "Nuclear Operations" in out
    assert "Natural Gas, Oil, and Renewables Operations" in out
    # The recon heading and its tax boilerplate never enter.
    assert "Operating Earnings Reconciliation" not in out
    assert "income tax impact of each reconciling adjustment" not in out
    assert "(In millions, except per share data)" not in out
    assert "GAAP Net Income (Loss) Attributable to Common Shareholders $ 1,200" not in out


def test_bro_style_lede_drops_recon_heading_and_wrap():
    out = _extract(
        [
            "Brown & Brown, Inc. announces first quarter 2024 results, including total revenues of $1,258 million, an increase of 12.7%; Organic Revenue growth of 8.6%; diluted net income per share of $1.02; Diluted Net Income Per Share - Adjusted of $1.14; and a quarterly dividend of $0.13 per share",
            "DAYTONA BEACH, Fla., April 22, 2024 - Brown & Brown, Inc. (NYSE:BRO) (the \"Company\") announced its unaudited financial results for the first quarter of 2024.",
            "Revenues for the first quarter of 2024 under U.S. generally accepted accounting principles (\"GAAP\") were $1,258 million, increasing $142 million, or 12.7%, compared to the first quarter of the prior year, with commissions and fees increasing by 11.6% and Organic Revenue increasing by 8.6%.",
            "J. Powell Brown, President and Chief Executive Officer of the Company, noted, “Our teammates delivered strong organic revenue growth and margin expansion in the first quarter of 2024. We are very pleased with the start of the year.”",
            "In addition, the Company today announced that the Board of Directors has declared a regular quarterly cash dividend of $0.13 per share. The dividend is payable on May 15, 2024, to shareholders of record on May 6, 2024.",
            BRO_HEADING,
            "to Organic Revenue",
            "(in millions, unaudited)",
            "Three Months Ended March 31,",
            "2024",
            "Commissions and fees",
            "$",
            "1,237",
        ]
    )
    assert out is not None
    assert "Reconciliation of Commissions and Fees" not in out
    assert "to Organic Revenue" not in out
    assert "(in millions, unaudited)" not in out
    # The prose and the quote stay.
    assert "Revenues for the first quarter of 2024" in out
    assert "Our teammates delivered strong organic revenue growth" in out
    assert "regular quarterly cash dividend of $0.13 per share" in out


def test_csx_style_lede_drops_recon_table_and_serves_quote():
    out = _extract(
        [
            "CSX Corp. Announces Third Quarter 2025 Results",
            "JACKSONVILLE, Fla. – October 16, 2025 – CSX Corp. (NASDAQ: CSX) today announced third quarter operating income of $1.09 billion and net earnings of $694 million, or $0.37 per share.",
            "In the quarter, adjusted operating income and adjusted earnings per share included $35 million and $0.01, respectively, in corporate restructuring, severance, and advisory expenses.",
            CSX_HEADING,
            "For the Quarter ended Sept. 30, 2025",
            "Dollars in millions,",
            "except per share amounts Operating Income Operating Margin Net",
            "Earnings Net Earnings Per Share, Assuming Dilution",
            "GAAP Operating Results $ 1,087",
            "30.3% $ 694",
            "$ 0.37",
            "Goodwill Impairment 164 4.6% 124 0.07",
            "Adjusted Operating Results (Non-GAAP) $ 1,251",
            "“This quarter’s operational performance reflects the dedication of our workforce and our commitment to running the best railroad in North America,” said President and Chief Executive Officer Steve Angel. “We are proud that the network is operating well, and we see clear opportunities to leverage that operational strength moving forward.”",
            "Volume totaled 1.61 million units for the quarter, up 1% compared to third quarter 2024 and up 2% sequentially. Revenue totaled $3.59 billion for the quarter, decreasing 1% year-over-year.",
            CSX_NOTICE,
            CSX_WEBCAST,
            CSX_POINTER,
            "1See the Non-GAAP Measures section of the quarterly financial report for additional information",
        ]
    )
    assert out is not None
    # The recon heading, units lines and header fragment are gone.
    assert "Reconciliation of GAAP to Non-GAAP Measures" not in out
    assert "Dollars in millions," not in out
    assert "except per share amounts Operating Income" not in out
    assert "GAAP Operating Results $ 1,087" not in out
    # The notice pair, the pointer and the glued footnote are gone.
    assert "will conduct a conference call" not in out
    assert "In conjunction with the call" not in out
    assert "is contained in the CSX Quarterly Financial Report" not in out
    assert "1See the Non-GAAP Measures section" not in out
    # The quote and the volume paragraph survive the table — the heading
    # is a skip, not a break.
    assert "operational performance reflects the dedication" in out
    assert "Volume totaled 1.61 million units" in out


def test_gpc_style_segment_heading_dropped_and_paragraph_served():
    out = _extract(
        [
            "Genuine Parts Company Reports First Quarter 2026 Results and Reaffirms Full-Year Outlook",
            "ATLANTA -- Genuine Parts Company (NYSE: GPC), a leading global service provider of automotive and industrial replacement parts and value-added solutions, announced today its results for the first quarter ended March 31, 2026.",
            "“The GPC team delivered first quarter results ahead of expectations, driven by solid sales growth and operating discipline across our business segments,\" said Will Stengel, Chair-Elect and Chief Executive Officer.",
            "Sales were $6.3 billion, a 6.8% increase compared to $5.9 billion in the same period of the prior year. The improvement is attributable to a 2.4% increase in comparable sales, a 1.3% benefit from acquisitions and a net 3.1% favorable impact of foreign currency and other.",
            "Net income was $189 million, or $1.37 per diluted earnings per share. This compares to net income of $194 million, or $1.40 per diluted share in the prior year period.",
            GPC_SEGMENT,
            "North America Automotive sales were $2.4 billion, up 4.3% from the same period in 2025. The improvement is attributable to a 2.2% increase in comparable sales, a 1.6% benefit from acquisitions and a net 0.5% favorable impact of foreign currency and other. Segment EBITDA of $156 million increased 6.3%, with segment EBITDA margin of 6.6%, up 10 basis points from the same period of the prior year.",
        ]
    )
    assert out is not None
    # The heading is gone but its paragraph is served.
    assert GPC_SEGMENT not in out
    assert "North America Automotive sales were $2.4 billion" in out
    assert "Segment EBITDA of $156 million increased 6.3%" in out


def test_section_collector_breaks_at_call_notice():
    # Direct collector test (EQIX): the notice heading ends the section
    # instead of being collected as content, so the section keeps its
    # financial density and wins the ranking.
    sections = _extract_highlights_sections(
        [
            "Business Highlights",
            "•Delivered $378 million of annualized gross bookings and record annualized presales of approximately $140 million.",
            "•Approximately 60% of the company’s largest deals were AI-related.",
            "Q1 2026 Results Conference Call and Replay Information",
            "Equinix will discuss its quarterly results for the period ended March 31, 2026, along with its future outlook.",
            "A replay of the call will be available one hour after the call through Tuesday, June 30, 2026.",
        ]
    )
    assert len(sections) == 1
    assert len(sections[0]) == 2
    assert "Delivered $378 million" in sections[0][0]
    assert "60% of the company’s largest deals" in sections[0][1]


def test_axp_style_section_drops_pointer_and_notice():
    out = _extract(
        [
            "American Express Reports Second-Quarter 2025 Results",
            "NEW YORK, July 18, 2025 - American Express Company (NYSE: AXP) today reported second-quarter 2025 earnings.",
            "Second-Quarter 2025 Highlights",
            "•Total revenues net of interest expense of $17.3 billion, up 9 percent from a year ago.",
            "•Net income of $2.9 billion, or $4.08 per share, compared with net income of $3.0 billion, or $4.15 per share, a year ago.",
            "•Card Member spending growth accelerated to 8 percent on an FX-adjusted basis.",
            AXP_POINTER,
            "An investor conference call will be held at 8:30 a.m. (ET) today to discuss second-quarter results. Live audio and presentation slides for the investor conference call will be available to the general public on the above-mentioned American Express Investor Relations website. A replay of the conference call will be available later today at the same website address.",
        ]
    )
    assert out is not None
    assert "Total revenues net of interest expense of $17.3 billion" in out
    assert "Net income of $2.9 billion" in out
    assert "Card Member spending growth accelerated" in out
    assert "should be read in conjunction with" not in out
    assert "investor conference call will be held" not in out
