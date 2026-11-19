"""Batch 280 regression tests.

Quest Diagnostics' releases open with a headline, then a short teaser
figure-bullet block, then a dateline paragraph, a CEO quote, the
"Serving ..." strategic sections (Corewell / Fresenius / WHOOP / OURA
/ Epic / Haystack narrative bullets), and finally the financial
tables. The stored rows are stale snapshots of the seed-era extractor:
a headline truncated at the first ";" plus the strategic section
only -- no figure bullet, no dateline, no quote -- and on 2 rows a
trailing financial-table header residue. The current extractor serves
the leading block: full headline + 3-7 figure bullets (revenues,
reported + adjusted diluted EPS, cash from operations, guidance) +
dateline + CEO quote. The 5 other DGX siblings (2024-09-30,
2024-12-31, 2025-03-31, 2025-06-30, 2026-09-30) already store the
live shape (stored == live under norm), which is the consistency
cross-check for the re-sync.

One acknowledged loss, pinned in the repair gates: the 2025-09-30
row's stored Corewell bullet carries a forward Co-Lab revenue
expectation ("approximately $1 billion next year") that the live
shape drops. The other 3 rows have no stored-only $/% figure at all,
and the stored rows' unique non-figure content is operational counts
(200,000 dialysis patients, 150+ tests, 85+ biomarkers, 350,000 AI
Companion uses) -- none of them EPS, revenue, margin, cash-flow, or
guidance figures.

No extractor change in batch 280: the re-sync is a DB repair.

Open, noted not fixed: the remaining 56 SKIP-loss rows (largest
groups now DHI x4, GPC x4).
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

# key, headline, first figure bullet, dateline prefix, line count.
# All 4 live shapes are headline + figure bullets + dateline + CEO
# quote, with no strategic-section heading and no table header.
RESYNCED_QUARTERS = (
    (
        "DGX_2025-09-30",
        "Quest Diagnostics Reports Third Quarter 2025 Financial Results; Raises Guidance for Full Year 2025",
        "• Third quarter revenues of $2.82 billion, up 13.1% from 2024",
        "SECAUCUS, N.J., October 21, 2025",
        7,
    ),
    (
        "DGX_2025-12-31",
        "Quest Diagnostics Reports Fourth Quarter and Full Year 2025 Financial Results; Provides Guidance for Full Year 2026; Increases Quarterly Dividend 7.5% to $0.86 Per Share",
        "• Fourth quarter revenues of $2.81 billion, up 7.1% from 2024",
        "SECAUCUS, N.J., February 10, 2026",
        10,
    ),
    (
        "DGX_2026-03-31",
        "Quest Diagnostics Reports First Quarter 2026 Financial Results; Raises Revenue and EPS Guidance for Full Year 2026",
        "• First quarter revenues of $2.90 billion, up 9.2% from 2025, with 9.0% organic revenue growth",
        "SECAUCUS, N.J., April 21, 2026",
        6,
    ),
    (
        "DGX_2026-06-30",
        "Quest Diagnostics Reports Second Quarter 2026 Financial Results; Raises Revenue and EPS Guidance for Full Year 2026",
        "• Second quarter revenues of $3.04 billion, up 10.2% from 2025, with 10.0% organic revenue growth",
        "SECAUCUS, N.J., July 23, 2026",
        7,
    ),
)

# Siblings already store the live shape: headline, first bullet,
# line count.
SIBLING_QUARTERS = (
    (
        "DGX_2024-09-30",
        "Quest Diagnostics Reports Third Quarter 2024 Financial Results; Updates Guidance for Full Year 2024",
        "• Third quarter revenues of $2.49 billion, up 8.5% from 2023",
        7,
    ),
    (
        "DGX_2024-12-31",
        "Quest Diagnostics Reports Fourth Quarter and Full Year 2024 Financial Results; Provides Guidance for Full Year 2025; Increases Quarterly Dividend 6.7% to $0.80 Per Share",
        "• Fourth quarter revenues of $2.62 billion, up 14.5% from 2023",
        9,
    ),
    (
        "DGX_2025-03-31",
        "Quest Diagnostics Reports First Quarter 2025 Financial Results; Reaffirms Revenue and Adjusted Diluted EPS Guidance for Full Year 2025",
        "• First quarter revenues of $2.65 billion, up 12.1% from 2024",
        6,
    ),
    (
        "DGX_2025-06-30",
        "Quest Diagnostics Reports Second Quarter 2025 Financial Results; Raises Guidance for Full Year 2025",
        "• Second quarter revenues of $2.76 billion, up 15.2% from 2024",
        7,
    ),
    (
        "DGX_2026-09-30",
        "Quest Diagnostics Reports Third Quarter 2026 Financial Results; Raises Revenue and EPS Guidance for Full Year 2026",
        "• Third quarter revenues of $3.10 billion, up 10.0% from 2025, on strong organic revenue growth",
        7,
    ),
)

# Strategic-section headings and table-header residue the seed-era
# extractor captured and live drops.
DROPPED_CHROME = (
    "Serving Clinicians and Health Systems",
    "Serving Consumers",
    "Serving Customers and Delivering Innovations",
    "Delivering Clinical Innovations",
    "Delivering Diagnostic Innovations",
    "Driving Operational Excellence",
    "Three Months Ended",
    "(dollars in millions, except per share data)",
    "Reported:",
)


def _live(ticker_period: str) -> str:
    with open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ) as fh:
        return extract_press_release_highlights(fh.read()) or ""


def _live_lines(ticker_period: str) -> list[str]:
    return [ln for ln in _live(ticker_period).split("\n") if ln.strip()]


def _check_shape(key, headline, first_bullet, dateline_prefix, n_lines):
    live = _live(key)
    lines = _live_lines(key)
    assert lines[0] == headline, key
    assert lines[1] == first_bullet, key
    assert lines[-2].startswith(dateline_prefix), key
    assert "Jim Davis" in lines[-1], key
    assert len(lines) == n_lines, key
    assert "diluted earnings per share" in live, key
    for chrome in DROPPED_CHROME:
        assert chrome not in live, key


def test_resynced_quarters_serve_leading_block():
    for key, headline, bullet, dateline, n in RESYNCED_QUARTERS:
        _check_shape(key, headline, bullet, dateline, n)


def test_sibling_quarters_keep_live_shape():
    for key, headline, bullet, n in SIBLING_QUARTERS:
        live = _live(key)
        lines = _live_lines(key)
        assert lines[0] == headline, key
        assert lines[1] == bullet, key
        assert len(lines) == n, key
