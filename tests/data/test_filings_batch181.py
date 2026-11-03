"""Batch 181: the Emerson lede residue swap (batch-178 wash).

Eight extractor changes, one cluster: batch 178 freed lede budget by
dropping table residue, and the loop then reached deeper into
Emerson's releases — where it served guidance-table rows and an
investor-conference notice, dropped the guidance paragraph the
table-intro rule over-matched, and orphaned a CEO quote at a split
attribution. Live was WORSE than stored on four EMR quarters:

1. Table-intro with prose continuation: the batch-156 branch dropped
   any line containing "following table summarizes", including the
   Q3 FY2025 guidance paragraph whose first sentence is the intro
   and the rest is real guidance prose ("Net and underlying sales
   guidance of ~3.5% ... GAAP EPS is now expected to be ~$4.08 ...").
   Fix: _is_table_intro_only — only when the intro sentence IS the
   line. The batch-157 trailing rule already knew this ("Emerson's
   guidance paragraph ... must never be dropped") but only applied at
   the tail.
2. Single-value guidance-table rows: "Operating Cash Flow ~$3.6B",
   "Free Cash Flow ~$3.2B", "Discrete taxes related to AspenTech
   transaction $0.09", "IEEPA tariff refunds - ~($0.11)" carry one $
   figure, so the data-row predicate (2 figures) never caught them.
   Fix: _is_lede_single_value_row, with the verb + "to" guards that
   keep wrapped summary lines ("FULL-YEAR EARNINGS PER SHARE
   INCREASED 14% TO $11.21").
3. Split quote attribution at the budget: the Q4 FY2024 quote's
   attribution wraps ("...said Emerson President and Chief Executive
   Officer" / "Lal Karsanbhai. "We have done..."), so the finish rule
   read the role line as a complete item and broke, orphaning the
   quote's second half. Fix: _is_lede_split_quote_attribution as a
   third finish-item trigger, plus _lede_quote_is_open suppressing
   the sentence-terminated break while the quote is still open (the
   quote's third sentence follows a terminated second sentence).
4. Investor-conference notice: "will hold/host an investor
   conference on Nov. 20 ..." has no "conference call", so the
   batch-166 notice regex never fired. Fix: _INVESTOR_CONFERENCE_
   NOTICE_RE, plus _is_lede_conf_call_heading for the "Conference
   Call and Upcoming Events" section heading above it.
5. Table-header gaps: "Adjusted Segment EBITA4" is 3 words (floor
   was 4) with the digit glued to the metric (EBITA not in the
   metric list, and the metric regex needed a word boundary after
   it); FICO's "Fourth Quarter Fiscal 2024 GAAP Revenue" carries a
   bare year the capital-led check rejected. Fix: EBITA/EBIT in the
   metric regex with an optional footnote digit, 3-word floor, and
   bare-year transparency.

Three blast-review follow-ons (the first blast's 41 diffs, 1,699
exhibits): the new predicate over-fired on prose summary lines and
under-fired on two residue shapes the freed budget exposed:

6. The single-value predicate dropped wrapped summary lines whose
   label ends in a preposition ("Adjusted* Diluted EPS of $2.58",
   Citi's "BOOK VALUE PER SHARE OF $99.08", Duke's "reported and
   adjusted EPS of $1.44") — a table-row label ends in a noun, never
   a preposition. Fix: the last-word guard is now {"to", "of"}
   ("at"/"for" have zero attested candidates, so they stay out).
7. CSX's recon-table EPS cell "$ 0.44" survived as a lone bare
   value once the row above it dropped — a residue swap, not a fix.
   Fix: _BARE_CELL_RE now matches a lone $ amount ("$ 0.44",
   "$ 1,251", "$(502)"); a metric value carries a scale word or
   suffix ("$50.2 billion", "$1.2B"), which the number-only class
   never matches, so the batch-157 lone-value rule is untouched.
8. Emerson's 699-char Copeland footnote survived as the tail once
   the guidance rows dropped — the bare-numbered-footnote 500-char
   cap predates the evidence. Fix: cap 500 -> 1000 (attested
   footnotes run to 984 chars; above 1000 the population is
   dominated by page/table mega-lines, so the cap stays there).

The pin is behavioral: on stashed old code the new predicates do not
exist (collection error) and the end-to-end tests serve the defect
lines / drop the quote.
"""
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _INVESTOR_CONFERENCE_NOTICE_RE,
    _is_bare_numbered_footnote,
    _is_lede_conf_call_heading,
    _is_lede_single_value_row,
    _is_lede_split_quote_attribution,
    _is_lede_table_header,
    _is_lede_table_line,
    _is_table_intro_only,
    _lede_quote_is_open,
    _looks_like_table_cell,
    extract_press_release_highlights,
)

