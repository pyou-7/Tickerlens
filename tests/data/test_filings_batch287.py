"""Batch 287 regression tests.

Four wrong-block re-syncs of stored press-release highlights
(stored wrong-block, live headline figures, siblings already
live-shape):

BLK_2024-09-30 + BLK_2025-06-30 + BLK_2025-09-30: the stored rows
served the release's expense-detail MD&A bullets (employee
compensation, sales/asset/account expense, G&A, amortization deltas
+ footnote). Live serves the headline summary block (net inflows,
AUM, revenue and operating-income growth): headline identical, live
gains the quarter's headline figures, and the stored rows' unique $
figures are expense-detail deltas — none of them EPS, revenue, AUM,
or inflow headlines. The 5 cached BLK siblings already store the
live shape.

CSCO_2025-10-25: the stored row served the balance-sheet section
(cash/investments, RPO, deferred revenue, capital allocation,
acquisitions) with no revenue, EPS, or margin figure at all. Live
serves the earnings highlights (revenue $14.9B, GAAP/non-GAAP EPS,
gross/operating margins, product orders): headline identical, live
gains the quarter's headline figures, and the stored row's unique
$/% figures are balance-sheet / capital-allocation figures. The 7
cached CSCO siblings already store the live shape.

No extractor change in batch 287: the re-syncs are DB repairs.

Open, noted not fixed: the remaining SKIP-loss rows (largest groups
DHI x4, GPC x4, APH x3, CSX x3, DASH x3, EQIX x3 — all lose stored
figures on re-sync; DASH x3 + EQIX x3 held as trade-offs since batch
286; CSX x3 held as a group since batch 285; SPG 2024-09-30 held).
META_2025-09-30 figure-probed in batch 287: the stored row is
flattened table residue carrying EPS/net income the live bullets
drop — held as a trade-off (needs an extractor fix, not a re-sync).
DHI x4 + GPC x4 + APH x3 figure-probed in batch 287: stored rows are
the live block plus guidance/body tails — held (re-sync loses
guidance figures).
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

BLK_Q3_2024_HEADLINE = "BlackRock Reports Third Quarter 2024 Diluted EPS of $10.90, or $11.46 as adjusted"
BLK_Q3_2024_FIRST = "$360 billion of year-to-date total net inflows reflect continued strength of broad-based platform, and surpass full year net inflows of 2022 and 2023"
BLK_Q3_2024_LAST = "23% increase in operating income year-over-year (26% as adjusted)"

BLK_Q2_2025_HEADLINE = "BlackRock Reports Second Quarter 2025 Diluted EPS of $10.19, or $12.05 as adjusted"
BLK_Q2_2025_FIRST = "$152 billion of year-to-date total net inflows led by a record first half for iShares® ETFs, alongside private markets and cash net inflows"
BLK_Q2_2025_LAST = "12% increase in year-over-year as adjusted operating income"

BLK_Q3_2025_HEADLINE = "BlackRock Reports Third Quarter 2025 Diluted EPS of $8.43, or $11.55 as adjusted"
BLK_Q3_2025_FIRST = "$205 billion of quarterly total net inflows led by a record quarter for iShares® ETFs, alongside private markets and cash net inflows"
BLK_Q3_2025_LAST = "23% increase in year-over-year as adjusted operating income"

CSCO_HEADLINE = "CISCO REPORTS FIRST QUARTER EARNINGS"

# Siblings already store the live shape: headline, line count.
BLK_SIBLINGS = (
    ("BLK_2024-12-31", "BlackRock Reports Full Year 2024 Diluted EPS of $42.01, or $43.61 as adjusted", 6),
    ("BLK_2025-03-31", "BlackRock Reports First Quarter 2025 Diluted EPS of $9.64, or $11.30 as adjusted", 7),
    ("BLK_2025-12-31", "BlackRock Reports Full Year 2025 Diluted EPS of $35.31, or $48.09 as adjusted", 7),
    ("BLK_2026-03-31", "BlackRock Reports First Quarter 2026 Diluted EPS of $14.06, or $12.53 as adjusted", 8),
    ("BLK_2026-06-30", "BlackRock Reports Second Quarter 2026 Diluted EPS of $12.19, or $13.91 as adjusted", 7),
)
CSCO_SIBLINGS = (
    ("CSCO_2024-10-26", "CISCO REPORTS FIRST QUARTER EARNINGS", 12),
    ("CSCO_2025-01-25", "CISCO REPORTS SECOND QUARTER EARNINGS", 12),
    ("CSCO_2025-04-26", "CISCO REPORTS THIRD QUARTER EARNINGS", 12),
    ("CSCO_2025-07-26", "CISCO REPORTS FOURTH QUARTER AND FISCAL YEAR 2025 EARNINGS", 12),
    ("CSCO_2026-01-24", "CISCO REPORTS SECOND QUARTER EARNINGS", 15),
    ("CSCO_2026-04-25", "CISCO REPORTS THIRD QUARTER EARNINGS", 15),
    ("CSCO_2026-07-25", "CISCO REPORTS FOURTH QUARTER AND FISCAL YEAR 2026 EARNINGS", 15),
)


def _live(ticker_period: str) -> str:
    with open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ) as fh:
        return extract_press_release_highlights(fh.read()) or ""


def _live_lines(ticker_period: str) -> list[str]:
    return [ln for ln in _live(ticker_period).split("\n") if ln.strip()]


def test_blk_resynced_quarters_serve_summary_blocks():
    key = "BLK_2024-09-30"
    live = _live(key)
    lines = _live_lines(key)
    assert lines[0] == BLK_Q3_2024_HEADLINE, key
    assert lines[2] == BLK_Q3_2024_FIRST, key
    assert lines[-1] == BLK_Q3_2024_LAST, key
    assert len(lines) == 7, key
    # The stored row's expense-detail block is gone.
    assert "Investment advisory and administration fees" not in live, key
    assert "Securities lending revenue of $149 million" not in live, key
    # Live carries the inflow/AUM headlines the stored row lacked.
    assert "Record $221 billion of quarterly total net inflows" in live, key
    assert "$11.5 trillion in AUM" in live, key

    key = "BLK_2025-06-30"
    live = _live(key)
    lines = _live_lines(key)
    assert lines[0] == BLK_Q2_2025_HEADLINE, key
    assert lines[2] == BLK_Q2_2025_FIRST, key
    assert lines[-1] == BLK_Q2_2025_LAST, key
    assert len(lines) == 7, key
    assert "Employee compensation and benefits expense increased $261 million" not in live, key
    assert "$68 billion of quarterly total net inflows" in live, key
    assert "13% increase in revenue year-over-year" in live, key

    key = "BLK_2025-09-30"
    live = _live(key)
    lines = _live_lines(key)
    assert lines[0] == BLK_Q3_2025_HEADLINE, key
    assert lines[2] == BLK_Q3_2025_FIRST, key
    assert lines[-1] == BLK_Q3_2025_LAST, key
    assert len(lines) == 7, key
    assert "Employee compensation and benefits expense increased $779 million" not in live, key
    assert "10% annualized organic base fee growth" in live, key
    assert "25% increase in revenue year-over-year" in live, key


def test_csco_resynced_quarter_serves_earnings_highlights():
    key = "CSCO_2025-10-25"
    live = _live(key)
    lines = _live_lines(key)
    assert lines[0] == CSCO_HEADLINE, key
    assert len(lines) == 9, key
    # The stored row's balance-sheet section is gone.
    assert "Cash and Cash Equivalents and Investments" not in live, key
    assert "Remaining Performance Obligations (RPO)" not in live, key
    assert "Deferred Revenue" not in live, key
    # Live carries the revenue/EPS/margin headlines the stored row lacked.
    assert "Revenue of $14.9 billion, up 8% year over year" in live, key
    assert "GAAP EPS of $0.72" in live, key
    assert "Non-GAAP EPS of $1.00" in live, key
    assert "GAAP gross margin of 65.5%" in live, key


def test_blk_sibling_quarters_keep_live_shape():
    for key, headline, n in BLK_SIBLINGS:
        lines = _live_lines(key)
        assert lines[0] == headline, key
        assert len(lines) == n, key


def test_csco_sibling_quarters_keep_live_shape():
    for key, headline, n in CSCO_SIBLINGS:
        lines = _live_lines(key)
        assert lines[0] == headline, key
        assert len(lines) == n, key
