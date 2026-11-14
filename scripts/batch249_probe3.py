"""Batch 249 probe 3: verify the blast diff — every line the fix adds
to live output, on each of the 24 flipped rows, is a genuine
executive-quote line, and no stored line is lost.

Usage: .venv/bin/python scripts/batch249_probe3.py
"""
import os
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import non_empty, norm
from batch245_probe import lost_lines
from tickerlens.data.filings import (
    _is_executive_quote_line,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"

FLIPPED = """ADBE_2024-11-29 ADBE_2025-02-28 ADBE_2025-05-30 ADBE_2025-08-29
ADBE_2026-02-27 ADBE_2026-08-28 ANET_2025-12-31 ANET_2026-06-30
CRWD_2025-01-31 CRWD_2025-10-31 CRWD_2026-01-31 CRWD_2026-07-31
CSX_2025-06-30 EBAY_2024-09-30 EBAY_2024-12-31 EBAY_2025-03-31
PLTR_2024-09-30 PLTR_2024-12-31 PLTR_2025-03-31 PLTR_2025-06-30
PLTR_2025-09-30 PLTR_2025-12-31 PLTR_2026-03-31 PLTR_2026-06-30""".split()


def main() -> int:
    con = sqlite3.connect(DB)
    bad = 0
    for key in FLIPPED:
        t, pe = key.split("_", 1)
        stored = con.execute(
            "SELECT q.press_release_highlights FROM quarterly_financials q "
            "JOIN companies c ON c.cik = q.cik WHERE c.ticker = ? "
            "AND q.period_end = ?",
            (t, pe),
        ).fetchone()[0]
        html = open(f"{CACHE}/{key}.html", encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        s_lines = non_empty(stored)
        l_lines = non_empty(live)
        s_set = set(s_lines)
        added = [x for x in l_lines if x not in s_set and norm(x) not in {norm(y) for y in s_lines}]
        lost = lost_lines(stored, live)
        non_quote = [x for x in added if not _is_executive_quote_line(x)]
        flag = ""
        if non_quote:
            flag = " <-- NON-QUOTE ADDED"
            bad += 1
        if lost:
            flag += " <-- LOST LINES"
            bad += 1
        print(f"{key}: added={len(added)} quote_only={len(added) - len(non_quote)} "
              f"lost={len(lost)}{flag}")
        for x in added:
            print(f"    + {x[:180]}")
        for x in non_quote:
            print(f"    !! NON-QUOTE: {x[:180]}")
        for x in lost:
            print(f"    !! LOST: {x[:180]}")
    print(f"\nBAD ROWS: {bad} / {len(FLIPPED)}")
    con.close()
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