EMR_GUIDANCE_PARA = (
    "The following table summarizes the fiscal year 2025 guidance "
    "framework. Net and underlying sales guidance of ~3.5% growth "
    "reflects our updated expectations for pricing actions as the "
    "tariff expense exposure has reduced. GAAP EPS is now expected to "
    "be ~$4.08 and adjusted EPS guidance is now ~$6.00, an increase "
    "versus the previous midpoint."
)
EMR_INTRO_ONLY = (
    "The following table summarizes the fiscal year 2025 guidance framework."
)
CIGNA_INTRO_UNTERMINATED = (
    "The following table summarizes The Cigna Group's medical customers"
)


def test_table_intro_only_attested_lines():
    # The Emerson guidance paragraph opens with the intro but continues
    # with real prose — it is content, not residue.
    assert not _is_table_intro_only(EMR_GUIDANCE_PARA)
    assert not _is_lede_table_line(EMR_GUIDANCE_PARA)
    # A standalone intro sentence is still table residue.
    assert _is_table_intro_only(EMR_INTRO_ONLY)
    assert _is_lede_table_line(EMR_INTRO_ONLY)
    # An unterminated single sentence is still just the intro.
    assert _is_table_intro_only(CIGNA_INTRO_UNTERMINATED)
    assert _is_lede_table_line(CIGNA_INTRO_UNTERMINATED)
    # "sets forth" was never a table intro (Crown Castle) — untouched.
    assert not _is_table_intro_only(
        "The following table sets forth Crown Castle's current full "
        "year 2026 Outlook, which includes a $40 million decrease."
    )


def test_single_value_row_attested_rows():
    assert _is_lede_single_value_row("Operating Cash Flow ~$3.6B")
    assert _is_lede_single_value_row("Free Cash Flow ~$3.2B")
    assert _is_lede_single_value_row(
        "Discrete taxes related to AspenTech transaction $0.09"
    )
    assert _is_lede_single_value_row("IEEPA tariff refunds - ~($0.11)")
    assert _is_lede_single_value_row(
        "Net cash provided by operating activities $ 3,803"
    )
    assert _is_lede_single_value_row("Free cash flow $ 1,806")
    assert _is_lede_single_value_row("Net debt $ 30,673")
    assert _is_lede_single_value_row("Other income/(expense) ~$250M")
    for row in (
        "Operating Cash Flow ~$3.6B",
        "Discrete taxes related to AspenTech transaction $0.09",
    ):
        assert _is_lede_table_line(row)


