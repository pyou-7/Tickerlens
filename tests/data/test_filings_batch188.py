"""Batch 188 regression tests: AJG 2026 table header lines.

Two header lines still filled the AJG 2026 lede after batch 187
dropped the table's labels and dash value rows:

1. "Summary of Financial Results - First Quarter" — a table title
   with no "ended" period phrase, so _is_lede_table_title never
   fired on it. The fix recognizes AJG's anchored title
   (_is_lede_summary_results_title): the anchor plus an optional
   " - <period>" tail of period/date tokens only, covering all 12
   cached variants (First/Second/Third/Fourth Quarter, the wrapped
   "Fourth", "Six-Months ended June 30", "Nine-Months ended
   September 30", "Year Ended December 31") — all AJG, attested by
   a full-cache survey.

2. "Net Earnings (Loss) EBITDAC Diluted Net Earnings" — a column
   header whose "(Loss)" paren token defeated the table-header
   capital-led check. The fix strips parens before the isupper
   check in _is_lede_table_header: a parenthesized capital word
   is capital-led, a parenthesized lowercase word still fails.
"""
from tickerlens.data.filings import (
    _ADMIN_LINE_RE,
    _BOILERPLATE_RE,
    _glossary_def_block_len,
    _is_glossary_def_line,
    _is_lede_recon_heading,
    _is_lede_report_pointer,
    _is_lede_summary_results_title,
    _is_lede_table_header,
    _is_lede_table_title,
    _lede_quote_is_open,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html


def test_table_header_paren_word_shape() -> None:
    # The AJG 2026 column header: metric + repeated label words,
    # capital-led once "(Loss)" counts as capital-led.
    assert _is_lede_table_header(
        "Net Earnings (Loss) EBITDAC Diluted Net Earnings"
    )


def test_table_header_paren_word_rejects_non_headers() -> None:
    # No repeat word and no qualifier: a bare label, not a header.
    for ln in (
        "Operating Earnings (Loss)",
        "Net Earnings (Loss) Per Share",
        "Net Earnings (Loss)",
        "(Loss) Per Share",
        "Earnings per Share (Unaudited)",
    ):
        assert not _is_lede_table_header(ln), ln
    # Lowercase words still fail the capital-led check, parens or not.
    assert not _is_lede_table_header(
        "Liabilities and Stockholders’ Equity (Deficit)"
    )
    # No metric token: a period header, not a column header.
    assert not _is_lede_table_header("(Decrease) 12 Months Ended")
    # A $ figure still vetoes.
    assert not _is_lede_table_header("Quarterly Net Income (Loss) ($M)")
    # A headline verb still vetoes — the ACN margin header stays out
    # even though its paren words are now capital-led.
    assert not _is_lede_table_header(
        "Margin (Non-GAAP) Increase (Decrease) (Non-GAAP)"
    )
    assert not _is_lede_table_header("Margin (GAAP) Increase (Decrease)")


def test_summary_results_title_shape() -> None:
    # Every cached variant (all AJG).
    for ln in (
        "Summary of Financial Results - First Quarter",
        "Summary of Financial Results - Second Quarter",
        "Summary of Financial Results - Third Quarter",
        "Summary of Financial Results - Fourth Quarter",
        "Summary of Financial Results - Fourth",
        "Summary of Financial Results - Six-Months ended June 30",
        "Summary of Financial Results - Six-Months ended June 30,",
        "Summary of Financial Results - Nine-Months ended September 30",
        "Summary of Financial Results - Nine-Months ended September 30,",
        "Summary of Financial Results - Year Ended December 31",
        "Summary of Financial Results - Year Ended December 31,",
        "Summary of Financial Results",
    ):
        assert _is_lede_summary_results_title(ln), ln
        assert _is_lede_table_title(ln), ln


def test_summary_results_title_rejects_non_titles() -> None:
    # A prose continuation after the anchor is not a period tail.
    for ln in (
        "Summary of Financial Results for the First Quarter",
        "Summary of Financial Results - Record Revenue",
        "Summary of Financial Results - Full Year Outlook Raised",
        "A Summary of Financial Results",
        "Summary of Results - First Quarter",
    ):
        assert not _is_lede_summary_results_title(ln), ln
        assert not _is_lede_table_title(ln), ln
    # The Southern Company shape still matches via the old path, not
    # the anchor.
    assert _is_lede_table_title(
        "Non-GAAP Financial Measures Three Months Ended September"
    )
    assert not _is_lede_summary_results_title(
        "Non-GAAP Financial Measures Three Months Ended September"
    )


def test_recon_heading_trailing_paren_colon_shape() -> None:
    # AJG's segment recon headings end with a units parenthetical
    # and a colon; the trailing groups are stripped before the
    # guards, so the heading shape is judged on the heading itself.
    for ln in (
        "Brokerage Segment Reported GAAP to Adjusted Non-GAAP "
        "Reconciliations (dollars in millions):",
        "Brokerage Segment Reported GAAP to Adjusted Non-GAAP "
        "Reconciliations (continued) (dollars in millions):",
        "Corporate Segment Reported GAAP to Adjusted Non-GAAP "
        "Reconciliation Information (dollars in millions):",
        "GAAP to Adjusted Non-GAAP Reconciliations "
        "(dollars in millions):",
        "Non-GAAP Reconciliations (dollars in millions):",
        "Reconciliations (continued) (dollars in millions):",
        "Reconciliations (dollars in millions):",
        "Risk Management Segment Reported GAAP to Adjusted "
        "Non-GAAP Reconciliations (continued) (dollars in millions):",
    ):
        assert _is_lede_recon_heading(ln), ln
    # The pre-existing shapes still match.
    for ln in (
        "Reconciliation of Commissions and Fees",
        "GAAP/Adjusted (non-GAAP) Operating Earnings Reconciliation",
        "Reconciliation of GAAP to Non-GAAP Measures1",
    ):
        assert _is_lede_recon_heading(ln), ln


def test_recon_heading_still_rejects_non_headings() -> None:
    # Cash-flow statement headings name a reconciliation but are
    # terminated sentences, not section headings.
    for ln in (
        "Adjustments to reconcile net income to cash generated by "
        "operating activities:",
        "A reconciliation of the first-quarter tax rates for 2024 "
        "and 2023 is shown below:",
        "The tables below present the reconciliations of the "
        "following GAAP measures to their non-GAAP measures:",
        "Company Provides Reconciliation of Net Income to Adjusted "
        "EBITDA",
        "Please see a reconciliation of these measures in the "
        "tables below.",
    ):
        assert not _is_lede_recon_heading(ln), ln


def test_report_pointer_see_beginning_on_page() -> None:
    # AJG's recon-table pointer: "See" plus a page reference.
    for ln in (
        "See “Information Regarding Non-GAAP Measures” beginning "
        "on page 8 of 17.",
        'See "Information Regarding Non-GAAP Measures" beginning '
        "on page 9 of 20.",
        "See “Information Regarding Non-GAAP Measures” beginning "
        "on page 9 of",
        "See “Information Regarding Non-GAAP Measures” beginning "
        "on page 9 of 15.",
    ):
        assert _is_lede_report_pointer(ln), ln
    # The pre-existing branch still matches.
    assert _is_lede_report_pointer(
        "See information regarding non-GAAP measures presented "
        "later in this press release."
    )
    # A "See" sentence with no page reference is not a pointer.
    assert not _is_lede_report_pointer(
        "See our website for more information about the company."
    )


def test_report_pointer_attachment_and_comparison_note() -> None:
    # Con Edison's attachment pointer and Citigroup's methodology
    # note are the same document-tail boilerplate class.
    assert _is_lede_report_pointer(
        "See Attachment A to this press release for a reconciliation "
        "of Con Edison’s reported earnings per share to adjusted "
        "earnings per share and reported net income for common stock "
        "to adjusted earnings for the three months ended March 31, "
        "2026 and 2025."
    )
    assert _is_lede_report_pointer(
        "Percentage comparisons throughout this press release are "
        "calculated for the first quarter 2026 versus the first "
        "quarter 2025, unless otherwise specified."
    )
    assert not _is_lede_report_pointer(
        "See Attachment A for the full table of results."
    )


def test_admin_line_title_plus_page_marker() -> None:
    # Con Edison repeats the release title at the top of each page
    # with a page marker ("CON EDISON REPORTS 2026 FIRST QUARTER
    # EARNINGS page 2") — admin, never headline or lede material.
    for ln in (
        "CON EDISON REPORTS 2026 FIRST QUARTER EARNINGS page 2",
        "CON EDISON REPORTS 2025 THIRD QUARTER EARNINGS page 4",
    ):
        assert _ADMIN_LINE_RE.match(ln), ln
    # A lowercase prefix is prose, not a title — the cross-reference
    # inside AJG's ratio labels and AAL's date footers stay out.
    # ("News Release continued: Page 2" is admin too, but via the
    # "news release" alternative, not this rule.)
    for ln in (
        "Adjusted compensation expense ratios using adjusted "
        "revenues on page 1",
        "Oct. 22, 2026 | Page 10",
        "Financial highlights continued on page 2",
    ):
        assert not _ADMIN_LINE_RE.match(ln), ln


def test_open_quote_is_unfinished_at_budget() -> None:
    # The budget lands on a quote line ending in a noun ("business"),
    # so no wrap tail fires — but the quote is open, which is
    # unfinished by definition, and the continuation must be pulled
    # in (AJG 2024: the quote was cut at "bedrock culture").
    assert _lede_quote_is_open(
        ["“We delivered strong growth across our business"]
    )
    assert not _lede_quote_is_open(
        ["“We delivered strong growth.” said Jane Doe, CEO."]
    )
    # Stack pairing (batch 188): a curly open closed by a straight
    # mark is closed, not open — Bristol Myers' “…” and Cintas'
    # “…” quotes end that way, and the old by-kind count read them
    # as open and pulled the table chrome below (BMY's "$ in
    # millions, except per share amounts" header, CTAS's
    # guidance-table fragments).
    assert not _lede_quote_is_open(
        [
            "“Our strong execution in the first quarter drove "
            "continued momentum across our Growth Portfolio and "
            "meaningful progress in the pipeline,” said Christopher "
            "Boerner, Ph.D., board chair and chief executive officer, "
            "Bristol Myers Squibb. “We are advancing our multi-year "
            "plan to become a more agile and efficient company, while "
            "strengthening the foundation for top-tier, long-term "
            "growth. Our strategy is clear, and our actions are "
            "accelerating the delivery of transformational medicines "
            "to patients.\"",
        ]
    )
    assert _lede_quote_is_open(
        [
            "Todd M. Schneider, Cintas' Chief Executive Officer, "
            "stated “We are pleased with our start to fiscal 2027.",
        ]
    )
    hl = extract_press_release_highlights(
        _contact_release_html(
            "ACME REPORTS THIRD QUARTER 2026 RESULTS",
            "ANYTOWN, USA, October 29, 2026 — Acme Corp. today "
            "reported results for the quarter ended September 30, "
            "2026. Management will host a webcast conference call "
            "to discuss these results today at 5:00 p.m. ET.",
            "Total revenue grew 10 percent to $1.0 billion in the "
            "third quarter.",
            "Net earnings increased 12 percent to $100 million.",
            "Adjusted EBITDA grew 15 percent to $200 million.",
            "Organic growth was 6 percent in the quarter.",
            "Cash flow from operations was $150 million.",
            "“We delivered strong growth across our business",
            "and our margins expanded.” said Jane Doe, Chief "
            "Executive Officer.",
        )
    )
    assert hl is not None
    assert "and our margins expanded" in hl
    assert "Cash flow from operations was $150 million." in hl


def test_ajg_2026_lede_serves_quote_not_headers() -> None:
    # Verbatim AJG Q1 2026 shape (batch 187's fixture): the lede must
    # now serve the pretax prose and the quote with neither table
    # header line — the title is skipped before any content exists
    # and the column header is skipped as a table header. The
    # dateline carries the webcast conference-call sentence, as the
    # real release does, so the loop skips it and `lede` is still
    # empty at the title line (a bare dateline would be collected
    # as content and the table-title branch would break instead).
    hl = extract_press_release_highlights(
        _contact_release_html(
            "ARTHUR J. GALLAGHER & CO. ANNOUNCES FIRST QUARTER 2026 "
            "FINANCIAL RESULTS",
            "ROLLING MEADOWS, IL, April 30, 2026 — Arthur J. "
            "Gallagher & Co. (NYSE: AJG) today reported its financial "
            "results for the quarter ended March 31, 2026. Management "
            "will host a webcast conference call to discuss these "
            "results on Thursday, April 30, 2026 at 5:15 p.m. ET.",
            "Summary of Financial Results - First Quarter",
            "Revenues Before",
            "Reimbursements",
            "Net Earnings (Loss) EBITDAC Diluted Net Earnings",
            "(Loss) Per Share",
            "Segment",
            "1st Q 26 1st Q 25 1st Q 26 1st Q 25 1st Q 26 1st Q 25 "
            "1st Q 26 1st Q 25",
            "(in millions) (in millions) (in millions)",
            "Brokerage, as reported $ 4,293 $ 3,314 $ 913 $ 816 "
            "$ 1,562 $ 1,351 $ 3.51 $ 3.13",
            "Net (gains) on divestitures",
            "(7) (6) (5) (4) (7) (6) (0.02) (0.02)",
            "Acquisition integration",
            "– – 65 33 87 44 0.25 0.13",
            "For first quarter 2026, the pretax impact of "
            "adjustments for the Brokerage, Risk Management, and "
            "Corporate Segments totals $431 million, $15 million and "
            "$30 million, respectively, and corresponding adjustment "
            "to the provision (benefit) for income taxes was $111 "
            "million, $4 million and ($20) million, respectively, "
            "relating to these adjustments.",
            "“We had a terrific first quarter!” said J. Patrick "
            "Gallagher, Jr., Chairman and CEO. “For our combined "
            "brokerage and risk management segments, our two-pronged "
            "revenue growth strategy – growing both organically and "
            "through acquisitions – delivered revenue growth of 28% "
            "in the quarter.”",
            "Brokerage Segment Reported GAAP to Adjusted Non-GAAP "
            "Reconciliations (dollars in millions):",
            "See “Information Regarding Non-GAAP Measures” beginning "
            "on page 8 of 17.",
            "Base Commissions and Fees",
            "Commissions and fees, as reported",
            "$ 3,915 $ 2,869",
            "Less supplemental revenues from acquisitions, divested "
            "operations and other",
            "Less contingent revenues from acquisitions, divested "
            "operations and other",
            "Reported compensation expense ratios using reported "
            "revenues on page 1",
            "Interest, banking costs and debt - At March 31, 2026, "
            "Gallagher had borrowings from public debt.",
            "Clean energy-related - For 2026, this consists of "
            "operating results related to new clean energy projects.",
            "Acquisition costs - Consists mostly of external "
            "professional fees and other due diligence costs related "
            "to acquisitions.",
            "Corporate - Consists of overhead allocations mostly "
            "related to corporate staff compensation.",
            "About Arthur J. Gallagher & Co.",
            "This press release contains forward-looking statements "
            "that are intended to qualify for the safe-harbor "
            "provisions of Section 27A of the Securities Act of 1933.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0].startswith(
        "ARTHUR J. GALLAGHER & CO. ANNOUNCES FIRST QUARTER 2026"
    )
    assert "pretax impact of adjustments" in hl
    assert "We had a terrific first quarter" in hl
    assert "revenue growth of 28%" in hl
    assert "Summary of Financial Results" not in hl
    assert "Net Earnings (Loss) EBITDAC" not in hl
    assert "Revenues Before" not in hl
    assert "Acquisition integration" not in hl
    assert "65 33 87 44 0.25 0.13" not in hl
    assert "Reconciliations (dollars in millions)" not in hl
    assert "beginning on page 8 of 17" not in hl
    # The recon table's nested label chain is table-mode residue
    # once the recon heading enters table mode — a label whose next
    # line is another label matches no table predicate on its own.
    assert "Base Commissions and Fees" not in hl
    assert "Less supplemental revenues" not in hl
    assert "Less contingent revenues" not in hl
    assert "Reported compensation expense ratios" not in hl
    # Batch 188 (blast follow-up): the adjustment-item glossary that
    # follows the recon tables is skipped as a block, and the
    # safe-harbor intro after the About break never reaches the lede.
    assert "banking costs and debt" not in hl
    assert "Clean energy-related - For 2026" not in hl
    assert "forward-looking statements" not in hl


def test_ajg_2026_six_months_title_skipped_not_break() -> None:
    # The six-months table title after the quote is a table title too,
    # but it is skipped, never a break (batch 188): AJG's summary
    # title heads a table whose narrative follows it, and the dateline
    # tail collected ahead of the first title is boilerplate, not
    # prose — so the break-on-content rule must not fire on it. The
    # prose after the second table is therefore still collected.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "ARTHUR J. GALLAGHER & CO. ANNOUNCES SECOND QUARTER 2026 "
            "FINANCIAL RESULTS",
            "ROLLING MEADOWS, IL, July 30, 2026 — Arthur J. "
            "Gallagher & Co. (NYSE: AJG) today reported its financial "
            "results for the quarter ended June 30, 2026. Management "
            "will host a webcast conference call to discuss these "
            "results on Thursday, July 30, 2026 at 5:15 p.m. ET.",
            "Summary of Financial Results - Second Quarter",
            "Revenues Before",
            "Reimbursements",
            "Net Earnings (Loss) EBITDAC Diluted Net Earnings",
            "(Loss) Per Share",
            "Segment",
            "2nd Q 26 2nd Q 25 2nd Q 26 2nd Q 25 2nd Q 26 2nd Q 25 "
            "2nd Q 26 2nd Q 25",
            "(in millions) (in millions) (in millions)",
            "Brokerage, as reported $ 3,502 $ 2,787 $ 450 $ 510 "
            "$ 948 $ 892 $ 1.74 $ 1.95",
            "For second quarter 2026, the pretax impact of "
            "adjustments for the Brokerage, Risk Management, and "
            "Corporate Segments totals $505 million, $12 million and "
            "$33 million, respectively.",
            "“We delivered an excellent second quarter!” said "
            "J. Patrick Gallagher, Jr., Chairman and CEO. “Our "
            "combined Brokerage and Risk Management segments delivered "
            "revenue growth of 24%, including organic growth of 6%.”",
            "Summary of Financial Results - Six-Months ended June 30",
            "Revenues Before",
            "Brokerage, as reported $ 7,795 $ 6,101 $ 1,363 $ 1,326 "
            "$ 2,510 $ 948 $ 2,243 $ 5.25 $ 5.08",
            "For the six months ended June 30, 2026, total revenues "
            "grew 24 percent.",
        )
    )
    assert hl is not None
    assert "We delivered an excellent second quarter" in hl
    assert "revenue growth of 24%" in hl
    assert "Summary of Financial Results" not in hl
    assert "Net Earnings (Loss) EBITDAC" not in hl
    assert "For the six months ended June 30, 2026" in hl


