"""Batch 278 probe: MU x5 SKIP-loss rows.

MU's 5 SKIP-loss rows share first-loss line "Quarterly Financial Results"
with small stored-vs-live length deltas (~70 chars). Compare stored vs
live per row, char counts, and the raw exhibit lines around the loss.
DRY RUN only — no DB writes.

Usage: .venv/bin/python scripts/batch278_probe.py
"""
import os
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import norm
from tickerlens.data import filings as F

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"
KEYS = ["MU_2024-08-29", "MU_2024-11-28", "MU_2025-02-27",
        "MU_2025-05-29", "MU_2025-08-28"]


def main() -> int:
    con = sqlite3.connect(DB)
    for key in KEYS:
        t, pe = key.split("_")
        stored = con.execute(
            "SELECT q.press_release_highlights FROM quarterly_financials q "
            "JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = ? AND q.period_end = ?", (t, pe)
        ).fetchone()[0]
        html = open(f"{CACHE}/{key}.html", encoding="utf-8").read()
        live = F.extract_press_release_highlights(html)
        print(f"\n{'='*100}\n{key}: stored {len(stored)} chars, live {len(live)} chars, "
              f"delta {len(live) - len(stored)}")
        sl = [x for x in stored.splitlines() if x.strip()]
        ll = [x for x in live.splitlines() if x.strip()]
        print(f"stored lines: {len(sl)}, live lines: {len(ll)}")
        print("--- STORED-ONLY lines (exact, not in live) ---")
        lset = set(ll)
        for x in sl:
            if x not in lset:
                print(f"  S: {x[:300]}")
        print("--- LIVE-ONLY lines (exact, not in stored) ---")
        sset = set(sl)
        for x in ll:
            if x not in sset:
                print(f"  L: {x[:300]}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
