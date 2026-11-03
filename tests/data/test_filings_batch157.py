"""Batch 157 regression tests: horizontal-rule lines and trailing table
stubs are dropped from assembled highlights.

The batch-156 stale-cohort probe surfaced two live-extraction warts that
block repair: Meta's releases carry a 36-underscore rule line between the
Highlights bullets and the footnote plus a dangling "CFO Outlook
Commentary" heading with nothing after it, and Moody's live bodies end
with the next section's heading plus its table-intro sentence after the
bullets. A final cleanup on the assembled result drops rule lines
anywhere and trims a trailing table stub (lone table-intro sentence
and/or heading-shaped line), while the headline itself is never trimmed.
"""

from tickerlens.data.filings import (
    _clean_highlights_result,
    _is_lede_data_row,
    _is_trailing_heading,
    extract_press_release_highlights,
)


def _bare_release_html(*lines: str) -> str:
    # Like tests.data.test_filings._contact_release_html but without the
    # filler paragraph — the fixtures are long enough to clear the
    # 800-char release floor on their own, and filler would be collected
    # into the Highlights section.
    body = "".join(f"<p>{ln}</p>" for ln in lines)
    return f"<html><body>{body}</body></html>"


_META_LINES = (
    "Meta Reports Third Quarter 2025 Results",
    "MENLO PARK, Calif. – October 29, 2025 – Meta Platforms, Inc. (NASDAQ: META) "
    "today reported financial results for the quarter ended September 30, 2025.",
    "Third Quarter 2025 Financial Highlights",
    "•Family daily active people (DAP) – DAP was 3.54 billion on average for "
    "September 2025, an increase of 8% year-over-year.",
    "•Revenue – Revenue was $51.24 billion, an increase of 26% year-over-year. "
    "Revenue on a constant currency basis would have increased 25% year-over-year.",
    "•Cash flow from operating activities was $30.0 billion and free cash flow "
    "was $10.62 billion.",
    "____________________________________",
    '(1) For more information on our free cash flow non-GAAP financial measure, '
    'see the sections entitled "Non-GAAP Financial Measures" in this press release.',
    "CFO Outlook Commentary",
)

_MCO_LINES = (
    "Moody's Corporation Reports Results for Third Quarter 2026",
    "NEW YORK, NY - October 21, 2026 - Moody's Corporation (NYSE: MCO) today "
    "announced results for the third quarter 2026, reaffirmed guidance for "
    "full year 2026, and declared a quarterly dividend of $0.85 per share.",
    "Third Quarter 2026 Highlights",
    "•MCO revenue of $2.0 billion increased 1% from the prior-year period and "
    "3% on an organic constant currency basis.",
    "•MCO's operating margin was 44.8% and MCO's Adjusted Operating Margin "
    "was 52.6%.",
    "•Diluted EPS and Adjusted Diluted EPS increased 18% and 6%, respectively, "
    "from the prior-year period.",
    "•Year-to-date, operating cash flow was $2,471 million, up 21%, and Free "
    "Cash Flow was $2,200 million, up 22%.",
    "Third Quarter 2026 Financial Results",
    "The following table summarizes the key financial performance measures for "
    "the third quarter of 2026.",
)


def test_rule_line_and_dangling_heading_are_dropped() -> None:
    # Batch 157: Meta's rule line and dangling "CFO Outlook Commentary"
    # heading never reach the served body; the bullets survive.
    # Batch 162: the "(1) For more information on our free cash flow ..."
    # footnote-definition line is dropped too — it is a footnote pointer,
    # not a highlight, and the section collector is the one collection
    # path that used to keep it (the lede path has dropped "(1) ..." lines
    # since batch 97). The batch-157 assertion that it survived pinned
    # incidental behavior, not content.
    hl = extract_press_release_highlights(_bare_release_html(*_META_LINES))
    assert hl is not None
    assert "____" not in hl
    assert "CFO Outlook Commentary" not in hl
    assert "Family daily active people" in hl
    assert "For more information on our free cash flow" not in hl


def test_trailing_heading_and_table_intro_pair_are_dropped() -> None:
    # Batch 157: Moody's next-section heading plus its table-intro
    # sentence trail the bullets and are both trimmed; the bullets stay.
    hl = extract_press_release_highlights(_bare_release_html(*_MCO_LINES))
    assert hl is not None
    assert "Third Quarter 2026 Financial Results" not in hl
    assert "The following table summarizes" not in hl
    assert "MCO revenue of $2.0 billion" in hl
    assert "Diluted EPS and Adjusted Diluted EPS" in hl


def test_trailing_heading_predicate() -> None:
    assert _is_trailing_heading("CFO Outlook Commentary")
    assert _is_trailing_heading("First Quarter 2026 Financial Results")
    assert _is_trailing_heading("Recent Investment Activity")
    assert _is_trailing_heading("Additional Financial Highlights:")
    # A quote attribution is dash-led, not a heading.
    assert not _is_trailing_heading(
        "— Rob Fauber, President and Chief Executive Officer, Moody's Corporation"
    )
    # A lowercase-led wrapped prose fragment is not a heading.
    assert not _is_trailing_heading("and other items")
    # Terminated prose never qualifies, however short.
    assert not _is_trailing_heading("We look forward to updating you next quarter.")
    # A metric line carries figures and never qualifies.
    assert not _is_trailing_heading("Revenue $ 51,242 $ 40,589")
    # A truncated headline fragment is heading-shaped (7 capitalized
    # words, unterminated) but ends with "Common", not a section word —
    # it is content, and trimming it plus the banner below it dropped a
    # 248-char Goldman cover result under the 200-char floor. Batch 157.
    assert not _is_trailing_heading(
        "Goldman Sachs Reports Second Quarter Earnings Per Common"
    )
    # Too long to be a heading.
    assert not _is_trailing_heading(
        "This is a long sentence that happens to have no terminal punctuation"
    )


