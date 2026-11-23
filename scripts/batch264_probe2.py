"""Batch 264 probe 2: diff stored vs live for DIS_2024-09-28, the second
row the sub-list completion moves — verify the added lines are genuine
sub-list children, not a heading or guidance leak.
"""
import os
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import non_empty
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"

con = sqlite3.connect(DB)


def show(key):
    row = con.execute(
        "SELECT q.press_release_highlights FROM quarterly_financials q "
        "JOIN companies c ON c.cik = q.cik "
        "WHERE c.ticker = ? AND q.period_end = ?",
        (key.split("_")[0], key.split("_", 1)[1]),
    ).fetchone()
    html = open(f"{CACHE}/{key}.html", encoding="utf-8").read()
    live = extract_press_release_highlights(html)
    stored = non_empty(row[0])
    live_lines = non_empty(live)
    print(f"===== {key}: stored {len(stored)} lines, live {len(live_lines)} lines")
    ls, ll = set(stored), set(live_lines)
    print("--- in live only:")
    for x in live_lines:
        if x not in ls:
            print("  +", repr(x))
    print("--- in stored only:")
    for x in stored:
        if x not in ll:
            print("  -", repr(x))


show("DIS_2024-09-28")
