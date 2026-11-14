"""Batch 249 cache blast: full-cache stored-vs-live census under gates
S4 -> S5 -> S6 -> S7. One deterministic line per cached row so a
before/after run of the batch-249 extractor fix diffs cleanly.

Usage: .venv/bin/python scripts/batch249_cache_blast.py > /tmp/blast249.txt
"""
import os
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import norm
from batch242_repair import sweep_gate_s4
from batch244_repair import classify_s5
from batch247_repair import sweep_gate_s6
from batch248_repair import sweep_gate_s7
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
            elif sweep_gate_s4(stored, live) is None:
                status = "S4"
            elif classify_s5(stored, live) is not None:
                status = f"S5-{classify_s5(stored, live)}"
            elif sweep_gate_s6(stored, live, html) is None:
                status = "S6"
            elif sweep_gate_s7(stored, live) is None:
                status = "S7"
            else:
                r6 = sweep_gate_s6(stored, live, html)
                r7 = sweep_gate_s7(stored, live)
                status = f"SKIP-{r6 if r6 is not None else r7}"
        counts[status] = counts.get(status, 0) + 1
        print(f"{key} {status}")
    print(f"\nCOUNTS {counts}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
