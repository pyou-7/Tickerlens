"""Batch 266 regression tests.

BNY's 8 stored highlights rows are the lede + CEO COMMENTARY prose
shape (headline + dateline paragraph + three long CEO-quote paragraphs),
while the extractor serves the HIGHLIGHTS bullet section (Results /
Profitability / Balance sheet / Capital distribution — 8 figure lines)
for all 8 quarters. The stored rows are stale snapshots of the
seed-era extractor, when the section did not qualify; the current
extractor serves the section outright — no leading bullet block exists
and the single anchored candidate scores (1, 8) under the
batch-102/261 absolute figure-line rule. No extractor change in batch
266: the re-sync is a DB repair, not a code fix. These tests pin the
extractor side of that decision: the live output for all 8 exhibits is
the section shape, and there is no leading block to compete — so any
future extractor change that flips BNY back to the lede/quote shape
fails loudly instead of silently re-staling the rows.
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

BNY_PERIODS = (
    "2024-09-30",
    "2024-12-31",
    "2025-03-31",
    "2025-06-30",
    "2025-09-30",
    "2025-12-31",
    "2026-03-31",
    "2026-06-30",
)

# First-bullet revenue figure per quarter, from the cached exhibits.
BNY_REVENUE = {
    "2024-09-30": "Total revenue of $4.6 billion, increased 5%",
    "2024-12-31": "Total revenue of $4.8 billion, increased 11%",
    "2025-03-31": "Total revenue of $4.8 billion, increased 6%",
    "2025-06-30": "Total revenue of $5.0 billion, increased 9%",
    "2025-09-30": "Total revenue of $5.1 billion, increased 9%",
    "2025-12-31": "Total revenue of $5.2 billion, increased 7%",
    "2026-03-31": "Total revenue of $5.4 billion, increased 13%",
    "2026-06-30": "Total revenue of $5.7 billion, increased 13%",
}


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
    hi = next(i for i, ln in enumerate(lines) if ln.startswith("BNY Reports"))
    return lines[hi + 1 :]


def test_bny_all_quarters_live_is_section_shape():
    for pe in BNY_PERIODS:
        live = _live(f"BNY_{pe}")
        assert live.startswith("BNY Reports "), pe
        # The section opens on the "Results" sub-heading, not the lede.
        assert live.split("\n\n", 1)[1].split("\n")[0] == "Results", pe
        assert f"• {BNY_REVENUE[pe]}" in live, pe
        # The grouped sub-sections are served: Results / Profitability /
        # Balance sheet in every quarter; non-Q4 quarters add Capital
        # distribution, while Q4 quarters carry a "4Q Notable items"
        # sub-heading instead (no capital-distribution group that quarter).
        for sub in ("Results", "Profitability", "Balance sheet"):
            assert sub in live, (pe, sub)
        if pe.endswith(("12-31",)):
            assert "Notable items (a)" in live, pe
        else:
            assert "Capital distribution" in live, pe
        # The stored lede+quote shape is not served.
        assert "CEO COMMENTARY" not in live, pe
        assert "today has reported" not in live, pe
        assert "today reported" not in live, pe


def test_bny_all_quarters_no_leading_block_single_section_candidate():
    for pe in BNY_PERIODS:
        body = _body_lines(f"BNY_{pe}")
        assert _leading_bullet_block(body) is None, pe
        cands = _extract_highlights_sections_anchored(body)
        assert len(cands) == 1, (pe, [a for a, _, _, _ in cands])
        anchor, content, _, _ = cands[0]
        assert anchor in ("HIGHLIGHTS", "4Q24 HIGHLIGHTS", "4Q25 HIGHLIGHTS"), (
            pe, anchor)
        assert _financial_line_count(content) == 8, pe


def test_bny_q3_2024_section_wins_uncontested():
    body = _body_lines("BNY_2024-09-30")
    section = _extract_highlights_section(body) or []
    # 12 section lines: 4 sub-headings + 8 figure bullets.
    assert len(section) == 12
    assert _financial_line_count(section) == 8
    assert section[0] == "Results"
    assert section[1].startswith(
        "• Total revenue of $4.6 billion, increased 5%")
    assert section[-1].startswith(
        "• Returned $1,078 million of capital to common shareholders")
    # The CEO COMMENTARY prose sits before the section in the body and
    # is never a candidate: it has no Highlights anchor and no bullets.
    assert "CEO COMMENTARY" in body
    assert "CEO COMMENTARY" not in section
