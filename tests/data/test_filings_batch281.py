"""Batch 281 regression tests.

Brown & Brown's releases open with a headline, a dateline paragraph,
a "For the ... quarter ended ..., the Company achieved:" lead-in,
then figure bullets (total revenues, income before income taxes,
EBITDAC - Adjusted, net income, diluted EPS), and on Q4/Q2 rows a
second year-to-date bullet block. The 3 stored rows are truncated
snapshots: each stops mid-list -- the diluted-EPS bullet is missing
on all 3, and the year-to-date block is missing on the Q4 2025 and
Q2 2026 rows -- and each carries the "achieved:" lead-in line the
current extractor drops. Live is a strict superset: every stored
bullet appears verbatim in live, headline and dateline are
identical, and the only stored-only line is the lead-in furniture,
which carries no $/% figure. The 6 other BRO siblings (2024-09-30,
2024-12-31, 2025-03-31, 2025-06-30, 2025-09-30, 2026-09-30)
already store the live shape (stored == live under norm), which is
the consistency cross-check for the re-sync.

No extractor change in batch 281: the re-sync is a DB repair.

Open, noted not fixed: the remaining SKIP-loss rows (largest groups
now DHI x4, GPC x4).
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

# key, headline, first bullet, last bullet, line count.
# All 3 live shapes are headline + dateline + full bullet block(s),
# with no "achieved:" lead-in.
RESYNCED_QUARTERS = (
    (
        "BRO_2025-12-31",
        "Brown & Brown, Inc. announces fourth quarter 2025 results, including total revenues of $1.6 billion, an increase of 35.7%; Organic Revenue decrease of 2.8%; diluted net income per share of $0.59; and Diluted Net Income Per Share - Adjusted of $0.93",
        "• Total revenues of $1.6 billion, increasing $423 million, or 35.7%, compared to the fourth quarter of the prior year, with Organic Revenue decreasing 2.8%.",
        "• Diluted net income per share of $3.16, a decrease of 8.7%, with Diluted Net Income Per Share - Adjusted increasing to $4.26, or 10.9%, each compared to 2024.",
        12,
    ),
    (
        "BRO_2026-03-31",
        "Brown & Brown, Inc. announces first quarter 2026 results, including total revenues of $1.9 billion, an increase of 35.4%; flat Organic Revenue; growth of Organic Revenue with Contingents of 2.2%; diluted net income per share of $1.06; Diluted Net Income Per Share - Adjusted of $1.39; and a quarterly dividend of $0.165 per share",
        "• Total revenues of $1.9 billion, increasing $497 million, or 35.4%, compared to the first quarter of the prior year, with flat Organic Revenue and Organic Revenue with Contingents increasing 2.2%.",
        "• Diluted net income per share of $1.06, a decrease of 7.8%, with Diluted Net Income Per Share - Adjusted increasing to $1.39, or 7.8%, each compared to the first quarter of the prior year.",
        7,
    ),
    (
        "BRO_2026-06-30",
        "Brown & Brown, Inc. announces second quarter 2026 results",
        "• Total revenues of $1.7 billion, increasing $391 million, or 30.4%, compared to the second quarter of the prior year, with Organic Revenue decreasing 0.7% and Organic Revenue with Contingents increasing 0.7%.",
        "• Diluted net income per share of $1.90, a decrease of 1.6%, with Diluted Net Income Per Share - Adjusted increasing to $2.46, or 6.0%, each compared to the same period in 2025.",
        13,
    ),
)

# Siblings already store the live shape: headline prefix, line count.
SIBLING_QUARTERS = (
    ("BRO_2024-09-30", "Brown & Brown, Inc. announces third quarter 2024 results", 5),
    ("BRO_2024-12-31", "Brown & Brown, Inc. announces fourth quarter 2024 results", 5),
    ("BRO_2025-03-31", "Brown & Brown, Inc. announces first quarter 2025 results", 5),
    ("BRO_2025-06-30", "Brown & Brown, Inc. announces second quarter 2025 results", 5),
    ("BRO_2025-09-30", "Brown & Brown, Inc. announces third quarter 2025 results", 5),
    ("BRO_2026-09-30", "Brown & Brown, Inc. announces third quarter 2026 results", 13),
)


def _live(ticker_period: str) -> str:
    with open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ) as fh:
        return extract_press_release_highlights(fh.read()) or ""


def _live_lines(ticker_period: str) -> list[str]:
    return [ln for ln in _live(ticker_period).split("\n") if ln.strip()]


def test_resynced_quarters_serve_full_bullet_block():
    for key, headline, first_bullet, last_bullet, n in RESYNCED_QUARTERS:
        live = _live(key)
        lines = _live_lines(key)
        assert lines[0] == headline, key
        bullets = [ln for ln in lines if ln.startswith("•")]
        assert bullets[0] == first_bullet, key
        assert bullets[-1] == last_bullet, key
        assert len(lines) == n, key
        assert "the Company achieved:" not in live, key
        assert "DAYTONA BEACH, Fla." in live, key
        assert "Diluted net income per share" in live, key


def test_sibling_quarters_keep_live_shape():
    for key, headline_prefix, n in SIBLING_QUARTERS:
        lines = _live_lines(key)
        assert lines[0].startswith(headline_prefix), key
        assert len(lines) == n, key
