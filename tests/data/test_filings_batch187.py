"""Batch 187 regression tests: AJG 2026 dash-led table value rows.

Arthur J. Gallagher's 2026 summary tables flatten each adjustment
row as a label line plus a values line, and the values line starts
with dash cells for the empty revenue columns — "– – 65 33 87 44
0.25 0.13" (Q1 2026), "— — 84 30 113 41 0.33 0.12" (Q2 2026).
_BULLET_LEAD_RE matches the dash lead, so the batch-175 bullet guard
in _is_lede_data_row exempted the whole row, which in turn kept its
label from _is_lede_table_label (the next line was not a data row).
Both the label and the values then filled the 6-line lede budget as
fake bullets, starving the CEO quote — the whole 2026 lede was table
chrome. The fix recognizes a dash-led wordless line of dash
placeholders and figures as a data row (_is_lede_dash_value_row),
exempt from the bullet guard.
"""
from tickerlens.data.filings import (
    _is_lede_dash_value_row,
    _is_lede_data_row,
    _is_lede_table_label,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html


def test_dash_value_row_shape() -> None:
    for ln in (
        "– – 65 33 87 44 0.25 0.13",
        "— — 84 30 113 41 0.33 0.12",
        "– – 20 14 27 18 0.08 0.05",
        "– – – 1 – – – –",
        "– 57 – 13 – 19 – 0.05",
        "– – 1 1 1 2 – –",
        "– – 201 152 – – 0.77 0.59",
        "– 1 — (7) — (9) — (0.03)",
        "– – (130) (128) (61) (99) (0.50) (0.49)",
        "– 65 33",
    ):
        assert _is_lede_dash_value_row(ln), ln
        assert _is_lede_data_row(ln), ln


def test_dash_value_row_rejects_non_rows() -> None:
    # A real bullet carries words; a dashes-only line is a lone
    # marker; a terminated line is prose; a figure-less dash line is
    # not a value row; a word-led line is not dash-led.
    for ln in (
        "– Revenue grew 28% in the quarter",
        "— Our organic growth of 5% reflected strong retention",
        "– – – –",
        "– – 65 33.",
        "– –",
        "65 33 87 44 0.25 0.13",
        "Brokerage, as adjusted 4,286 3,365 1,233 1,050",
        "– N/A 65 33",
    ):
        assert not _is_lede_dash_value_row(ln), ln


def test_table_label_matches_above_dash_value_row() -> None:
    # The label line above a dash value row is a table label now
    # that the next line counts as a data row (batch-160 check).
    for label in (
        "Acquisition integration",
        "Workforce and lease termination",
        "Acquisition related adjustments",
        "Amortization of intangible assets",
        "Effective income tax rate impact",
        "Levelized foreign currency translation",
    ):
        assert _is_lede_table_label(
            label, "– – 65 33 87 44 0.25 0.13"
        ), label


def test_dash_value_row_not_a_bullet_anymore() -> None:
    # The batch-175 bullet guard must not exempt a wordless dash
    # row: the guard exists for figure-dense BULLETS (Trane's
    # Wingdings "l" EPS bullet), and a dash row carries no words.
    assert _is_lede_data_row("– – 65 33 87 44 0.25 0.13")
    assert not _is_lede_data_row(
        "l GAAP continuing EPS of $3.43; adjusted continuing EPS* "
        "of $3.37, up 21 percent"
    )


def test_ajg_2026_lede_serves_quote_not_table() -> None:
    # Verbatim AJG Q1 2026 shape (headline, dateline, summary-table
    # heading + column-header fragments + label/value rows, pretax
    # paragraph, CEO quote): the lede must serve the pretax prose
    # and the quote, not the table's labels and dash value rows.
    # The two table header lines ("Summary of Financial Results -
    # First Quarter", "Net Earnings (Loss) EBITDAC Diluted Net
    # Earnings") are dropped by batch 188, not this one — the
    # "(Loss)" paren token defeats the table-header capital-led
    # check and the title line carries no "ended" period phrase —
    # and are asserted absent in test_filings_batch188.py. The
    # dateline carries the webcast conference-call sentence, as
    # the real release does, so the loop skips it (batch 188: a
    # bare dateline collected as content would make the table-title
    # branch break instead of skipping).
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
            "Workforce and lease termination",
            "– – 20 14 27 18 0.08 0.05",
            "Acquisition related adjustments",
            "– – 39 25 50 30 0.15 0.09",
            "Amortization of intangible assets",
            "– – 201 152 – – 0.77 0.59",
            "Effective income tax rate impact",
            "– – – 1 – – – –",
            "Levelized foreign currency translation",
            "– 57 – 13 – 19 – 0.05",
            "Brokerage, as adjusted 4,286 3,365 1,233 1,050 1,719 "
            "1,456 4.74 4.02",
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
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0].startswith(
        "ARTHUR J. GALLAGHER & CO. ANNOUNCES FIRST QUARTER 2026"
    )
    assert "pretax impact of adjustments" in hl
    assert "We had a terrific first quarter" in hl
    assert "revenue growth of 28%" in hl
    assert "Acquisition integration" not in hl
    assert "Workforce and lease termination" not in hl
    assert "Acquisition related adjustments" not in hl
    assert "Amortization of intangible assets" not in hl
    assert "Effective income tax rate impact" not in hl
    assert "Levelized foreign currency translation" not in hl
    assert "65 33 87 44 0.25 0.13" not in hl
    assert "20 14 27 18 0.08 0.05" not in hl
    assert "201 152" not in hl
