"""Batch 276 regression tests.

CEG's releases open with a short highlights block, but the stored
rows for 5 quarters are stale snapshots of the seed-era extractor:
headline + the "Operational Highlights" section (the long "Nuclear
Operations" / "Natural Gas, Oil, and Renewables Operations" bullets)
plus, in 4 of the 5, the GAAP/Adjusted reconciliation table -- and
every one of the 5 is truncated mid-sentence or mid-table by the old
seed-era capture. The current extractor serves the release's own
highlights block for these rows: headline + 3-7 short figure bullets
(GAAP/adjusted EPS, guidance range, the quarter's deals condensed)
+ dateline + CEO/CFO quotes (2024-12-31 has bullets only, no lede
paragraph in the exhibit).

The three CEG siblings (2025-06-30, 2025-12-31, 2026-06-30) already
store the live shape (stored == live), which is the consistency
cross-check for the re-sync. Their live shape is the long
operational bullets, not the short lede, because those releases have
no short lede at all: their leading bullet block IS the operational
highlights. No extractor change in batch 276: the re-sync is a DB
repair.

The design question is the one settled in batches 266-270 (BNY,
BKR, AMZN, COR, V) and 273 (AXON): the highlights card's job is the
quarter's key financial figures. Live carries the headline EPS and
guidance figures; the stored rows' unique figures are
reconciliation-table tax rates/amounts, operational percentages
(capacity factor, dispatch match rate, renewable capture, EFOF),
and deal figures whose topic live covers condensed ($1.6B Crane
restart capex, $4.5B Calpine cash consideration, $900M green bond).

The AZO x5, EBAY x5, and MU x5 groups were probed in this batch and
are NOT re-synced here: AZO's stored rows are shorter than live
(truncated ledes vs the fuller live lede -- a line-matching question,
not a content loss); EBAY is the same narrative-vs-figures shape as
CEG/AXON and is the natural next batch; MU's first-loss line is the
"Quarterly Financial Results" heading with small length deltas.
No test is pinned for them here.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

# key, headline, first figure bullet (prefix), live non-empty lines,
# stored operational-section fragment that must NOT appear in live.
LEDE_QUARTERS = (
    (
        "CEG_2024-09-30",
        "CONSTELLATION REPORTS THIRD QUARTER 2024 RESULTS",
        "\u2022 GAAP Net Income of $3.82 per share",
        7,
        "Nuclear Operations:",
    ),
    (
        "CEG_2024-12-31",
        "CONSTELLATION REPORTS FOURTH QUARTER AND FULL YEAR 2024 RESULTS",
        "\u2022 GAAP Net Income of $2.71 per share",
        13,
        "Nuclear Operations:",
    ),
    (
        "CEG_2025-03-31",
        "CONSTELLATION REPORTS FIRST QUARTER 2025 RESULTS",
        "\u2022 GAAP Net Income of $0.38 per share",
        8,
        "Nuclear Operations:",
    ),
    (
        "CEG_2025-09-30",
        "CONSTELLATION REPORTS THIRD QUARTER 2025 RESULTS",
        "\u2022 GAAP Net Income of $2.97 per share",
        7,
        "Nuclear Operations:",
    ),
    (
        "CEG_2026-03-31",
        "CONSTELLATION REPORTS FIRST QUARTER 2026 RESULTS",
        "\u2022 GAAP Net Income of $4.49 per share",
        11,
        "Nuclear Operations:",
    ),
)

# The siblings already store the live shape: headline, first bullet
# (the operational highlights ARE the leading block here), live
# non-empty lines. Their releases have no short lede.
SIBLING_QUARTERS = (
    (
        "CEG_2025-06-30",
        "CONSTELLATION REPORTS SECOND QUARTER 2025 RESULTS",
        "\u2022 20-Year Deal with Meta for clean, reliable nuclear energy:",
        9,
    ),
    (
        "CEG_2025-12-31",
        "CONSTELLATION REPORTS FOURTH QUARTER AND FULL YEAR 2025 RESULTS",
        "\u2022 Calpine acquisition: On January 7, 2026, we completed",
        9,
    ),
    (
        "CEG_2026-06-30",
        "CONSTELLATION REPORTS SECOND QUARTER 2026 RESULTS",
        "\u2022 Progress continues at Crane Clean Energy Center paving way",
        10,
    ),
)

RECON_HEADER = "GAAP/Adjusted (non-GAAP) Operating Earnings Reconciliation"


def _live(ticker_period: str) -> str:
    with open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ) as fh:
        return extract_press_release_highlights(fh.read()) or ""


def _live_lines(ticker_period: str) -> list[str]:
    return [ln for ln in _live(ticker_period).split("\n") if ln.strip()]


def test_lede_quarters_serve_figure_bullets():
    for key, headline, first_bullet, n_lines, stored_frag in LEDE_QUARTERS:
        live = _live(key)
        lines = _live_lines(key)
        assert lines[0] == headline, key
        assert lines[1].startswith(first_bullet), key
        assert len(lines) == n_lines, key
        bullets = [ln for ln in lines if ln.startswith("\u2022")]
        assert len(bullets) >= 3, key
        assert sum(1 for b in bullets if "$" in b) >= 2, key
        assert "per share" in live, key
        assert stored_frag not in live, key
        assert RECON_HEADER not in live, key


def test_sibling_quarters_serve_operational_bullets():
    for key, headline, first_bullet, n_lines in SIBLING_QUARTERS:
        live = _live(key)
        lines = _live_lines(key)
        assert lines[0] == headline, key
        assert lines[1].startswith(first_bullet), key
        assert len(lines) == n_lines, key
        assert "Nuclear Operations:" in live, key
        assert "Natural Gas, Oil, and Renewables Operations:" in live, key
        assert RECON_HEADER not in live, key
