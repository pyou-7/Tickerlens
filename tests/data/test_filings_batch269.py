"""Batch 269 regression tests.

Cencora's releases carry no "Highlights" section and no leading
bullet block — the current extractor serves the lede fallback for all
8 COR quarters: headline sub-heads carrying the quarter's figures
("Revenue of $79.1 Billion ...", "Adjusted Diluted EPS Guidance
Range Raised to ..."), the dateline paragraph with revenue and
GAAP/adjusted EPS, the guidance-update paragraph, and the CEO
quote(s). The stored rows for 7 quarters were a stale snapshot of
the seed-era extractor, which instead captured the business-narrative
bullets ("•Cencora completed the acquisition of RCA ...", "•Good
Neighbor Pharmacy ...") plus a "Fiscal Year 20XX Expectations"
guidance section — a partial capture (2024-09-30 ends mid-list on a
dangling "•Revenue growth to be in the range of 7 to 9 percent;";
the three 2026 quarters end in guidance-table residue). The
2025-09-30 sibling already stores the live shape (stored == live),
which is the consistency cross-check for the re-sync. No extractor
change in batch 269: the re-sync is a DB repair, not a code fix.
These tests pin the extractor side of that decision, so any future
extractor change that flips a COR quarter back to the
business-bullets shape — or fixes the lede tail — fails loudly
instead of silently re-staling the row.

Known live-shape warts pinned here rather than fixed: the three
fiscal-2025 Q1-Q3 rows carry a trailing "Below, Cencora presents
descriptive summaries ..." furniture line (the lede fallback
collects one paragraph past the quotes); the Q4 rows and the 2026
quarters end on the CEO quote. The Q4 2024 row has no
guidance-update paragraph (its live shape is headline sub-heads +
dateline + two quotes only).
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

# key, headline, first figure sub-head (prefix), live non-empty lines,
# has trailing "Below, Cencora presents" furniture line, stored
# business-bullet fragment that must NOT appear in live.
LEDE_QUARTERS = (
    (
        "COR_2024-09-30",
        "CENCORA REPORTS FISCAL 2024 FOURTH QUARTER AND YEAR END RESULTS",
        "Revenue of $79.1 Billion for the Fourth Quarter, a 14.7 Percent",
        7, False,
        "entered into a definitive agreement to acquire Retina Consultants of America",
    ),
    (
        "COR_2024-12-31",
        "CENCORA REPORTS FISCAL 2025 FIRST QUARTER RESULTS",
        "Revenue of $81.5 billion for the First Quarter, a 12.8 Percent",
        8, True,
        "completed the acquisition of RCA",
    ),
    (
        "COR_2025-03-31",
        "CENCORA REPORTS FISCAL 2025 SECOND QUARTER RESULTS",
        "Revenue of $75.5 billion for the Second Quarter, a 10.3 percent",
        8, True,
        "released its 2024 Corporate Responsibility Report",
    ),
    (
        "COR_2025-06-30",
        "CENCORA REPORTS FISCAL 2025 THIRD QUARTER RESULTS",
        "Revenue of $80.7 billion for the Third Quarter, an 8.7 percent",
        8, True,
        "brought together in July 2025 more than 4,000 community pharmacy owners",
    ),
    (
        "COR_2025-12-31",
        "CENCORA REPORTS FISCAL 2026 FIRST QUARTER RESULTS",
        "Revenue of $85.9 billion for the First Quarter, a 5.5% Increase",
        9, False,
        "completed its acquisition of the majority of the outstanding equity interests",
    ),
    (
        "COR_2026-03-31",
        "CENCORA REPORTS FISCAL 2026 SECOND QUARTER RESULTS",
        "Revenue of $78.4 billion for the Second Quarter, a 3.8 percent",
        8, False,
        "Cencora and Covetrus, a global animal health technology",
    ),
    (
        "COR_2026-06-30",
        "CENCORA REPORTS FISCAL 2026 THIRD QUARTER RESULTS",
        "Revenue of $84.8 billion for the Third Quarter, a 5.1 percent",
        8, False,
        "ranked \u201c#1 in Customer Satisfaction with Chain Drug Store Pharmacies\u201d",
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
        i for i, ln in enumerate(lines) if ln.startswith("CENCORA REPORTS")
    )
    return lines[hi + 1:]


def test_cor_lede_quarters_serve_figure_subheads():
    for (
        key,
        headline,
        first_subhead,
        live_lines,
        has_tail,
        business_frag,
    ) in LEDE_QUARTERS:
        live = _live(key)
        lines = _live_lines(key)
        assert live.startswith(headline), key
        assert lines[1].startswith(first_subhead), key
        # The lede fallback serves: no leading block, no section.
        body = _body_lines(key)
        assert _leading_bullet_block(body) is None, key
        assert _extract_highlights_section(body) is None, key
        # The dateline paragraph carries the quarter's figures.
        assert any(ln.startswith("CONSHOHOCKEN, PA,") for ln in lines), key
        assert "Revenue of $" in live, key
        # The stored business-bullets shape is not served.
        assert business_frag not in live, key
        assert "\u2022" not in live, key
        assert "Expectations on an Adjusted" not in live, key
        # No guidance-table residue from the stored shape.
        assert "Guidance(1)" not in live, key
        assert "growth $" not in live, key
        assert len(lines) == live_lines, key
        if has_tail:
            assert lines[-1].startswith("Below, Cencora presents"), key
        else:
            assert lines[-1].startswith("\u201c"), key


def test_cor_q4_2024_has_no_guidance_update_paragraph():
    # The Q4 2024 release's live shape is headline sub-heads + dateline
    # + two quotes only — there is no guidance-update paragraph.
    live = _live("COR_2024-09-30")
    assert "Cencora is updating its outlook" not in live
    assert "Fiscal Year 2025 Expectations" not in live


def test_cor_other_quarters_carry_guidance_update_paragraph():
    for key, *_ in LEDE_QUARTERS[1:]:
        assert "Cencora is updating its outlook" in _live(key), key


def test_cor_q4_2025_sibling_already_lede_figures_shape():
    # The Q4 2025 sibling already stores the live shape (stored == live
    # under norm) — the same lede shape as the other quarters — which
    # is the consistency cross-check for the re-sync.
    key = "COR_2025-09-30"
    body = _body_lines(key)
    assert _leading_bullet_block(body) is None
    assert _extract_highlights_section(body) is None
    live = _live(key)
    lines = _live_lines(key)
    assert live.startswith(
        "CENCORA REPORTS FISCAL 2025 FOURTH QUARTER AND FISCAL YEAR END RESULTS"
    )
    assert lines[1].startswith(
        "Revenue of $83.7 Billion for the Fourth Quarter, a 5.9 Percent"
    )
    assert len(lines) == 7
    assert lines[-1].startswith("\u201c")
    assert "Below, Cencora presents" not in live
    assert "Good Neighbor Pharmacy" not in live
