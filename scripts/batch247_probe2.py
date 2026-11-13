"""Batch 247 probe 2: full census with per-row classification.

Dumps one line per stored highlights row: KEY CLASS, where CLASS is
B (in-sync under norm), S4, S5-<class>, or SKIP-<reason>. The baseline
run (before the batch-247 norm change) is saved and diffed against
the post-norm run, so every classification flip the dash-spacing rule
causes is visible and inspectable — the blast for a comparison change.

Usage: .venv/bin/python scripts/batch247_probe2.py > /tmp/batch247_census.txt
"""
import os
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import norm
from batch242_repair import sweep_gate_s4
from batch244_repair import classify_s5, verify_fy_stored
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    for t, pe, stored in rows:
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            print(f"{key} SKIP-nocache")
            continue
        html = open(path, encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None:
            print(f"{key} SKIP-live-none")
            continue
        if norm(stored) == norm(live):
            print(f"{key} B")
            continue
        r4 = sweep_gate_s4(stored, live)
        if r4 is None:
            print(f"{key} S4")
            continue
        cls5 = classify_s5(stored, live)
        if cls5 is None and verify_fy_stored(html, stored, live):
            cls5 = "s5-fy-stored"
        if cls5 is not None:
            print(f"{key} S5-{cls5}")
            continue
        print(f"{key} SKIP-{r4}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
