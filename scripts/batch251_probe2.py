"""Batch 251 probe2: dump stored-vs-live for the large loss cohorts the
batch-250 carry-forward did not name: BNY x8, CEG x8, CHD x7, COR x7,
DHR x7, DLR x7, V x7, plus AZO/EBAY/EQIX/MU x5. Which of these is one
provable shape?

Usage: .venv/bin/python scripts/batch251_probe2.py > /tmp/batch251_dump2.txt
"""
import os
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import non_empty, norm
from batch251_probe import classify
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"

DUMP_TICKERS = ("BNY", "CEG", "CHD", "COR", "DHR", "DLR", "V", "AZO")


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    for t in DUMP_TICKERS:
        for t2, pe, stored in rows:
            if t2 != t:
                continue
            key = f"{t2}_{pe}"
            path = f"{CACHE}/{key}.html"
            if not os.path.exists(path):
                continue
            html = open(path, encoding="utf-8").read()
            live = extract_press_release_highlights(html)
            if live is None or norm(stored) == norm(live):
                continue
            if classify(stored, live, html) != "loss":
                continue
            print(f"\n{'=' * 100}\n{key}  stored {len(stored)} chars / live {len(live)} chars")
            print("--- STORED ---")
            for i, x in enumerate(non_empty(stored)):
                print(f"  S{i:02d} {x[:240]}")
            print("--- LIVE ---")
            for i, x in enumerate(non_empty(live)):
                print(f"  L{i:02d} {x[:240]}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