def test_single_value_row_keeps_summary_lines_and_prose():
    # Wrapped summary lines end in a bare $ figure too — the verb and
    # "to" guards are what keep them.
    assert not _is_lede_single_value_row(
        "FULL-YEAR EARNINGS PER SHARE INCREASED 14% TO $11.21"
    )
    assert not _is_lede_single_value_row("GAAP Diluted EPS Increased 2% to $1.13")
    assert not _is_lede_single_value_row(
        "quarter 2023 represents enterprise selling, general and "
        "administrative expenses of $3,788"
    )
    assert not _is_lede_single_value_row("given product generated $100")
    assert not _is_lede_single_value_row(
        "(B)Unrealized gain attributable to noncontrolling partners was $25.2"
    )
    # A lone value is a metric value, not a row (batch-157 rule).
    assert not _is_lede_single_value_row("$50.2 billion")
    # A bullet is narrative, never a table row.
    assert not _is_lede_single_value_row("•Adjusted EPS* of ~$2.80")
    # Terminated prose is never a table row.
    assert not _is_lede_single_value_row(
        "Net income for the quarter totaled $135.7 million."
    )
    # A $ figure with a scale word is prose, not a bare value; and a
    # wrapped prose fragment ending in a bare $ figure is kept by the
    # verb guard ("totaled").
    assert not _is_lede_single_value_row(
        "Net income for the quarter totaled $135.7"
    )
    assert not _is_lede_single_value_row(
        "Net income for the quarter totaled $135.7 million, or $5.44"
    )
    # The "of" guard: a table-row label ends in a noun, never a
    # preposition — these are wrapped summary lines, not rows (BBY,
    # Citi, Duke, Dollar General; 140 attested "of" candidates, every
    # one sampled a prose summary line).
    assert not _is_lede_single_value_row("Adjusted* Diluted EPS of $2.58")
    assert not _is_lede_single_value_row("BOOK VALUE PER SHARE OF $99.08")
    assert not _is_lede_single_value_row(
        "TANGIBLE BOOK VALUE PER SHARE OF $86.67(4)"
    )
    assert not _is_lede_single_value_row(
        "▪First-quarter 2024 reported and adjusted EPS of $1.44"
    )
    assert not _is_lede_single_value_row(
        "The Company reported net income of $374.2"
    )
    assert not _is_lede_single_value_row(
        "Board of Directors Declares Quarterly Cash Dividend of $0.59"
    )


def test_split_attribution_attested_lines():
    assert _is_lede_split_quote_attribution(
        "their commitment and passion which were integral to delivering "
        "these results,\" said Emerson President and Chief Executive Officer"
    )
    assert _is_lede_split_quote_attribution(
        '"We delivered a record quarter," said Jane Smith, President'
    ) is False  # a comma follows the name: complete attribution
    # A complete attribution names the speaker on the same line.
    assert not _is_lede_split_quote_attribution(
        '"Great quarter," said Jane Smith, President and Chief Executive Officer.'
    )
    assert not _is_lede_split_quote_attribution(
        '"Great quarter," said Jane Smith, CEO.'
    )
    # A bare role line has no verb; a prose line ending in a role word
    # without a quote verb is not an attribution either.
    assert not _is_lede_split_quote_attribution(
        "President and Chief Executive Officer"
    )
    assert not _is_lede_split_quote_attribution(
        "Emerson President and Chief Executive Officer"
    )
    # Chair-Elect and Chairman variants of the same shape (name-less
    # role attribution — the speaker's name sits on the next line).
    assert _is_lede_split_quote_attribution(
        '"Solid results," said the Chair-Elect and Chief Executive Officer'
    )
    assert _is_lede_split_quote_attribution(
        '"Solid results," commented the Chairman and Chief Financial Officer'
    )


def test_quote_open_balance():
    assert _lede_quote_is_open(['"Emerson completed an outstanding fiscal 2024,'])
    assert not _lede_quote_is_open(
        ['"Emerson completed an outstanding fiscal 2024," said the CEO.']
    )
    assert _lede_quote_is_open(["“Constellation delivered another strong quarter,"])
    assert not _lede_quote_is_open(
        ["“Constellation delivered another strong quarter,” said Joe."]
    )
    assert not _lede_quote_is_open(["No quotes here at all."])


def test_investor_conference_notice_attested_lines():
    assert _INVESTOR_CONFERENCE_NOTICE_RE.search(
        "Emerson will hold an in-person and virtual investor conference "
        "on Thursday, Nov. 20 in New York City. A live webcast of the "
        "investor conference will begin at 8:00 a.m. Central Time."
    )
    assert _INVESTOR_CONFERENCE_NOTICE_RE.search(
        "Emerson also announces it will host an investor conference on "
        "Nov. 20, 2025 in New York City. Event details will be "
        "distributed closer to this date."
    )
    # A conference CALL notice is the batch-166 regex's job, not this one.
    assert not _INVESTOR_CONFERENCE_NOTICE_RE.search(
        "Emerson management will discuss the third quarter results "
        "during an investor conference call. Participants can access a "
        "live webcast at https://ir.emerson.com at the time of the call."
    )
    # A passing mention of an investor conference is not a notice.
    assert not _INVESTOR_CONFERENCE_NOTICE_RE.search(
        "We presented at the investor conference last month."
    )


