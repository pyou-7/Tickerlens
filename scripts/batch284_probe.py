"""Batch 284 probe: ENPH x2 deep-dive. For the 2 SKIP-loss ENPH rows,
dump stored vs live, figure sets, and sibling shapes.

Diagnosis: Enphase releases carry a financial figure block (revenue,
margins, EPS, cash flow) followed by a "Recent Business Highlights"
section of dated operational announcements. The 2 stored rows serve
ONLY the operational announcements (every bullet is a dated
"•On <date>, Enphase Energy announced..." line) and carry zero $/%
figures; live serves the financial figure block. Stored also carries
the seed-era no-space bullet defect ("•On" for "• On"). Live gains
15 figures (2026-06-30) and 12 figures (2026-09-30) at zero stored
figure loss. The 8 cached ENPH siblings already store the live
financial-block shape (stored == live under norm).

Usage: .venv/bin/python scripts/batch284_probe.py
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


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE c.ticker = 'ENPH' AND q.press_release_highlights IS NOT NULL "
        "ORDER BY q.period_end"
    ).fetchall()
    for pe, stored in rows:
        key = f"ENPH_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            print(f"{key}: NO CACHE")
            continue
        live = F.extract_press_release_highlights(open(path, encoding="utf-8").read())
        same = live is not None and norm(stored) == norm(live)
        s_figs = set(FIG_RE.findall(stored))
        l_figs = set(FIG_RE.findall(live or ""))
        print(f"\n{key}: stored==live(norm)={same} "
              f"stored figs={len(s_figs)} live figs={len(l_figs)} "
              f"stored-only={sorted(s_figs - l_figs)} live-only={len(l_figs - s_figs)}")
        if not same:
            print("  --- STORED ---")
            for i, ln in enumerate([x for x in stored.splitlines() if x.strip()]):
                print(f"   S{i}: {ln[:150]}")
            print("  --- LIVE ---")
            for i, ln in enumerate([x for x in (live or "").splitlines() if x.strip()]):
                print(f"   L{i}: {ln[:150]}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
