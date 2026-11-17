"""Batch 270 regression tests.

Visa's releases open with a leading bullet block of figure bullets
(GAAP/non-GAAP net income + EPS, net revenue + growth, buybacks,
dividend/repurchase program), but the stored rows for 7 quarters are
stale snapshots of the seed-era extractor:

- The five Q1-Q3 rows store the long "Financial Highlights" prose
  paragraphs (~4000 chars each, truncated mid-sentence by the old
  4000-char cap: 2024-12-31 ends "The\u2026", 2025-03-31 ends "Cash,
  cash equivalents\u2026", 2026-03-31 ends "The weighted-average\u2026").
  The current extractor serves the lede fallback for these rows
  (the two-comma dateline "San Francisco, CA, <date> \u2013 Visa
  (NYSE: V)" is not recognized by either dateline regex, so the
  leading-bullet block is None and the lede serves): headline +
  dateline + 4-5 figure bullets + CEO quote (Q2 rows have no quote).
- The two Q4 rows store a mangled shape: the 3 narrative bullets
  ("Fiscal fourth quarter growth ... remained relatively stable /
  strong", buybacks, dividend) plus "Income Statement Summary"
  table residue with the CEO quote embedded in a table row, and
  none of the 4 figure bullets. The current extractor serves the
  figure bullets for both.

The 2024-06-30 sibling already stores the live shape (stored ==
live), which is the consistency cross-check for the re-sync. No
extractor change in batch 270: the re-sync is a DB repair.

Known live-shape wart pinned here rather than fixed: Q4 FY2025
(V_2025-09-30) serves only the 4 figure bullets, with no dateline
and no CEO quote. Its dateline ("San Francisco, October 28, 2025
\u2013 Visa (NYSE: V)") matches _DATED_DATELINE_LEAD_RE, so the
leading-bullet block exists and wins over the lede — but the block
breaks on the "Other Highlights:" sub-heading (the
_HIGHLIGHTS_HEADING_RE break), stranding the 3 narrative bullets
(and the quote, which sits inside the summary table that follows).
The Q4 FY2024 sibling has the identical line structure but its
two-comma dateline is unrecognized, so its leading block is None
and the lede serves all 7 bullets + dateline. A naive continuation
fix (let the block continue past a "Highlights" heading whose next
line is a bullet) was tried in batch 270 and REVERTED: the
full-cache blast moved 5 rows — APD x3 (the grown block flips the
competition from the "Recent Highlights" section to a capped
leading block, losing the guidance bullets and swallowing prose
tails), BKNG x1 (a bullet line ending in the glued "Full Year
2024 Highlights" label trips the same break), and V_2025-09-30
itself (the block then runs past the table into "Income Statement
Summary" residue, because the leading block has no stop for that
title). Fixing the wart properly needs both a narrowed heading
continuation (colon-ended standalone heading only, never a bullet
line) and a table-title stop for "Income Statement Summary" —
carried forward, not shipped here.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _extract_highlights_section,
    _html_to_text,
    _leading_bullet_block,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

# key, headline, first figure bullet (prefix), live non-empty lines,
# ends on CEO quote, stored prose fragment that must NOT appear in live.
LEDE_QUARTERS = (
    (
        "V_2024-12-31",
        "Visa Reports Fiscal First Quarter 2025 Results",
        "\u2022 GAAP net income of $5.1B or $2.58 per share",
        7, True,
        "GAAP net income in the fiscal first quarter was $5.1 billion or $2.58 per share",
    ),
    (
        "V_2025-03-31",
        "Visa Reports Fiscal Second Quarter 2025 Results",
        "\u2022 GAAP net income of $4.6B or $2.32 per share",
        7, False,
        "GAAP net income in the fiscal second quarter was $4.6 billion or $2.32 per share",
    ),
    (
        "V_2025-06-30",
        "Visa Reports Fiscal Third Quarter 2025 Results",
        "\u2022 GAAP net income of $5.3B or $2.69 per share",
        7, True,
        "GAAP net income in the fiscal third quarter was $5.3 billion or $2.69 per share",
    ),
    (
        "V_2025-12-31",
        "Visa Reports Fiscal First Quarter 2026 Results",
        "\u2022 GAAP net income of $5.9B or $3.03 per share",
        7, True,
        "GAAP net income in the fiscal first quarter was $5.9 billion or $3.03 per share",
    ),
    (
        "V_2026-03-31",
        "Visa Reports Fiscal Second Quarter 2026 Results",
        "\u2022 GAAP net income of $6.0B or $3.14 per share",
        7, False,
        "GAAP net income in the fiscal second quarter was $6.0 billion or $3.14 per share",
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
        i for i, ln in enumerate(lines) if ln.startswith("Visa Reports Fiscal")
    )
    return lines[hi + 1:]


def test_visa_lede_quarters_serve_figure_bullets():
    for (
        key,
        headline,
        first_bullet,
        live_lines,
        ends_on_quote,
        prose_frag,
    ) in LEDE_QUARTERS:
        live = _live(key)
        lines = _live_lines(key)
        assert live.startswith(headline), key
        # The lede serves: no leading block (two-comma dateline is
        # unrecognized), no anchored section.
        body = _body_lines(key)
        assert _leading_bullet_block(body) is None, key
        assert _extract_highlights_section(body) is None, key
        # Headline + dateline + figure bullets (+ quote).
        assert lines[1].startswith("San Francisco, CA,"), key
        assert lines[2].startswith(first_bullet), key
        assert "\u2022 Net revenue of $" in live, key
        assert "\u2022 Share repurchases and dividends of $" in live, key
        # The stored prose shape is not served.
        assert prose_frag not in live, key
        assert "GAAP operating expenses were $" not in live, key
        assert "Income Statement Summary" not in live, key
        assert len(lines) == live_lines, key
        if ends_on_quote:
            assert lines[-1].startswith("\u201c") or lines[-1].startswith('"'), key
        else:
            assert lines[-1].startswith("\u2022"), key


def test_visa_q4_2024_lede_serves_all_seven_bullets():
    # The Q4 FY2024 sibling has the identical line structure to Q4
    # FY2025, but its two-comma dateline is unrecognized, so the
    # leading block is None and the lede serves headline + dateline +
    # all 7 bullets (4 figure + 3 narrative).
    key = "V_2024-09-30"
    body = _body_lines(key)
    assert _leading_bullet_block(body) is None
    assert _extract_highlights_section(body) is None
    live = _live(key)
    lines = _live_lines(key)
    assert live.startswith(
        "Visa Reports Fiscal Fourth Quarter and Full-Year 2024 Results"
    )
    assert lines[1].startswith("San Francisco, CA, October 29, 2024")
    assert lines[2].startswith(
        "\u2022 GAAP net income of $5.3B or $2.65 per share"
    )
    assert lines[4].startswith(
        "\u2022 GAAP net income of $19.7B or $9.73 per share"
    )
    assert lines[5].startswith("\u2022 Net revenue of $35.9B")
    assert lines[6].startswith(
        "\u2022 Fiscal fourth quarter growth in payments volume"
    )
    assert lines[8].startswith(
        "\u2022 The board of directors increased Visa's quarterly cash dividend"
    )
    assert len(lines) == 9
    # The stored mangled shape is not served: no table residue, and
    # the CEO quote stays inside the summary table.
    assert "Income Statement Summary" not in live
    assert "$9.6 12% $35.9 10%" not in live
    assert "Visa had a robust fourth quarter" not in live


def test_visa_q4_2025_leading_block_serves_four_figure_bullets_only():
    # KNOWN WART (see module docstring): the Q4 FY2025 live shape is
    # the leading bullet block only — headline + 4 figure bullets, no
    # dateline, no CEO quote, and the 3 "Other Highlights" narrative
    # bullets are stranded by the _HIGHLIGHTS_HEADING_RE break. The
    # naive continuation fix was tried and reverted in batch 270
    # (blast: APD x3, BKNG x1, V table residue) — pin the current
    # shape so any future fix (or regression) fails loudly.
    key = "V_2025-09-30"
    body = _body_lines(key)
    block = _leading_bullet_block(body)
    assert block is not None
    assert len(block) == 5  # 4 bullets + "Fiscal Full-Year Results:" label
    assert block[2] == "Fiscal Full-Year Results:"
    section = _extract_highlights_section(body)
    assert section is not None
    assert len(section) == 4  # label dropped post-selection (batch 177)
    live = _live(key)
    lines = _live_lines(key)
    assert live.startswith(
        "Visa Reports Fiscal Fourth Quarter and Full-Year 2025 Results"
    )
    assert lines[0].startswith("Visa Reports Fiscal Fourth Quarter")
    assert lines[1].startswith(
        "\u2022 GAAP net income of $5.1B or $2.62 per share"
    )
    assert lines[3].startswith(
        "\u2022 GAAP net income of $20.1B or $10.20 per share"
    )
    assert len(lines) == 5
    # No dateline, no quote, no stranded narrative bullets, no table.
    assert "San Francisco" not in live
    assert "continued healthy consumer spending" not in live
    assert "remained strong" not in live
    assert "Share repurchases and dividends of $6.1B" not in live
    assert "quarterly cash dividend 14% to $0.670" not in live
    assert "Income Statement Summary" not in live
    assert "$10.7 12% $40.0 11%" not in live


def test_visa_q3_2024_sibling_already_live_shape():
    # The Q3 FY2024 sibling already stores the live shape (stored ==
    # live under norm) — the same lede shape as the other quarters —
    # which is the consistency cross-check for the re-sync.
    key = "V_2024-06-30"
    body = _body_lines(key)
    assert _leading_bullet_block(body) is None
    assert _extract_highlights_section(body) is None
    live = _live(key)
    lines = _live_lines(key)
    assert live.startswith("Visa Reports Fiscal Third Quarter 2024 Results")
    assert lines[1].startswith("San Francisco, CA, July 23, 2024")
    assert lines[2].startswith(
        "\u2022 GAAP net income of $4.9B or $2.40 per share"
    )
    assert len(lines) == 7
    assert lines[-1].startswith('"Visa delivered strong results')
    assert "Income Statement Summary" not in live
