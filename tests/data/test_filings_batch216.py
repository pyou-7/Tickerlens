"""Batch 216: AJG's 2026 combined pretax-adjustment note is dropped
from the lede, and the six-month combined note tail with it.

In 2026 AJG changed the note's shape from three per-segment
sentences ("For fourth quarter 2023, the pretax impact of the
Brokerage segment adjustments totals $559.5 million, ..." — batch
215) to one combined sentence for all three segments ("For first
quarter 2026, the pretax impact of adjustments for the Brokerage,
Risk Management, and Corporate Segments totals $431 million, $15
million and $30 million, respectively, ..."), and the same combined
wording for the six/nine-month period note ("For the six-month
period ended June 30, 2026, the pretax impact of adjustments for
the Brokerage, Risk Management, and Corporate Segments totals $936
million, ..."). Batch 215's regex matched neither, so both 2026
cached exhibits served the note: the quarterly note as a lede
paragraph (2026-03-31, 2026-06-30) and the six-month note as the
trailing paragraph of 2026-06-30. The fix extends
_PRETAX_ADJUSTMENT_NOTE_RE with both combined shapes; the existing
footnote-definition block skip (plus the batch-215 table-mode clear)
does the rest. The OLD per-segment period note stays deliberately
UNMATCHED — no stored row serves it, and the batch-215 test pins
the exclusion.

Blast over all 1,699 cached exhibits
(scripts/batch216_cache_blast.py, hidden_files/blast216/h_old ->
h_new): 2 diffs, both AJG 2026, both pure removals of note content
— 2026-03-31 loses the quarterly note paragraph, 2026-06-30 loses
the quarterly note paragraph and the six-month note tail; 1,697
byte-identical. Guidance old-vs-new over all AJG exhibits
(scripts/batch216_guidance_check.py, blast216/g_old -> g_new):
byte-identical.
"""

import os

