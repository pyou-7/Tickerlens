"""Batch 262: the white-bullet "◦" (U+25E6) joins _BULLET_LEAD_RE.

Disney, Amgen, Gilead, Boston Scientific, Capital One and others typeset
their segment sub-bullets with "◦" ("◦ Direct-to-Consumer operating
income increased $431 million to $293 million"). The glyph was missing
from _BULLET_LEAD_RE even though the rest of filings.py already treats
it as a bullet (the 81-120 band exclusion, the _is_trailing_table_data_row
guard, _strip_bullet), so the batch-175 bullet guard in _is_lede_data_row
missed it: figure-dense ◦ lines read as table rows, the lede bullet-run
collection stopped at the first one, and S4's added-table check blocked
the DIS x4 re-sync (live adds 8 genuine ◦/• lines; stored only loses its
dateline).

The fix is one glyph in the regex. Blast over the 1,699-exhibit cache:
42 exhibits change, all grow, none shrink — 285 added lines, every one a
◦/• narrative bullet (verified in scripts/batch262_probe5.py). The
headline-repeat wart in AMGN_2023-12-31 (a repeated page header inside
a wrapped ◦ bullet's continuation) is the single exception: that quarter
is not a stored row, so it is carried forward, not fixed here.

Census: B 1068 -> 1072 after the repair (32 rows re-sync under S4:
AMGN x8, APLD, BSX x8, CARR, CCI, COF x7, DIS x4, ET, GILD x2);
SKIP-loss 131 unchanged; SKIP-added-table 4 -> 0.
"""
import os
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import hard_table
from batch242_repair import sweep_gate_s4
from tickerlens.data.filings import (
    _BULLET_LEAD_RE,
    _is_lede_data_row,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _read(key: str) -> str:
    with open(os.path.join(CACHE, f"{key}.html"), encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _highlights(key: str) -> str:
    hl = extract_press_release_highlights(_read(key))
    assert hl is not None
    return hl


def _lines(text: str) -> list[str]:
    return [ln for ln in text.split("\n") if ln.strip()]


# --- The regex: "◦" is a bullet lead. ---


def test_bullet_lead_matches_white_bullet() -> None:
    assert _BULLET_LEAD_RE.match("◦ Direct-to-Consumer operating income")
    # Attached form (AWK's "◦2023 weather-normalized earnings ...").
    assert _BULLET_LEAD_RE.match("◦2023 weather-normalized earnings of $4.77")
    # The existing leads are untouched.
    assert _BULLET_LEAD_RE.match("• Revenues increased 5%")
    assert _BULLET_LEAD_RE.match("n The Cincinnati Indemnity Company")
    assert not _BULLET_LEAD_RE.match("Direct-to-Consumer operating income")


def test_white_bullet_lines_are_not_data_rows() -> None:
    # Every DIS line that tripped hard_table before the fix.
    tripping = [
        "◦ Direct-to-Consumer operating income increased $431 million to $293 million",
        "◦ 178 million Disney+ and Hulu subscriptions, an increase of 0.9 million vs. Q4 fiscal 2024",
        "◦ 125 million Disney+ subscribers, a decrease of 0.7 million vs. Q4 fiscal 2024",
        "◦ Domestic ESPN advertising revenue up 15% vs. Q1 fiscal 2024",
        "◦ Direct-to-Consumer operating income increased $289 million to $336 million",
        "◦ Direct-to-Consumer operating income increased $365 million to $346 million",
        "◦ Direct-to-Consumer operating income increased $99 million to $352 million",
    ]
    for ln in tripping:
        assert not _is_lede_data_row(ln), ln
        assert not hard_table(ln), ln


def test_genuine_table_rows_still_qualify() -> None:
    # The bullet guard must not swallow real rows: no bullet lead here.
    assert _is_lede_data_row(
        "Net income (loss) per share—diluted $0.65 $(3,903) N/A $0.55 $0.10"
    )
    assert _is_lede_data_row("Restructuring / Related Costs ~$0.06 ~$0.20")
    assert _is_lede_data_row(
        "Net income (loss) applicable to common shareholders 1,161 (41) NM 2,651 (1,776) NM"
    )


# --- Real-exhibit pins: the bullet run no longer stops at the first ◦. ---


def test_dis_sub_bullets_served_and_gate_blesses() -> None:
    hl = _highlights("DIS_2024-12-28")
    assert "◦ Direct-to-Consumer operating income increased $431 million to $293 million" in hl
    assert "◦ 178 million Disney+ and Hulu subscriptions" in hl
    assert "• Sports: Segment operating income increased $350 million to $247 million" in hl
    # The stored row (seed-era, dateline + 5 top bullets) re-syncs under
    # S4 now that the ◦ lines are bullets, not added-table material.
    import sqlite3

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    con = sqlite3.connect(os.path.join(repo_root, "tickerlens.db"))
    stored = con.execute(
        "SELECT q.press_release_highlights FROM quarterly_financials q "
        "JOIN companies c ON c.cik = q.cik "
        "WHERE c.ticker='DIS' AND q.period_end='2024-12-28'"
    ).fetchone()[0]
    assert sweep_gate_s4(stored, hl) is None


def test_amgn_horizon_sub_bullet_served() -> None:
    hl = _highlights("AMGN_2024-03-31")
    assert "$914 million of sales from our Horizon Therapeutics" in hl
    assert "◦ Excluding sales from Horizon, our product sales grew 6%" in hl
    assert "• GAAP loss per share was $0.21" in hl


def test_gild_revenue_bullet_served_with_sub_bullets() -> None:
    hl = _highlights("GILD_2026-06-30")
    assert "Total second quarter 2026 revenues increased 10% to $7.8 billion" in hl
    assert "primarily driven by:" in hl
    assert "◦ Higher sales of HIV products" in hl
    assert "◦ Higher royalty, contract and other revenues" in hl
    assert "• During the second quarter 2026, Gilead generated $3.6 billion in operating cash flow." in _lines(hl)[-1]
    assert len(hl) == 3381


def test_cci_outlook_sub_bullets_served() -> None:
    hl = _highlights("CCI_2026-03-31")
    assert "◦ Interest expense is expected to decrease by approximately $40 million" in hl
    assert "◦ Interest income is expected to increase by approximately $10 million" in hl
    assert len(hl) == 3666


def test_cof_expense_sub_bullets_served() -> None:
    hl = _highlights("COF_2024-03-31")
    assert "◦ 19 percent decrease in marketing." in hl
    assert "◦ 8 percent decrease in operating expenses." in hl
    assert "• Pre-provision earnings(2) increased 13 percent to $4.3 billion." in hl
