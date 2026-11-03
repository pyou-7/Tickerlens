"""Batch 178: the batch-177 exposed table-row/title leak.

Four classes the batch-177 repair guards blocked but the extractor still
served, all attested live:
  A. A $-carrying recon/table row above _is_lede_data_row's 80-char
     $-figures cap: Ares Capital's "Fair value of accruing debt and
     other income producing securities(5) $ 24,831 $ 23,643" (86 chars,
     5 quarters). Fix: the cap moves 80 -> 120, matching the batch-160
     $-less cap and the repair script's $-row guard.
  B. An exhibit title line served mid-lede once the budget frees up:
     Capital One's "Capital One Third Quarter 2024 Earnings" (7 rows).
     Fix: a lede-loop skip on _is_lede_title_line — _is_trailing_heading
     plus a headline-verb veto, so the batch-177 sub-headline keeps
     ("Q2 ORGANIC SALES AND ADJUSTED EPS EXCEED OUTLOOK", "COMPANY
     MAINTAINS FULL-YEAR REVENUE AND EPS GUIDANCE", "AMERICAN WATER
     REPORTS SOLID SECOND QUARTER RESULTS") all survive it.
  C. A spaced-decimal $ row: Estée Lauder's "Diluted Net Earnings Per
     Common Share $ .44 $ .91 (52) %" ("$ .44" — the $ is space- and
     period-separated from its figure). Fix: the $-figure count accepts
     an optional dot ("$\\s?\\.?[\\d(]"), and the two table headers
     around it ("Organic Net Sales, Non-GAAP1", "Adjusted Diluted Net
     Earnings Per Common Share, Non-GAAP1,2") are caught by
     _is_lede_table_header once its qualifier/repeat comparison strips
     trailing footnote digits/commas and "Earnings" joins its metric
     list.
  D. An as-of date fragment: Ares Capital's "As of December 31,".
     Fix: _is_lede_asof_date, wired into _is_lede_table_line next to
     _is_lede_date_header; plus the units line that rides with it
     ("(dollar amounts in millions, except per share data) Total
     Amount Per Share ...") — _TABLE_UNITS_RE gains the singular
     "dollar", with a lookahead so a hyphenated prose parenthetical
     ("(dollar-cost averaging ...)") never matches.
  E. A table-label line one word past the colon-heading bound: Ares
     Capital's "Weighted average yields on debt and other income
     producing securities(7):" (10 words, no verb). Fix: the bare-phrase
     bound in _is_lede_colon_heading moves 8 -> 12 words; the verb veto
     is unchanged.

The pin is behavioral: on stashed old code the new helpers do not exist
(collection error) and the ARCC/EL rows are not data rows or headers.
"""
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _TABLE_UNITS_RE,
    _clean_highlights_result,
    _is_lede_asof_date,
    _is_lede_colon_heading,
    _is_lede_data_row,
    _is_lede_table_header,
    _is_lede_table_line,
    _is_lede_title_line,
    extract_press_release_highlights,
)

ARCC_ROW = (
    "Fair value of accruing debt and other income producing "
    "securities(5) $ 24,831 $ 23,643"
)
EL_SPACED_DEC_ROW = "Diluted Net Earnings Per Common Share $ .44 $ .91 (52) %"


def test_data_row_cap_attested_arcc_row():
    assert len(ARCC_ROW) == 86
    assert _is_lede_data_row(ARCC_ROW)


def test_data_row_cap_boundary():
    # Same figures, longer label: the 120-char cap is the boundary.
    label = (
        "Fair value of accruing debt and other income producing "
        "securities(5)"
    )
    row120 = f"{label} {'x' * (120 - len(label) - len(' $ 24,831 $ 23,643') - 1)} $ 24,831 $ 23,643"
    row121 = f"{label} {'x' * (121 - len(label) - len(' $ 24,831 $ 23,643') - 1)} $ 24,831 $ 23,643"
    assert len(row120) == 120, len(row120)
    assert len(row121) == 121, len(row121)
    assert _is_lede_data_row(row120)
    assert not _is_lede_data_row(row121)