from tickerlens.data.filings import (
    _PRETAX_ADJUSTMENT_NOTE_RE,
    _footnote_def_block_len,
    _opens_footnote_def,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _load(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


# --- unit: the combined opener shapes ---


def test_combined_quarterly_opener_matches_all_quarters():
    for quarter in ("first", "second", "third", "fourth"):
        line = (
            f"For {quarter} quarter 2026, the pretax impact of "
            f"adjustments for the Brokerage, Risk Management, and "
            f"Corporate Segments totals $431 million, $15 million and "
            f"$30 million, respectively,"
        )
        assert _PRETAX_ADJUSTMENT_NOTE_RE.match(line)
        assert _opens_footnote_def(line, "")


def test_combined_period_opener_matches_six_and_nine_month():
    for period, date in (
        ("six", "June 30, 2026"),
        ("nine", "September 30, 2026"),
    ):
        line = (
            f"For the {period}-month period ended {date}, the pretax "
            f"impact of adjustments for the Brokerage, Risk Management, "
            f"and Corporate Segments totals $936 million,"
        )
        assert _PRETAX_ADJUSTMENT_NOTE_RE.match(line)
        assert _opens_footnote_def(line, "")
    # The wrapped form: the opener line ends mid-figure ("totals
    # $936") and the amount wraps onto the next line.
    assert _PRETAX_ADJUSTMENT_NOTE_RE.match(
        "For the six-month period ended June 30, 2026, the pretax "
        "impact of adjustments for the Brokerage, Risk Management, "
        "and Corporate Segments totals $936"
    )


def test_combined_opener_rejects_lookalikes():
    # The full-year note in the combined wording is a different
    # sentence and is deliberately NOT matched — it sits past the
    # lede zone, same as the old per-segment full-year note.
    assert not _PRETAX_ADJUSTMENT_NOTE_RE.match(
        "For the year ended December 31, 2026, the pretax impact of "
        "adjustments for the Brokerage, Risk Management, and Corporate "
        "Segments totals $1,000 million,"
    )
    # The OLD per-segment period note stays unmatched (batch 215's
    # deliberate exclusion — no stored row serves it).
    assert not _PRETAX_ADJUSTMENT_NOTE_RE.match(
        "For the nine-month period ended September 30, 2025, the pretax "
        "impact of the Brokerage segment adjustments"
    )
    assert not _PRETAX_ADJUSTMENT_NOTE_RE.match(
        "For the six-month period ended June 30, 2025, the pretax "
        "impact of the Brokerage segment adjustments totals $500.0 million,"
    )
    # Narrative that merely mentions a pretax impact is not the note.
    assert not _PRETAX_ADJUSTMENT_NOTE_RE.match(
        "For first quarter 2026, the pretax impact of the new tax law "
        "was $10 million."
    )
    assert not _opens_footnote_def(
        "For first quarter 2026, the pretax impact of the new tax law "
        "was $10 million.",
        "",
    )


# --- unit: the block consumes the combined note ---


def test_footnote_block_consumes_combined_quarterly_note():
    lines = [
        "For first quarter 2026, the pretax impact of adjustments for "
        "the Brokerage, Risk Management, and Corporate Segments totals "
        "$431 million, $15 million and $30 million, respectively, and "
        "corresponding adjustment to the provision (benefit) for income "
        "taxes was $111 million, $4 million and ($20) million, "
        "respectively, relating to these adjustments. A detailed "
        "reconciliation is shown on pages 16 and 17.",
        "“We had a terrific first quarter!” said J. Patrick Gallagher, "
        "Jr., Chairman and CEO.",
    ]
    assert _footnote_def_block_len(lines, 0) == 1


def test_footnote_block_consumes_combined_period_note():
    # In the extractor's line view the note is ONE line — the
    # font-span boundary ("$936" / " million") inside the div is
    # joined by _html_to_text, so the block takes the whole note in
    # one step (real-exhibit pin below proves it on AJG 2026-06-30).
    lines = [
        "For the six-month period ended June 30, 2026, the pretax "
        "impact of adjustments for the Brokerage, Risk Management, and "
        "Corporate Segments totals $936 million, $27 million and $63 "
        "million, respectively, and corresponding adjustment to the "
        "provision (benefit) for income taxes was $241 million, $7 "
        "million and ($27) million, respectively, relating to these "
        "adjustments. A detailed reconciliation is shown on page 19.",
        "“We delivered an excellent second quarter!” said J. Patrick "
        "Gallagher, Jr., Chairman and CEO.",
    ]
    assert _footnote_def_block_len(lines, 0) == 1


# --- synthetic: the combined note is skipped and the quote is served ---


def test_synthetic_combined_quarterly_note_skipped_quote_served():
    html = _contact_release_html(
        "ACME REPORTS FIRST QUARTER 2026 RESULTS",
        "ROLLING MEADOWS, IL, April 25, 2026 — Acme Corp. (NYSE: ACME) "
        "today reported its financial results for the quarter ended "
        "March 31, 2026.",
        "For first quarter 2026, the pretax impact of adjustments for "
        "the Brokerage, Risk Management, and Corporate Segments totals "
        "$431 million, $15 million and $30 million, respectively, and "
        "corresponding adjustment to the provision (benefit) for income "
        "taxes was $111 million, $4 million and ($20) million, "
        "respectively, relating to these adjustments. A detailed "
        "reconciliation is shown on pages 16 and 17.",
        "“We had a terrific first quarter!” said Jane Smith, Chair and "
        "Chief Executive Officer. “Our core business delivered 28% "
        "revenue growth and 5% organic growth in the quarter.”",
    )
    result = extract_press_release_highlights(html)
    assert result is not None
    assert "pretax impact" not in result
    assert "detailed reconciliation" not in result
    assert "We had a terrific first quarter!" in result
    assert "Jane Smith" in result


def test_synthetic_combined_period_note_tail_dropped_after_quote():
    html = _contact_release_html(
        "ACME REPORTS SECOND QUARTER 2026 RESULTS",
        "ROLLING MEADOWS, IL, July 25, 2026 — Acme Corp. (NYSE: ACME) "
        "today reported its financial results for the quarter ended "
        "June 30, 2026.",
        "For second quarter 2026, the pretax impact of adjustments for "
        "the Brokerage, Risk Management, and Corporate Segments totals "
        "$505 million, $12 million and $33 million, respectively, and "
        "corresponding adjustment to the provision (benefit) for income "
        "taxes was $130 million, $3 million and ($7) million, "
        "respectively, relating to these adjustments. A detailed "
        "reconciliation is shown on page 17.",
        "“We delivered an excellent second quarter!” said Jane Smith, "
        "Chair and Chief Executive Officer. “Our core business "
        "delivered 24% revenue growth and 6% organic growth.”",
        "For the six-month period ended June 30, 2026, the pretax "
        "impact of adjustments for the Brokerage, Risk Management, and "
        "Corporate Segments totals $936 million, $27 million and $63 "
        "million, respectively, and corresponding adjustment to the "
        "provision (benefit) for income taxes was $241 million, $7 "
        "million and ($27) million, respectively, relating to these "
        "adjustments. A detailed reconciliation is shown on page 19.",
    )
    result = extract_press_release_highlights(html)
    assert result is not None
    assert "pretax impact" not in result
    assert "detailed reconciliation" not in result
    assert "six-month period" not in result
    assert "We delivered an excellent second quarter!" in result
    assert "Jane Smith" in result


# --- real-exhibit pins ---


def test_ajg_q1_2026_combined_note_gone_quote_kept():
    result = extract_press_release_highlights(_load("AJG_2026-03-31.html"))
    assert result is not None
    assert len(result) == 1504
    assert "pretax impact" not in result
    assert "detailed reconciliation" not in result
    assert "We had a terrific first quarter!" in result
    assert "J. Patrick Gallagher" in result
    assert "24th consecutive quarter of double-digit adjusted EBITDAC growth" in result


def test_ajg_q2_2026_combined_notes_gone_quote_kept():
    result = extract_press_release_highlights(_load("AJG_2026-06-30.html"))
    assert result is not None
    assert len(result) == 1196
    assert "pretax impact" not in result
    assert "detailed reconciliation" not in result
    assert "six-month period" not in result
    assert "We delivered an excellent second quarter!" in result
    assert "J. Patrick Gallagher" in result
    assert "continue creating long-term value for our clients, colleagues and shareholders" in result
