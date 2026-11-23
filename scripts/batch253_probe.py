"""Batch 253 probe: full-cache census of stored-vs-live press-release
highlights, with the full gate chain (S4/S5/S6/S7/S8/S9), plus a
detail dump for the DLR x7 black-square-bullet rows and the DHR x7 cohort.

The DLR x7 rows are the batch's target: live returns TOC junk (220
chars) for the combined release+supplement packet because the
"Highlights" section is rejected as a financial table — the section's
black-square bullets ("◾", U+25FE) are not in _BULLET_LEAD_RE, so
two $+%-carrying bullets count as data rows and, with the two $+%
narrative lines under "Financial Results", trip the data_rows >= 4
threshold in _looks_like_financial_table (the batch-154 defect class,
a new glyph). Once ◾ counts as a bullet lead, the section qualifies
and live should match the stored real bullets.

Usage: .venv/bin/python scripts/batch253_probe.py [--census FILE]
  --census FILE  write one "KEY CLASS" line per cached row (for
                 before/after diffing across the extractor fix)
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
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"


def classify(stored, live, html):
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
    detail: dict[str, tuple[list[str], list[str]]] = {}
    for t, pe, stored in rows:
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            totals["nocache"] += 1
            census_lines.append(f"{key} nocache")
            continue
        html = open(path, encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None:
            totals["live-none"] += 1
            census_lines.append(f"{key} live-none")
            continue
        if norm(stored) == norm(live):
            totals["in-sync"] += 1
            census_lines.append(f"{key} in-sync")
            continue
        cls = classify(stored, live, html)
        totals[cls] += 1
        census_lines.append(f"{key} {cls}")
        if t in ("DLR", "DHR") and cls == "loss":
            s_lines = non_empty(stored)
            l_lines = non_empty(live)
            s_norm = [norm(x) for x in s_lines]
            l_norm = [norm(x) for x in l_lines]
            l_set, s_set = set(l_norm), set(s_norm)
            lost = [x for x in s_lines if norm(x) not in l_set]
            added = [x for x in l_lines if norm(x) not in s_set]
            detail[key] = (lost, added)
    print(f"census: {dict(totals)}")
    print(f"total stored rows: {len(rows)}")
    if args.census:
        with open(args.census, "w", encoding="utf-8") as fh:
            fh.write("\n".join(census_lines) + "\n")
        print(f"wrote {args.census} ({len(census_lines)} rows)")
    for key in sorted(detail):
        lost, added = detail[key]
        print(f"\n===== {key} =====")
        for x in lost:
            print(f"  LOST  {x}")
        for x in added:
            print(f"  ADDED {x[:160]}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
