"""Batch 247 probe: the ADSK x6 rows batch 246 carried forward.

Batch 246 now serves the executive quote after the dateline, but the
six ADSK loss rows still do not re-sync: the stored dateline differs
only in "--" spacing (stored " -- " vs live "--") and the stored row
ends on the trailing period subheading ("First Quarter Fiscal 2026"
...). This probe dumps stored vs live for every ADSK row, runs the
S4/S5 gates to confirm the blocker, and char-diffs the dateline
lines so the norm rule can be written exactly.

Usage: .venv/bin/python scripts/batch247_probe.py > /tmp/batch247_dump.txt
"""
import difflib
import os
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import non_empty, norm
from batch242_repair import sweep_gate_s4
from batch244_repair import classify_s5
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE c.ticker = 'ADSK' ORDER BY q.period_end"
    ).fetchall()
    for pe, stored in rows:
        key = f"ADSK_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            print(f"{key}: NO CACHE")
            continue
        html = open(path, encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None:
            print(f"{key}: LIVE NONE")
            continue
        if norm(stored) == norm(live):
            print(f"{key}: IN-SYNC")
            continue
        r4 = sweep_gate_s4(stored, live)
        cls5 = classify_s5(stored, live) if r4 else None
        print(f"\n{'=' * 100}\n{key}: S4={r4} S5={cls5} "
              f"stored {len(stored)} chars / live {len(live)} chars")
        s_lines = non_empty(stored)
        l_lines = non_empty(live)
        print("--- STORED ---")
        for i, x in enumerate(s_lines):
            print(f"  S{i:02d} {x[:200]}")
        print("--- LIVE ---")
        for i, x in enumerate(l_lines):
            print(f"  L{i:02d} {x[:200]}")
        print("--- LINE DIFF (stored vs live, unified) ---")
        for ln in difflib.unified_diff(
            s_lines, l_lines, lineterm="", n=0
        ):
            print(f"  {ln[:200]}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
