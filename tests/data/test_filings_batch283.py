"""Batch 283 regression tests.

Akamai's Q4 releases open with a headline, a "Fourth quarter
highlights" bullet list, then a "Full-year highlights" bullet list,
then the dateline lede, CEO quote, and results narrative. The 2
stored rows are truncated snapshots at 7 lines: 2024-12-31 stops one
bullet into the full-year list, and 2025-12-31 stops AT the
"Full-year highlights" heading with no full-year bullets at all. Both
also carry the seed-era no-space bullet defect ("•Revenue" for
"• Revenue"). Live serves the full shape: every stored bullet appears
in live after removing all whitespace, in order; the headline is
identical; and no stored $/% figure is missing from live. The only
stored line with no live counterpart is the "Fourth quarter
highlights" section heading, which carries no figures. Live gains 9
figures on each row (the missing full-year bullets). The 6 cached
AKAM siblings already store the live shape (stored == live under
norm), which is the consistency cross-check for the re-sync.

No extractor change in batch 283: the re-sync is a DB repair.

Open, noted not fixed: the remaining SKIP-loss rows (largest groups
DHI x4, GPC x4, APH x3, BLK x3, CSX x3, DASH x3, EQIX x3 -- DHI/GPC/
APH/BLK lose stored figures on re-sync; CSX 2024/2025 are
zero-figure-loss but trade conference-call furniture for the lede,
and CSX_2026-06-30 live is a strict subset of stored, so the cluster
is inconsistent).
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

# key, headline, first bullet, last bullet, line count.
# Both live shapes are headline + Q4 bullets + "Full-year highlights"
# bullets + dateline/quote tail.
RESYNCED_QUARTERS = (
    (
        "AKAM_2024-12-31",
        "AKAMAI REPORTS FOURTH QUARTER 2024 AND FULL-YEAR 2024 FINANCIAL RESULTS",
        "• Revenue of $1.020 billion, up 3% year-over-year and when adjusted for foreign exchange*",
        "• GAAP net income per diluted share of $3.27, down 7% year-over-year and down 4% when adjusted for foreign exchange*, and non-GAAP net income per diluted share* of $6.48, up 5% year-over-year and up 6% when adjusted for foreign exchange*",
        12,
    ),
    (
        "AKAM_2025-12-31",
        "AKAMAI REPORTS FOURTH QUARTER 2025 AND FULL-YEAR 2025 FINANCIAL RESULTS",
        "• Revenue of $1.095 billion, up 7% year-over-year and up 6% when adjusted for foreign exchange*",
        "• GAAP net income per diluted share of $3.07, down 6% year-over-year and down 5% when adjusted for foreign exchange*, and non-GAAP net income per diluted share* of $7.12, up 10% year-over-year and when adjusted for foreign exchange*",
        13,
    ),
)

# Siblings already store the live shape: headline, line count.
SIBLING_QUARTERS = (
    ("AKAM_2024-09-30", "AKAMAI REPORTS THIRD QUARTER 2024 FINANCIAL RESULTS", 7),
    ("AKAM_2025-03-31", "AKAMAI REPORTS FIRST QUARTER 2025 FINANCIAL RESULTS", 7),
    ("AKAM_2025-06-30", "AKAMAI REPORTS SECOND QUARTER 2025 FINANCIAL RESULTS", 7),
    ("AKAM_2025-09-30", "AKAMAI REPORTS THIRD QUARTER 2025 FINANCIAL RESULTS", 7),
    ("AKAM_2026-03-31", "AKAMAI REPORTS FIRST QUARTER 2026 FINANCIAL RESULTS", 7),
    ("AKAM_2026-06-30", "AKAMAI REPORTS SECOND QUARTER 2026 FINANCIAL RESULTS", 7),
)


def _live(ticker_period: str) -> str:
    with open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ) as fh:
        return extract_press_release_highlights(fh.read()) or ""


def _live_lines(ticker_period: str) -> list[str]:
    return [ln for ln in _live(ticker_period).split("\n") if ln.strip()]


def test_resynced_quarters_serve_full_shape():
    for key, headline, first_bullet, last_bullet, n in RESYNCED_QUARTERS:
        live = _live(key)
        lines = _live_lines(key)
        assert lines[0] == headline, key
        bullets = [ln for ln in lines if ln.startswith("•")]
        assert bullets[0] == first_bullet, key
        assert bullets[-1] == last_bullet, key
        assert len(lines) == n, key
        assert "Full-year highlights" in live, key
        assert "CAMBRIDGE, Mass." in live, key
        assert "Dr. Tom Leighton" in live or "Leighton" in live, key
        # The stored snapshots' no-space bullet defect is gone in live.
        assert "•Revenue" not in live, key
        # The stored snapshots stopped inside the full-year list; live
        # carries the full-year EPS bullet.
        assert "per diluted share of $3.27" in live or "per diluted share of $3.07" in live, key


def test_sibling_quarters_keep_live_shape():
    for key, headline, n in SIBLING_QUARTERS:
        lines = _live_lines(key)
        assert lines[0] == headline, key
        assert len(lines) == n, key
