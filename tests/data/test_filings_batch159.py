"""Batch 159 regression tests: diluted-density table rows and table-title
lines no longer leak into the lede.

The batch-159 probe found two lede leaks on live releases. Aon's table
carries a two-figure row whose 4-word label dilutes figure density to
33% ("Organic revenue growth (Non-GAAP) 6% 6%"), below the 40% bar in
_is_lede_data_row, so the row rode the lede between the dateline and the
real bullets. Southern Company's release puts a non-GAAP table after two
good prose paragraphs: its title line ("Non-GAAP Financial Measures
Three Months Ended September") matches no table predicate, and its
header row and "(2)" rows dilute below 40% too, so the table filled the
rest of the 6-line lede budget. The fix adds a $-less short-row branch
(>=2 figures, >=25% density, ends in a figure) and a table-title break
in the lede loop.
"""

from tickerlens.data.filings import (
    _is_lede_data_row,
    _is_lede_table_title,
    extract_press_release_highlights,
)


def _bare_release_html(*lines: str) -> str:
    # Like tests.data.test_filings._contact_release_html but without the
    # filler paragraph — the fixtures are long enough to clear the
    # 800-char release floor on their own, and filler would be collected
    # into the Highlights section.
    body = "".join(f"<p>{ln}</p>" for ln in lines)
    return f"<html><body>{body}</body></html>"


def test_diluted_density_rows_are_data_rows() -> None:
    # Batch 159: $-less rows whose label runs 3-4 words dilute density
    # below the 40% bar but are still table rows.
    assert _is_lede_data_row("Organic revenue growth (Non-GAAP) 6% 6%")
    assert _is_lede_data_row(
        "Net Income – Excluding Items (in millions) 2024 2023 2024 2023"
    )
    assert _is_lede_data_row("Acquisition and Disposition Impacts — (2) — (2)")
    assert _is_lede_data_row("Tax Impact — 1 — 1")


def test_diluted_density_branch_keeps_prose_out() -> None:
    # Terminated prose never qualifies; a wrapped fragment ending on a
    # word (not a figure) never qualifies; a $-carrying prose fragment
    # with only one $ figure never qualifies.
    assert not _is_lede_data_row("Revenue grew 10 percent in fiscal 2025.")
    assert not _is_lede_data_row(
        "Service revenue for the three months ended September 30, 2024 "
        "was $238.3 million"
    )
    assert not _is_lede_data_row("revenue of $94.9 billion, up 6 percent year over")
    assert not _is_lede_data_row("EPS of $2.40, up 10 percent in fiscal 2025")
    assert not _is_lede_data_row("Organic revenue growth (Non-GAAP)")
    # A comparison clause is prose, not a row (Kinder Morgan's EPS
    # summary line — its figures would otherwise clear the new branch).
    assert not _is_lede_data_row(
        "Earnings per share (EPS) up 23% versus Q2 2024; Adjusted EPS up 12%"
    )
    assert not _is_lede_data_row(
        "2025 Earnings per share (EPS) 17% greater than 2024; Adjusted EPS up 13%"
    )
    assert not _is_lede_data_row(
        "Earnings per share (EPS) 38% greater than 2025; Adjusted EPS up 41%"
    )


def test_lede_table_title_predicate() -> None:
    assert _is_lede_table_title(
        "Non-GAAP Financial Measures Three Months Ended September"
    )
    assert _is_lede_table_title("Financial Summary Nine Months Ended September")
    # A figure (year/day/value) means a header row or prose, not a title.
    assert not _is_lede_table_title("Three Months Ended December 31,")
    assert not _is_lede_table_title("Fourth Quarter 2024")
    assert not _is_lede_table_title(
        "Non-GAAP Financial Measures Three Months Ended September 30, 2024."
    )
    # Plain "summary"/"results" prose without table vocabulary fails.
    assert not _is_lede_table_title(
        "A summary of results for the three months ended"
    )
    # Bullet-led lines never qualify.
    assert not _is_lede_table_title(
        "•Financial summary for the three months ended"
    )


_SO_LINES = (
    "Southern Company reports third-quarter 2024 earnings",
    "ATLANTA – Southern Company today reported third-quarter earnings of "
    "$1.5 billion, or $1.40 per share, in 2024 compared with earnings of "
    "$1.4 billion, or $1.30 per share, in the third quarter of 2023. For "
    "the nine months ended September 30, 2024, Southern Company reported "
    "earnings of $3.9 billion, or $3.53 per share, compared with $3.1 "
    "billion, or $2.86 per share, for the same period in 2023.",
    "Excluding the items described under “Net Income – Excluding Items” in "
    "the table below, Southern Company earned $1.6 billion, or $1.43 per "
    "share, during the third quarter of 2024, compared with $1.5 billion, "
    "or $1.42 per share, during the third quarter of 2023. For the nine "
    "months ended September 30, 2024, excluding these items, Southern "
    "Company earned $3.9 billion, or $3.56 per share, compared with $3.3 "
    "billion, or $3.01 per share, for the same period in 2023.",
    "Non-GAAP Financial Measures Three Months Ended September",
    "Year-to-Date",
    "September",
    "Net Income – Excluding Items (in millions) 2024 2023 2024 2023",
    "Net Income – As Reported $ 1,535 $ 1,422 $ 3,867 $ 3,121",
    "Less:",
    "Estimated Loss on Plants Under Construction (3) (166) 11 (171)",
    "Tax Impact 1 42 (16) 43",
    "Acquisition and Disposition Impacts — (2) — (2)",
    "NOTE: For more information regarding these non-GAAP adjustments, see "
    "the footnotes accompanying the Financial Highlights page of the release.",
)


