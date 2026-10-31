"""Batch 160 regression tests: Allstate's long table rows + label lines +
symbol legend no longer leak into the lede.

The batch-159 follow-up named the ALL long-row lede leak: Allstate's
Consolidated Highlights table flattens two rows past the batch-159
predicates — "Net income (loss) applicable to common shareholders
1,161 (41) NM 2,651 (1,776) NM" (82 chars, 31% density, ends in "NM")
and "Property-Liability insurance premiums earned 13,694 12,270 11.6 %
39,933 35,826 11.5 %" (86 chars, >=40% density) — plus three
figure-less label lines whose values sit on the next line ("Return on
Allstate common shareholders' equity (trailing twelve months)",
"Property-Liability combined ratio", "Total policies in force (in
thousands)"), plus the table's symbol legend ("NM = not meaningful").
The fix raises the $-less data-row caps 80 -> 120 chars, accepts a
trailing "NM" as a figure-like ending, adds a label rule keyed on the
following data row, and treats symbol legends as table residue.
"""

from tickerlens.data.filings import (
    _is_lede_data_row,
    _is_lede_table_label,
    _is_lede_table_line,
    extract_press_release_highlights,
)


def _bare_release_html(*lines: str) -> str:
    # Like tests.data.test_filings._contact_release_html but without the
    # filler paragraph — the fixtures are long enough to clear the
    # 800-char release floor on their own, and filler would be collected
    # into the Highlights section.
    body = "".join(f"<p>{ln}</p>" for ln in lines)
    return f"<html><body>{body}</body></html>"


def test_long_nm_terminated_rows_are_data_rows() -> None:
    # Batch 160: Allstate's 82-char row ends in "NM" at 31% density;
    # its 86-char premiums row is >=40% density — both past the old
    # 80-char cap.
    assert _is_lede_data_row(
        "Net income (loss) applicable to common shareholders "
        "1,161 (41) NM 2,651 (1,776) NM"
    )
    assert _is_lede_data_row(
        "Property-Liability insurance premiums earned 13,694 12,270 "
        "11.6 % 39,933 35,826 11.5 %"
    )
    assert _is_lede_data_row(
        "Net income (loss) applicable to common shareholders "
        "1,899 1,460 30.1 % 4,550 (316) NM"
    )


def test_long_row_cap_still_blocks_mega_lines() -> None:
    # The 120-char cap keeps Tesla's flattened mega-line out: a
    # ~4000-char figure-dense line is still not a data row, and neither
    # is a wrapped prose fragment or a comparison clause.
    mega = " ".join(["Revenue 100 200 300 400"] * 100)
    assert len(mega) > 2000
    assert not _is_lede_data_row(mega)
    assert not _is_lede_data_row(
        "Net income was $2.4 billion in the first quarter of 2026, "
        "compared to $566 million in the prior year quarter"
    )
    assert not _is_lede_data_row(
        "Earnings per share (EPS) up 23% versus Q2 2024; Adjusted EPS up 12%"
    )
    # One figure only is a metric value, not a row — even at 100 chars.
    assert not _is_lede_data_row(
        "Policies in force reached 212 million, reflecting increased "
        "growth in auto and homeowners insurance and Protection Plans"
    )


def test_lede_table_label_predicate() -> None:
    # Batch 160: a figure-less, unterminated line directly above its
    # values row is that row's label.
    assert _is_lede_table_label(
        "Return on Allstate common shareholders’ equity "
        "(trailing twelve months)",
        "Net income (loss) applicable to common shareholders "
        "26.1 % (14.7) % 40.8",
    )
    assert _is_lede_table_label(
        "Property-Liability combined ratio",
        "Recorded 96.4 103.4 (7.0) 96.9 109.8 (12.9)",
    )
    assert _is_lede_table_label(
        "Total policies in force (in thousands)",
        "205,483 190,089 8.1 %",
    )
    # No values row below: a sub-headline above prose is not a label.
    assert not _is_lede_table_label(
        "Property-Liability combined ratio",
        "Third Quarter 2024 Results",
    )
    assert not _is_lede_table_label(
        "Generates excellent returns despite higher catastrophe losses",
        "NORTHBROOK, Ill., October 30, 2024 – The Allstate Corporation "
        "(NYSE: ALL) today reported financial results for the third "
        "quarter of 2024.",
    )
    # Terminated, figure-carrying, and bullet-led lines never qualify.
    assert not _is_lede_table_label(
        "Property-Liability combined ratio was strong.",
        "Recorded 96.4 103.4 (7.0) 96.9 109.8 (12.9)",
    )
    assert not _is_lede_table_label(
        "Property-Liability combined ratio 96.4 103.4",
        "Recorded 96.4 103.4 (7.0) 96.9 109.8 (12.9)",
    )
    assert not _is_lede_table_label(
        "•Property-Liability combined ratio",
        "Recorded 96.4 103.4 (7.0) 96.9 109.8 (12.9)",
    )
    # A wrapped prose fragment carrying a completed sentence is prose,
    # not a label — even directly above a $-figure continuation line
    # (Coinbase Q4 2024: the first blast ate this fragment and served
    # the "[3] $USD resources" footnote instead).
    assert not _is_lede_table_label(
        "majority of which were unrealized. These gains were",
        "$357 million and $514 million after reflecting the tax",
    )


def test_symbol_legend_is_table_residue() -> None:
    # Batch 160: "NM = not meaningful" is the table's symbol legend.
    assert _is_lede_table_line("NM = not meaningful")
    # A prose line that merely contains " = " is not a legend: the
    # symbol must lead the line in all caps.
    assert not _is_lede_table_line(
        "Net income = $566 million in the quarter, lower than last year"
    )