def test_glossary_def_line_shape() -> None:
    # AJG's adjustment-item glossary lines (verbatim terms, shortened
    # definitions) and EFX's are glossary lines; datelines share the
    # "Term - sentence" shape but carry a date in the term, and a
    # bulleted definition is not one (it lives under the Non-GAAP
    # heading, past the About break, and never reaches the loop).
    assert _is_glossary_def_line(
        "Interest, banking costs and debt - At March 31, 2026, "
        "Gallagher had borrowings from public debt."
    )
    assert _is_glossary_def_line(
        "Clean energy-related - For 2026, this consists of operating "
        "results related to new clean energy projects."
    )
    assert _is_glossary_def_line(
        "Antitrust litigation costs - Antitrust litigation costs "
        "include legal fees to respond to antitrust litigation."
    )
    assert not _is_glossary_def_line(
        "COLUMBUS, Ohio, July 30, 2025 - American Electric Power "
        "today reported second-quarter 2025 GAAP earnings."
    )
    assert not _is_glossary_def_line(
        "Bethesda, MD - April 20, 2026 - AGNC Investment Corp. today "
        "announced financial results."
    )
    assert not _is_glossary_def_line(
        "•Net gains (losses) on divestitures, which are primarily net "
        "proceeds received related to sales of businesses."
    )
    assert not _is_glossary_def_line(
        "Clean energy-related - For 2026, this consists of operating "
        "results related to new clean energy projects"
    )


