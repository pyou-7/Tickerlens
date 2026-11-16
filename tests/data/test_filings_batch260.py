"""Batch 260 regression tests: gate S4's policing refused three rows
that are pure additions of genuine bullets.

1. EIX x2 (scripts/batch260_probe.py): S4 "added-table" was tripped
   NOT by the added EPS bullet (hard_table is False on it) but by
   the leading contact line "Investor Relations: Sam Ramraj, (626)
   302-2540" — the phone number matches _is_lede_data_row /
   _is_trailing_table_data_row. The line is in stored too, but
   _strip_leading_chrome removed it from stored only, so the
   added-table scan saw it as live-only. The fix strips leading
   chrome from the live lines as well before that scan.
2. BRO 2026-09-30: S4 "fragment" fired on live's second line,
   "including total revenues of $1.7 billion, ..." — a lowercase
   headline continuation stored carries in the same position. The
   fix exempts the fragment refusal when live's second line equals
   stored's second line post-alignment.

The full-census simulation (batch260_probe.py) shows fixes A+B
move exactly those 3 rows, SKIP-loss -> S4, and nothing else. The
controls below pin the guards: a contact line added mid-text still
trips added-table (the strip is front-only), a genuinely new
lowercase second line still trips fragment, and DIS's added
sub-bullet (a real hard_table line) still trips added-table.
"""
import sys

sys.path.insert(0, "scripts")

from batch242_repair import sweep_gate_s4

# Real EIX 2025-06-30 lines, verbatim (stored from the DB, live from
# the cached exhibit). The only live addition is the final bullet.
_STORED_EIX = (
    "Investor Relations: Sam Ramraj, (626) 302-2540\n"
    "Edison International Reports Second-Quarter 2025 Results\n"
    "• Second-quarter 2025 GAAP EPS of $0.89; Core EPS of $0.97\n"
    "• Eaton Fire investigations ongoing; SCE plans to launch Wildfire "
    "Recovery Compensation Program\n"
    "• Confident that legislative action will ultimately enhance "
    "California’s AB 1054 regulatory framework\n"
    "• Continued strong regulatory progress: WMCE settlement approved; "
    "final decision issued in WM/VM proceeding; GRC proposed decision issued\n"
    "• Reaffirmed 2025 Core EPS guidance of $5.94-$6.34\n"
)
_LIVE_EIX = _STORED_EIX + (
    "• Continued confidence in delivering 5-7% Core EPS growth from "
    "2025 to 2028 ($6.74-$7.14)\n"
)

# Real BRO 2026-09-30 lines, verbatim (headline, lowercase
# continuation, dateline, first bullet; live adds the Q3 bullet).
_STORED_BRO = (
    "Brown & Brown, Inc. announces third quarter 2026 results\n"
    "including total revenues of $1.7 billion, an increase of 7.4%; "
    "growth of Organic Revenue of 1.2%; growth of Organic Revenue "
    "with Contingents of 1.5%; diluted net income per share of $0.67; "
    'and Diluted Net Income Per Share - Adjusted of $1.07\n'
    "DAYTONA BEACH, Fla., October 26, 2026 - Brown & Brown, Inc. "
    '(NYSE:BRO) (the "Company") announced its unaudited financial '
    "results for the third quarter of 2026.\n"
    "• Total revenues of $1.7 billion, increasing $119 million, or "
    "7.4%, compared to the third quarter of the prior year, with "
    "growth of Organic Revenue of 1.2% and growth of Organic Revenue "
    "with Contingents of 1.5%.\n"
)
_LIVE_BRO = _STORED_BRO + (
    "• Diluted net income per share of $0.67, a decrease of 1.5%, "
    "with Diluted Net Income Per Share - Adjusted increasing to "
    "$1.07, or 1.9%, each compared to the third quarter of the prior "
    "year.\n"
)


def test_gate_s4_eix_contact_line_no_longer_added_table() -> None:
    assert sweep_gate_s4(_STORED_EIX, _LIVE_EIX) is None


def test_gate_s4_bro_shared_lowercase_second_line_no_longer_fragment() -> None:
    assert sweep_gate_s4(_STORED_BRO, _LIVE_BRO) is None


def test_gate_s4_mid_text_contact_line_still_added_table() -> None:
    # The chrome strip is front-only: a contact line appended after
    # the content is still live-only table material.
    stored = (
        "ACME CORP REPORTS THIRD QUARTER 2026 RESULTS\n"
        "• Revenue of $1.0 billion, up 5%\n"
    )
    live = stored + "Investor Relations: Sam Ramraj, (626) 302-2540\n"
    assert sweep_gate_s4(stored, live) == "added-table"


def test_gate_s4_new_lowercase_second_line_still_fragment() -> None:
    # The exemption needs the lowercase line in stored too: a
    # genuinely new lowercase second line is still a fragment.
    stored = (
        "ACME CORP REPORTS THIRD QUARTER 2026 RESULTS\n"
        "• Revenue of $1.0 billion, up 5%\n"
    )
    live = (
        "ACME CORP REPORTS THIRD QUARTER 2026 RESULTS\n"
        "including revenue of $1.0 billion, up 5%\n"
        "• Revenue of $1.0 billion, up 5%\n"
    )
    assert sweep_gate_s4(stored, live) == "fragment"


def test_gate_s4_dis_sub_bullet_still_added_table() -> None:
    # DIS 2024-12-28 shape: the added "◦" sub-bullet is a real
    # hard_table line, not chrome, so it must still block.
    stored = (
        "THE WALT DISNEY COMPANY REPORTS FIRST QUARTER EARNINGS FOR "
        "FISCAL 2025\n"
        "• Revenues increased 5% for Q1 to $24.7 billion from $23.5 "
        "billion in Q1 fiscal 2024\n"
    )
    live = stored + (
        "◦ Direct-to-Consumer operating income increased $431 million "
        "to $293 million\n"
    )
    assert sweep_gate_s4(stored, live) == "added-table"
