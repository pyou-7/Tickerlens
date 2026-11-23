"""Batch 285 regression tests.

Two zero-figure-loss re-syncs of truncated stored press-release
highlights (stored truncated, live fuller, siblings already
live-shape):

MCO_2026-09-30: the stored row served the dateline paragraph + CEO
quote + "Third Quarter 2026 Highlights" heading + only the first 2
highlight bullets (revenue, operating margin), with the seed-era
no-space bullet defect ("•MCO"). Live serves the full 6-bullet
highlight block: headline identical, no stored $/% figure missing
from live, live gains 11 figures (EPS +18%/+6%, operating cash flow
$2,471M, Free Cash Flow $2,200M, $3.1B returned, $16.00-$16.50
guidance). The 8 cached MCO siblings already store the live shape.

CB_2024-06-30: the stored row carried a stray standalone "●"
bullet-marker line and was truncated mid-release (missing the P&C
underwriting income paragraph). Live serves the full block: headline
identical, no stored $/% figure missing from live, live gains 8
figures (P&C underwriting income $1.42B, record $1.81B
ex-catastrophe, 83.2% combined ratio). The 9 cached CB siblings
already store the live shape.

No extractor change in batch 285: the re-syncs are DB repairs.

Open, noted not fixed: the remaining SKIP-loss rows (largest groups
DHI x4, GPC x4, APH x3, BLK x3, CSX x3, DASH x3, EQIX x3 —
DHI/GPC/APH/BLK lose stored figures on re-sync; CSX x3 probed in
batch 285: two Q4 rows gain figures at zero loss but the 2026-06-30
row's live is shorter than stored, so CSX stays held as a group;
remaining zero-figure-loss candidates: CLX x2, DG x1, EXPE x1,
SPG 2025-09-30; SPG 2024-09-30 loses figures and stays held).
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

MCO_HEADLINE = "MOODY’S CORPORATION REPORTS RESULTS FOR THIRD QUARTER 2026"
MCO_FIRST_BULLET = "• MCO revenue of $2.0 billion increased 1% from the prior-year period and 3% on an organic constant currency1 basis."
MCO_LAST_BULLET = "• Reaffirmed guidance2 for full-year 2026, including Diluted EPS range of $16.00 to $16.50 and Adjusted Diluted EPS1 range of $16.50 to $17.00."

CB_HEADLINE = "Chubb Reports Second Quarter Per Share Net Income and Core Operating Income of $5.46 and $5.38, Up 26.4% and 9.3%, Respectively; Consolidated Net Premiums Written of $13.4 Billion, Up 11.8%, or 12.3% in Constant Dollars, with P&C Up 10.6% and Life Insurance Up 27.6%; P&C Combined Ratio of 86.8%; Record Year-to-Date Per Share Net Income and Core Operating Income of $10.68 and $10.78, Up 20.8% and 15.7%, Respectively"
CB_FIRST_BODY = "Net income was $2.23 billion, up 24.3%, and core operating income was $2.20 billion, up 7.5%. For the"
CB_LAST_LINE = "year excluding catastrophe losses basis. Both were records."

# Siblings already store the live shape: headline, line count.
MCO_SIBLINGS = (
    ("MCO_2024-09-30", "MOODY'S CORPORATION REPORTS RESULTS FOR THIRD QUARTER 2024", 13),
    ("MCO_2024-12-31", "MOODY'S CORPORATION REPORTS RESULTS FOR FOURTH QUARTER AND FULL YEAR 2024; SETS OUTLOOK FOR 2025", 13),
    ("MCO_2025-03-31", "MOODY'S CORPORATION REPORTS RESULTS FOR FIRST QUARTER 2025", 13),
    ("MCO_2025-06-30", "MOODY'S CORPORATION REPORTS RESULTS FOR SECOND QUARTER 2025", 13),
    ("MCO_2025-09-30", "MOODY'S CORPORATION REPORTS RESULTS FOR THIRD QUARTER 2025", 13),
    ("MCO_2025-12-31", "MOODY'S CORPORATION REPORTS RESULTS FOR FOURTH QUARTER AND FULL YEAR 2025; SETS OUTLOOK FOR 2026", 13),
    ("MCO_2026-03-31", "MOODY'S CORPORATION ACHIEVED RECORD RESULTS FOR FIRST QUARTER 2026", 8),
    ("MCO_2026-06-30", "MOODY’S CORPORATION DELIVERS EXCEPTIONAL RESULTS FOR SECOND QUARTER 2026", 7),
)
CB_SIBLINGS = (
    ("CB_2024-09-30", "Chubb Reports Third Quarter Per Share Net Income and Core Operating Income of $5.70 and $5.72, Up 15.2% and 15.6%, Respectively, with P&C Underwriting and Net Investment Income Both Up Double-Digit; Global P&C and Life Insurance Net Premiums Written were Up 8.5% and 10.6%, in Constant Dollars", 9),
    ("CB_2024-12-31", "Chubb Reports Fourth Quarter Per Share Net Income and Core Operating Income of $6.33 and $6.02, Respectively; Consolidated Net Premiums Written of $12.1 Billion, with Global P&C and Life Insurance Up 6.7% and 7.6%; P&C Combined Ratio of 85.7%; Record Full-Year Per Share Net Income of $22.70 and Core Operating Income of $22.51; Consolidated Net Premiums Written of $51.5 Billion, Up 8.7%, with Global P&C Up 9.6% and Life Insurance Up 15.7%; P&C Combined Ratio of 86.6%", 8),
    ("CB_2025-03-31", "Chubb Reports First Quarter Per Share Net Income and Core Operating Income of $3.29 and $3.68, Respectively; Consolidated Net Premiums Written of $12.6 Billion, Up 5.7% in Constant Dollars, with P&C and Life Insurance Up 5.0% and 10.3%; P&C Combined Ratio of 95.7%, or 82.3% Excluding Catastrophe Losses and Prior Period Development", 8),
    ("CB_2025-06-30", "Chubb Reports Second Quarter Per Share Net Income of $7.35, Up 34.6%, and Record Per Share Core Operating Income of $6.14, Up 14.1%; Consolidated Net Premiums Written of $14.2 Billion, Up 6.3%, or 7.1% in Constant Dollars, with P&C and Life Insurance Up 5.8% and 17.3%, Respectively; P&C Combined Ratio of 85.6%", 9),
    ("CB_2025-09-30", "Chubb Reports Third Quarter Net Income Per Share of $6.99, Up 22.6%, and Record Core Operating Income Per Share of $7.49, Up 30.9%; Consolidated Net Premiums Written of $14.9 Billion, Up 7.5%; Record P&C Combined Ratio of 81.8%", 7),
    ("CB_2025-12-31", "Chubb Reports Fourth Quarter Net Income of $3.21 Billion, Up 24.7%, and Core Operating Income of $2.98 Billion, Up 21.7%; Consolidated Net Premiums Written of $13.1 Billion, Up 8.9%, with P&C and Life Insurance Up 7.7% and 16.9%; Record P&C Combined Ratio of 81.2%; Full-Year Record Net Income of $10.31 Billion, Up 11.2%, and Record Core Operating Income of $9.95 Billion, Up 8.9%; Consolidated Net Premiums Written of $54.8 Billion, Up 6.6%, with P&C and Life Insurance Up 5.4% and 15.1%; Record P&C Combined Ratio of 85.7%", 10),
    ("CB_2026-03-31", "Chubb Reports First Quarter Per Share Net Income and Core Operating Income of $5.88 and $6.82, Respectively, Up 78.8% and 85.2%; Consolidated Net Premiums Written of $14.0 Billion, Up 10.7%, with P&C and Life Insurance Up 7.2% and 33.1%; P&C Combined Ratio of 84.0%", 7),
    ("CB_2026-06-30", "Chubb Reports Second Quarter Per Share Net Income of $7.30 and Per Share Core Operating Income of $7.26, Up 18.2%; Consolidated Net Premiums Written of $14.7 Billion, Up 3.6%, with P&C and Life Insurance Up 3.0% and 7.5%; P&C Combined Ratio of 83.8%", 9),
    ("CB_2026-09-30", "Chubb Reports Third Quarter Per Share Net Income and Record Core Operating Income of $7.30 and $7.66, Respectively, Up 4.4% and 0.8%; Consolidated Net Premiums Written of $15.1 Billion, Up 1.9%, with P&C and Life Insurance Up 1.9% and 1.4%; P&C Combined Ratio of 84.1%; Record Year-to-Date Per Share Net Income and Core Operating Income of $20.46 and $21.94, Up 16.2% and 24.5%, Respectively; Annualized Return on Equity (ROE) of 14.5% and Core Operating ROE of 14.6%", 8),
)


def _live(ticker_period: str) -> str:
    with open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ) as fh:
        return extract_press_release_highlights(fh.read()) or ""


def _live_lines(ticker_period: str) -> list[str]:
    return [ln for ln in _live(ticker_period).split("\n") if ln.strip()]


def test_mco_resynced_quarter_serves_full_highlight_block():
    key = "MCO_2026-09-30"
    live = _live(key)
    lines = _live_lines(key)
    assert lines[0] == MCO_HEADLINE, key
    bullets = [ln for ln in lines if ln.startswith("•")]
    assert bullets[0] == MCO_FIRST_BULLET, key
    assert bullets[-1] == MCO_LAST_BULLET, key
    assert len(lines) == 7, key
    assert len(bullets) == 6, key
    # The stored row's dateline + CEO quote + heading shape is gone.
    assert "NEW YORK, NY - October 21, 2026" not in live, key
    assert "Moody’s delivered another quarter" not in live, key
    assert "Third Quarter 2026 Highlights" not in live, key
    # The stored rows' no-space bullet defect is gone in live.
    assert "•MCO" not in live, key
    # Live carries the quarter's figures the stored row truncated away.
    assert "Diluted EPS and Adjusted Diluted EPS1 increased 18% and 6%" in live, key
    assert "operating cash flow was $2,471 million" in live, key
    assert "Diluted EPS range of $16.00 to $16.50" in live, key


def test_cb_resynced_quarter_serves_full_block():
    key = "CB_2024-06-30"
    live = _live(key)
    lines = _live_lines(key)
    assert lines[0] == CB_HEADLINE, key
    assert lines[1] == CB_FIRST_BODY, key
    assert lines[-1] == CB_LAST_LINE, key
    assert len(lines) == 9, key
    # The stored row's stray standalone bullet-marker line is gone.
    assert "●" not in lines, key
    # Live carries the underwriting paragraph the stored row truncated.
    assert "P&C underwriting income was $1.42 billion" in live, key
    assert "record low combined ratio of 83.2%" in live, key
    assert "Both were records." in live, key


def test_mco_sibling_quarters_keep_live_shape():
    for key, headline, n in MCO_SIBLINGS:
        lines = _live_lines(key)
        assert lines[0] == headline, key
        assert len(lines) == n, key


def test_cb_sibling_quarters_keep_live_shape():
    for key, headline, n in CB_SIBLINGS:
        lines = _live_lines(key)
        assert lines[0] == headline, key
        assert len(lines) == n, key
