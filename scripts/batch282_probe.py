"""Batch 282 probe: compare stored vs live for candidate SKIP-loss clusters.

Usage: .venv/bin/python scripts/batch282_probe.py CRWD DHI GPC ...
DRY RUN only — no DB writes.
"""
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from tickerlens.data import filings as F

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"


def main() -> int:
    tickers = sys.argv[1:] or ["CRWD"]
    con = sqlite3.connect(DB)
    for t in tickers:
        rows = con.execute(
            "SELECT q.period_end, q.press_release_highlights FROM quarterly_financials q "
            "JOIN companies c ON c.cik = q.cik WHERE c.ticker = ? "
            "AND q.press_release_highlights IS NOT NULL ORDER BY q.period_end", (t,)
        ).fetchall()
        for pe, stored in rows:
            key = f"{t}_{pe}"
            try:
                html = open(f"{CACHE}/{key}.html", encoding="utf-8").read()
            except FileNotFoundError:
                continue
            live = F.extract_press_release_highlights(html)
            if live is None:
                continue
            from batch231_repair import norm
            if norm(stored) == norm(live):
                continue
            print(f"\n{'='*100}\n{key}: stored {len(stored)} chars, live {len(live)} chars, delta {len(live)-len(stored)}")
            sl = [x for x in stored.splitlines() if x.strip()]
            ll = [x for x in live.splitlines() if x.strip()]
            print(f"stored lines: {len(sl)}, live lines: {len(ll)}")
            print("--- STORED-ONLY ---")
            lset = set(ll)
            for x in sl:
                if x not in lset:
                    print(f"  S: {x[:300]}")
            print("--- LIVE-ONLY ---")
            sset = set(sl)
            for x in ll:
                if x not in sset:
                    print(f"  L: {x[:300]}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