def test_data_row_extended_band_keeps_wrapped_prose():
    # The 81-120 band is bare-number table values only. These wrapped
    # prose fragments are all 81-120 chars with 2 $ figures — the blunt
    # cap raise dropped all three, and the full suite caught it.
    # Coinbase Q1 FY2025: ends mid-clause on a word, scaled $ figures.
    assert not _is_lede_data_row(
        "We delivered strong financial results in Q1, generating $2.0 "
        "billion in total revenue, $66 million in net income,"
    )
    # Chubb Q3 2024 bullet continuation: same shape.
    assert not _is_lede_data_row(
        "Net income was $2.32 billion, up 13.8%, and core operating "
        "income was $2.33 billion, up 14.3%. For the"
    )
    # Batch-160 guard: a comparison clause is prose, not a row.
    assert not _is_lede_data_row(
        "Net income was $2.4 billion in the first quarter of 2026, "
        "compared to $566 million in the prior year quarter"
    )
    # Bare $ figures but ending mid-clause on a word: still prose.
    assert not _is_lede_data_row(
        "Fair value of accruing debt and other income producing "
        "securities(5) $ 24,831 $ 23,643 in total"
    )
    # A bare-year ending is prose, never a row (Eaton).
    assert not _is_lede_data_row(
        "Fourth quarter earnings per share of $2.35 and record adjusted "
        "earnings per share of $2.55, up 24% over 2022"
    )
    # A $-to-$ range is a guidance statement, never a table row.
    assert not _is_lede_data_row(
        "FULL-YEAR 2024 GUIDANCE FOR REVENUE GROWTH OF 9% TO 11% AND "
        "EPS OF $12.65 TO $13.15"
    )
    assert not _is_lede_data_row(
        "Adjusted Diluted EPS Guidance Range Reaffirmed at $17.45 to "
        "$17.75 for Fiscal 2026"
    )
    # Flattened-list bullets are narrative, never rows (AIG "■", AWK "◦").
    assert not _is_lede_data_row(
        "■Net income per diluted share was $0.12 and adjusted "
        "after-tax income* (AATI) per diluted share was $1.79"
    )
    assert not _is_lede_data_row(
        "◦2023 weather-normalized earnings of $4.77 per share, compared "
        "to $4.45 per share in 2022"
    )


def test_title_line_keeps_verb_sub_headlines():
    # The batch-178 verb additions: AFFIRMS / PROVIDES / CONFIRMS /
    # REVISES / INITIATES / REITERATES are headline verbs, so these
    # sub-headlines survive the title-line skip.
    assert not _is_lede_title_line(
        "AFFIRMS 2024 EPS GUIDANCE AND LONG-TERM GROWTH TARGETS"
    )
    assert not _is_lede_title_line("PROVIDES FULL-YEAR FISCAL 2027 GUIDANCE")
    assert not _is_lede_title_line(
        "Confirms Full-Year Fiscal 2024 Adjusted Earnings Outlook"
    )
    assert not _is_lede_title_line(
        "Revises Full-Year Fiscal 2025 Earnings Outlook"
    )
    assert not _is_lede_title_line(
        "Initiates Full-year Fiscal 2026 Earnings Outlook"
    )
    assert not _is_lede_title_line("REITERATING FULL YEAR 2026 OUTLOOK")


def test_bare_units_declaration_is_table_line():
    assert _is_lede_table_line(
        "In billions, except percentages and per share data."
    )
    assert _is_lede_table_line("In millions, except per share data")
    # A prose sentence that merely mentions units is not a declaration.
    assert not _is_lede_table_line(
        "In billions, except percentages and per share data, revenue grew 8%."
    )
    assert not _is_lede_table_line(
        "We report in billions, except percentages and per share data."
    )
    # Lowercase form (eBay/Emerson flattened fragments): a sentence
    # never opens lowercase, so the tail is free.
    assert _is_lede_table_line(
        "in millions, except per share data and percentages"
    )
    assert _is_lede_table_line("in millions, except per share)")
    # The "Dollars in" form (DuPont's table header, same class).
    assert _is_lede_table_line("Dollars in millions, except EPS")
    assert _is_lede_table_line("Dollars in thousands, except per share data")
    # ... but the capital form still needs its (data|information) tail,
    # so a prose sentence that merely mentions units survives.
    assert not _is_lede_table_line(
        "In millions, except per share data, revenue grew 8%."
    )


def test_glued_footnote_number_opens_definition():
    from tickerlens.data.filings import (
        _footnote_def_block_len,
        _is_bare_numbered_footnote,
        _opens_footnote_def,
    )

    assert _is_bare_numbered_footnote(
        "1See pages 17 and 18 for reconciliation between GAAP and "
        "Adjusted Non-GAAP measures."
    )
    assert _is_bare_numbered_footnote(
        "2Adjusted Non-GAAP measures are calculated based on Net Sales "
        "adjusted only for Returns associated with restructuring and "
        "other activities."
    )
    assert _opens_footnote_def(
        "1See pages 17 and 18 for reconciliation between GAAP and "
        "Adjusted Non-GAAP measures."
    )
    # A company name never opens a block ("3M reports ...").
    assert not _is_bare_numbered_footnote(
        "3M reports third quarter 2025 results."
    )
    assert not _opens_footnote_def("3M reports third quarter 2025 results.")
    # A digit-led wrap ("1 million shares ...") stays a continuation.
    assert not _is_bare_numbered_footnote(
        "1 million shares are included in the diluted count."
    )
    # The block consumes the glued footnote line.
    assert _footnote_def_block_len(
        [
            "1See pages 17 and 18 for reconciliation between GAAP and "
            "Adjusted Non-GAAP measures.",
            "•Net sales decreased 10% to $3.6 billion.",
        ],
        0,
    ) == 1


