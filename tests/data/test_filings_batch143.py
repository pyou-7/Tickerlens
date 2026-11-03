"""Batch 143 regression tests: flattened-cell "Financial Highlights" tables
must not win the highlights section — the lede fallback serves instead.

Three stored table shapes escaped the batch-97 guard, which only saw
"(Dollars|USD|$" unit lines, "% change" wording, and $+% data rows on a
single line:
- FedEx: "(In millions, except earnings per share)" units in words,
  a "Percent Change" header in words, and period headers ("Three
  Months Ended") with split year cells.
- Simon Q1: every cell on its own line ("$", "1,757,093", "$",
  "1,473,012", ...) — no % anywhere, no units line at all.
- AutoZone: a count-only "Store Count" table — no $ or % anywhere,
  just "Beginning stores 6,627 6,432" rows under a doubled
  "12 Weeks Ended" header.
"""

from tickerlens.data.filings import (
    _looks_like_financial_table,
    extract_press_release_highlights,
)


def test_fedex_shaped_table_rejected() -> None:
    # FedEx Q1 2025 "FEDEX CORP. FINANCIAL HIGHLIGHTS": units in words,
    # "Percent Change" in words, period header, split year cells.
    assert _looks_like_financial_table(
        [
            "First Quarter Fiscal 2025",
            "(In millions, except earnings per share)",
            "(Unaudited)",
            "Three Months Ended",
            "August 31,",
            "2024",
            "2023",
            "Percent Change",
            "Revenue:",
            "Federal Express segment",
            "$",
            "18,305",
        ]
    )


def test_simon_shaped_split_cell_table_rejected() -> None:
    # Simon Q1 2026 "Financial Highlights": every cell on its own line.
    assert _looks_like_financial_table(
        [
            "Total Revenue – Consolidated Properties",
            "$",
            "1,757,093",
            "$",
            "1,473,012",
            "Consolidated Net Income",
            "$",
            "568,535",
            "$",
            "477,860",
            "Net Income Attributable to Common Stockholders",
            "$",
        ]
    )


def test_autozone_shaped_count_table_rejected() -> None:
    # AutoZone "Selected Operating Highlights" store-count table: no $
    # or % anywhere, just a doubled period header and label + number rows.
    assert _looks_like_financial_table(
        [
            "Store Count & Square Footage",
            "12 Weeks Ended 12 Weeks Ended",
            "November 22, 2025 November 23, 2024",
            "Domestic:",
            "Beginning stores 6,627 6,432",
            "Stores opened 39 23",
            "Stores closed - -",
            "Ending domestic stores 6,666 6,455",
            "Relocated stores 3 2",
            "Stores with commercial programs 6,182 5,935",
            "Square footage (in thousands) 44,433 42,844",
            "Mexico:",
        ]
    )


def test_fedex_header_only_stub_rejected() -> None:
    # FedEx FY2026 Q2/Q3 "FINANCIAL HIGHLIGHTS": the section that
    # survives the first pass is six header lines and no data rows —
    # a standalone "(Unaudited)", a doubled period header, date lines
    # ending in "Percent", and a lone "Change" line. Five cells.
    assert _looks_like_financial_table(
        [
            "Second Quarter Fiscal 2026",
            "(Unaudited)",
            "Three Months Ended Six Months Ended",
            "November 30, 2025 November 30, 2024 Percent",
            "Change November 30, 2025 November 30, 2024 Percent",
            "Change",
        ]
    )


def test_single_unaudited_line_does_not_condemn_prose() -> None:
    # One header-fragment line among prose is not a table: the 3-cell
    # threshold needs company, not a single stray annotation.
    assert not _looks_like_financial_table(
        [
            "Revenue rose to $4.6 billion for the quarter, driven by",
            "broad-based growth across the domestic store base.",
            "(Unaudited)",
            "Management expects continued momentum into the next quarter",
            "as new store openings and commercial programs expand.",
        ]
    )


def test_doubled_date_header_is_not_a_count_row() -> None:
    # "November 22, 2025 November 23, 2024" ends in two numbers but is a
    # date header, not a data row — the month-name guard keeps it from
    # counting toward the 3-cell threshold on its own.
    assert not _looks_like_financial_table(
        [
            "November 22, 2025 November 23, 2024",
            "Domestic:",
        ]
    )


def test_mid_sentence_units_in_words_not_a_table() -> None:
    # An anchored word-units check: "(in millions)" mid-sentence in
    # narrative prose is not a units header line.
    assert not _looks_like_financial_table(
        [
            "Revenue rose to $4.6 billion (in millions, except per share",
            "data) for the quarter, driven by broad-based growth across",
            "the domestic store base and continued commercial momentum.",
        ]
    )


