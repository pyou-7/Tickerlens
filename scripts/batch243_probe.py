"""Batch 243 probe: dump the 16 SKIP-first-diff rows (as censused by
batch 242, DRY re-run) stored-vs-live, side by side, so the batch
can decompose them into gate classes.

Also prints a per-ticker count of the 204 SKIP-loss rows, to size
the loss cohort's clusters for the next gate.

Usage: .venv/bin/python scripts/batch243_probe.py > /tmp/batch243_dump.txt
"""
import os
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import norm
from batch242_repair import sweep_gate_s4
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"

FIRST_DIFF = [
    "AGNC_2024-12-31", "AGNC_2025-12-31", "AMT_2024-09-30",
    "APO_2024-09-30", "APO_2024-12-31", "APO_2025-03-31",
    "APO_2025-06-30", "APO_2025-09-30", "APO_2025-12-31",
    "APO_2026-03-31", "APO_2026-06-30", "COIN_2026-03-31",
    "CSCO_2026-01-24", "CSCO_2026-04-25", "CSCO_2026-07-25",
    "NFLX_2025-06-30",
]


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights, q.cik "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    loss_by_ticker: Counter[str] = Counter()
    for t, pe, stored, cik in rows:
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            continue
        html = open(path, encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None or norm(stored) == norm(live):
            continue
        reason = sweep_gate_s4(stored, live)
        if reason == "loss":
            loss_by_ticker[t] += 1
        if key not in FIRST_DIFF:
            continue
        print(f"\n{'=' * 100}\n{key}  stored {len(stored)} chars / live {len(live)} chars")
        s_lines = [x for x in stored.split("\n") if x.strip()]
        l_lines = [x for x in live.split("\n") if x.strip()]
        print(f"--- STORED ({len(s_lines)} lines) ---")
        for i, x in enumerate(s_lines):
            print(f"  S{i:02d} {x[:200]}")
        print(f"--- LIVE ({len(l_lines)} lines) ---")
        for i, x in enumerate(l_lines):
            print(f"  L{i:02d} {x[:200]}")
    print("\n\nLOSS BY TICKER (204 rows):")
    for t, n in loss_by_ticker.most_common():
        print(f"  {t}: {n}")
    print(f"  TOTAL: {sum(loss_by_ticker.values())}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
