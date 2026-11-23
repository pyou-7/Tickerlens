"""Batch 253 regression tests.

Two changes ship together:

  * Extractor: the black-square bullet "◾" (U+25FE) joins
    _BULLET_LEAD_RE. Digital Realty renders its Highlights bullets
    with it, and the glyph was missing from the class — two $+%
    ◾ bullets plus the two $+%-carrying "Financial Results"
    narrative lines tripped the data_rows >= 4 threshold in
    _looks_like_financial_table, so the genuine 7-bullet "Highlights"
    section was rejected as a financial table and the lede fallback
    served the supplement TOC instead (DLR 2026-03-31: live 220
    chars of TOC junk vs 1638 stored). The batch-154 defect class,
    a new glyph.
  * Gate S10 (scripts/batch253_repair.py): S4 with the S7
    spacing-equivalence rescue in the loss check. The fix restores
    the real section, but live still differs from the seed-era
    stored rows in two ways no earlier gate accepts: seed-era
    flattening spaced the curly possessive ("Digital Realty ’ s" vs
    live "Digital Realty’s") and left a lone zero-width-space line
    the current _html_to_text drops — both excused by
    spacing-equivalence / S3 residue, never content — and live
    serves one more genuine "Financial Results" narrative line than
    the seed-era section cap did (FFO/EBITDA prose), a pure
    addition policed by S4's own checks. S7 refuses the addition
    by design; S4 refuses the spacing drift by design. The
    full-cache census re-syncs exactly the DLR x7 rows (SKIP-loss
    162 -> 155) and moves no other cohort.
"""
import sys

sys.path.insert(0, "scripts")

