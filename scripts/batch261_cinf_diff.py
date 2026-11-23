"""Batch 261 diff: full stored-vs-live diffs for the CINF SKIP-loss rows."""
import difflib
import os
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch242_repair import sweep_gate_s4
from batch244_repair import classify_s5
from batch247_repair import sweep_gate_s6
from batch248_repair import sweep_gate_s7
from batch250_repair import sweep_gate_s8
from batch251_repair import sweep_gate_s9
from batch253_repair import sweep_gate_s10
from batch254_repair import sweep_gate_s11
from batch255_repair import sweep_gate_s12
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"
KEYS = [
    "CINF_2024-09-30",
    "CINF_2025-03-31",
    "CINF_2025-09-30",
    "CINF_2026-03-31",
    "CINF_2026-06-30",
    "CINF_2026-09-30",
]


def main():
    con = sqlite3.connect(DB)
    for key in KEYS:
        t, pe = key.rsplit("_", 1)
        stored = con.execute(
            "SELECT q.press_release_highlights FROM quarterly_financials q "
            "JOIN companies c ON c.cik = q.cik WHERE c.ticker=? AND q.period_end=?",
            (t, pe),
        ).fetchone()
        if not stored:
            print(f"\n===== {key}: NO STORED ROW")
            continue
        stored = stored[0]
        html = open(os.path.join(CACHE, f"{key}.html"), encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        print(f"\n===== {key} stored={len(stored)} live={len(live or '')}")
        print(f"  S4={sweep_gate_s4(stored, live)} S5={classify_s5(stored, live)} "
              f"S6={sweep_gate_s6(stored, live, html)} S7={sweep_gate_s7(stored, live)} "
              f"S8={sweep_gate_s8(stored, live, html)} S9={sweep_gate_s9(stored, live, html)} "
              f"S10={sweep_gate_s10(stored, live)} S11={sweep_gate_s11(stored, live)} "
              f"S12={sweep_gate_s12(stored, live)}")
        o = stored.split("\n")
        n = (live or "").split("\n")
        print(f"  --- stored ({len(o)} lines) ---")
        for ln in o:
            print(f"  S| {ln[:200]}")
        print(f"  --- live ({len(n)} lines) ---")
        for ln in n:
            print(f"  L| {ln[:200]}")


if __name__ == "__main__":
    main()
