"""Batch 262 probe: identify the SKIP-added-table (4) and SKIP-live-table (1)
rows, and diff stored vs live for the DIS rows to see the sub-bullet shape.

The carried-forward note says DIS x4: live adds a ◦ sub-bullet that is
genuinely table-shaped — hard_table fires on the sub-bullet itself, so
re-sync needs the sub-bullet-table design question, not a chrome fix.
"""
import os
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import non_empty, norm
from batch242_repair import hard_table, sweep_gate_s4
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"

con = sqlite3.connect(DB)
rows = con.execute(
    "SELECT c.ticker, q.period_end, q.press_release_highlights "
    "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
    "WHERE q.press_release_highlights IS NOT NULL "
    "ORDER BY c.ticker, q.period_end"
).fetchall()

by_reason = {}
for t, pe, stored in rows:
    key = f"{t}_{pe}"
    path = f"{CACHE}/{key}.html"
    if not os.path.exists(path):
        continue
    html = open(path, encoding="utf-8").read()
    live = extract_press_release_highlights(html)
    if live is None or norm(stored) == norm(live):
        continue
    reason = sweep_gate_s4(stored, live)
    by_reason.setdefault(reason, []).append((key, stored, live))

for reason in ("added-table", "live-table"):
    print(f"=== {reason}: {len(by_reason.get(reason, []))} rows")
    for key, _, _ in by_reason.get(reason, []):
        print("   ", key)

print()
for key, stored, live in by_reason.get("added-table", []):
    if not key.startswith("DIS"):
        continue
    s_lines = non_empty(stored)
    l_lines = non_empty(live)
    s_set = set(s_lines)
    print(f"### {key}: stored {len(s_lines)} lines, live {len(l_lines)} lines")
    print("--- live-only lines tripping hard_table:")
    for x in l_lines:
        if x not in s_set and hard_table(x):
            print("    TABLE:", repr(x))
    print("--- live-only lines NOT tripping hard_table:")
    for x in l_lines:
        if x not in s_set and not hard_table(x):
            print("    OTHER:", repr(x))
    print("--- stored-only lines:")
    for x in s_lines:
        if x not in set(l_lines):
            print("    STORED:", repr(x))