def test_footnote_block_crosses_blank_line():
    from tickerlens.data.filings import _footnote_def_block_len

    # Ares Capital's (7) yields footnote wraps across a blank line; the
    # block must consume the orphaned continuation, not serve it.
    lines = [
        "(7)Weighted average yields on debt and other income producing "
        "securities are computed as (a) the annual stated interest rate "
        "or yield earned plus the net annual",
        "2",
        "",
        "securities at amortized cost or at fair value (including the "
        "amortized cost or fair value of Ares Capital’s equity "
        "investment in IHAM as applicable), as applicable.",
        "•Net sales decreased 10% to $3.6 billion.",
    ]
    assert _footnote_def_block_len(lines, 0) == 4
    # A terminated definition still stops at the blank: the prose after
    # it is not consumed.
    lines2 = [
        "(1) See Table A for a reconciliation of GAAP to Non-GAAP results.",
        "",
        "We delivered strong financial results in Q1.",
    ]
    assert _footnote_def_block_len(lines2, 0) == 1


def test_data_row_spaced_decimal():
    assert _is_lede_data_row(EL_SPACED_DEC_ROW)
    # One spaced-decimal figure is a metric value, not a row.
    assert not _is_lede_data_row(
        "Diluted Net Earnings Per Common Share $ .44"
    )
    # Terminated $-carrying prose is never a row, at any length.
    assert not _is_lede_data_row(
        "Capital One Reports Third Quarter 2024 Net Income of $1.8 "
        "billion, or $4.41 per share."
    )
    # A bullet is narrative, never a row (batch 175).
    assert not _is_lede_data_row(f"•{ARCC_ROW}")


def test_units_regex_singular_dollar():
    assert _TABLE_UNITS_RE.match(
        "(dollar amounts in millions, except per share data) Total "
        "Amount Per Share Total Amount Per Share"
    )
    assert _TABLE_UNITS_RE.match("(dollars in millions, except per share data)")
    assert _TABLE_UNITS_RE.match("(Dollars in millions, except per share data) Pre-Tax")
    # A hyphenated prose parenthetical is not a units line.
    assert not _TABLE_UNITS_RE.match("(dollar-cost averaging is a strategy)")


def test_units_line_is_table_line():
    assert _is_lede_table_line(
        "(dollar amounts in millions, except per share data) Total "
        "Amount Per Share Total Amount Per Share"
    )
    assert _is_lede_table_line("As of December 31,")
    assert _is_lede_table_line(ARCC_ROW)
    assert _is_lede_table_line(EL_SPACED_DEC_ROW)


def test_asof_date_attested_and_guards():
    assert _is_lede_asof_date("As of December 31,")
    assert _is_lede_asof_date("As of March 31,")
    assert _is_lede_asof_date("As of December 31")
    # A year makes it a dateline, not a table fragment.
    assert not _is_lede_asof_date("As of December 31, 2025")
    assert not _is_lede_asof_date("As of September 30, 2024")
    # A continuing sentence is prose, not a fragment.
    assert not _is_lede_asof_date("As of December 31, revenue grew 8%.")
    assert not _is_lede_asof_date("As of December 31, we had $1 billion.")
    # The wrong month name never matches.
    assert not _is_lede_asof_date("As of Dec 31,")


def test_table_header_footnote_digits():
    # Estée Lauder's summary-table headers: the qualifier rides with
    # footnote digits, and "Earnings" is the metric on the second.
    assert _is_lede_table_header("Organic Net Sales, Non-GAAP1")
    assert _is_lede_table_header(
        "Adjusted Diluted Net Earnings Per Common Share, Non-GAAP1,2"
    )
    # The batch-177 lines keep working.
    assert _is_lede_table_header("MCO Diluted EPS MCO Adjusted Diluted EPS2")
    assert _is_lede_table_header("Impact After-Tax Diluted EPS")
    # Sub-headlines keep the verb veto.
    assert not _is_lede_table_header(
        "Q2 ORGANIC SALES AND ADJUSTED EPS EXCEED OUTLOOK"
    )
    assert not _is_lede_table_header(
        "COMPANY MAINTAINS FULL-YEAR REVENUE AND EPS GUIDANCE"
    )
    # A metric + qualifier line that is a real bullet stays prose.
    assert not _is_lede_table_header(
        "•Diluted EPS up 8% and Adjusted Diluted EPS2 up 13% from the prior-year period."
    )