def test_glossary_def_block_len_needs_a_run() -> None:
    # A lone "Term - sentence" line is not a glossary; only a run of
    # 3+ counts, and the run length is returned whole.
    lines = [
        "Interest, banking costs and debt - At March 31, 2026, "
        "Gallagher had borrowings from public debt.",
        "Clean energy-related - For 2026, this consists of operating "
        "results related to new clean energy projects.",
    ]
    assert _glossary_def_block_len(lines, 0) == 0
    lines.append(
        "Acquisition costs - Consists mostly of external professional "
        "fees and other due diligence costs related to acquisitions."
    )
    lines.append(
        "Corporate - Consists of overhead allocations mostly related "
        "to corporate staff compensation."
    )
    assert _glossary_def_block_len(lines, 0) == 4
    assert _glossary_def_block_len(lines, 1) == 3
    assert _glossary_def_block_len(lines, 4) == 0


def test_boilerplate_forward_looking_intro() -> None:
    # The safe-harbor intro starts "This press release contains
    # forward-looking ..." — the bare "forward-looking" alternative
    # never matched it, so ED's lede ran on into the safe-harbor
    # paragraph. The intro is always boilerplate; a results sentence
    # starting "This press release ..." without it is not.
    assert _BOILERPLATE_RE.match(
        "This press release contains forward-looking statements that "
        "are intended to qualify for the safe-harbor provisions of "
        "Section 27A of the Securities Act of 1933."
    )
    assert _BOILERPLATE_RE.match(
        "This release contains forward-looking statements, which "
        "address a variety of subjects."
    )
    assert not _BOILERPLATE_RE.match(
        "This press release reports third-quarter results and a "
        "dividend increase."
    )
