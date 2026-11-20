"""Batch 287 probe: survey the largest remaining SKIP-loss groups
(DHI x4, GPC x4, APH x3, BLK x3) plus APD x2, FTNT x2, ADBE x2 and
the singletons (CARR, CRM, CSCO, D, DECK, DLTR, META, BIIB, AMT,
SPG) to pick the batch target. For each candidate ticker, dump
stored vs live, figure sets, and sibling shapes.

Findings (see batch287_repair.py): BLK x3 stored rows serve
expense-detail MD&A bullets while live serves the headline summary
(inflows/AUM/revenue); CSCO_2025-10-25 stored row serves the
balance-sheet section with no revenue/EPS while live serves the
earnings highlights. META_2025-09-30 held (stored table carries
EPS/net income live drops); DHI/GPC/APH held (stored = live block
plus guidance/body tails).

Usage: .venv/bin/python scripts/batch287_probe.py
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

TICKERS = ("DHI", "GPC", "APH", "BLK", "APD", "FTNT", "ADBE", "META", "CSCO")


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
