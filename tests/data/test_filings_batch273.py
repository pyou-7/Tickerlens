"""Batch 273 regression tests.

Axon's releases open with a shareholder-letter body, but the stored
rows for 6 quarters are stale snapshots of the seed-era extractor:
headline + letter prose (\"Axon AI -- The AI Era Plan\", \"Axon Week
2025\", \"Axon Software & Services\", \"Axon 911\", the 2026
product-ecosystem letter, \"The Axon Ecosystem\"), each ~2800-4000
chars and truncated mid-sentence or mid-list by the old 4000-char
cap (2025-06-30 ends on the dangling \"\u2022Draft One: 11 hours\";
2026-06-30 ends mid-sentence on a drone-response anecdote). The
current extractor serves the lede fallback for these rows (no
leading block, no section anchor): headline + 4-5 figure bullets
(Software & Services / Cloud & Services revenue, ARR, net income /
non-GAAP net income / Adjusted EBITDA, raised outlook) + the lede
paragraph opening the letter.

The two Q4 siblings (2024-12-31, 2025-12-31) already store the
live shape (stored == live), which is the consistency cross-check
for the re-sync. No extractor change in batch 273: the re-sync is
a DB repair.

The design question is the one settled in batches 266-270 (BNY,
BKR, AMZN, COR, V): the highlights card's job is the quarter's key
financial figures. Live carries the headline revenue / ARR /
net-income / EBITDA / outlook figures; the stored row's unique
figures are narrative, not quarterly figures -- the $159B total
addressable market and $74B market-opportunity figures in the
2025-09-30 letter, the 70%/75% time-savings figures, the 40%/120%
report-writing figures. The stored \"\u2022\" lines, where present,
are customer quotes and product-feature lists, not figure bullets.

The F x6 group was diagnosed in this batch and is NOT re-synced:
live gains the 4 figure bullets + dateline + quotes but DROPS the
\"Business Segment Highlights\" table (Ford Blue / Model e / Pro
wholesales, revenue, EBIT) that the stored rows hold -- a genuine
trade-off, not a stale-snapshot repair. It needs a decision (or an
extractor change that serves both tables) of its own, so no F test
is pinned here.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

# key, headline, first figure bullet (prefix), live non-empty lines,
# stored letter fragment that must NOT appear in live.
LEDE_QUARTERS = (
    (
        "AXON_2024-09-30",
        "Axon reports Q3 2024 revenue of $544 million, up 32% year over year, raises outlook",
        "\u2022 Axon Cloud & Services revenue grows 36% to $203 million",
        6,
        "Axon AI \u2014 The AI Era Plan",
    ),
    (
        "AXON_2025-03-31",
        "Axon reports Q1 2025 revenue of $604 million, up 31% year over year",
        "\u2022 Software & Services revenue grows 39% to $263 million",
        6,
        "Axon Week 2025",
    ),
    (
        "AXON_2025-06-30",
        "Axon reports Q2 2025 revenue of $669 million, up 33% year over year",
        "\u2022 Software & Services revenue grows 39% to $292 million",
        6,
        "Axon Software & Services",
    ),
    (
        "AXON_2025-09-30",
        "Axon reports Q3 2025 revenue of $711 million, up 31% year over year",
        "\u2022 Software & Services revenue grows 41% to $305 million",
        6,
        "Axon 911",
    ),
    (
        "AXON_2026-03-31",
        "Axon reports Q1 2026 revenue of $807 million, up 34% year over year",
        "\u2022 Software & Services revenue grows 35% to $355 million",
        7,
        "In April, Axon introduced a series of innovations",
    ),
    (
        "AXON_2026-06-30",
        "Axon reports Q2 2026 revenue of $904 million, up 35% year over year",
        "\u2022 Annual recurring revenue grows 39% to $1.6 billion",
        7,
        "The Axon Ecosystem",
    ),
)

# The Q4 siblings already store the live shape: headline, first
# figure bullet, live non-empty lines.
SIBLING_QUARTERS = (
    (
        "AXON_2024-12-31",
        "Axon 2024 revenue grows 33% to $2.1 billion; third consecutive year of 30%+ annual growth",
        "\u2022 Axon Cloud & Services revenue grows 44% to $806 million",
        6,
    ),
    (
        "AXON_2025-12-31",
        "Axon reports Q4 2025 revenue of $797 million, up 39% year over year",
        "\u2022 Software & Services revenue grows 40% to $343 million",
        6,
    ),
)


def _live(ticker_period: str) -> str:
    with open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ) as fh:
        return extract_press_release_highlights(fh.read()) or ""


def _live_lines(ticker_period: str) -> list[str]:
    return [ln for ln in _live(ticker_period).split("\n") if ln.strip()]


def test_lede_quarters_serve_figure_bullets():
    for key, headline, first_bullet, n_lines, stored_frag in LEDE_QUARTERS:
        lines = _live_lines(key)
        assert lines[0] == headline, key
        assert lines[1].startswith(first_bullet), key
        assert len(lines) == n_lines, key
        bullets = [ln for ln in lines if ln.startswith("\u2022")]
        assert len(bullets) >= 4, key
        assert sum(1 for b in bullets if "$" in b) >= 3, key
        assert stored_frag not in _live(key), key


def test_sibling_quarters_already_live_shape():
    for key, headline, first_bullet, n_lines in SIBLING_QUARTERS:
        lines = _live_lines(key)
        assert lines[0] == headline, key
        assert lines[1].startswith(first_bullet), key
        assert len(lines) == n_lines, key
        assert "Axon AI" not in _live(key), key


def test_2026_q1_keeps_no_dollar_bullet_among_figures():
    # The 2026-03-31 bullet list mixes a no-$ bullet (counter-drone
    # revenue up 300%) between $-figure bullets; the figure set is
    # still >= 3 $-bullets. This pins the batch-273 gate calibration:
    # the gate counts $-bullets over the whole list, not the first 3.
    lines = _live_lines("AXON_2026-03-31")
    bullets = [ln for ln in lines if ln.startswith("\u2022")]
    assert len(bullets) == 5
    assert bullets[1] == "\u2022 Counter-drone product revenue up over 300% year over year"
    assert "$" not in bullets[3]
    assert sum(1 for b in bullets if "$" in b) == 3


def test_2025_q3_live_drops_tam_narrative():
    # The stored 2025-09-30 letter's unique figures are narrative
    # (TAM / market opportunity), not quarterly figures; live must
    # not carry them.
    live = _live("AXON_2025-09-30")
    assert "$159 billion total addressable market" not in live
    assert "exceeding $74 billion" not in live


def test_2025_q2_live_drops_customer_quote_bullets():
    # The stored 2025-06-30 row's "\u2022" lines are customer quotes
    # and a time-savings list, not figure bullets; live must not
    # carry them.
    live = _live("AXON_2025-06-30")
    assert "Policy Chat" not in live
    assert "Draft One: 11 hours" not in live
