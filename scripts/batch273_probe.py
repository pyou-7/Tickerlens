"""Batch 273 probe: dump stored vs live press-release highlights for AXON
and F quarters, to rank the two tied SKIP-loss groups (x6 each) and see
what the stored rows hold vs what the current extractor serves. Read-only.
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


def probe(ticker: str) -> None:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE c.ticker = ? AND q.press_release_highlights IS NOT NULL "
        "ORDER BY q.period_end",
        (ticker,),
    ).fetchall()
    for pe, stored in rows:
        key = f"{ticker}_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            print(f"=== {key}: NO CACHE")
            continue
        live = F.extract_press_release_highlights(
            open(path, encoding="utf-8").read()
        )
        same = live is not None and norm(stored) == norm(live)
        print(f"=== {key}: stored={len(stored)} live="
              f"{len(live) if live else None} in-sync={same}")
        print("--- stored (first 10 nonblank lines):")
        for ln in [x for x in stored.split("\n") if x.strip()][:10]:
            print(f"  S| {ln}")
        print("--- live (first 10 nonblank lines):")
        if live:
            for ln in [x for x in live.split("\n") if x.strip()][:10]:
                print(f"  L| {ln}")
        else:
            print("  L| (None)")
    con.close()


def main() -> int:
    for t in sys.argv[1:]:
        probe(t)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
