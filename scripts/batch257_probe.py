"""Batch 257 probe: re-run the full-cache census (gate chain
S4/S5/S6/S7/S8/S9/S10/S11/S12) to confirm batch 256's end state, then
probe the AMT seeding gap named in the carried-forward list: AMT
2023-12-31 / 2024-03-31 / 2024-06-30 have cached exhibits but NULL
stored highlights. For each, dump the stored row, the cached exhibit
path, what the live extractor serves from the cached HTML, and why
the seeder may have left it NULL (exhibit parse failure? no
highlights section? seeder skip?).

Usage: .venv/bin/python scripts/batch257_probe.py [--census FILE]
"""
import argparse
import os
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import non_empty, norm
from batch242_repair import sweep_gate_s4
from batch244_repair import classify_s5
from batch247_repair import sweep_gate_s6
from batch248_repair import sweep_gate_s7
from batch250_repair import sweep_gate_s8
from batch251_repair import sweep_gate_s9
from batch253_repair import sweep_gate_s10
from batch254_repair import sweep_gate_s11
from batch255_repair import sweep_gate_s12
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"


def classify(stored, live, html):
    # Batch 257: the norm-equality fast path lives HERE, not in the
    # caller. S4's policing can trip on the live text itself (a
    # lowercase second line -> "fragment"; a chrome-stripped contact
    # line that reads as a table -> "added-table") even when stored
    # and live are byte-identical — the first draft of this probe ran
    # the gate chain on every row and reported a phantom 19-row
    # regression (AAPL x1, BRK.B x6, BRO, CI, EIX x8, ELV, SKYD)
    # that was purely the missing fast path. A row whose stored text
    # norm-equals live is in-sync by definition; the gates police
    # differences, not the live text alone.
    if norm(stored) == norm(live):
        return "in-sync"
    if sweep_gate_s4(stored, live) is None:
        return "s4"
    c5 = classify_s5(stored, live)
    if c5 is not None:
        return f"s5-{c5}"
    if sweep_gate_s6(stored, live, html) is None:
        return "s6"
    if sweep_gate_s7(stored, live) is None:
        return "s7"
    if sweep_gate_s8(stored, live, html) is None:
        return "s8"
    if sweep_gate_s9(stored, live, html) is None:
        return "s9"
    if sweep_gate_s10(stored, live) is None:
        return "s10"
    if sweep_gate_s11(stored, live) is None:
        return "s11"
    if sweep_gate_s12(stored, live) is None:
        return "s12"
    return "loss"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--census", default=None)
    args = ap.parse_args()
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    totals: Counter[str] = Counter()
    census_lines: list[str] = []
    for t, pe, stored in rows:
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            totals["nocache"] += 1
            census_lines.append(f"{key} nocache")
            continue
        html = open(path, encoding="utf-8", errors="replace").read()
        live = extract_press_release_highlights(html)
        if live is None:
            totals["live-none"] += 1
            census_lines.append(f"{key} live-none")
            continue
        cls = classify(stored, live, html)
        totals[cls] += 1
        census_lines.append(f"{key} {cls}")
    print("CENSUS:", dict(sorted(totals.items())))
    print("in-sync (B):", totals.get("in-sync", 0))
    print("SKIP-loss:", totals.get("loss", 0))
    if args.census:
        with open(args.census, "w", encoding="utf-8") as fh:
            fh.write("\n".join(census_lines) + "\n")

    # --- AMT seeding gap ---
    print("\n=== AMT rows ===")
    amt = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights, "
        "q.press_release_source "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE c.ticker = 'AMT' ORDER BY q.period_end"
    ).fetchall()
    for t, pe, stored, src in amt:
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        print(f"\n--- {key} ---")
        print("stored:", "NULL" if stored is None else f"{len(stored)} chars")
        print("cached exhibit:", os.path.exists(path),
              f"({os.path.getsize(path)} bytes)" if os.path.exists(path) else "")
        print("press_release_source:", src)
        if os.path.exists(path):
            html = open(path, encoding="utf-8", errors="replace").read()
            live = extract_press_release_highlights(html)
            if live is None:
                print("live extractor: None")
            else:
                lines = non_empty(live)
                print(f"live extractor: {len(lines)} lines, {len(live)} chars")
                for ln in lines[:12]:
                    print("  |", ln[:160])
                if len(lines) > 12:
                    print(f"  ... +{len(lines) - 12} more lines")
    # how many NULL-highlights rows overall have a cached exhibit?
    nulls = con.execute(
        "SELECT c.ticker, q.period_end FROM quarterly_financials q "
        "JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    cached_nulls = [f"{t}_{pe}" for t, pe in nulls
                    if os.path.exists(f"{CACHE}/{t}_{pe}.html")]
    print(f"\nNULL-highlights rows total: {len(nulls)}; "
          f"with cached exhibit: {len(cached_nulls)}")
    print("cached NULL rows:", ", ".join(cached_nulls))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
