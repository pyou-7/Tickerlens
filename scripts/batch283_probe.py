"""Batch 283 probe: for every SKIP-loss row, compute stored-only $/%
figures (figure loss on re-sync) and stored/live line counts. Rows with
zero stored-only figures are strict-superset re-sync candidates.

Usage: .venv/bin/python scripts/batch283_probe.py [TICKER ...]
DRY RUN only — no DB writes.
"""
import os
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import norm
from tickerlens.data import filings as F

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"
FIG_RE = re.compile(r"\$[\d,]+(?:\.\d+)?(?:\s*(?:billion|million|trillion))?|\d+(?:\.\d+)?%")


def main() -> int:
    want = set(sys.argv[1:])
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    # Re-derive SKIP-loss set via batch282 census gate chain is heavy;
    # instead probe all rows where stored != live under norm and report
    # figure loss — the census already told us which 50 are SKIP-loss.
    loss_tickers = {
        "ADBE", "AKAM", "AMT", "APD", "APH", "BIIB", "BLK", "CARR", "CB",
        "CLX", "CRM", "CSCO", "CSX", "D", "DASH", "DECK", "DG", "DHI",
        "DLTR", "ENPH", "EQIX", "EXPE", "FTNT", "GPC", "MCO", "META", "SPG",
    }
    by_ticker: Counter = Counter()
    for t, pe, stored in rows:
        if t not in loss_tickers:
            continue
        if want and t not in want:
            continue
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            continue
        html = open(path, encoding="utf-8").read()
        live = F.extract_press_release_highlights(html)
        if live is None or norm(stored) == norm(live):
            continue
        s_figs = set(FIG_RE.findall(stored))
        l_figs = set(FIG_RE.findall(live))
        s_only = s_figs - l_figs
        l_only = l_figs - s_figs
        sl = [x for x in stored.splitlines() if x.strip()]
        ll = [x for x in live.splitlines() if x.strip()]
        by_ticker[t] += 1
        print(f"\n{key}: stored {len(sl)} lines / live {len(ll)} lines; "
              f"stored-only figs {len(s_only)}, live-only figs {len(l_only)}")
        if s_only:
            print(f"  S-only: {sorted(s_only)[:12]}")
        print(f"  S head: {sl[0][:120] if sl else ''}")
        print(f"  L head: {ll[0][:120] if ll else ''}")
    print("\nprobed rows by ticker:", dict(by_ticker))
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
