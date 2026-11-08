"""Batch 191: a table-mode paragraph's wrapped head is served with its tail.

Arthur J. Gallagher's pretax paragraph sits inside the summary-table
region: its wrapped head lines are unterminated, so the lede loop skips
them as table-mode residue, and only the terminated tail is served — a
dangling fragment ("income taxes is shown on pages 14 and 15.") with no
subject (batch 186's wrap-tail wart). The fix prepends the skipped head
lines when the tail is collected — budget-neutral, only the tail counts,
so the CEO quote after the paragraph keeps exactly the budget it had.
The naive alternative (lowercase-led terminated lines as residue) would
eat the CEO quote's own wrapped lines, so this helper only ever ADDS
lines, and only the paragraph's own head: the residue run is scanned
back from its end, past the orphaned table labels that precede the
paragraph, and a label can never be the head (it never ends mid-sentence).
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _lede_wrapped_paragraph_head,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

# AJG Q3 2023: the paragraph wraps over four lines, tail on the fifth.
Q3_2023_RUN = [
    "For third quarter 2023, the pretax impact of the Brokerage segment adjustments totals $183.4 million, with",
    "a corresponding adjustment to the provision for income taxes of $45.3 million relating to these items. For third quarter 2023, the pretax impact of the Risk Management se",
    "adjustment to the provision for income taxes of $0.5 million relating to these items. For third quarter 2023, the pretax impact of the Corporate segment adjustments total",
]
Q3_2023_TAIL = (
    "income taxes of $3.4 million relating to these items and the other tax items noted on page 7. "
    "A detailed reconciliation of the 2023 and 2022 provision (benefit) for income taxes is shown on pages 14 and 15."
)

# AJG Q2 2024: a year wrap mid-paragraph ("relating to " / "2024, the pretax ...").
Q2_2024_RUN = [
    "For second quarter 2024, the pretax impact of the Brokerage segment adjustments totals $291.3 million,",
    "mostly due to non-cash period expenses related to intangible amortization, with a corresponding adjustment to the provision for income taxes of $73.7 million relating to ",
    "2024, the pretax impact of the Risk Management segment adjustments totals $1.6 million, with a corresponding adjustment to the provision for income taxes of $0.3 million ",
    "of the Corporate segment adjustments totals $2.8 million, with a corresponding adjustment to the benefit for income taxes of $0.5 million relating to these items. A detai",
]
Q2_2024_TAIL = "income taxes is shown on pages 14 and 15."

# The real residue run also opens with the summary table's orphaned
# labels (batch 185/186): the scan must pass them over and return only
# the paragraph head.
LABELS_THEN_HEAD = [
    "Risk Management, as adjusted *",
    "Corporate related adjustments (see page 7)",
    "Total Company, as adjusted *",
    "Total Brokerage & Risk Management, as reported",
    "Total Brokerage & Risk Management, as adjusted *",
    "For fourth quarter 2023, the pretax impact of the Brokerage segment adjustments totals $559.5 million,",
    "mostly due to non-cash period expenses related to intangible amortization and acquisition earnout payable adjustments, with a corresponding adjustment to the provision for income taxes of $139.2 million",
]
Q4_2023_TAIL = (
    "relating to these items. For fourth quarter 2023, the pretax impact of the Risk Management segment "
    "adjustments totals $4.5 million, with a corresponding adjustment to the provision for income taxes of $1.2 million relating to these items."
)


def test_wrapped_paragraph_head_shapes():
    assert _lede_wrapped_paragraph_head(Q3_2023_RUN, Q3_2023_TAIL) == Q3_2023_RUN
    assert _lede_wrapped_paragraph_head(Q2_2024_RUN, Q2_2024_TAIL) == Q2_2024_RUN
    # A single-line head still joins.
    assert _lede_wrapped_paragraph_head(
        ["For first quarter 2024, the pretax impact of the Brokerage segment adjustments totals $204.7 million,"],
        "mostly due to non-cash period expenses related to intangible amortization, with a corresponding adjustment to the provision for income taxes of $51.6 million relating to these items.",
    ) == ["For first quarter 2024, the pretax impact of the Brokerage segment adjustments totals $204.7 million,"]
    # Orphaned labels ahead of the paragraph are passed over, never joined.
    assert _lede_wrapped_paragraph_head(LABELS_THEN_HEAD, Q4_2023_TAIL) == LABELS_THEN_HEAD[-2:]


def test_wrapped_paragraph_head_negatives():
    # Empty run: the tail stands alone.
    assert _lede_wrapped_paragraph_head([], Q3_2023_TAIL) == []
    # A capital-led tail starts a new paragraph, not a continuation.
    assert _lede_wrapped_paragraph_head(
        Q3_2023_RUN,
        "A detailed reconciliation of the 2023 and 2022 provision for income taxes is shown on pages 14 and 15.",
    ) == []
    # An unterminated tail is not a tail.
    assert _lede_wrapped_paragraph_head(
        Q3_2023_RUN, "income taxes of $3.4 million relating to these items and the other"
    ) == []
    # No capital-led head: the paragraph's true head was consumed by
    # another branch — the wraps alone never join.
    assert _lede_wrapped_paragraph_head(
        ["a corresponding adjustment to the provision for income taxes of $45.3 million relating to these items."],
        Q3_2023_TAIL,
    ) == []
    # A label as the only head candidate: it ends in "*", never
    # mid-sentence, so it is not a paragraph head.
    assert _lede_wrapped_paragraph_head(
        ["Total Brokerage & Risk Management, as adjusted *"],
        Q3_2023_TAIL,
    ) == []
    # A capital-led wrap in the run: a table-label chain, not a paragraph.
    assert _lede_wrapped_paragraph_head(
        [
            "For third quarter 2023, the pretax impact of the Brokerage segment adjustments totals $183.4 million, with",
            "Base Commissions and Fees and Supplemental Revenues",
        ],
        Q3_2023_TAIL,
    ) == []
    # A short wrap line: a table label, not prose.
    assert _lede_wrapped_paragraph_head(
        [
            "For third quarter 2023, the pretax impact of the Brokerage segment adjustments totals $183.4 million, with",
            "Less supplemental revenues",
        ],
        Q3_2023_TAIL,
    ) == []
    # A terminated wrap line: a heading or a complete sentence, not a wrap.
    assert _lede_wrapped_paragraph_head(
        [
            "For third quarter 2023, the pretax impact of the Brokerage segment adjustments totals $183.4 million, with",
            "a corresponding adjustment to the provision for income taxes of $45.3 million relating to these items.",
        ],
        Q3_2023_TAIL,
    ) == []
    # A quote tail belongs to a quote, not to the paragraph.
    assert _lede_wrapped_paragraph_head(
        Q3_2023_RUN, "income taxes is shown on pages 14 and 15.”",
    ) == []
    # A digit-led wrap that is not a year wrap: a table row.
    assert _lede_wrapped_paragraph_head(
        [
            "For third quarter 2023, the pretax impact of the Brokerage segment adjustments totals $183.4 million, with",
            "65 33 87 44 0.25 0.13 in the third quarter of the year",
        ],
        Q3_2023_TAIL,
    ) == []
    # A short tail is junk, not a paragraph ending.
    assert _lede_wrapped_paragraph_head(Q3_2023_RUN, "taxes.") == []
    # A head that ends on a noun (no wrap-tail signal) is a label, not
    # a paragraph head — even at prose length.
    assert _lede_wrapped_paragraph_head(
        ["Total Brokerage & Risk Management, as adjusted for the quarter"],
        Q3_2023_TAIL,
    ) == []


def _extract(ticker_period):
    html = open(os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8").read()
    out = extract_press_release_highlights(html)
    assert out is not None
    return out


def test_ajg_q3_2023_pretax_paragraph_served_whole():
    # Batch 215 supersedes the batch-191 pin: the pretax paragraph is
    # the summary table's "*" footnote definition, not narrative, so it
    # is dropped from the lede now — the quote it used to crowd out is
    # served instead. The head-join mechanism itself is unchanged (the
    # unit tests above still exercise it); only this paragraph's
    # classification changed.
    out = _extract("AJG_2023-09-30")
    assert "pretax impact" not in out
    assert "detailed reconciliation" not in out
    # The CEO quote still follows — now with the note's budget freed.
    assert "“We had an excellent third quarter,” said J. Patrick Gallagher, Jr., Chairman, President and CEO." in out
    assert "22% reported revenue growth" in out


def test_ajg_q2_2024_pretax_paragraph_served_whole():
    # Batch 215 supersedes the batch-191 pin (see Q3 2023 above): the
    # pretax note is dropped; the quote head the first blast lost is
    # served whole thanks to the table-mode clear on the note skip.
    out = _extract("AJG_2024-06-30")
    assert "pretax impact" not in out
    assert "detailed reconciliation" not in out
    assert "“We had an excellent second quarter,” said J. Patrick Gallagher, Jr., Chairman and CEO." in out
    assert "14% reported revenue growth" in out


def test_ajg_q4_2023_pretax_paragraph_served_whole():
    # Batch 215 supersedes the batch-191 pin (see Q3 2023 above): the
    # pretax note is dropped — this is the quarter whose CEO quote the
    # note starved entirely before the fix.
    out = _extract("AJG_2023-12-31")
    assert "pretax impact" not in out
    assert "detailed reconciliation" not in out
    assert "We had a strong fourth quarter, to wrap up another fantastic year!" in out
    assert "J. Patrick Gallagher" in out
    assert "20% growth in revenue, of which 8.1% was organic" in out
