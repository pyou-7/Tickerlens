"""Batch 263 probe: the DIS_2025-09-27 tail row and the EL colon-opener
shape — the batch-259 extension refuses colon-ended bullets as sub-list
openers on the premise that ◦ items "the loop does not recognize as
bullets". Batch 262 made that premise false for ◦. Dump the exact line
sequences to see whether relaxing the refusal is safe.
"""
import os
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import non_empty, norm
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
    path = f"{CACHE}/{key}.html"
    html = open(path, encoding="utf-8").read()
    live = extract_press_release_highlights(html)
    print(f"===== {key} =====")
    print(f"--- stored ({len(non_empty(row[0]))} lines):")
    for x in non_empty(row[0]):
        print("  S:", repr(x))
    print(f"--- live ({len(non_empty(live))} lines):")
    for x in non_empty(live):
        print("  L:", repr(x))
    print()


for key in ("DIS_2025-09-27", "EL_2025-03-31", "EL_2024-06-30", "ABT_2024-12-31"):
    if os.path.exists(f"{CACHE}/{key}.html"):
        show(key)
    else:
        print(f"===== {key}: no cached exhibit")