def test_conf_call_heading_attested_lines():
    assert _is_lede_conf_call_heading("Conference Call and Upcoming Events")
    assert _is_lede_conf_call_heading("Webcast and Conference Calls")
    # An announcement names the quarter/results — kept, not skipped.
    assert not _is_lede_conf_call_heading(
        "Company to Host Conference Call to Discuss Q3 Results"
    )
    assert not _is_lede_conf_call_heading(
        "Fourth Quarter Fiscal 2024 GAAP Results"
    )
    # A scheduling notice with no quarter/results reference is a
    # section heading, not a results announcement.
    assert _is_lede_conf_call_heading(
        "Conference Call Scheduled for Thursday Morning"
    )
    assert _is_lede_conf_call_heading("Conference Call")


def test_table_header_ebita_and_year_lines():
    assert _is_lede_table_header("Adjusted Segment EBITA4")
    assert _is_lede_table_header("Adjusted Earnings Per Share5")
    assert _is_lede_table_header("Fourth Quarter Fiscal 2024 GAAP Revenue")
    assert _is_lede_table_header("MCO Diluted EPS MCO Adjusted Diluted EPS2")
    # "Results" is not a metric word — the GAAP Results heading stays
    # (carried: whether the first-section heading should drop is a
    # separate judgment from the GAAP Revenue wash).
    assert not _is_lede_table_header("Fourth Quarter Fiscal 2024 GAAP Results")
    # Sub-headlines keep their verb veto.
    assert not _is_lede_table_header(
        "Q2 ORGANIC SALES AND ADJUSTED EPS EXCEED OUTLOOK"
    )
    assert not _is_lede_table_header(
        "COMPANY MAINTAINS FULL-YEAR REVENUE AND EPS GUIDANCE"
    )


def _extract(body_lines):
    body = "".join(f"<p>{ln}</p>" for ln in body_lines)
    return extract_press_release_highlights(
        f"<html><body>{body}<h2>About Acme</h2><p>Boilerplate.</p></body></html>"
    )


def test_emerson_style_release_keeps_guidance_paragraph_and_drops_rows():
    out = _extract(
        [
            "Emerson Reports Third Quarter 2025 Results; Updates 2025 Outlook",
            "ST. LOUIS, Aug. 6, 2025 /PRNewswire/ -- Emerson (NYSE: EMR) today reported results for its third quarter ended June 30, 2025 and updated its full year outlook for fiscal 2025. Emerson also declared a quarterly cash dividend of $0.5275 per share of common stock payable September 10, 2025 to stockholders of record on August 15, 2025.",
            "“Emerson's solid third quarter results reflect our sustained momentum, delivering strong underlying growth, profitability and cash flow, which we expect to continue as we finish the fiscal year,” said Emerson President and Chief Executive Officer Lal Karsanbhai. “We are experiencing positive momentum in key end markets, and our team's ability to execute in this dynamic environment demonstrates the resilience of our business model and our operational excellence.”",
            "Karsanbhai continued, “We are taking pivotal steps to advance our industrial software capabilities, launching breakthrough innovations that are transforming how our customers optimize their operations. We deliver value by unlocking productivity and efficiency, and we are seeing accelerated adoption of our digital solutions.”",
            EMR_GUIDANCE_PARA,
            "Discrete taxes related to AspenTech transaction $0.09",
            "Operating Cash Flow ~$3.6B",
            "Free Cash Flow ~$3.2B",
            "Conference Call and Upcoming Events",
            "Today, beginning at 6:30 a.m. Central Time, Emerson management will discuss the third quarter results during an investor conference call. Participants can access a live webcast at https://ir.emerson.com at the time of the call. A replay of the call will be available for 90 days.",
            "Emerson also announces it will host an investor conference on Nov. 20, 2025 in New York City. Event details will be distributed closer to this date.",
        ]
    )
    assert out is not None
    # The guidance paragraph is content now, not residue.
    assert "GAAP EPS is now expected to be ~$4.08" in out
    assert "Net and underlying sales guidance of ~3.5% growth" in out
    # The single-value guidance rows are gone.
    assert "Discrete taxes related to AspenTech" not in out
    assert "Operating Cash Flow ~$3.6B" not in out
    assert "Free Cash Flow ~$3.2B" not in out
    # The conference-call heading and both notices are gone.
    assert "Conference Call and Upcoming Events" not in out
    assert "investor conference call" not in out
    assert "investor conference on Nov. 20" not in out
    # The quotes stay.
    assert "Emerson's solid third quarter results" in out
    assert "Karsanbhai continued" in out


