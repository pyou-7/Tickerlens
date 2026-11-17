"""Batch 267 regression tests.

BKR's 2024-12-31 stored highlights row was the full-year bullets (7
bullets, $28.2B orders) + the lede prose (dateline paragraph + three
Lorenzo Simonelli CEO-quote paragraphs + the "Baker Hughes Company News
Release" trailer), while the extractor serves the combined section
outright: the "Fourth-quarter highlights" anchor (6 Q4 bullets) followed
by the "Full-year highlights" sub-heading (batch-195 sub-heading rule)
and the same 7 full-year bullets — 14 section lines / 13 figure lines,
no leading bullet block, no CEO prose. The stored row is a stale
snapshot of the seed-era extractor, when the combined section did not
qualify. No extractor change in batch 267: the re-sync is a DB repair,
not a code fix. These tests pin the extractor side of that decision:
the live output for the 2024-12-31 exhibit is the combined section
shape, the Q4 sibling 2025-12-31 already stores that same shape, and
the 7 full-year bullets in live are the stored row's bullets — so any
future extractor change that flips BKR 2024-12-31 back to the
full-year + lede-quote shape fails loudly instead of silently
re-staling the row.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _extract_highlights_section,
    _extract_highlights_sections_anchored,
    _financial_line_count,
    _html_to_text,
    _leading_bullet_block,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

# The stored row's 7 full-year bullets, verbatim modulo the "• " spacing
# the normalizer treats as equal.
FULL_YEAR_BULLETS = (
    "Orders of $28.2 billion, including $13.0 billion of IET orders.",
    "Revenue of $27.8 billion, up 9% year-over-year.",
    "Attributable net income of $2,979 million.",
    "GAAP diluted EPS of $2.98 and adjusted diluted EPS* of $2.35.",
    "Adjusted EBITDA* of $4,591 million, up 22% year-over-year.",
    "Cash flows from operating activities of $3,332 million and free cash flow* of $2,257 million.",
    "Returns to shareholders of $1,320 million, including $484 million of share repurchases.",
)


def _html_text(ticker_period: str) -> str:
    with open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ) as fh:
        return fh.read()


def _live(ticker_period: str) -> str:
    return extract_press_release_highlights(_html_text(ticker_period)) or ""


def _body_lines(ticker_period: str) -> list[str]:
    lines = [
        ln.strip()
        for ln in _html_to_text(_html_text(ticker_period)).split("\n")
        if ln.strip()
    ]
    hi = next(
        i for i, ln in enumerate(lines)
        if ln.startswith("Baker Hughes Announces"))
    return lines[hi + 1:]


def test_bkr_q4_2024_live_is_combined_section_shape():
    live = _live("BKR_2024-12-31")
    assert live.startswith(
        "Baker Hughes Announces Fourth-Quarter and Full-Year 2024 Results")
    # The Q4 bullets open the card, then the full-year group.
    assert "• Orders of $7.5 billion, including $3.8 billion of IET orders." in live
    assert "Full-year highlights" in live
    for bullet in FULL_YEAR_BULLETS:
        assert f"• {bullet}" in live, bullet
    # The stored lede+quote shape is not served.
    assert "Lorenzo Simonelli" not in live
    assert "HOUSTON & LONDON (January 30, 2025)" not in live
    assert "Baker Hughes Company News Release" not in live


def test_bkr_q4_2024_no_leading_block_combined_section():
    body = _body_lines("BKR_2024-12-31")
    assert _leading_bullet_block(body) is None
    cands = _extract_highlights_sections_anchored(body)
    anchors = [a for a, _, _, _ in cands]
    assert anchors[0] == "Fourth-quarter highlights", anchors
    # The winning candidate is the combined section: the "Full-year
    # highlights" sub-heading sits inside it, not as a rival candidate.
    assert anchors[1] == "Full-year highlights", anchors
    section = _extract_highlights_section(body) or []
    assert len(section) == 14
    assert _financial_line_count(section) == 13
    assert section[0].startswith("• Orders of $7.5 billion")
    assert section[6] == "Full-year highlights"
    assert section[7].startswith("• Orders of $28.2 billion")
    assert section[-1].startswith("• Returns to shareholders of $1,320 million")


def test_bkr_q4_2025_sibling_already_combined_shape():
    # The Q4 sibling already stores the combined shape (stored == live),
    # which is the consistency cross-check for the 2024-12-31 re-sync.
    live = _live("BKR_2025-12-31")
    assert "• Orders of $7.9 billion, including $4.0 billion of IET orders." in live
    assert "Full-year highlights" in live
    assert "• Orders of $29.6 billion, including record $14.9 billion of IET orders." in live
    assert "Lorenzo Simonelli" not in live
    body = _body_lines("BKR_2025-12-31")
    assert _leading_bullet_block(body) is None
    section = _extract_highlights_section(body) or []
    assert len(section) == 14
    assert _financial_line_count(section) == 13