def test_title_line_attested_and_verb_veto():
    assert _is_lede_title_line("Capital One Third Quarter 2024 Earnings")
    assert _is_lede_title_line("Capital One First Quarter 2025 Earnings")
    assert _is_lede_title_line("2025 First Quarter Results")
    assert _is_lede_title_line("First Quarter 2025 Financial Results")
    # Sub-headlines carry a headline verb — the veto keeps them.
    assert not _is_lede_title_line(
        "Q2 ORGANIC SALES AND ADJUSTED EPS EXCEED OUTLOOK"
    )
    assert not _is_lede_title_line(
        "COMPANY MAINTAINS FULL-YEAR REVENUE AND EPS GUIDANCE"
    )
    assert not _is_lede_title_line(
        "AMERICAN WATER REPORTS SOLID SECOND QUARTER RESULTS"
    )
    assert not _is_lede_title_line(
        "RESETTING DIVIDEND TO ACCELERATE DEBT REDUCTION"
    )
    # A headline-shaped line carries a verb too.
    assert not _is_lede_title_line(
        "Capital One Reports Third Quarter 2024 Earnings"
    )
    # Terminated lines and bullets are never title lines.
    assert not _is_lede_title_line("First Quarter 2025 Financial Results.")
    assert not _is_lede_title_line("•Capital One Third Quarter 2024 Earnings")


def test_colon_heading_twelve_word_bound():
    # Ares Capital's yields label: 10 words, no verb.
    assert _is_lede_colon_heading(
        "Weighted average yields on debt and other income producing "
        "securities(7):"
    )
    # The 12-word bound itself.
    assert _is_lede_colon_heading(
        "Weighted average yields on debt and other income producing "
        "securities and loans(7):"
    )
    # Thirteen words is past the bound.
    assert not _is_lede_colon_heading(
        "Weighted average yields on debt and other income producing "
        "securities and total loans(7):"
    )
    # The verb veto is unchanged: a verb-carrying 10-word colon line
    # is a lead-in, not a label.
    assert not _is_lede_colon_heading(
        "Weighted average yields on debt and other income producing "
        "securities increased:"
    )
    # The batch-177 lines keep working.
    assert _is_lede_colon_heading("Financial Results for the Quarter:")
    assert _is_lede_colon_heading("Fiscal 2026 outlook:")
    assert not _is_lede_colon_heading(
        "Sundar Pichai, CEO of Google and Alphabet, said:"
    )


def _extract(body_lines):
    body = "".join(f"<p>{ln}</p>" for ln in body_lines)
    return extract_press_release_highlights(
        f"<html><body>{body}<h2>About Acme</h2><p>Boilerplate.</p></body></html>"
    )


def test_cof_style_release_drops_title_line():
    out = _extract(
        [
            "Capital One Reports First Quarter 2025 Net Income of $1.4 billion, or $3.45 per share",
            "Net of adjusting items, First Quarter 2025 Net Income of $4.06 per share(1)",
            "McLean, Va. (April 22, 2025) – Capital One Financial Corporation (NYSE: COF) today announced net income for the first quarter of 2025 of $1.4 billion, or $3.45 per diluted common share, compared with net income of $1.1 billion, or $2.67 per diluted common share in the fourth quarter of 2024.",
            "“Last week, we received regulatory approval for our acquisition of Discover and we're fully mobilized to complete the transaction on May 18th,” said Richard D. Fairbank, Founder, Chairman, and Chief Executive Officer.",
            "Capital One First Quarter 2025 Earnings",
            "All comparisons below are for the first quarter of 2025 compared with the fourth quarter of 2024 unless otherwise noted.",
            "•Total net revenue decreased 2 percent to $10.0 billion.",
            "•Total non-interest expense increased 3 percent to $5.9 billion.",
        ]
    )
    assert out is not None
    assert "Capital One First Quarter 2025 Earnings" not in out
    # The headline, subtitle, dateline, quote, note, and both bullets stay.
    assert "Reports First Quarter 2025 Net Income of $1.4 billion" in out
    assert "Net of adjusting items" in out
    assert "regulatory approval for our acquisition of Discover" in out
    assert "All comparisons below are for the first quarter of 2025" in out
    assert "Total net revenue decreased 2 percent" in out
    assert "Total non-interest expense increased 3 percent" in out