def test_split_attribution_quote_continuation_served():
    out = _extract(
        [
            "Emerson Reports Fourth Quarter and Full Year 2024 Results; Provides Initial 2025 Outlook",
            "ST. LOUIS (November 5, 2024) - Emerson (NYSE: EMR) today",
            "reported results for its fourth quarter and fiscal year ended September 30, 2024. Emerson also declared a quarterly cash",
            "dividend increase to $0.5275 per share of common stock payable December 10, 2024 to stockholders of record November 15, 2024.",
            '"Emerson completed an outstanding fiscal 2024, with strong underlying',
            "sales growth, operating leverage, adjusted earnings per share and cash generation. I want to thank our employees around the world for",
            'their commitment and passion which were integral to delivering these results," said Emerson President and Chief Executive Officer',
            'Lal Karsanbhai. "We have done an exceptional job integrating Test & Measurement with $100 million of synergies realized in the',
            "first year, and we remain resolute in our focus on executing at a world-class level, guided by our Emerson Management System. Emerson's",
            "leading technology, alignment with secular trends and customer focus provide confidence for continued momentum in fiscal 2025.\"",
        ]
    )
    assert out is not None
    # The quote's second half, previously orphaned at the budget line.
    assert "We have done an exceptional job integrating Test & Measurement" in out
    # The third sentence follows a terminated second sentence — the
    # open-quote suppression keeps it in the same item.
    assert "leading technology, alignment with secular trends" in out
    assert "continued momentum in fiscal 2025" in out
    # The attribution and the first half stay.
    assert "Emerson completed an outstanding fiscal 2024" in out
    assert "Lal Karsanbhai." in out


def test_fico_style_revenue_heading_dropped_and_quote_served():
    out = _extract(
        [
            "FICO Announces Earnings of $5.44 per Share for Fourth Quarter Fiscal 2024",
            "BOZEMAN, Mont.--(BUSINESS WIRE)--November 6, 2024--FICO (NYSE:FICO), a global analytics software leader, today announced results for its fourth fiscal quarter ended September 30, 2024.",
            "Net income for the quarter totaled $135.7 million, or $5.44 per share, versus $101.4 million, or $4.01 per share, in the prior year period.",
            "Net cash provided by operating activities for the quarter was $226.5 million versus $164.0 million in the prior year period.",
            "Non-GAAP Net Income for the quarter was $163.2 million versus $126.7 million in the prior year period. Non-GAAP EPS for the quarter was $6.54 versus $5.01 in the prior year period. Free cash flow was $219.4 million for the current quarter versus $163.0 million in the prior year period.",
            "Fourth Quarter Fiscal 2024 GAAP Revenue",
            "The company reported revenues of $453.8 million for the quarter as compared to $389.7 million reported in the prior year period, an increase of 16%.",
            "“I am very proud of our performance in FY24, another record year for FICO financially,” said Will Lansing, chief executive officer. “I am also pleased to provide our FY 2025 guidance, which includes double-digit percentage growth for all our metrics, and I look forward to sharing more detail on our outlook for the year ahead.”",
        ]
    )
    assert out is not None
    assert "Fourth Quarter Fiscal 2024 GAAP Revenue" not in out
    assert "The company reported revenues of $453.8 million" in out
    assert "I am very proud of our performance in FY24" in out


def test_lone_dollar_cell_is_table_residue():
    # CSX: the recon-table EPS cell "$ 0.44" survived as a lone bare
    # value once the row above it dropped. A lone $ amount is a
    # flattened cell, not a metric value.
    for cell in ("$ 0.44", "$ 1,251", "$(502)", "$ 3,803"):
        assert _looks_like_table_cell(cell)
        assert _is_lede_table_line(cell)
    # A metric value carries a scale word or suffix — the batch-157
    # lone-value rule is untouched.
    assert not _looks_like_table_cell("$50.2 billion")
    assert not _is_lede_table_line("$50.2 billion")
    assert not _looks_like_table_cell("$1.2B")
    assert not _is_lede_table_line("$1.2B")
    # The pre-existing cell shapes still hold.
    assert _looks_like_table_cell("$")
    assert _looks_like_table_cell("1,757,093")
    assert _looks_like_table_cell("(1,371,420 )")