from batch253_repair import sweep_gate_s10
from tickerlens.data.filings import (
    _BULLET_LEAD_RE,
    _looks_like_financial_table,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html

_HEADLINE = "Digital Realty Reports First Quarter 2026 Results"
_DATELINE = (
    "Austin, TX — April 23, 2026 — Digital Realty (NYSE: DLR), the "
    "world’s largest cloud- and carrier-neutral data center platform, "
    "today announced results for the first quarter of 2026."
)
_BULLETS = [
    "◾ Reported net income available to common stockholders of $0.46 per share in 1Q26, compared to $0.27 in 1Q25",
    "◾ Reported FFO per share of $1.99 in 1Q26, compared to $1.67 in 1Q25",
    "◾ Reported Core FFO per share of $2.04 in 1Q26, compared to $1.77 in 1Q25; reported Constant-Currency Core FFO per share of $1.96 in 1Q26",
    "◾ Signed total bookings during 1Q26 that are expected to generate $707 million of annualized GAAP base rent at 100% share; at Digital Realty’s share, total bookings were $423 million, including a $98 million contribution from the 0 – 1 megawatt category",
    "◾ Reported a total backlog of $1.8 billion of annualized GAAP base rent at 100% share at the end of 1Q26; at Digital Realty’s share, the total backlog was $1.0 billion",
    "◾ Reported rental rate increases on renewal leases of 5.0% on a cash basis in 1Q26",
    "◾ Raised 2026 Core FFO per share outlook to $8.00 - $8.10 and 2026 Constant-Currency Core FFO per share outlook to $7.95 - $8.05",
]
_NARRATIVE = [
    "Digital Realty reported total revenues of $1.6 billion in the first quarter of 2026, in line with the previous quarter and a 16% increase from the same quarter last year.",
    "The company delivered net income of $175 million in the first quarter of 2026, as well as net income available to common stockholders of $169 million and $0.46 per share.",
    "Digital Realty generated Adjusted EBITDA of $920 million in the first quarter of 2026, a 7% increase from the previous quarter and a 16% increase over the same quarter last year.",
    "The company reported Funds From Operations (FFO) of $700 million in the first quarter of 2026, or $1.99 per share, compared to $1.89 per share in the previous quarter and $1.67 per share in the same quarter last year.",
]


def _dlr_html() -> str:
    # Minimal DLR shape: headline, dateline, Highlights section with
    # ◾ bullets, then the "Financial Results" narrative. (The real
    # packet's supplement TOC is not reproduced here — the
    # "Table of Contents" headline wart it leaves on the stored rows
    # is a separate issue; this test pins the section qualification.)
    return _contact_release_html(
        "EX-99.1",
        _HEADLINE,
        _DATELINE,
        "Highlights",
        *_BULLETS,
        "Financial Results",
        *_NARRATIVE,
        "Leasing Activity",
        "Digital Realty signed total bookings during the first quarter.",
    )


def test_black_square_bullet_section_is_not_a_table() -> None:
    # DLR Q1 2026 shape: the 7-bullet Highlights section plus the
    # "Financial Results" narrative that follows it. Without the ◾
    # fix, two $+%-carrying bullets plus two $+%-carrying narrative
    # lines trip data_rows >= 4 and the section is rejected.
    result = extract_press_release_highlights(_dlr_html())
    assert result is not None
    assert result.split("\n\n")[0] == _HEADLINE
    assert "Reported net income available to common stockholders of $0.46" in result
    assert "Signed total bookings during 1Q26" in result
    assert "Raised 2026 Core FFO per share outlook to $8.00 - $8.10" in result
    assert "total revenues of $1.6 billion" in result
    # No supplement/TOC residue survives.
    assert "Financial Supplement" not in result
    assert "Leasing Activity" not in result


def test_financial_table_check_guards_black_square_bullets() -> None:
    # The DLR snapshot: 7 ◾ bullets (2 carrying $ and %) plus the
    # "Financial Results" heading and 4 narrative lines (2 carrying
    # $ and %) — narrative, not a table. The bullets are guarded;
    # only the 2 narrative lines count as data rows.
    snapshot = _BULLETS + ["Financial Results"] + _NARRATIVE
    assert not _looks_like_financial_table(snapshot)
    # The same shape with plain (non-bullet) $+%-carrying lines still
    # reads as a table — the guard is the bullet, not the figures.
    assert _looks_like_financial_table(
        [
            "Signed total bookings during 1Q26 that are expected to generate $707 million at 100% share; at 100% share",
            "Reported a total backlog of $1.8 billion at 100% share at the end of 1Q26",
            "Digital Realty reported total revenues of $1.6 billion, a 16% increase from last year.",
            "Digital Realty generated Adjusted EBITDA of $920 million, a 7% increase from the previous quarter.",
        ]
    )


def test_black_square_bullet_is_a_bullet_lead() -> None:
    assert _BULLET_LEAD_RE.match("◾ Reported net income of $0.46 per share")
    assert _BULLET_LEAD_RE.match("◾Reported net income of $0.46 per share")


# ── Gate S10 ────────────────────────────────────────────────────────────────
# Stored is the seed-era DLR row: spaced curly possessive (" ’ s"),
# a lone zero-width-space line the current _html_to_text drops, and
# one fewer "Financial Results" narrative line than live serves.
_STORED_BULLETS = [
    b.replace("Digital Realty’s", "Digital Realty ’ s") for b in _BULLETS
]
_STORED = "\n".join(
    ["Table of Contents"]
    + _STORED_BULLETS
    + ["​", "Financial Results"]
    + _NARRATIVE[:3]
)
_LIVE = "\n".join(
    ["Table of Contents"] + _BULLETS + ["Financial Results"] + _NARRATIVE
)


def test_s10_passes_on_the_dlr_shape() -> None:
    assert sweep_gate_s10(_STORED, _LIVE) is None


def test_s10_still_refuses_a_dropped_bullet() -> None:
    # Live drops the backlog bullet entirely: real content loss,
    # not spacing drift — the gate must refuse.
    live = "\n".join(
        ["Table of Contents"]
        + [b for b in _BULLETS if "backlog" not in b]
        + ["Financial Results"]
        + _NARRATIVE
    )
    assert sweep_gate_s10(_STORED, live) == "loss"


def test_s10_still_refuses_a_changed_figure() -> None:
    # "$707 million" becomes "$708 million": same spacing shape, a
    # different figure — spacing_equivalent refuses, so the gate does.
    live = _LIVE.replace("$707 million", "$708 million")
    assert sweep_gate_s10(_STORED, live) == "loss"


def test_s10_still_refuses_an_added_table_row() -> None:
    # Live adds a table row under the narrative: the addition is
    # policed by S4's added-table check, not waved through.
    live = _LIVE + "\nSite rental revenues $1,593 $1,577 1%"
    assert sweep_gate_s10(_STORED, live) == "added-table"


def test_s10_still_refuses_a_dangling_tail() -> None:
    # Live ends on a dangling heading: S4's tail check still fires.
    live = _LIVE + "\nOutlook:"
    assert sweep_gate_s10(_STORED, live) == "tail"
