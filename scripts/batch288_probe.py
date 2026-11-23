"""Batch 288 probe: survey remaining SKIP-loss groups not yet
figure-probed in detail (APD x2, FTNT x2, CSX x3, and singletons
CARR, CRM, D, DECK, DLTR, BIIB, AMT, META) to pick the batch
target. For each candidate ticker, dump stored vs live, figure
sets, and sibling shapes.

Usage: .venv/bin/python scripts/batch288_probe.py
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

TICKERS = ("APD", "FTNT", "CSX", "CARR", "CRM", "D", "DECK", "DLTR", "BIIB", "AMT", "META")


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
                  f"live-only={sorted(l_figs - s_figs)[:12]}")
            if not same:
                print("  --- STORED ---")
                for i, ln in enumerate(s_lines):
                    print(f"   S{i}: {ln[:180]}")
                print("  --- LIVE ---")
                for i, ln in enumerate(l_lines):
                    print(f"   L{i}: {ln[:180]}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
