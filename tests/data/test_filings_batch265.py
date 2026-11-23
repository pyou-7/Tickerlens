"""Batch 265 regression tests.

CINF Q3 2024 + Q3 2025 stored the lede shape (headline + "today
reported:" + 5 bullets) while the extractor serves the section shape
(Insurance Operations + Investment bullets + CEO quote) — the same
shape it serves for the other 7 CINF quarters. The stored rows were
stale snapshots of the pre-batch-222 extractor, when the section was
rejected as a financial table because the CEO quote's $/% lines
pushed data_rows to 4; batch 222's snapshot fix made the section
qualify again. No extractor change in batch 265: the section wins the
leading-block competition on the batch-102/261 absolute figure-line
rule (9 vs 5 — even quote-free the section's 7 bullet figure lines
beat the lede's 5), so the re-sync is a DB repair, not a code fix.
These tests pin the extractor side of that decision: the live output
for both Q3 exhibits is the section shape, and the leading block is
collected but loses the competition — so any future extractor change
that flips CINF back to the lede fails loudly instead of silently
re-staling the rows.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _extract_highlights_section,
    _financial_line_count,
    _html_to_text,
    _leading_bullet_block,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


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
        i for i, ln in enumerate(lines) if ln.startswith("Cincinnati Financial Reports")
    )
    return lines[hi + 1 :]


def test_cinf_q3_2024_live_is_section_shape():
    live = _live("CINF_2024-09-30")
    assert live.startswith(
        "Cincinnati Financial Reports Third-Quarter 2024 Results"
    )
    body = live.split("\n\n", 1)[1]
    assert body.split("\n")[0].startswith(
        "• 97.4% third-quarter 2024 property casualty combined ratio"
    )
    assert "Investment and Balance Sheet Highlights" in live
    assert "Stephen M. Spray" in live
    # The lede bullets are not served: the section won the competition.
    assert "today reported:" not in live
    assert "net income of $820 million" not in live


def test_cinf_q3_2025_live_is_section_shape():
    live = _live("CINF_2025-09-30")
    assert live.startswith(
        "Cincinnati Financial Reports Third-Quarter 2025 Results"
    )
    body = live.split("\n\n", 1)[1]
    assert body.split("\n")[0].startswith(
        "• 88.2% third-quarter 2025 property casualty combined ratio"
    )
    assert "Investment and Balance Sheet Highlights" in live
    assert "Stephen M. Spray" in live
    assert "today reported:" not in live
    assert "net income of $1.122 billion" not in live


def test_cinf_q3_2024_leading_block_loses_on_figure_count():
    body = _body_lines("CINF_2024-09-30")
    leading = _leading_bullet_block(body) or []
    section = _extract_highlights_section(body) or []
    # The lede IS collected: 5 "today reported:" bullets, net income first.
    assert len(leading) == 5
    assert leading[0].startswith(
        "• Third-quarter 2024 net income of $820 million, or $5.20 per share"
    )
    assert _financial_line_count(leading) == 5
    # But the section candidate has more figure lines, so it wins the
    # absolute-count competition (batch 102/261 rule).
    assert _financial_line_count(section) == 9
    assert _financial_line_count(section) > _financial_line_count(leading)
    assert section[0].startswith(
        "• 97.4% third-quarter 2024 property casualty combined ratio"
    )


def test_cinf_q3_2025_leading_block_loses_on_figure_count():
    body = _body_lines("CINF_2025-09-30")
    leading = _leading_bullet_block(body) or []
    section = _extract_highlights_section(body) or []
    assert len(leading) == 5
    assert leading[0].startswith(
        "• Third-quarter 2025 net income of $1.122 billion, or $7.11 per share"
    )
    assert _financial_line_count(leading) == 5
    assert _financial_line_count(section) == 9
    assert _financial_line_count(section) > _financial_line_count(leading)
