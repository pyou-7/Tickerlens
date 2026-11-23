"""Batch 285 probe: survey the remaining zero-figure-loss candidates
plus CSX x3 (which needs its own probe) to pick the batch target.
For each candidate ticker, dump stored vs live, figure sets, and
sibling shapes.

Candidates from batch 284 notes: CB x1 (+8 live figures), CLX x2
(+1 each), DG x1 (headline defect, equal figures), EXPE x1 (equal
figures), MCO x1 (+11), SPG 2025-09-30 (equal); CSX x3 unknown.

Usage: .venv/bin/python scripts/batch285_probe.py
DRY RUN only — no DB writes.
"""
import os
import re
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import norm
from tickerlens.data import filings as F

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"
FIG_RE = re.compile(r"\$[\d,]+(?:\.\d+)?(?:\s*(?:billion|million|trillion))?|\d+(?:\.\d+)?%")

TICKERS = ("MCO", "CB", "CSX", "CLX", "SPG", "DG", "EXPE")


def main() -> int:
    con = sqlite3.connect(DB)
    for ticker in TICKERS:
        rows = con.execute(
            "SELECT q.period_end, q.press_release_highlights "
            "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = ? AND q.press_release_highlights IS NOT NULL "
            "ORDER BY q.period_end",
            (ticker,),
        ).fetchall()
        print(f"\n{'=' * 70}\n{ticker}: {len(rows)} stored rows")
        for pe, stored in rows:
            key = f"{ticker}_{pe}"
            path = f"{CACHE}/{key}.html"
            if not os.path.exists(path):
                print(f"{key}: NO CACHE")
                continue
            live = F.extract_press_release_highlights(
                open(path, encoding="utf-8").read()
            )
            same = live is not None and norm(stored) == norm(live)
            s_figs = set(FIG_RE.findall(stored))
            l_figs = set(FIG_RE.findall(live or ""))
            s_lines = [x for x in stored.splitlines() if x.strip()]
            l_lines = [x for x in (live or "").splitlines() if x.strip()]
            print(f"\n{key}: stored==live(norm)={same} "
                  f"s_lines={len(s_lines)} l_lines={len(l_lines)} "
                  f"s_chars={len(stored)} l_chars={len(live or '')} "
                  f"stored figs={len(s_figs)} live figs={len(l_figs)} "
                  f"stored-only={sorted(s_figs - l_figs)} "
                  f"live-only={len(l_figs - s_figs)}")
            if not same:
                print("  --- STORED ---")
                for i, ln in enumerate(s_lines):
                    print(f"   S{i}: {ln[:160]}")
                print("  --- LIVE ---")
                for i, ln in enumerate(l_lines):
                    print(f"   L{i}: {ln[:160]}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
