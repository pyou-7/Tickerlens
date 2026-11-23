"""Batch 268 regression tests.

Amazon's releases carry two bullet blocks: the financial-figures block
up top ("Net sales increased ...", segment sales, operating income, net
income) and the business-narrative block further down ("Some other
highlights since the company's last earnings announcement include that
Amazon:" — Prime delivery speeds, movie viewers, AWS launches). The
stored rows for 8 quarters were the business block — a stale snapshot
of the seed-era extractor, when the financial block did not qualify
(the bullets' "•" glyph sits on its own line, split from the bold
lead-in). The current extractor serves the financial block outright
for 7 of the 8 (leading bullet block, no anchored rival), and the lede
fallback serves it for the 8th (2026-06-30: Amazon's 2026 releases
lead with three teaser lines ahead of the dateline, so there is no
leading block and no section anchor). No extractor change in batch
268: the re-sync is a DB repair, not a code fix. These tests pin the
extractor side of that decision, so any future extractor change that
flips an AMZN quarter back to the business-bullets shape — or fixes
the 2026-06-30 lede truncation — fails loudly instead of silently
re-staling the row.

Known live-shape warts pinned here rather than fixed: Q1-Q3 quarters
carry a trailing Jassy CEO-quote paragraph (the quote directly follows
the last financial bullet with no intervening heading, so the section
collector's completion allowance pulls it in); Q4 quarters end on the
net-income bullet (the "Full Year" heading terminates the section).
2026-06-30's lede stops at 8 bullets (AWS operating income) — the
net-income, non-operating-income and cash-flow bullets are NOT in
live. The 2026-09-30 sibling already stores the live shape (stored ==
live), which is the consistency cross-check for the re-sync.
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

# key, headline, first financial bullet (prefix), leading-block lines,
# section lines, section figure lines, live non-empty lines, live
# bullets, has trailing Jassy quote, stored business-bullet fragment
# that must NOT appear in live.
SECTION_QUARTERS = (
    (
        "AMZN_2024-09-30",
        "AMAZON.COM ANNOUNCES THIRD QUARTER RESULTS",
        "• Net sales increased 11% to $158.9 billion",
        14, 14, 13, 15, 13, True,
        "Held its annual Prime Big Deal Days shopping event",
    ),
    (
        "AMZN_2024-12-31",
        "AMAZON.COM ANNOUNCES FOURTH QUARTER RESULTS",
        "• Net sales increased 10% to $187.8 billion",
        9, 9, 9, 10, 9, False,
        "Delivered at its fastest speeds ever for Prime members in 2024",
    ),
    (
        "AMZN_2025-03-31",
        "AMAZON.COM ANNOUNCES FIRST QUARTER RESULTS",
        "• Net sales increased 9% to $155.7 billion",
        12, 12, 11, 13, 11, True,
        "Introduced Alexa+, our next-generation Alexa personal assistant",
    ),
    (
        "AMZN_2025-06-30",
        "AMAZON.COM ANNOUNCES SECOND QUARTER RESULTS",
        "• Net sales increased 13% to $167.7 billion",
        12, 12, 11, 13, 11, True,
        "Held its biggest Prime Day event ever",
    ),
    (
        "AMZN_2025-09-30",
        "AMAZON.COM ANNOUNCES THIRD QUARTER RESULTS",
        "• Net sales increased 13% to $180.2 billion",
        13, 13, 13, 14, 12, True,
        "Saw continued strong adoption of Trainium2",
    ),
    (
        "AMZN_2025-12-31",
        "AMAZON.COM ANNOUNCES FOURTH QUARTER RESULTS",
        "• Net sales increased 14% to $213.4 billion",
        9, 9, 9, 10, 9, False,
        "Announced new AWS agreements with OpenAI, Visa, the NBA",
    ),
    (
        "AMZN_2026-03-31",
        "AMAZON.COM ANNOUNCES FIRST QUARTER RESULTS",
        "• Net sales increased 17% to $181.5 billion",
        13, 13, 13, 14, 12, True,
        "Continued growing custom silicon business",
    ),
)


def _html_text(ticker_period: str) -> str:
    with open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ) as fh:
        return fh.read()


def _live(ticker_period: str) -> str:
    return extract_press_release_highlights(_html_text(ticker_period)) or ""


def _live_lines(ticker_period: str) -> list[str]:
    return [ln for ln in _live(ticker_period).split("\n") if ln.strip()]


def _body_lines(ticker_period: str) -> list[str]:
    lines = [
        ln.strip()
        for ln in _html_to_text(_html_text(ticker_period)).split("\n")
        if ln.strip()
    ]
    hi = next(
        i for i, ln in enumerate(lines) if ln.startswith("AMAZON.COM ANNOUNCES")
    )
    return lines[hi + 1:]


def test_amzn_section_quarters_serve_financial_block():
    for (
        key,
        headline,
        first_bullet,
        leading_len,
        section_len,
        section_fig,
        live_lines,
        live_bullets,
        has_quote,
        business_frag,
    ) in SECTION_QUARTERS:
        live = _live(key)
        lines = _live_lines(key)
        assert live.startswith(headline), key
        assert first_bullet in live, key
        # The stored business-bullets shape is not served.
        assert business_frag not in live, key
        assert "Some other highlights" not in live, key
        body = _body_lines(key)
        leading = _leading_bullet_block(body)
        assert leading is not None and len(leading) == leading_len, key
        section = _extract_highlights_section(body) or []
        assert len(section) == section_len, key
        assert _financial_line_count(section) == section_fig, key
        assert section[0].startswith(first_bullet), key
        assert len(lines) == live_lines, key
        assert sum(1 for ln in lines if ln.startswith("•")) == live_bullets, key
        if has_quote:
            assert "Andy Jassy" in live, key
            assert lines[-1].startswith("“"), key
        else:
            assert "Andy Jassy" not in live, key
            assert lines[-1].startswith("• Net income"), key


def test_amzn_q2_2026_lede_shape_truncated_at_aws_operating_income():
    # Amazon's 2026 releases lead with three teaser lines ahead of the
    # dateline, so there is no leading bullet block and no section
    # anchor: the lede fallback serves the financial block, stopping at
    # 8 bullets (AWS operating income). The net-income, non-operating
    # and cash-flow bullets are NOT in live — pinned so a future
    # extractor fix fails loudly instead of silently changing the row.
    key = "AMZN_2026-06-30"
    body = _body_lines(key)
    assert _leading_bullet_block(body) is None
    assert _extract_highlights_section(body) is None
    live = _live(key)
    lines = _live_lines(key)
    assert live.startswith("AMAZON.COM ANNOUNCES SECOND QUARTER RESULTS")
    assert "Net sales increased 20% year-over-year" in live  # teaser line
    assert "Operating income was $27.5 billion, up 43% year-over-year" in live
    assert "AWS net sales increased 37%" in live
    assert "SEATTLE—(BUSINESS WIRE) July 30, 2026" in live  # dateline
    assert "• Net sales increased 20% to $200.6 billion" in live
    assert lines[-1].startswith("• AWS segment operating income was $16.6 billion")
    assert len(lines) == 13
    assert sum(1 for ln in lines if ln.startswith("•")) == 8
    assert "Net income increased to $62.6 billion" not in live
    assert "Operating cash flow increased 33%" not in live
    assert "Andy Jassy" not in live
    # The stored business-bullets shape is not served.
    assert "Exceeded a $25 billion annual revenue run rate for AWS" not in live
    assert "Some other highlights" not in live


def test_amzn_q3_2026_sibling_already_financial_shape():
    # The Q3 2026 sibling already stores the live shape (stored == live
    # under norm) — the same lede shape as 2026-06-30 — which is the
    # consistency cross-check for the 2026-06-30 re-sync.
    key = "AMZN_2026-09-30"
    body = _body_lines(key)
    assert _leading_bullet_block(body) is None
    assert _extract_highlights_section(body) is None
    live = _live(key)
    lines = _live_lines(key)
    assert live.startswith("AMAZON.COM ANNOUNCES THIRD QUARTER RESULTS")
    assert "• Net sales increased 12% to $201.9 billion" in live
    assert lines[-1].startswith("• Net income decreased to $20.7 billion")
    assert len(lines) == 13
    assert sum(1 for ln in lines if ln.startswith("•")) == 9
    assert "Andy Jassy" not in live
