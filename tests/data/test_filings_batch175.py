"""Batch 175: Trane's Wingdings "l" bullets and bare-dollar units line.

Trane Technologies renders its highlight bullets as a Wingdings "l"
glyph (<font face="Wingdings">l</font>), which flattens to a lone "l"
("l Reported revenues of $5.4 billion ..."). _BULLET_LEAD_RE did not
recognize "l ", so the bullets were invisible to every bullet guard:
the Highlights section collector ran past them, and the summary-table
units line ("$, millions except EPS Q3 2024 Q3 2023 ...") matched
neither units regex (both require a paren), so the section ran through
the table and served its data rows as highlights (5 TT quarters). The
figure-dense EPS bullet ("l GAAP continuing EPS of $3.43; adjusted
continuing EPS* of $3.37, up 21 percent") was also misflagged as a data
row by _is_lede_data_row's $-figures branch, because that predicate had
no bullet exemption (unlike _is_lede_table_line).

Fixes: "l " joins _BULLET_LEAD_RE (space required, so a line starting
with the letter "l" as a word never matches); _TABLE_UNITS_RE gains
the bare-dollar form ("$, millions|thousands|billions"); and
_is_lede_data_row exempts bullet-led lines outright.
"""
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _BULLET_LEAD_RE,
    _TABLE_UNITS_RE,
    _is_lede_data_row,
    _is_lede_table_label,
    extract_press_release_highlights,
)


def test_wingdings_l_bullet_matches():
    assert _BULLET_LEAD_RE.match("l Reported revenues of $5.4 billion")
    assert _BULLET_LEAD_RE.match("l GAAP continuing EPS of $3.43")
    # The space is required: a line starting with the letter "l" glued
    # to a word is prose, not a bullet.
    assert not _BULLET_LEAD_RE.match("lower revenue grew 5%")
    assert not _BULLET_LEAD_RE.match("l")
    # The existing glyphs and hyphen are untouched.
    assert _BULLET_LEAD_RE.match("\u2022Record sales of $4.04 billion")
    assert _BULLET_LEAD_RE.match("- Record sales of $4.04 billion")
    assert not _BULLET_LEAD_RE.match("-$1,234")


def test_bare_dollar_units_line_matches():
    assert _TABLE_UNITS_RE.search(
        "$, millions except EPS Q3 2024 Q3 2023 Y-O-Y Change Organic Y-O-Y Change"
    )
    assert _TABLE_UNITS_RE.search("$, thousands except per share amounts")
    assert _TABLE_UNITS_RE.search("$, billions")
    # The parenthesized form still matches.
    assert _TABLE_UNITS_RE.search("(Dollars in millions)")
    assert _TABLE_UNITS_RE.search("($ in millions)")
    # A prose $ line is not a units line.
    assert not _TABLE_UNITS_RE.search("Reported revenues of $5.4 billion")
    assert not _TABLE_UNITS_RE.search("$5,213 $4,946 5% 5%")


def test_lede_data_row_exempts_bullets():
    # Trane's EPS bullet: 2 $ figures in 78 chars trips the $-figures
    # branch without the exemption.
    assert not _is_lede_data_row(
        "l GAAP continuing EPS of $3.43; adjusted continuing EPS* of $3.37, up 21 percent"
    )
    assert not _is_lede_data_row(
        "\u2022Reported 2024 earnings of $5.39 per share, compared to $4.90 per share in 2023"
    )
    # A real data row still qualifies.
    assert _is_lede_data_row("Bookings $5,213 $4,946 5% 5%")
    assert _is_lede_data_row("Net Revenues $5,441 $4,883 11% 11%")
    assert _is_lede_data_row("Restructuring / Related Costs ~$0.06 ~$0.20")


def test_table_label_needs_a_values_row_not_a_bullet():
    # A subtitle above a figure-dense bullet is not a table label: the
    # bullet below it is content, not a values row. (Batch 175 blast:
    # AWK's "CEO HARDWICK TO RETIRE ..." subtitle and Carrier's "Signed
    # LTAs ..." subtitle are now served instead of being skipped as
    # labels above bullets misread as data rows.)
    assert not _is_lede_table_label(
        "CEO HARDWICK TO RETIRE IN MAY; GRIFFITH TO ASSUME CEO ROLE",
        "\u2022Reported 2024 earnings of $5.39 per share, compared to $4.90 per share in 2023",
    )
    # A genuine label above a values row still qualifies.
    assert _is_lede_table_label(
        "Property-Liability combined ratio",
        "Recorded 96.4 103.4 (7.0) 96.9 109.8 (12.9)",
    )


def _extract(body_lines):
    body = "".join(f"<p>{ln}</p>" for ln in body_lines)
    return extract_press_release_highlights(
        f"<html><body>{body}<h2>About Acme</h2><p>Boilerplate.</p></body></html>"
    )


def test_trane_style_release_serves_bullets_not_table():
    out = _extract(
        [
            "Trane Technologies Reports Strong Third Quarter Results and Raises 2024 Revenue and EPS Guidance",
            "l Reported revenues of $5.4 billion, up 11 percent; organic revenues* up 11 percent",
            "l GAAP operating margin up 110 bps; adjusted operating margin* up 90 bps",
            "l Adjusted EBITDA margin* of 20.7 percent, up 120 bps",
            "l GAAP continuing EPS of $3.43; adjusted continuing EPS* of $3.37, up 21 percent",
            "l Continued strong bookings of $5.2 billion, up 5 percent",
            "SWORDS, Ireland, October 30, 2024 - Trane Technologies plc (NYSE:TT), a global climate innovator, today reported diluted earnings per share (EPS) from continuing operations of $3.43 for the third quarter of 2024. Adjusted continuing EPS was $3.37, up 21 percent.",
            "Third-Quarter 2024 Results",
            "Financial Comparisons - Third-Quarter Continuing Operations",
            "$, millions except EPS Q3 2024 Q3 2023 Y-O-Y Change Organic Y-O-Y Change",
            "Bookings $5,213 $4,946 5% 5%",
            "Net Revenues $5,441 $4,883 11% 11%",
            "GAAP Operating Income $819 $634 29%",
        ]
    )
    assert out is not None
    for bullet in (
        "l Reported revenues of $5.4 billion",
        "l GAAP operating margin up 110 bps",
        "l Adjusted EBITDA margin* of 20.7 percent",
        "l GAAP continuing EPS of $3.43; adjusted continuing EPS* of $3.37",
        "l Continued strong bookings of $5.2 billion",
    ):
        assert bullet in out
    # The summary table never reaches the highlights: neither its units
    # line nor any data row.
    assert "$, millions except EPS" not in out
    assert "Bookings $5,213" not in out
    assert "Net Revenues $5,441" not in out
    assert "GAAP Operating Income $819" not in out
