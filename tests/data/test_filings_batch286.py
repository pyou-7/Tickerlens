"""Batch 286 regression tests.

Five zero-figure-loss re-syncs of defective/truncated stored
press-release highlights (stored defective/truncated, live fuller or
cleaner, siblings already live-shape) — the last five remaining
zero-figure-loss candidates from the batch-283 list:

CLX_2024-12-31 + CLX_2025-09-30: the stored rows carried the
seed-era lead-in line ("The following are recent strategic and
operational highlights:") + the no-space bullet defect ("•Grew" /
"•Introduced"), and were truncated mid-segment-results (2024-12-31
stopped before the Household segment; 2025-09-30 stopped before the
final Household EBIT bullet). Live serves the full block: headline
identical, no stored $/% figure missing from live, live gains 1
figure each (Household net sales -11% / Household EBIT -55%). The 6
cached CLX siblings already store the live shape.

DG_2024-11-01: the stored headline dropped the company's first word
("General Corporation Reports Third Quarter 2024 Results" for Dollar
General); body identical, figures equal. Live serves the correct
headline. The 7 cached DG siblings already store the live shape.

EXPE_2025-03-31: the stored row carried the no-space bullet defect
("•Booked") and served the bullets + CEO quote. Live serves the
release's three teaser subheads + dateline + the same bullets with
spaced markers: headline identical, figures equal. The stored row's
unique content is the CEO quote. The 7 cached EXPE siblings already
store the live shape.

SPG_2025-09-30: the stored row carried standalone "•" bullet-marker
lines and was truncated (teaser lines only, no dateline). Live
serves the clean teaser lines + dateline: headline identical,
figures equal. The 6 cached SPG siblings already store the live
shape. (SPG_2024-09-30 loses $118.1M / $0.32 on re-sync and stays
held.)

No extractor change in batch 286: the re-syncs are DB repairs.

Open, noted not fixed: the remaining SKIP-loss rows (largest groups
DHI x4, GPC x4, APH x3, BLK x3, CSX x3, DASH x3, EQIX x3 — all lose
stored figures on re-sync; DASH x3 + EQIX x3 figure-probed in batch
286 and held as trade-offs; CSX x3 held as a group since batch 285;
SPG 2024-09-30 held). With this batch, the zero-figure-loss
candidate list from batch 283 is exhausted.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

LEAD_IN = "The following are recent strategic and operational highlights:"

CLX_Q2_HEADLINE = "Clorox Reports Q2 Fiscal Year 2025 Results, Updates Outlook"
CLX_Q2_FIRST_BULLET = "• Grew share in seven of its eight categories, supported by strong demand creation plans as the company laps the impact of the cyberattack."
CLX_Q2_LAST_LINE = "• Net sales decreased 11%, driven by 11 points of lower volume."
CLX_Q1_HEADLINE = "Clorox Reports Q1 Fiscal Year 2026 Results, Updates Outlook"
CLX_Q1_LAST_LINE = "• Segment adjusted EBIT decreased 55%, primarily due to lower net sales."

DG_HEADLINE = "Dollar General Corporation Reports Third Quarter 2024 Results"

EXPE_HEADLINE = "Expedia Group Reports First Quarter 2025 Results"
EXPE_SUBHEAD = "Meets top-line guidance, delivering 4% bookings growth and 3% revenue growth year-over-year"
EXPE_LAST_BULLET = "• Paid quarterly dividend of $0.40 per share on March 27, 2025."

SPG_HEADLINE = "Simon® Reports Third Quarter 2025 Results"
SPG_DIVIDEND = "Raises quarterly dividend by 4.8% year-over-year to $2.20 per share"

# Siblings already store the live shape: headline, line count.
CLX_SIBLINGS = (
    ("CLX_2024-06-30", "Clorox Reports Q4 and FY24 Results, Provides FY25 Outlook", 13),
    ("CLX_2024-09-30", "Clorox Reports Q1 Fiscal Year 2025 Results, Updates Outlook", 12),
    ("CLX_2025-03-31", "Clorox Reports Q3 Fiscal Year 2025 Results, Updates Outlook", 12),
    ("CLX_2025-06-30", "Clorox Reports Q4 and FY25 Results, Provides FY26 Outlook", 12),
    ("CLX_2025-12-31", "Clorox Reports Q2 Fiscal Year 2026 Results, Confirms Outlook", 13),
    ("CLX_2026-03-31", "Clorox Reports Q3 Fiscal Year 2026 Results, Updates Outlook", 13),
)
DG_SIBLINGS = (
    ("DG_2025-01-31", "Dollar General Corporation Reports Fourth Quarter and Fiscal Year 2024 Results", 17),
    ("DG_2025-05-02", "Dollar General Corporation Reports First Quarter 2025 Results", 14),
    ("DG_2025-08-01", "Dollar General Corporation Reports Second Quarter 2025 Results", 14),
    ("DG_2025-10-31", "Dollar General Corporation Reports Third Quarter 2025 Results", 16),
    ("DG_2026-01-30", "Dollar General Corporation Reports Strong Fourth Quarter and Fiscal Year 2025 Results", 14),
    ("DG_2026-05-01", "Dollar General Corporation Reports First Quarter 2026 Results", 7),
    ("DG_2026-07-31", "Dollar General Corporation Reports Second Quarter 2026 Results", 7),
)
EXPE_SIBLINGS = (
    ("EXPE_2024-09-30", "Expedia Group Reports Third Quarter 2024 Results", 9),
    ("EXPE_2024-12-31", "Expedia Group Reports Fourth Quarter and Full Year 2024 Results", 9),
    ("EXPE_2025-06-30", "Expedia Group Reports Second Quarter 2025 Results", 10),
    ("EXPE_2025-09-30", "Expedia Group Reports Third Quarter 2025 Results", 11),
    ("EXPE_2025-12-31", "Expedia Group Reports Fourth Quarter and Full Year 2025 Results", 10),
    ("EXPE_2026-03-31", "Expedia Group Reports First Quarter 2026 Results", 10),
    ("EXPE_2026-06-30", "Expedia Group Reports Second Quarter 2026 Results", 10),
)
SPG_SIBLINGS = (
    ("SPG_2024-12-31", "Simon® Reports Fourth Quarter and Full Year 2024 Results", 7),
    ("SPG_2025-03-31", "Simon® Reports First Quarter 2025 Results and Reaffirms Full Year 2025 Real Estate FFO Per Share Guidance", 7),
    ("SPG_2025-06-30", "Simon® Reports Second Quarter 2025 Results, Increases Full Year 2025 Real Estate FFO Per Share Guidance and Raises Quarterly Dividend", 7),
    ("SPG_2025-12-31", "Simon® Reports Fourth Quarter and Full Year 2025 Results", 7),
    ("SPG_2026-03-31", "Simon® Reports First Quarter 2026 Results, Increases Full Year 2026 Real Estate FFO Per Share Guidance and Raises Quarterly Dividend", 7),
    ("SPG_2026-06-30", "Simon® Reports Second Quarter 2026 Results and Increases Guidance for Full Year 2026 Real Estate FFO Per Share", 7),
)


def _live(ticker_period: str) -> str:
    with open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ) as fh:
        return extract_press_release_highlights(fh.read()) or ""


def _live_lines(ticker_period: str) -> list[str]:
    return [ln for ln in _live(ticker_period).split("\n") if ln.strip()]


def test_clx_resynced_quarters_serve_full_blocks():
    key = "CLX_2024-12-31"
    live = _live(key)
    lines = _live_lines(key)
    assert lines[0] == CLX_Q2_HEADLINE, key
    assert lines[1] == CLX_Q2_FIRST_BULLET, key
    assert lines[-1] == CLX_Q2_LAST_LINE, key
    assert len(lines) == 13, key
    # The stored rows' lead-in + no-space bullet defects are gone.
    assert LEAD_IN not in live, key
    assert "•Grew" not in live, key
    # Live carries the Household segment the stored row truncated away.
    assert "Household (Bags and Wraps; Cat Litter; Grilling)" in live, key

    key = "CLX_2025-09-30"
    live = _live(key)
    lines = _live_lines(key)
    assert lines[0] == CLX_Q1_HEADLINE, key
    assert lines[-1] == CLX_Q1_LAST_LINE, key
    assert len(lines) == 13, key
    assert LEAD_IN not in live, key
    assert "•Introduced" not in live, key
    assert "• Introduced new products inspired by emerging consumer trends" in live, key


def test_dg_resynced_quarter_serves_correct_headline():
    key = "DG_2024-11-01"
    live = _live(key)
    lines = _live_lines(key)
    assert lines[0] == DG_HEADLINE, key
    assert len(lines) == 12, key
    # The stored row's dropped-word headline is gone.
    assert "General Corporation Reports Third Quarter 2024 Results" not in lines, key
    # Live carries the quarter's figures (body unchanged).
    assert "sales increased 5.0% to $10.2 billion" in live, key
    assert "profit as a percentage of net sales was 28.8%" in live, key


def test_expe_resynced_quarter_serves_subheads_and_bullets():
    key = "EXPE_2025-03-31"
    live = _live(key)
    lines = _live_lines(key)
    assert lines[0] == EXPE_HEADLINE, key
    assert lines[1] == EXPE_SUBHEAD, key
    assert lines[-1] == EXPE_LAST_BULLET, key
    assert len(lines) == 13, key
    # The stored row's spacing defect + CEO quote are gone.
    assert "•Booked" not in live, key
    assert "Ariane Gorin" not in live, key
    # Live carries the dateline + spaced bullets.
    assert "SEATTLE, WA – May 8, 2025" in live, key
    assert "• Booked room nights grew 6%" in live, key
    assert "Adjusted EPS was $0.40 and grew 90%" in live, key


def test_spg_resynced_quarter_serves_clean_block():
    key = "SPG_2025-09-30"
    live = _live(key)
    lines = _live_lines(key)
    assert lines[0] == SPG_HEADLINE, key
    assert len(lines) == 5, key
    # The stored row's standalone bullet-marker lines are gone.
    assert "•" not in lines, key
    # Live carries the teaser lines + dateline the stored row truncated.
    assert SPG_DIVIDEND in live, key
    assert "INDIANAPOLIS, November 3, 2025" in live, key
    assert "Completes acquisition of remaining 12% interest in The Taubman Realty Group" in live, key


def test_clx_sibling_quarters_keep_live_shape():
    for key, headline, n in CLX_SIBLINGS:
        lines = _live_lines(key)
        assert lines[0] == headline, key
        assert len(lines) == n, key


def test_dg_sibling_quarters_keep_live_shape():
    for key, headline, n in DG_SIBLINGS:
        lines = _live_lines(key)
        assert lines[0] == headline, key
        assert len(lines) == n, key


def test_expe_sibling_quarters_keep_live_shape():
    for key, headline, n in EXPE_SIBLINGS:
        lines = _live_lines(key)
        assert lines[0] == headline, key
        assert len(lines) == n, key


def test_spg_sibling_quarters_keep_live_shape():
    for key, headline, n in SPG_SIBLINGS:
        lines = _live_lines(key)
        assert lines[0] == headline, key
        assert len(lines) == n, key
