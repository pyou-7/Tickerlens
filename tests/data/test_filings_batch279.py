"""Batch 279 regression tests.

AutoZone's releases open with a headline carrying the comp-sales
figures ("Total Company Same Store Sales Increase X%; Domestic Same
Store Sales Increase Y%"), then a dateline lede paragraph that ends
with "Same store sales ... are as follows:" and a same-store-sales
table. The stored rows are stale snapshots of the seed-era extractor:
the full lede (table-intro sentence included) plus the table
flattened into lines; the current extractor serves the clean shape:
the lede cut at the sentence boundary, the table dropped, and the
full narrative set (gross profit, operating profit, buyback,
inventory, CEO quote) instead. The 4 other AZO siblings (2024-08-31,
2024-11-23, 2025-02-15, 2025-11-22) already store the live shape
(stored == live under norm), which is the consistency cross-check
for the re-sync.

One acknowledged loss, pinned in the repair gates: the 2025-05-10
row's stored table carries 3 data rows the live shape drops (the
international and 36-week comp breakdowns). The total and domestic
comp figures survive in the headline, and the other 4 rows' stored
tables carry no data rows at all (headers + footnote only).

No extractor change in batch 279: the re-sync is a DB repair.

Open, noted not fixed: the remaining 60 SKIP-loss rows (largest
groups now DGX x4, DHI x4, GPC x4).
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

# key, headline, lede prefix, gross-profit line prefix, operating
# profit line prefix. All 5 live shapes have exactly 7 non-empty
# lines and no flattened comp-table chrome.
RESYNCED_QUARTERS = (
    (
        "AZO_2025-05-10",
        "AutoZone 3rd Quarter Total Company Same Store Sales Increase 5.4%; Domestic Same Store Sales Increase 5.0%; EPS of $35.36",
        "MEMPHIS, Tenn., May 27, 2025 (GLOBE NEWSWIRE) -- AutoZone, Inc. (NYSE: AZO) today reported net sales of $4.5 billion",
        "For the quarter, gross profit, as a percentage of sales, was 52.7%",
        "Operating profit decreased 3.8% to $866.2 million.",
    ),
    (
        "AZO_2025-08-30",
        "AutoZone 4th Quarter Total Company Same Store Sales Increase 5.1%; Domestic Same Store Sales Increase 4.8%; 4th Quarter EPS of $48.71; Annual Sales of $18.9 Billion",
        "MEMPHIS, Tenn., Sept. 23, 2025 (GLOBE NEWSWIRE) -- AutoZone, Inc. (NYSE: AZO) today reported net sales of $6.2 billion",
        "For the quarter, gross profit, as a percentage of sales, was 51.5%",
        "Operating profit decreased 7.8% to $1.2 billion.",
    ),
    (
        "AZO_2026-02-14",
        "AutoZone 2nd Quarter Total Company Same Store Sales Increase 3.3%; Domestic Same Store Sales Increase 3.4%; EPS of $27.63",
        "MEMPHIS, Tenn., March 03, 2026 (GLOBE NEWSWIRE) -- AutoZone, Inc. (NYSE: AZO) today reported net sales of $4.3 billion",
        "For the quarter, gross profit, as a percentage of sales, was 52.5%",
        "Operating profit decreased 1.2% to $698.5 million.",
    ),
    (
        "AZO_2026-05-09",
        "AutoZone 3rd Quarter Total Company Same Store Sales Increase 3.9%; Domestic Same Store Sales Increase 4.1%; EPS of $38.07",
        "MEMPHIS, Tenn., May 26, 2026 (GLOBE NEWSWIRE) -- AutoZone, Inc. (NYSE: AZO) today reported net sales of $4.8 billion",
        "For the quarter, gross profit, as a percentage of sales, was 52.2%",
        "Operating profit increased 6.6% to $923.8 million.",
    ),
    (
        "AZO_2026-08-29",
        "AutoZone 4th Quarter Total Company Same Store Sales Increase 1.5%; Domestic Same Store Sales Increase 1.6%; 4th Quarter EPS of $56.05; Annual Sales of $20.3 Billion",
        "MEMPHIS, Tenn., Sept. 22, 2026 (GLOBE NEWSWIRE) -- AutoZone, Inc. (NYSE: AZO) today reported net sales of $6.6 billion",
        "For the quarter, gross profit, as a percentage of sales, was 53.3%",
        "Operating profit increased 10.1% to $1.3 billion.",
    ),
)

# Siblings already store the live shape: headline, lede prefix,
# gross-profit line prefix.
SIBLING_QUARTERS = (
    (
        "AZO_2024-08-31",
        "AutoZone 4th Quarter Total Company Same Store Sales Increase 1.3%; Domestic Same Store Sales Increase 0.2%; 4th Quarter EPS Increases to $51.58; Annual Sales of $18.5 Billion",
        "MEMPHIS, Tenn., Sept. 24, 2024 (GLOBE NEWSWIRE) -- AutoZone, Inc. (NYSE: AZO) today reported net sales of $6.2 billion",
        "For the quarter, gross profit, as a percentage of sales, was 52.5%",
    ),
    (
        "AZO_2024-11-23",
        "AutoZone 1st Quarter Total Company Same Store Sales Increase 1.8%; Domestic Same Store Sales Increase 0.3%; 1st Quarter EPS of $32.52",
        "MEMPHIS, Tenn., Dec. 10, 2024 (GLOBE NEWSWIRE) -- AutoZone, Inc. (NYSE: AZO) today reported net sales of $4.3 billion",
        "For the quarter, gross profit, as a percentage of sales, was 53.0%",
    ),
    (
        "AZO_2025-02-15",
        "AutoZone 2nd Quarter Total Company Same Store Sales Increase 2.9%; Domestic Same Store Sales Increase 1.9%; EPS of $28.29",
        "MEMPHIS, Tenn., March 04, 2025 (GLOBE NEWSWIRE) -- AutoZone, Inc. (NYSE: AZO) today reported net sales of $4.0 billion",
        "For the quarter, gross profit, as a percentage of sales, was flat to last year at 53.9%.",
    ),
    (
        "AZO_2025-11-22",
        "AutoZone 1st Quarter Total Company Same Store Sales Increase 4.7%; Domestic Same Store Sales Increase 4.8%; 1st Quarter EPS of $31.04",
        "MEMPHIS, Tenn., Dec. 09, 2025 (GLOBE NEWSWIRE) -- AutoZone, Inc. (NYSE: AZO) today reported net sales of $4.6 billion",
        "For the quarter, gross profit, as a percentage of sales, was 51.0%",
    ),
)

# Flattened comp-table chrome the seed-era extractor captured and
# live drops.
TABLE_CHROME = (
    "Constant Currency",
    "are as follows:",
    "Excludes impacts from fluctuations of foreign exchange rates.",
)


def _live(ticker_period: str) -> str:
    with open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ) as fh:
        return extract_press_release_highlights(fh.read()) or ""


def _live_lines(ticker_period: str) -> list[str]:
    return [ln for ln in _live(ticker_period).split("\n") if ln.strip()]


def _check_shape(key, headline, lede_prefix, gross_prefix, op_prefix=None):
    live = _live(key)
    lines = _live_lines(key)
    assert lines[0] == headline, key
    assert "Total Company Same Store Sales Increase" in lines[0], key
    assert "Domestic Same Store Sales Increase" in lines[0], key
    assert lines[1].startswith(lede_prefix), key
    assert lines[2].startswith(gross_prefix), key
    if op_prefix is not None:
        assert lines[3].startswith(op_prefix), key
    assert len(lines) == 7, key
    assert "Under its share repurchase program" in live, key
    assert "inventory increased" in live, key
    for chrome in TABLE_CHROME:
        assert chrome not in live, key


def test_resynced_quarters_serve_clean_narrative():
    for key, headline, lede, gross, op in RESYNCED_QUARTERS:
        _check_shape(key, headline, lede, gross, op)


def test_sibling_quarters_keep_live_shape():
    for key, headline, lede, gross in SIBLING_QUARTERS:
        _check_shape(key, headline, lede, gross)