def test_genuine_narrative_section_not_a_table() -> None:
    assert not _looks_like_financial_table(
        [
            "Record sales of $4.04 billion, up 26 percent in the quarter",
            "driven by volume growth across the portfolio and strong",
            "demand in the industrial and construction markets.",
            "Operating margin expanded to 20.3 percent on pricing and",
            "productivity gains, partly offset by higher input costs.",
        ]
    )


def test_fedex_like_doc_serves_lede_not_table() -> None:
    html = """<html><body>
<p>EX-99.1</p>
<h1>FedEx Reports First Quarter Diluted EPS of $3.21 and Adjusted Diluted EPS of $3.60</h1>
<p>FedEx Seamlessly Transitioned to One FedEx at the Start of Fiscal 2025</p>
<p>$1 Billion Share Repurchase Completed During Quarter</p>
<p>MEMPHIS, Tenn., September 19, 2024 ... FedEx Corp. (NYSE: FDX) today reported the following consolidated results for the first quarter ended August 31, with revenue growth across all segments and continued progress on cost reduction initiatives under the DRIVE program, including network optimization, improved service levels for customers, and continued investment in automation across the network.</p>
<h2>FEDEX CORP. FINANCIAL HIGHLIGHTS</h2>
<p>First Quarter Fiscal 2025</p>
<p>(In millions, except earnings per share)</p>
<p>(Unaudited)</p>
<p>Three Months Ended</p>
<p>August 31,</p>
<p>2024</p>
<p>2023</p>
<p>Percent Change</p>
<p>Revenue:</p>
<p>Federal Express segment</p>
<p>$</p>
<p>18,305</p>
</body></html>"""
    result = extract_press_release_highlights(html)
    assert result is not None
    assert "FedEx Reports First Quarter Diluted EPS" in result
    assert "Federal Express segment" not in result
    assert "18,305" not in result
    assert "MEMPHIS, Tenn., September 19, 2024" in result


def test_simon_like_doc_serves_lede_not_table() -> None:
    html = """<html><body>
<p>EX-99.1</p>
<h1>Simon Reports First Quarter 2026 Results, Increases Full Year 2026 Real Estate FFO Per Share Guidance</h1>
<p>INDIANAPOLIS, May 11, 2026 – Simon, a real estate investment trust engaged in the ownership of premier shopping, dining, entertainment and mixed-use destinations, today reported results for the quarter ended March 31, 2026, with occupancy gains and rent growth across its portfolio of premier properties.</p>
<p>We are very pleased with our first-quarter results, said Eli Simon, Chief Executive Officer, with strong operating performance supported by continued leasing momentum across the portfolio and new retailer openings in key markets.</p>
<h2>Financial Highlights</h2>
<p>Total Revenue – Consolidated Properties</p>
<p>$</p>
<p>1,757,093</p>
<p>$</p>
<p>1,473,012</p>
<p>Consolidated Net Income</p>
<p>$</p>
<p>568,535</p>
<p>$</p>
<p>477,860</p>
<p>Net Income Attributable to Common Stockholders</p>
<p>$</p>
</body></html>"""
    result = extract_press_release_highlights(html)
    assert result is not None
    assert "Simon Reports First Quarter 2026 Results" in result
    assert "1,757,093" not in result
    assert "INDIANAPOLIS, May 11, 2026" in result


def test_autozone_like_doc_serves_lede_not_table() -> None:
    html = """<html><body>
<p>EX-99.1</p>
<h1>AutoZone 1st Quarter Total Company Same Store Sales Increase 4.7%; 1st Quarter EPS of $31.04</h1>
<p>MEMPHIS, Tenn., Dec. 09, 2025 (GLOBE NEWSWIRE) -- AutoZone, Inc. (NYSE: AZO) today reported net sales of $4.6 billion for its first quarter (12 weeks) ended November 22, 2025, an increase of 8.2% from the first quarter of fiscal 2025.</p>
<p>For the quarter, gross profit increased on higher sales and improved merchandise margins across domestic and international stores.</p>
<h2>Selected Operating Highlights</h2>
<p>Store Count &amp; Square Footage</p>
<p>12 Weeks Ended 12 Weeks Ended</p>
<p>November 22, 2025 November 23, 2024</p>
<p>Domestic:</p>
<p>Beginning stores 6,627 6,432</p>
<p>Stores opened 39 23</p>
<p>Stores closed - -</p>
<p>Ending domestic stores 6,666 6,455</p>
<p>Relocated stores 3 2</p>
<p>Stores with commercial programs 6,182 5,935</p>
<p>Square footage (in thousands) 44,433 42,844</p>
<p>Mexico:</p>
</body></html>"""
    result = extract_press_release_highlights(html)
    assert result is not None
    assert "AutoZone 1st Quarter Total Company Same Store Sales" in result
    assert "Beginning stores 6,627 6,432" not in result
    assert "MEMPHIS, Tenn., Dec. 09, 2025" in result
