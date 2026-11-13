"""Batch 246 cache blast: full-cache stored-vs-live census under gate S4
then gate S5 (batch244_repair). One deterministic line per cached row so
a before/after run of the batch-246 extractor fix diffs cleanly.

Usage: .venv/bin/python scripts/batch246_cache_blast.py > /tmp/blast246.txt
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
    counts: dict[str, int] = {}
    for t, pe, stored in rows:
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            status = "SKIP-nocache"
        else:
            html = open(path, encoding="utf-8").read()
            live = extract_press_release_highlights(html)
            if live is None:
                status = "SKIP-live-none"
            elif norm(stored) == norm(live):
                status = "B"
            else:
                reason4 = sweep_gate_s4(stored, live)
                if reason4 is None:
                    status = "S4"
                else:
                    cls5 = classify_s5(stored, live)
                    if cls5 is None and verify_fy_stored(html, stored, live):
                        cls5 = "s5-fy-stored"
                    status = cls5 if cls5 is not None else f"SKIP-{reason4}"
        counts[status] = counts.get(status, 0) + 1
        print(f"{key} {status}")
    print(f"\nCOUNTS {counts}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
