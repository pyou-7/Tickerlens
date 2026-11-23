"""Batch 242 probe 2: full stored-vs-live diffs for the first-diff
cohort, so each row's repairability under a gate-S4 extension can
be judged on complete lines, not the 160-char heads from probe 1.

For each first-diff row prints:
  MISSING: stored lines not in live (and not S3-residue)
  ADDED:   live lines not in stored
  plus the full effective-line shapes for the CTVA single-line rows.

Usage: .venv/bin/python scripts/batch242_probe2.py [TICKER ...]
"""
import os
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import non_empty, norm
from batch241_repair import is_residue_s3, sweep_gate_s3
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"


def main() -> int:
    only = set(sys.argv[1:])
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    for t, pe, stored in rows:
        key = f"{t}_{pe}"
        if only and t not in only:
            continue
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            continue
        html = open(path, encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None or norm(stored) == norm(live):
            continue
        if sweep_gate_s3(stored, live) != "first-diff":
            continue
        s_lines = non_empty(stored)
        l_lines = non_empty(live)
        live_set = set(l_lines)
        print(f"=== {key}  stored {len(s_lines)} / live {len(l_lines)}")
        for i, x in enumerate(s_lines):
            nxt = s_lines[i + 1] if i + 1 < len(s_lines) else ""
            if x not in live_set and not is_residue_s3(x, nxt, live_set):
                print(f"  MISSING S{i+1}: {x[:200]}")
        s_set = set(s_lines)
        for j, x in enumerate(l_lines):
            if x not in s_set:
                print(f"  ADDED   L{j+1}: {x[:200]}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