def test_clean_result_never_trims_the_headline() -> None:
    # The headline itself is heading-shaped; a headline-only result is
    # returned untouched.
    assert (
        _clean_highlights_result("Meta Reports Third Quarter 2025 Results")
        == "Meta Reports Third Quarter 2025 Results"
    )
    # A mid-body heading stays: only the trailing stub is trimmed.
    result = _clean_highlights_result(
        "Acme Reports Record Third Quarter 2025 Results\n\n"
        "•Revenue grew 12% to $5.2 billion in the fourth quarter, with "
        "full-year revenue up 11% to $19.8 billion.\n\n"
        "•Net income was $1.4 billion, or $2.10 per diluted share, in the "
        "fourth quarter.\n\n"
        "Financial Targets\n\n"
        "These targets factor in expectation for current macroeconomic "
        "conditions and do not include contributions from pending "
        "acquisitions.\n\n"
        "CFO Outlook Commentary"
    )
    assert "Financial Targets" in result
    assert "These targets factor in" in result
    assert "CFO Outlook Commentary" not in result


def test_clean_result_keeps_multi_sentence_table_intro_line() -> None:
    # Emerson's guidance paragraph opens with the table-intro phrase and
    # continues with real guidance prose in the same flattened line — it
    # is not a lone table-intro sentence and must never be dropped, even
    # at the tail.
    line = (
        "The following table summarizes the fiscal year 2025 guidance framework. "
        "Net and underlying sales guidance of ~3.5% growth reflects our updated "
        "expectations for pricing actions."
    )
    result = _clean_highlights_result(
        "Emerson Reports Third Quarter 2025 Results\n\n" + line
    )
    assert line in result


def test_clean_result_drops_dash_rule_lines() -> None:
    result = _clean_highlights_result(
        "Acme Reports Results\n\n"
        "•Revenue grew 12% to $5.2 billion in the quarter.\n\n"
        "----------\n\n"
        "•Net income was $1.4 billion in the quarter."
    )
    assert "----------" not in result
    assert "Revenue grew 12%" in result
    assert "Net income was $1.4 billion" in result


def test_dollar_less_data_rows_are_data_rows() -> None:
    # Batch 157: the $-presence requirement is gone — $-less
    # guidance/margin rows are table rows, and the density rule is the
    # guard. Emerson's guidance ranges and Moody's repeated period
    # headers are the attested shapes.
    assert _is_lede_data_row("Net Sales Growth (0.5%) - 0.5% 1.5% - 3.5%")
    assert _is_lede_data_row("Underlying Sales Growth 1% - 2% 3% - 5%")
    assert _is_lede_data_row("Margin 14.7% 16.4% 170 bps 11.5% 16.3% 480 bps")
    assert _is_lede_data_row("FY 2024 FY 2024 FY 2024")
    assert _is_lede_data_row("YTD 2024 YTD 2024 YTD 2024")
    # The $-branch: a label + 2 $ figures in a short line is a
    # guidance-table row even under the 40% density bar.
    assert _is_lede_data_row("Restructuring / Related Costs ~$0.06 ~$0.20")
    assert _is_lede_data_row(
        "Acquisition / Divestiture Fees and Related Costs ~$0.01 ~$0.27"
    )
    # Terminated prose never qualifies, however figure-dense.
    assert not _is_lede_data_row("Revenue grew 26% and margins hit 44.3%.")
    # A lone value line is a metric value, not a row.
    assert not _is_lede_data_row("$50.2 billion")
    # A figure-sparse wrapped prose fragment never qualifies.
    assert not _is_lede_data_row(
        "up 8% in the quarter, with margins expanding to 44.3% and"
    )
    # A flattened table mega-line is figure-dense without a $ before its
    # figures, but it is never a lede data row: skipping it swaps one
    # table mega-line for the next (Tesla's FINANCIAL SUMMARY for its
    # OPERATIONAL SUMMARY), so the length cap keeps the old behavior.
    mega = " ".join(
        ["Model 3/Y production 345,454 396,835 435,826 422,652 394,611 14%"] * 6
    )
    assert len(mega) > 80
    assert not _is_lede_data_row(mega)


def test_clean_result_drops_colon_ending_table_intro() -> None:
    # Batch 157: Adobe's targets intro ends with a colon and is still
    # just the table's preamble — the trailing trim drops it, and the
    # "Financial Targets" heading above it becomes trailing and drops too.
    result = _clean_highlights_result(
        "Adobe Reports Record Q3 Results\n\n"
        "•Total Customer Group subscription revenue was $6.56 billion, "
        "which represents 14% year-over-year growth.\n\n"
        "•Business Professionals & Consumers subscription revenue was "
        "$1.91 billion, which represents 16% year-over-year growth.\n\n"
        "Financial Targets\n\n"
        "The following table summarizes Adobe’s fourth quarter FY2026 "
        "targets, which assumes current macroeconomic conditions:"
    )
    assert "The following table summarizes" not in result
    assert "Financial Targets" not in result
    assert "Total Customer Group subscription revenue" in result
