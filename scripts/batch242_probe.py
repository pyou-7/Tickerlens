"""Batch 242 probe: decompose the 82 SKIP-first-diff highlights rows.

Gate S3's first gate is first_line_relation(stored, live) in
(EQ, STORED-SUFFIX, LIVE-SUFFIX) — the stored and live texts must
share a first line (or one must be a suffix of the other). The 82
rows that fail it are a mixed bag by the batch-241 notes: a
different exhibit (drifted row), or a genuinely different first
line (a heading the live extraction keeps/drops, a bullet the
stored row opens with that live reorders, ...). This probe prints,
for each first-diff row, the first 3 non-empty lines of stored and
of live, so the cohort can be classified before any gate is
extended.

Usage: .venv/bin/python scripts/batch242_probe.py [TICKER ...]
"""
import os
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import non_empty, norm
from batch241_repair import sweep_gate_s3
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"


def main() -> int:
    only = set(sys.argv[1:])
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights, q.cik "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    n = 0
    for t, pe, stored, cik in rows:
        key = f"{t}_{pe}"
        if only and t not in only:
            continue
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            continue
        html = open(path, encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None or norm(stored) == norm(live):
            continue
        if sweep_gate_s3(stored, live) != "first-diff":
            continue
        n += 1
        s_lines = non_empty(stored)
        l_lines = non_empty(live)
        print(f"=== {key}  stored {len(s_lines)} lines / live {len(l_lines)} lines")
        print("  S1:", s_lines[0][:160])
        if len(s_lines) > 1:
            print("  S2:", s_lines[1][:160])
        if len(s_lines) > 2:
            print("  S3:", s_lines[2][:160])
        print("  L1:", l_lines[0][:160])
        if len(l_lines) > 1:
            print("  L2:", l_lines[1][:160])
        if len(l_lines) > 2:
            print("  L3:", l_lines[2][:160])
    print(f"\nfirst-diff rows: {n}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
