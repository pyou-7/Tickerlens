"""Batch 232 repair review: line-level diff of every S2-admitted row
plus the two SKIP-fragment BRK.B rows, for the human review before
applying the repair."""
import difflib
import os
import sqlite3
import sys

sys.path.insert(0, "src")
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"

S2 = [
    "AZO_2024-11-23",
    "AZO_2025-02-15",
    "AZO_2025-11-22",
    "BIIB_2024-06-30",
    "BIIB_2025-06-30",
    "BIIB_2025-09-30",
    "BIIB_2026-09-30",
    "CNC_2025-06-30",
    "CPB_2026-08-02",
    "FAST_2025-03-31",
    "FDX_2025-02-28",
]
FRAG = ["BRK.B_2025-03-31", "BRK.B_2026-03-31"]


def lines(s):
    return [x for x in (s or "").split("\n") if x.strip()]


def main() -> int:
    con = sqlite3.connect(DB)
    for key in S2 + FRAG:
        t, pe = key.rsplit("_", 1)
        stored = con.execute(
            "SELECT q.press_release_highlights FROM quarterly_financials q "
            "JOIN companies c ON c.cik = q.cik WHERE c.ticker = ? AND q.period_end = ?",
            (t, pe),
        ).fetchone()[0]
        html = open(f"{CACHE}/{key}.html", encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        print(f"\n===== {key} ({'S2' if key in S2 else 'SKIP-fragment'}) =====")
        print(f"  stored {len(lines(stored))} lines / live {len(lines(live))} lines")
        for ln in difflib.unified_diff(
            lines(stored), lines(live), lineterm="", n=0
        ):
            if ln.startswith(("---", "+++", "@@")):
                continue
            print(f"  {ln[:300]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
