"""Batch 215: AJG's pretax-adjustment footnote note is dropped from
the lede, and the CEO quote it starved is served again.

The note ("For fourth quarter 2023, the pretax impact of the
Brokerage segment adjustments totals $559.5 million, ..." — three
sentences: Brokerage / Risk Management / Corporate) is the "*"
footnote's definition of the summary table's adjustment items. It
sits between the summary table and the CEO quote, so the lede loop
collected it as content: it fills the 6-line budget and starves the
quote (Q4 2023: the quote is lost entirely — the note is 5 lines
against a budget already spent on the dateline and the CFO-Commentary
pointer lines). Cache survey (1,699 exhibits): 11 opener lines, all
AJG, all this exact shape.

The fix hooks the note into _opens_footnote_def, so the existing
footnote-definition block skip consumes the note (wrapped
continuations + chained segment sentences) — plus a table-mode clear
on the skip, because the note is prose that ends the summary-table
region: without it the quote's unterminated head lines are eaten as
table-mode residue (the batch-191 head-prepend refuses quote heads),
so the quote opens mid-sentence and the freed budget walks on to the
nine-month note's tail instead (first blast: 2024-06-30/09-30 lost
their quote heads, 2025-09-30 served the nine-month tail).

Blast over all 1,699 cached exhibits
(scripts/batch215_cache_blast.py, hidden_files/blast215/h_old ->
h_new): 10 diffs, all AJG 2023-09-30 through 2025-12-31, 1,689
byte-identical — every removed line is note content, every added
line is CEO-quote narrative, 0 content losses (verified line by
line in scripts/batch215_verify_blast.py).
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


# --- unit: the opener shape ---


def test_pretax_note_opener_matches_all_segments_and_quarters():
    for quarter in ("first", "second", "third", "fourth"):
        for segment in ("Brokerage", "Risk Management", "Corporate"):
            line = (
                f"For {quarter} quarter 2024, the pretax impact of the "
                f"{segment} segment adjustments totals $123.4 million,"
            )
            assert _PRETAX_ADJUSTMENT_NOTE_RE.match(line)
            assert _opens_footnote_def(line, "")


def test_pretax_note_opener_rejects_lookalikes():
    # The full-year note is a different sentence and is deliberately
    # NOT matched — it sits past the lede zone.
    assert not _PRETAX_ADJUSTMENT_NOTE_RE.match(
        "For the year ended December 31, 2024, the pretax impact of the "
        "Brokerage segment adjustments totals $500.0 million,"
    )
    # The nine-month / six-month period notes are the same footnote
    # class for the YTD period, but their opener wraps before "totals"
    # — out of this batch's scope (the lede loop stops in the quote
    # before reaching them).
    assert not _PRETAX_ADJUSTMENT_NOTE_RE.match(
        "For the nine-month period ended September 30, 2025, the pretax "
        "impact of the Brokerage segment adjustments"
    )
    # Narrative that merely mentions a pretax impact is not the note.
    assert not _PRETAX_ADJUSTMENT_NOTE_RE.match(
        "For fourth quarter 2024, the pretax impact of the new tax law "
        "was $10 million."
    )
    assert not _opens_footnote_def(
        "For fourth quarter 2024, the pretax impact of the new tax law "
        "was $10 million.",
        "",
    )


# --- unit: the block consumes the whole three-sentence note ---


def test_footnote_block_consumes_whole_pretax_note():
    lines = [
        "For fourth quarter 2023, the pretax impact of the Brokerage "
        "segment adjustments totals $559.5 million,",
        "mostly due to non-cash period expenses related to intangible "
        "amortization and acquisition earnout payable adjustments, with "
        "a corresponding adjustment to the provision for income taxes "
        "of $139.2 million",
        "relating to these items. For fourth quarter 2023, the pretax "
        "impact of the Risk Management segment adjustments totals $4.5 "
        "million, with a corresponding adjustment to the provision for "
        "income taxes of $1.2 million relating to these items.",
        "For fourth quarter 2023, the pretax impact of the Corporate "
        "segment adjustments totals $46.4 million, with a corresponding "
        "adjustment to the benefit for income taxes of $22.0 million "
        "relating to these items and the other tax items noted on",
        "page 7. A detailed reconciliation of the 2023 and 2022 "
        "provision (benefit) for income taxes is shown on pages 14 "
        "and 15.",
        "(1 of 15)",
        "“We had a strong fourth quarter, to wrap up another fantastic "
        "year!” said J. Patrick Gallagher,",
    ]
    assert _footnote_def_block_len(lines, 0) == 5


# --- synthetic: the note is skipped and the quote is served ---


def test_synthetic_pretax_note_skipped_quote_served():
    html = _contact_release_html(
        "ACME REPORTS FOURTH QUARTER 2025 RESULTS",
        "ROLLING MEADOWS, IL, January 25, 2026 — Acme Corp. (NYSE: ACME) "
        "today reported its financial results for the quarter ended "
        "December 31, 2025.",
        "For fourth quarter 2025, the pretax impact of the Brokerage "
        "segment adjustments totals $100.0 million,",
        "mostly due to non-cash period expenses related to intangible "
        "amortization, with a corresponding adjustment to the provision "
        "for income taxes of $25.0 million relating to these items. For "
        "fourth quarter 2025, the pretax impact of the Risk Management "
        "segment adjustments totals $5.0 million, with a corresponding "
        "adjustment to the provision for income taxes of $1.0 million "
        "relating to these items.",
        "For fourth quarter 2025, the pretax impact of the Corporate "
        "segment adjustments totals $10.0 million, with a corresponding "
        "adjustment to the benefit for income taxes of $2.0 million "
        "relating to these items and the other tax items noted on page 7. "
        "A detailed reconciliation of the 2025 and 2024 provision "
        "(benefit) for income taxes is shown on pages 12 and 13.",
        "“We had a fantastic fourth quarter,” said Jane Smith, Chair and "
        "Chief Executive Officer. “Our core business delivered 20% "
        "revenue growth and 8% organic growth in the quarter.”",
    )
    result = extract_press_release_highlights(html)
    assert result is not None
    assert "pretax impact" not in result
    assert "detailed reconciliation" not in result
    assert "We had a fantastic fourth quarter" in result
    assert "Jane Smith" in result


def test_synthetic_pretax_note_after_table_keeps_quote_head():
    # The regression the first blast caught: the note is skipped while
    # the loop is still in table mode, so the quote's unterminated head
    # lines were eaten as table-mode residue and the quote opened
    # mid-sentence. The table-mode clear on the note skip keeps them.
    html = _contact_release_html(
        "ACME REPORTS SECOND QUARTER 2025 RESULTS",
        "ROLLING MEADOWS, IL, July 25, 2025 — Acme Corp. (NYSE: ACME) "
        "today reported its financial results for the quarter ended "
        "June 30, 2025.",
        "4th Q 25",
        "Brokerage, as reported",
        "$ 2,051.5 $ 1,704.3",
        "For second quarter 2025, the pretax impact of the Brokerage "
        "segment adjustments totals $90.0 million,",
        "mostly due to non-cash period expenses related to intangible "
        "amortization, with a corresponding adjustment to the provision "
        "for income taxes of $20.0 million relating to these items. For "
        "second quarter 2025, the pretax impact of the Risk Management "
        "segment adjustments totals $2.0 million, with a corresponding "
        "adjustment to the provision for income taxes of $0.5 million "
        "relating to these items.",
        "For second quarter 2025, the pretax impact of the Corporate "
        "segment adjustments totals $3.0 million, with a corresponding "
        "adjustment to the benefit for income taxes of $0.5 million "
        "relating to these items. A detailed reconciliation of the 2025 "
        "and 2024 provision (benefit) for income taxes is shown on "
        "pages 14 and 15.",
        "“We had an excellent second quarter,” said Jane Smith, Chair "
        "and Chief Executive Officer. “Our",
        "core business combined to post 14% reported revenue growth and "
        "7.7% organic revenue growth in the quarter.”",
    )
    result = extract_press_release_highlights(html)
    assert result is not None
    assert "pretax impact" not in result
    assert "We had an excellent second quarter" in result
    assert "Jane Smith" in result
    assert "core business combined to post 14% reported revenue growth" in result


# --- real-exhibit pins ---


def test_ajg_q4_2023_quote_rescued():
    # The batch's target: the quote was entirely lost before the fix
    # (live extraction: pretax note only, no quote; stored row NULL).
    # Batch 222: the completion allowance lets the quote run to its
    # close (2017 chars, was 1540) instead of stranding it mid-quote.
    result = extract_press_release_highlights(_load("AJG_2023-12-31.html"))
    assert result is not None
    assert len(result) == 2017
    assert "pretax impact" not in result
    assert "detailed reconciliation" not in result
    assert "We had a strong fourth quarter, to wrap up another fantastic year!" in result
    assert "J. Patrick Gallagher" in result
    assert "20% growth in revenue, of which 8.1% was organic" in result


def test_ajg_q3_2024_note_gone_quote_kept():
    # Batch 222: the quote now completes (2124 chars, was 1867) — the
    # old pin asserted the mid-quote ending ("...get losses paid."),
    # which is exactly the cut batch 222 removes.
    result = extract_press_release_highlights(_load("AJG_2024-09-30.html"))
    assert result is not None
    assert len(result) == 2124
    assert "pretax impact" not in result
    assert "Our excellent financial performance continued during the third quarter!" in result
    assert "J. Patrick Gallagher" in result
    assert result.rstrip().endswith(
        "The opportunities ahead of us are immense and I am very excited "
        "about our long-term prospects!”"
    )


def test_ajg_q3_2023_note_gone_quote_kept():
    # Batch 222: the quote now completes (1794 chars, was 1507).
    result = extract_press_release_highlights(_load("AJG_2023-09-30.html"))
    assert result is not None
    assert len(result) == 1794
    assert "pretax impact" not in result
    assert "We had an excellent third quarter" in result
    assert "J. Patrick Gallagher" in result
    assert "22% reported revenue growth, 10.5% organic revenue growth" in result