def test_arcc_style_release_drops_table_tail():
    out = _extract(
        [
            "ARES CAPITAL CORPORATION ANNOUNCES JUNE 30, 2025 FINANCIAL RESULTS AND DECLARES THIRD QUARTER 2025 DIVIDEND OF $0.48 PER SHARE",
            "New York, NY — July 29, 2025 — Ares Capital Corporation (“Ares Capital”) (NASDAQ: ARCC) announced that its Board of Directors has declared a third quarter 2025 dividend of $0.48 per share. The third quarter 2025 dividend is payable on September 30, 2025 to stockholders of record as of September 15, 2025.",
            "Ares Capital also announced financial results for its second quarter ended June 30, 2025.",
            "(dollar amounts in millions, except per share data) Total Amount Per Share Total Amount Per Share",
            "“We reported another solid quarter with strong levels of core earnings and growth in our net asset value reflecting the positioning and performance of our investment portfolio,” said Kort Schnabel, Chief Executive Officer of Ares Capital.",
            "“We continued to further strengthen our capital and liquidity position by raising over $2 billion of new debt capital since the end of last quarter,” said Scott Lem, Chief Financial Officer of Ares Capital.",
            "As of December 31,",
            "Fair value of accruing debt and other income producing securities(5) $ 24,831 $ 23,643",
            "Weighted average yields on debt and other income producing securities(7):",
        ]
    )
    assert out is not None
    assert "(dollar amounts in millions" not in out
    assert "As of December 31," not in out
    assert "Fair value of accruing debt" not in out
    assert "Weighted average yields on debt" not in out
    assert "declared a third quarter 2025 dividend of $0.48 per share" in out
    assert "another solid quarter with strong levels of core earnings" in out
    assert "raising over $2 billion of new debt capital" in out


def test_el_style_release_drops_spaced_decimal_tail():
    out = _extract(
        [
            "THE ESTÉE LAUDER COMPANIES REPORTS FISCAL 2025 THIRD QUARTER RESULTS",
            "New York, May 1, 2025 - The Estée Lauder Companies Inc. (NYSE: EL) today reported its financial results for the third quarter ended March 31, 2025.",
            "Stéphane de La Faverie, President and Chief Executive Officer, said, “In the third quarter of fiscal 2025, we delivered our organic sales outlook and exceeded profitability expectations. We are moving decisively and building momentum as we bring our “Beauty Reimagined” strategic vision to life.”",
            "“Our global business organic sales trends, excluding travel retail, showed sequential improvement. With the strategic reset of our travel retail business well underway, we are confident in our ability to return to sales growth in fiscal 2026.”",
            "Organic Net Sales, Non-GAAP1",
            "Diluted Net Earnings Per Common Share $ .44 $ .91 (52) %",
            "Adjusted Diluted Net Earnings Per Common Share, Non-GAAP1,2",
        ]
    )
    assert out is not None
    assert "Organic Net Sales, Non-GAAP1" not in out
    assert "Diluted Net Earnings Per Common Share $ .44" not in out
    assert "Adjusted Diluted Net Earnings Per Common Share" not in out
    assert "delivered our organic sales outlook" in out
    assert "return to sales growth in fiscal 2026" in out


def test_final_cleanup_trims_trailing_bare_units():
    # eBay-style: a Highlights section serves its bullets, then the
    # next section's bare units declaration lands at the very end.
    body = (
        "eBay Inc. Reports Second Quarter 2025 Results\n\n"
        "•Revenue was $2.7 billion, up 6% on an as-reported basis and up 4% on an FX-Neutral basis.\n\n"
        "•GMV was $19.5 billion, up 6% on an as-reported basis and up 4% on an FX-Neutral basis.\n\n"
        "•Returned $759 million to stockholders, including $625 million of share repurchases.\n\n"
        "Second Quarter\n\n"
        "in millions, except per share data and percentages"
    )
    out = _clean_highlights_result(body)
    assert "in millions, except per share data and percentages" not in out
    assert "Revenue was $2.7 billion" in out
    assert "Returned $759 million" in out
    # The capital form trims the same way (Visa-style).
    body2 = body.replace(
        "in millions, except per share data and percentages",
        "In billions, except percentages and per share data.",
    )
    out2 = _clean_highlights_result(body2)
    assert "In billions, except percentages and per share data." not in out2
    # A body that is only the units line stays (the 200-char floor).
    assert _clean_highlights_result(
        "Headline\n\nin millions, except per share data"
    ).strip().endswith("in millions, except per share data")