def test_spaced_footnote_glyph_is_table_residue() -> None:
    # Batch 160: Allstate's non-GAAP legend leads with a spaced
    # asterisk ("* Measures used ..."). It is a terminated sentence, so
    # it is caught before the termination gate — like the table-intro
    # sentence above it. A bullet-led line is never table residue.
    assert _is_lede_table_line(
        "* Measures used in this release that are not based on accounting "
        "principles generally accepted in the United States of America "
        "(“non-GAAP”) are denoted with an asterisk."
    )
    assert not _is_lede_table_line("•Revenue grew 12% year over year.")


_ALL_LINES = (
    "Allstate Reports Third Quarter 2024 Results",
    "Generates excellent returns despite higher catastrophe losses",
    "NORTHBROOK, Ill., October 30, 2024 – The Allstate Corporation "
    "(NYSE: ALL) today reported financial results for the third quarter "
    "of 2024.",
    "The Allstate Corporation Consolidated Highlights",
    "Three months ended September 30, Nine months ended September 30,",
    "($ in millions, except per share data and ratios) 2024 2023 % / pts",
    "Change 2024 2023 % / pts",
    "Change",
    "Consolidated revenues $ 16,627 $ 14,497 14.7 % $ 47,600 $ 42,262 12.6 %",
    "Net income (loss) applicable to common shareholders "
    "1,161 (41) NM 2,651 (1,776) NM",
    "per diluted common share (1)",
    "4.33 (0.16) NM 9.91 (6.76) NM",
    "Adjusted net income (loss)* 1,048 214 NM 2,844 (1,290) NM",
    "per diluted common share* (1)",
    "3.91 0.81 NM 10.64 (4.91) NM",
    "Return on Allstate common shareholders’ equity "
    "(trailing twelve months)",
    "Net income (loss) applicable to common shareholders 26.1 % (14.7) % 40.8",
    "Adjusted net income (loss)* 26.1 % (9.7) % 35.8",
    "Common shares outstanding (in millions) 264.8 261.7 1.2 %",
    "Book value per common share $ 70.35 $ 47.79 47.2 %",
    "Consolidated premiums written (2)",
    "$ 15,872 $ 14,425 10.0 % $ 45,589 $ 41,021 11.1 %",
    "Property-Liability insurance premiums earned 13,694 12,270 "
    "11.6 % 39,933 35,826 11.5 %",
    "Property-Liability combined ratio",
    "Recorded 96.4 103.4 (7.0) 96.9 109.8 (12.9)",
    "Underlying combined ratio* 83.2 91.9 (8.7) 85.1 92.7 (7.6)",
    "Catastrophe losses $ 1,703 $ 1,181 44.2 % $ 4,554 $ 5,568 (18.2) %",
    "Total policies in force (in thousands)",
    "205,483 190,089 8.1 %",
    "(1)In periods where a net loss or adjusted net loss is reported, "
    "weighted average shares for basic earnings per share is used for "
    "calculating diluted earnings per share because all dilutive "
    "potential common shares are anti-dilutive and are therefore "
    "excluded from the calculation.",
    "(2)Includes premiums written for the Allstate Protection and "
    "Protection Services segments and premiums and contract charges for "
    "the Health and Benefits segment.",
    "* Measures used in this release that are not based on accounting "
    "principles generally accepted in the United States of America "
    "(“non-GAAP”) are denoted with an asterisk and defined and "
    "reconciled to the most directly comparable GAAP measure in the "
    "“Definitions of Non-GAAP Measures” section of this document.",
    "NM = not meaningful",
    "1",
    "Third Quarter 2024 Results",
    "•Total revenues of $16.6 billion in the third quarter of 2024 were "
    "$2.1 billion or 14.7% above the prior year quarter driven by "
    "increased Property-Liability earned premium.",
    "•Net income applicable to common shareholders was $1.2 billion in "
    "the third quarter of 2024 compared to a net loss of $41 million in "
    "the prior year quarter, as Property-Liability underwriting results "
    "improved. Adjusted net income* was $1.0 billion, or $3.91 per "
    "diluted share, compared to adjusted net income* of $214 million in "
    "the prior year quarter.",
    "“Allstate’s focus on near-term performance while implementing our "
    "long-term growth plan resulted in strong financial returns and an "
    "improved strategic position,” said Tom Wilson, Allstate’s Chair, "
    "CEO and President. “Revenues increased by almost 15% from the "
    "prior year, net income was $1.2 billion for the quarter and "
    "adjusted net income return on equity* was 26.1% for the prior "
    "twelve months. Successful execution of the auto insurance profit "
    "improvement plan benefited results generating $486 million of auto "
    "insurance underwriting income.”",
)


def test_allstate_table_does_not_reach_lede() -> None:
    # Batch 160: the whole Consolidated Highlights table is skipped —
    # long rows, label lines, and the NM legend — and the real bullets
    # and CEO quote after the table are served instead.
    hl = extract_press_release_highlights(_bare_release_html(*_ALL_LINES))
    assert hl is not None
    assert "Total revenues of $16.6 billion in the third quarter" in hl
    assert "Net income applicable to common shareholders was $1.2 billion" in hl
    assert "Allstate’s focus on near-term performance" in hl
    assert "1,161 (41) NM" not in hl
    assert "Property-Liability insurance premiums earned 13,694" not in hl
    assert "Property-Liability combined ratio" not in hl
    assert "Return on Allstate common shareholders’ equity" not in hl
    assert "Total policies in force (in thousands)" not in hl
    assert "NM = not meaningful" not in hl
    assert "Consolidated revenues $ 16,627" not in hl
    assert "Consolidated Highlights" not in hl
