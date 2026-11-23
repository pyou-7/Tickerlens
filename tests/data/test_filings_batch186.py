"""Batch 186 regression tests: AJG orphaned labels below compact period
fragments.

Arthur J. Gallagher flattens its summary-table column headers one cell
per line — "3rd Q 25", "9 Mths 25", "1st Q 26" — and the two
reconciliation labels below them ("Net (gains) losses on
divestitures", "Effective income tax rate impact") survived the lede
loop in 10 quarters (2023-09-30 through 2025-12-31): the bare-period
and period-header predicates never fire on the fragments ("3rd"/"Q"/
"25" are not period words and the year is 2 digits), so the batch-185
flat-table-label prev check refused them and the labels filled the
last lede budget lines, starving the CEO quote. The fix adds the
compact fragment to the header-block disjunction; the second label is
already caught by table-mode residue once the first enters the mode.
The 2026 quarters are a different class (dash-led value rows, not
period fragments) and are unchanged by this batch.
"""
from tickerlens.data.filings import (
    _is_lede_compact_period_fragment,
    _is_lede_flat_table_label,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html

_AJG_LABELS = (
    "Net losses (gains) on divestitures",
    "Net (gains) losses on divestitures",
    "Effective income tax rate impact",
)


def test_compact_period_fragment_shape() -> None:
    for ln in (
        "3rd Q 25",
        "3rd Q 24",
        "9 Mths 25",
        "9 Mths 24",
        "1st Q 26",
        "2nd Q 24",
        "4th Q 23",
        "6 Mths 2024",
        "3rd Q 2025",
    ):
        assert _is_lede_compact_period_fragment(ln), ln


def test_compact_period_fragment_rejects_non_fragments() -> None:
    # A bare quarter, a prose tail, a doubled header, and a full
    # period phrase are not single compact fragments.
    for ln in (
        "3rd Q",
        "Q3 25",
        "3rd Q 25 results",
        "1st Q 26 1st Q 25",
        "Third Quarter 2025",
        "Nine Months Ended September 30,",
        "For the third quarter of 2025",
        "9 Mths",
    ):
        assert not _is_lede_compact_period_fragment(ln), ln


def test_flat_table_label_matches_ajg_labels_below_compact_fragment() -> None:
    for ln in _AJG_LABELS:
        assert _is_lede_flat_table_label(ln, "3rd Q 25"), ln
        assert _is_lede_flat_table_label(ln, "9 Mths 25"), ln
        assert _is_lede_flat_table_label(ln, "1st Q 26"), ln


def test_flat_table_label_still_rejects_label_after_label() -> None:
    # The second AJG label sits below the first, not below a header
    # block — it is caught by table-mode residue in the loop, never by
    # the prev check (the batch-185 wrapped-sub-headline guard).
    assert not _is_lede_flat_table_label(
        "Effective income tax rate impact",
        "Net losses (gains) on divestitures",
    )


def test_ajg_lede_serves_quote_not_labels() -> None:
    # Verbatim AJG Q3 2025 shape (headline, dateline, CFO pointer
    # prose, summary-table heading + compact period fragments +
    # orphaned labels, pretax paragraph, CEO quote): the lede must
    # serve the quote, not the labels. The pretax paragraph's wrapped
    # lines are table-mode residue (unterminated) and its terminated
    # tail ends the mode — the tail line is a known wart, recorded in
    # the batch notes; the quote is the content that matters.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "ARTHUR J. GALLAGHER & CO. ANNOUNCES THIRD QUARTER 2025 "
            "FINANCIAL RESULTS",
            "ROLLING MEADOWS, IL, October 30, 2025 — Arthur J. "
            "Gallagher & Co. (NYSE: AJG) today reported its financial "
            "results for the quarter ended September 30, 2025.",
            "“CFO Commentary” and “Supplemental Quarterly Data,” which "
            "may also be referenced during the call, please visit "
            "ajg.com/IR. These documents contain both GAAP and non-GAAP",
            "measures. Investors and other users of this information "
            "should read carefully the section entitled “Information "
            "Regarding Non-GAAP Measures” beginning on page 9.",
            "Summary of Financial Results - Third Quarter",
            "Revenues Before",
            "3rd Q 25",
            "3rd Q 24",
            "3rd Q 25",
            "3rd Q 24",
            "3rd Q 25",
            "3rd Q 24",
            "Net losses (gains) on divestitures",
            "Effective income tax rate impact",
            "Risk Management, as adjusted *",
            "Total Company, as adjusted *",
            "For third quarter 2025, the pretax impact of the Brokerage "
            "segment adjustments totals $376.8 million,",
            "mostly due to non-cash period expenses related to "
            "intangible amortization, with a corresponding adjustment "
            "to the provision for income taxes.",
            "“We had a terrific and very active third quarter!” said "
            "J. Patrick Gallagher, Jr., Chairman and CEO. “For our "
            "combined brokerage and risk management segments, we "
            "delivered 20% total revenue growth.”",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0].startswith(
        "ARTHUR J. GALLAGHER & CO. ANNOUNCES THIRD QUARTER 2025"
    )
    assert "We had a terrific and very active third quarter" in hl
    assert "20% total revenue growth" in hl
    assert "Net losses (gains) on divestitures" not in hl
    assert "Effective income tax rate impact" not in hl
    assert "Risk Management, as adjusted" not in hl
