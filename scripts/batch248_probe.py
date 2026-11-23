"""Batch 248 probe: the APLD boilerplate-only loss rows.

Re-census the SKIP-loss cohort under the current gates (S4/S5/S6) and
dump, for every APLD row still classified loss, the stored text, the
live text, and the lost lines with their batch-245 bucket. The question
for this batch: are the APLD rows' lost lines all boilerplate, and is
that boilerplate provably non-content (non-GAAP definition sentences,
GAAP-guidance disclaimers, webcast boilerplate) so a gate S7 can bless
the swap?

Usage: .venv/bin/python scripts/batch248_probe.py
"""
import os
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import non_empty, norm
from batch242_repair import sweep_gate_s4
from batch244_repair import classify_s5
from batch245_probe import lost_lines
from batch245_probe2 import bucket
from batch247_repair import sweep_gate_s6
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"


def classify(stored, live, html):
    """Mirror the repair sweep order: S4, then S5, then S6."""
    if sweep_gate_s4(stored, live) == "repair":
        return "s4"
    c5 = classify_s5(stored, live)
    if c5 is not None:
        return f"s5-{c5}"
    if sweep_gate_s6(stored, live, html) == "repair":
        return "s6"
    if sweep_gate_s4(stored, live) == "loss":
        return "loss"
    return "other"


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    census: Counter[str] = Counter()
    for t, pe, stored in rows:
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            census["nocache"] += 1
            continue
        html = open(path, encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None:
            census["live-none"] += 1
            continue
        if norm(stored) == norm(live):
            census["in-sync"] += 1
            continue
        census[classify(stored, live, html)] += 1
    print("CENSUS:", dict(sorted(census.items())))

    # APLD detail
    for t, pe, stored in rows:
        if t != "APLD":
            continue
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            print(f"\n=== {key}: NO CACHED EXHIBIT")
            continue
        html = open(path, encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None:
            print(f"\n=== {key}: live None")
            continue
        print(f"\n=== {key}: class={classify(stored, live, html)} "
              f"stored={len(non_empty(stored))} live={len(non_empty(live))}")
        if norm(stored) == norm(live):
            continue
        lost = lost_lines(stored, live)
        s_lines = non_empty(stored)
        l_lines = non_empty(live)
        live_set = set(l_lines)
        for i, x in enumerate(lost):
            nxt = s_lines[s_lines.index(x) + 1] if x in s_lines and s_lines.index(x) + 1 < len(s_lines) else ""
            print(f"  LOST [{bucket(x, nxt, live_set)}]: {x[:220]}")
        print("  --- stored ---")
        for ln in s_lines:
            print(f"  S: {ln[:200]}")
        print("  --- live ---")
        for ln in l_lines:
            print(f"  L: {ln[:200]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
