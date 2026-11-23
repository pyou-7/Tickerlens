"""Batch 232 probe: the dangling table-intro tail.

Batch 231's stale-row sweep blocked 6 rows on the live extraction ending
on a dangling table-intro line ("Net earnings includes:", "...were as
follows:", "...have been adjusted for:", "...primarily driven by:"):
BRK.B x3, FAST 2025-03-31, FDX 2026-05-31, GILD 2026-06-30. This probe
prints the live tail (last 6 lines) and the stored tail for each, plus
which extractor path produced it, so the trim rule can be scoped.
"""
import os
import sqlite3
import sys

sys.path.insert(0, "src")
from tickerlens.data.filings import (
    extract_management_guidance,
    extract_press_release_highlights,
)

DB = "tickerlens.db"
CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
TARGETS = [
    ("BRK.B", None),
    ("FAST", "2025-03-31"),
    ("FDX", "2026-05-31"),
    ("GILD", "2026-06-30"),
]


def lines(s):
    return [x for x in (s or "").splitlines() if x.strip()]


def main() -> int:
    con = sqlite3.connect(DB)
    for t, pe in TARGETS:
        if pe:
            rows = con.execute(
                "SELECT q.period_end, q.press_release_highlights "
                "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
                "WHERE c.ticker = ? AND q.period_end = ?",
                (t, pe),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT q.period_end, q.press_release_highlights "
                "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
                "WHERE c.ticker = ? ORDER BY q.period_end",
                (t,),
            ).fetchall()
        for period_end, stored in rows:
            key = f"{t}_{period_end}"
            print(f"\n===== {key} =====")
            if not os.path.exists(f"{CACHE}/{key}.html"):
                print("  NOT CACHED")
                continue
            html = open(f"{CACHE}/{key}.html", encoding="utf-8").read()
            live = extract_press_release_highlights(html)
            sl, ll = lines(stored), lines(live)
            print(f"  stored {len(sl)} lines / live {len(ll)} lines")
            print("  -- stored tail --")
            for x in sl[-4:]:
                print(f"    S| {x}")
            print("  -- live tail --")
            for x in ll[-6:]:
                print(f"    L| {x}")
            lg = extract_management_guidance(html)
            if lg:
                gl = lines(lg)
                print(f"  -- guidance tail ({len(gl)} lines) --")
                for x in gl[-3:]:
                    print(f"    G| {x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
