"""Batch 272 diagnosis: stored-vs-live diffs for the three tied next-largest
SKIP-loss groups — AXON x6, DRI x5, F x6 — so the batch can pick the
tractable one. Read-only.

Usage: .venv/bin/python scripts/batch272_diagnose.py [AXON|DRI|F]
"""
import difflib
import os
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch242_repair import sweep_gate_s4
from batch255_repair import sweep_gate_s12
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"
GROUPS = {
    "AXON": ["AXON_2024-09-30", "AXON_2025-03-31", "AXON_2025-06-30",
             "AXON_2025-09-30", "AXON_2026-03-31", "AXON_2026-06-30"],
    "DRI": ["DRI_2024-11-24", "DRI_2025-02-23", "DRI_2025-08-24",
            "DRI_2025-11-23", "DRI_2026-02-22"],
    "F": ["F_2024-12-31", "F_2025-03-31", "F_2025-06-30", "F_2025-09-30",
          "F_2025-12-31", "F_2026-03-31"],
}


def main() -> int:
    want = sys.argv[1:] or list(GROUPS)
    con = sqlite3.connect(DB)
    for g in want:
        for key in GROUPS[g]:
            t, pe = key.rsplit("_", 1)
            stored = con.execute(
                "SELECT q.press_release_highlights FROM quarterly_financials q "
                "JOIN companies c ON c.cik = q.cik WHERE c.ticker=? AND q.period_end=?",
                (t, pe),
            ).fetchone()[0]
            html = open(os.path.join(CACHE, f"{key}.html"), encoding="utf-8").read()
            live = extract_press_release_highlights(html)
            print(f"\n===== {key}  stored={len(stored or '')} live={len(live or '')}")
            print(f"  S4: {sweep_gate_s4(stored, live)}  S12: {sweep_gate_s12(stored, live)}")
            o = (stored or "").split("\n")
            n = (live or "").split("\n")
            for ln in difflib.unified_diff(o, n, lineterm="", n=0):
                if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---")):
                    print(f"  {ln[:200]}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