EMR_COPELAND_FOOTNOTE = (
    "6 With the June 6, 2024 definitive agreement to completely exit "
    "its remaining interests in the Copeland joint venture, Emerson "
    "will report financial results for the Copeland equity ownership "
    "as discontinued operations for all periods presented, beginning "
    "in Q3 2024. The earnings from discontinued operations for 2024 "
    "are expected to be $0.55 to $0.60 per share, including the "
    "after-tax gain on the equity stake in Copeland. The Copeland Note "
    "Receivable interest income through June 6, 2024 remains in "
    "continuing operations. The pretax loss on the sale of the note "
    "receivable, $279M ($217M after-tax), is also reported in "
    "continuing operations but excluded from adjusted earnings per "
    "share, ($0.38)."
)


def test_bare_numbered_footnote_cap():
    # The Emerson Copeland footnote is 699 chars — above the old
    # 500-char cap, so it survived as the lede tail once the guidance
    # rows dropped. Attested footnotes run to 984 chars (Comcast's
    # pro-forma footnote); the cap is now 1000.
    assert len(EMR_COPELAND_FOOTNOTE) == 699
    assert _is_bare_numbered_footnote(EMR_COPELAND_FOOTNOTE)
    # Short footnotes still open a block.
    assert _is_bare_numbered_footnote(
        "1 Net debt is total debt of $39.0 billion."
    )
    assert _is_bare_numbered_footnote(
        "1 As used in this release, FX-adjusted information assumes a "
        "constant exchange rate."
    )
    # Above 1000 the population is page/table mega-lines — still out.
    assert not _is_bare_numbered_footnote("1 " + "x" * 1100 + ".")
    # The mirror negative: a wrapped bullet continuation starts with
    # a lowercase quantity word, not a capital.
    assert not _is_bare_numbered_footnote(
        "1 million shares are included in the diluted count."
    )


def test_long_footnote_definition_skipped_end_to_end():
    # Emerson Q3 FY2024 style: the guidance paragraph is kept, the
    # single-value guidance rows drop, and the long Copeland footnote
    # below them is skipped — not served as the tail.
    out = _extract(
        [
            "Emerson Reports Third Quarter 2024 Results",
            "ST. LOUIS (August 7, 2024) - Emerson (NYSE: EMR) today reported results for its third quarter ended June 30, 2024. Emerson also declared a quarterly cash dividend of $0.5275 per share of common stock payable September 10, 2024 to stockholders of record August 16, 2024.",
            "“Emerson delivered another strong quarter, with solid underlying orders growth and with profitability well ahead of expectations,” said Emerson President and Chief Executive Officer Lal Karsanbhai. “We continue to execute at a high level, and our momentum gives us confidence in our outlook for the remainder of the year.”",
            "The following tables summarize the fiscal year 2024 guidance framework for continuing operations. The 2024 outlook assumes approximately $500 million returned to shareholders through share repurchases and approximately $1.2 billion of dividend payments. Guidance figures are approximate.",
            "Amortization of Acquisition-related Inventory Step-up $0.38",
            "Acquisition / Divestiture Fees and Related Costs ~$0.24",
            "Adjusted Earnings Per Share $5.45 - $5.50",
            "Operating Cash Flow ~$3.2B",
            "Free Cash Flow ~$2.8B",
            EMR_COPELAND_FOOTNOTE,
        ]
    )
    assert out is not None
    assert "The following tables summarize the fiscal year 2024" in out
    assert "Amortization of Acquisition-related Inventory Step-up" not in out
    assert "Acquisition / Divestiture Fees and Related Costs" not in out
    assert "Operating Cash Flow ~$3.2B" not in out
    assert "Free Cash Flow ~$2.8B" not in out
    # The footnote's substance is not a highlight.
    assert "Copeland joint venture" not in out
    assert "discontinued operations for all periods presented" not in out
    # The quote stays.
    assert "Emerson delivered another strong quarter" in out