def test_table_title_ends_lede_before_table() -> None:
    # Batch 159: the lede stops at the table title — the two prose
    # paragraphs survive and no table line reaches the served body.
    hl = extract_press_release_highlights(_bare_release_html(*_SO_LINES))
    assert hl is not None
    assert "third-quarter earnings of $1.5 billion" in hl
    assert "earned $1.6 billion, or $1.43 per share" in hl
    assert "Non-GAAP Financial Measures" not in hl
    assert "Excluding Items (in millions)" not in hl
    assert "Less:" not in hl
    assert "Acquisition and Disposition Impacts" not in hl


_AON_LINES = (
    "Aon Reports Fourth Quarter and Full Year 2024 Results",
    "DUBLIN - January 31, 2025 - Aon plc (NYSE: AON) today reported results "
    "for the three and twelve months ended December 31, 2024.",
    "Fourth Quarter 2024",
    "Full Year 2024",
    "2024 2023 Change 2024 2023 Change",
    "Total revenue $4,147 $3,375 23% $15,698 $13,376 17%",
    "Organic revenue growth (Non-GAAP) 6% 6%",
    "Operating margin 26.3% 23.1% 24.4% 28.3%",
    "Diluted EPS $3.28 $2.47 33% $12.49 $12.51 —%",
    "•We closed the year with another strong quarter of performance and "
    "delivered an outstanding full year 2024, with 6% Organic revenue "
    "growth, strong margins, double-digit adjusted EPS growth and $2.8 "
    "billion of Free Cash Flow, with NFP performing inline or better than "
    "our business case.",
    "•We are introducing 2025 guidance that positions Aon to continue its "
    "long-term track record of delivering mid-single-digit or greater "
    "Organic revenue growth, adjusted margin expansion, strong adjusted "
    "EPS growth and double-digit Free Cash Flow growth.",
    "•Our 2025 Free Cash Flow generation is expected to enable us to "
    "execute our capital allocation model, including meeting our leverage "
    "objective in Q4’25, investing in organic growth and tuck-in M&A, and "
    "returning capital to shareholders, including $1 billion in share "
    "repurchases.",
    "“We ended 2024 with another quarter of strong performance and "
    "outstanding execution across all aspects of our strategy,” said Greg "
    "Case, CEO. “We generated 6% Organic revenue growth for the fourth "
    "quarter and full year, with mid-single digit growth or better across "
    "all our solution lines.”",
)


def test_diluted_table_row_does_not_reach_lede() -> None:
    # Batch 159: the diluted-density row between the dateline and the
    # bullets is skipped; the bullets and the CEO quote are served.
    hl = extract_press_release_highlights(_bare_release_html(*_AON_LINES))
    assert hl is not None
    assert "Organic revenue growth (Non-GAAP) 6% 6%" not in hl
    assert "Total revenue $4,147" not in hl
    assert "We closed the year with another strong quarter" in hl
    assert "We are introducing 2025 guidance" in hl
    assert "We ended 2024 with another quarter of strong performance" in hl


_TITLE_FIRST_LINES = (
    "Example Corp Reports Third Quarter 2025 Results",
    "Financial Summary Three Months Ended September",
    "Total revenue $1,234 $1,100 12% $3,400 $3,100 10%",
    "Net income $123 $110 12% $340 $310 10%",
    "•Revenue grew 12% year over year, driven by strong demand across all "
    "segments and continued momentum in the subscription business, with "
    "record net new customer additions in the quarter and expanding "
    "international contribution from new markets entered earlier in the "
    "year, more than offsetting currency headwinds in the period.",
    "•Net income margin expanded to 10% as operating leverage improved "
    "and cost discipline held, with adjusted earnings per share of $1.23 "
    "up 12% from $1.10 in the prior-year quarter, and free cash flow of "
    "$400 million funding both the dividend and continued buybacks under "
    "the board authorization.",
)


def test_table_title_before_any_content_is_skipped_not_breaking() -> None:
    # Batch 159: a table title before any lede content is skipped, not a
    # break — the bullets after the table are still collected.
    hl = extract_press_release_highlights(_bare_release_html(*_TITLE_FIRST_LINES))
    assert hl is not None
    assert "Financial Summary Three Months Ended September" not in hl
    assert "Total revenue $1,234" not in hl
    assert "Revenue grew 12% year over year" in hl
    assert "Net income margin expanded to 10%" in hl
