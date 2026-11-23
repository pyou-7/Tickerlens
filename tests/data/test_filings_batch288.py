"""Batch 288 regression tests.

Three furniture-tailed / truncated re-syncs of stored press-release
highlights (stored defective, live full block, siblings already
live-shape):

CSX_2024-12-31 + CSX_2025-12-31: the stored rows served the Q4/FY
highlight bullets followed by pure furniture (conference-call
dial-in, webcast, 8-K pointers, footnotes) and a "Financia l"
typo heading. Live serves the dateline paragraphs (with net income
figures) plus the same bullets: headline identical, zero stored
$/% figures missing from live, live gains 8/4 figures. The 6 other
cached CSX siblings already store the live shape. CSX_2026-06-30
stays held (live drops the volume paragraph + CEO quote).

AMT_2024-09-30: the stored row was truncated mid-block (India-sale
paragraph + "CONSOLIDATED HIGHLIGHTS" heading + only the first 3
highlight bullets). Live serves the full 6-bullet block (revenue,
property revenue, net income, Adjusted EBITDA, AFFO) + dateline +
CEO quote: headline identical, live gains 7 figures, and the stored
row's only unique figure is the "100%" in the India-sale completion
line. The 11 cached AMT siblings already store the live shape.

No extractor change in batch 288: the re-syncs are DB repairs.

Open, noted not fixed: the remaining SKIP-loss rows (largest groups
DHI x4, GPC x4, APH x3, DASH x3, EQIX x3 — all lose stored figures
on re-sync; DASH x3 + EQIX x3 held as trade-offs since batch 286;
CSX_2026-06-30 held; SPG 2024-09-30 held). META_2025-09-30
re-probed in batch 288: the stored row is flattened table residue
carrying EPS $1.05 / net income the live bullets drop entirely —
held (needs an extractor fix, not a re-sync). CARR_2024-12-31
probed in batch 288: stored carries Q4 EPS the live full-year
bullets drop — held as a trade-off.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

CSX_Q4_2024_HEADLINE = "CSX Corp. Announces Fourth Quarter and Full Year 2024 Results"
CSX_Q4_2024_LAST = "• EPS of $1.79 and adjusted EPS of $1.83, which compared to earnings of $1.82 per share in the prior year."

CSX_Q4_2025_HEADLINE = "CSX Corp. Announces Fourth Quarter and Full Year 2025 Results"
CSX_Q4_2025_LAST = "• EPS was $1.54, and adjusted EPS was $1.61."

AMT_HEADLINE = "AMERICAN TOWER CORPORATION REPORTS THIRD QUARTER 2024 FINANCIAL RESULTS"
AMT_FIRST = "Third Quarter 2024(1)"

# Siblings already store the live shape: headline, line count.
CSX_SIBLINGS = (
    ("CSX_2024-09-30", "CSX Corp. Announces Third Quarter 2024 Results", 7),
    ("CSX_2025-03-31", "CSX Corp. Announces First Quarter 2025 Results", 4),
    ("CSX_2025-06-30", "CSX Corp. Announces Second Quarter 2025 Results", 5),
    ("CSX_2025-09-30", "CSX Corp. Announces Third Quarter 2025 Results", 5),
    ("CSX_2026-03-31", "CSX Corp. Announces First Quarter 2026 Results", 4),
    ("CSX_2026-09-30", "CSX Corp. Announces Third Quarter 2026 Results", 5),
)
AMT_SIBLINGS = (
    ("AMT_2023-12-31", "AMERICAN TOWER CORPORATION REPORTS FOURTH QUARTER AND FULL YEAR 2023 FINANCIAL RESULTS", 9),
    ("AMT_2024-03-31", "AMERICAN TOWER CORPORATION REPORTS FIRST QUARTER 2024 FINANCIAL RESULTS", 7),
    ("AMT_2024-06-30", "AMERICAN TOWER CORPORATION REPORTS SECOND QUARTER 2024 FINANCIAL RESULTS", 11),
    ("AMT_2024-12-31", "AMERICAN TOWER CORPORATION REPORTS FOURTH QUARTER AND FULL YEAR 2024 FINANCIAL RESULTS", 11),
    ("AMT_2025-03-31", "AMERICAN TOWER CORPORATION REPORTS FIRST QUARTER 2025 FINANCIAL RESULTS", 8),
    ("AMT_2025-06-30", "AMERICAN TOWER CORPORATION REPORTS SECOND QUARTER 2025 FINANCIAL RESULTS", 8),
    ("AMT_2025-09-30", "AMERICAN TOWER CORPORATION REPORTS THIRD QUARTER 2025 FINANCIAL RESULTS", 8),
    ("AMT_2025-12-31", "AMERICAN TOWER CORPORATION REPORTS FOURTH QUARTER AND FULL YEAR 2025 FINANCIAL RESULTS", 13),
    ("AMT_2026-03-31", "AMERICAN TOWER CORPORATION REPORTS FIRST QUARTER 2026 FINANCIAL RESULTS", 7),
    ("AMT_2026-06-30", "AMERICAN TOWER CORPORATION REPORTS SECOND QUARTER 2026 FINANCIAL RESULTS", 7),
    ("AMT_2026-09-30", "AMERICAN TOWER CORPORATION REPORTS THIRD QUARTER 2026 FINANCIAL RESULTS", 9),
)


def _live(ticker_period: str) -> str:
    with open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ) as fh:
        return extract_press_release_highlights(fh.read()) or ""


def _live_lines(ticker_period: str) -> list[str]:
    return [ln for ln in _live(ticker_period).split("\n") if ln.strip()]


def test_csx_resynced_quarters_serve_full_blocks():
    key = "CSX_2024-12-31"
    live = _live(key)
    lines = _live_lines(key)
    assert lines[0] == CSX_Q4_2024_HEADLINE, key
    assert lines[-1] == CSX_Q4_2024_LAST, key
    assert len(lines) == 11, key
    # The stored row's furniture tail is gone.
    assert "CSX executives will conduct a conference call" not in live, key
    assert "Financia l Highlights" not in live, key
    # Live carries the dateline net-income figures the stored row lacked.
    assert "JACKSONVILLE, Fla. – January 23, 2025" in live, key
    assert "Net income was $733 million" in live, key
    assert "Net income for the year was $3.47 billion" in live, key

    key = "CSX_2025-12-31"
    live = _live(key)
    lines = _live_lines(key)
    assert lines[0] == CSX_Q4_2025_HEADLINE, key
    assert lines[-1] == CSX_Q4_2025_LAST, key
    assert len(lines) == 11, key
    assert "CSX executives will conduct a conference call" not in live, key
    assert "Financia l Highlights" not in live, key
    assert "JACKSONVILLE, Fla. – January 22, 2026" in live, key
    assert "net earnings of $720 million" in live, key
    assert "Fourth Quarter Financial Highlights1" in live, key


def test_amt_resynced_quarter_serves_full_block():
    key = "AMT_2024-09-30"
    live = _live(key)
    lines = _live_lines(key)
    assert lines[0] == AMT_HEADLINE, key
    assert lines[1] == AMT_FIRST, key
    assert len(lines) == 12, key
    # The stored row's truncation furniture is gone.
    assert "CONSOLIDATED HIGHLIGHTS" not in live, key
    assert "completed the sale of 100% of the equity interests" not in live, key
    # Live carries the EBITDA/AFFO bullets the truncated stored row lacked.
    assert "Adjusted EBITDA decreased 0.9% to $1,687 million" in live, key
    assert "AFFO attributable to AMT common stockholders increased 2.6% to $1,237 million" in live, key
    assert "Boston, Massachusetts – October 29, 2024" in live, key


def test_csx_sibling_quarters_keep_live_shape():
    for key, headline, n in CSX_SIBLINGS:
        lines = _live_lines(key)
        assert lines[0] == headline, key
        assert len(lines) == n, key


def test_amt_sibling_quarters_keep_live_shape():
    for key, headline, n in AMT_SIBLINGS:
        lines = _live_lines(key)
        assert lines[0] == headline, key
        assert len(lines) == n, key
