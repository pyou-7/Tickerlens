"""Batch 284 regression tests.

Enphase releases carry a financial figure block (revenue, margins,
operating/net income, EPS, cash flow) followed by a "Recent Business
Highlights" section of dated operational announcements. The 2 stored
rows serve ONLY the operational announcements — every bullet is a
dated "•On <date>, Enphase Energy announced..." line — and carry zero
$/% figures; they also carry the seed-era no-space bullet defect
("•On" for "• On"). Live serves the financial figure block: headline
identical, no stored $/% figure is missing from live (stored has
none), and live gains 15 figures (2026-06-30) and 12 figures
(2026-09-30). The 8 cached ENPH siblings already store the live
financial-block shape (stored == live under norm), which is the
consistency cross-check for the re-sync.

No extractor change in batch 284: the re-sync is a DB repair.

Open, noted not fixed: the remaining SKIP-loss rows (largest groups
DHI x4, GPC x4, APH x3, BLK x3, CSX x3, DASH x3, EQIX x3 — DHI/GPC/
APH/BLK lose stored figures on re-sync; CSX needs its own probe;
remaining zero-figure-loss candidates: CB x1, CLX x2, DG x1, EXPE x1,
MCO x1, SPG 2025-09-30).
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

# key, headline, first bullet, last bullet, line count.
# Both live shapes are headline + figure bullets + the
# "Our revenue and earnings..." tail line.
RESYNCED_QUARTERS = (
    (
        "ENPH_2026-06-30",
        "Enphase Energy Reports Financial Results for the Second Quarter of 2026",
        "• Strong progress on development of IQ® SST; achieved key technical milestones and deepened customer engagement with potential multi-gigawatt opportunities",
        "• Executed agreements year-to-date with third-party owners totaling approximately $1.08 billion: $202.4 million under the 5% ITC Safe Harbor and $878.6 million under the Physical Work Test",
        11,
    ),
    (
        "ENPH_2026-09-30",
        "Enphase Energy Reports Financial Results for the Third Quarter of 2026",
        "• Successfully demonstrated 13.8 kV AC to 800 VDC conversion using our IQ® SST technology",
        "• Cash, cash equivalents and marketable securities of $931.8 million",
        11,
    ),
)

# Siblings already store the live shape: headline, line count.
SIBLING_QUARTERS = (
    ("ENPH_2024-06-30", "Enphase Energy Reports Financial Results for the Second Quarter of 2024", 7),
    ("ENPH_2024-09-30", "Enphase Energy Reports Financial Results for the Third Quarter of 2024", 13),
    ("ENPH_2024-12-31", "Enphase Energy Reports Financial Results for the Fourth Quarter of 2024", 12),
    ("ENPH_2025-03-31", "Enphase Energy Reports Financial Results for the First Quarter of 2025", 11),
    ("ENPH_2025-06-30", "Enphase Energy Reports Financial Results for the Second Quarter of 2025", 11),
    ("ENPH_2025-09-30", "Enphase Energy Reports Financial Results for the Third Quarter of 2025", 10),
    ("ENPH_2025-12-31", "Enphase Energy Reports Financial Results for the Fourth Quarter of 2025", 11),
    ("ENPH_2026-03-31", "Enphase Energy Reports Financial Results for the First Quarter of 2026", 11),
)


def _live(ticker_period: str) -> str:
    with open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ) as fh:
        return extract_press_release_highlights(fh.read()) or ""


def _live_lines(ticker_period: str) -> list[str]:
    return [ln for ln in _live(ticker_period).split("\n") if ln.strip()]


def test_resynced_quarters_serve_financial_block():
    for key, headline, first_bullet, last_bullet, n in RESYNCED_QUARTERS:
        live = _live(key)
        lines = _live_lines(key)
        assert lines[0] == headline, key
        bullets = [ln for ln in lines if ln.startswith("•")]
        assert bullets[0] == first_bullet, key
        assert bullets[-1] == last_bullet, key
        assert len(lines) == n, key
        assert "Our revenue and earnings" in live, key
        # The stored rows' no-space bullet defect is gone in live.
        assert "•On" not in live, key
        # The stored rows served dated operational announcements with
        # no financial figures; live carries the quarter's figures.
        assert "Revenue of $" in live, key
        assert "diluted earnings per share" in live or "diluted EPS" in live, key


def test_sibling_quarters_keep_live_shape():
    for key, headline, n in SIBLING_QUARTERS:
        lines = _live_lines(key)
        assert lines[0] == headline, key
        assert len(lines) == n, key
