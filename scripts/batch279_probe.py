"""Batch 279 probe: AZO x5 SKIP-loss rows.

All 5 AZO rows share first-loss line "MEMPHIS, Tenn., ... (GLOBE
NEWSWIRE) -- AutoZone, Inc. (NYSE: AZO) today reported net sales of
$X billion ..." — the press-release lede paragraph. Compare stored vs
live per row, char counts, and the exact stored-only / live-only lines.
DRY RUN only — no DB writes.

Usage: .venv/bin/python scripts/batch279_probe.py
"""
import os
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from tickerlens.data import filings as F

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"
KEYS = ["AZO_2025-05-10", "AZO_2025-08-30", "AZO_2026-02-14",
        "AZO_2026-05-09", "AZO_2026-08-29"]


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
                print(f"  S: {x[:400]}")
        print("--- LIVE-ONLY lines (exact, not in stored) ---")
        sset = set(sl)
        for x in ll:
            if x not in sset:
                print(f"  L: {x[:400]}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
