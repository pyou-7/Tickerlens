"""Batch 291 repair: freshness re-seed.

Re-seeds (fetch_and_persist, periods=8, enrich=False) the 122 tickers whose
fresh EDGAR extraction carries quarters beyond the stored max (Q3 2026 for
117; Q2+Q3 2026 for CTSH/HCA/HUM/VMC/VRSK). Numeric columns only —
_upsert_financial never touches highlights/guidance/transcript columns.

Also recomputes the pending-filing note for the 11 tickers SEC's
companyfacts feed itself is stale for (AEP/C/D/DLR/DUK/ETR/NEE/PLD/PPL/SO/SRE)
without touching their financials.

Usage: .venv/bin/python scripts/batch291_repair.py [--pilot]
"""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tickerlens.data.edgar import EdgarClient
from tickerlens.services.financials import FinancialsService
import sqlite3

scope = json.load(open("/tmp/batch291_scope.json"))["fresh_gain"]
STALE = ['AEP', 'C', 'D', 'DLR', 'DUK', 'ETR', 'NEE', 'PLD', 'PPL', 'SO', 'SRE']
pilot = "--pilot" in sys.argv

con = sqlite3.connect("tickerlens.db")
cik_by_ticker = dict(con.execute("SELECT ticker, cik FROM companies").fetchall())

def snapshot(ticker):
    rows = con.execute(
        "SELECT q.period_end FROM quarterly_financials q JOIN companies c ON c.cik=q.cik "
        "WHERE c.ticker=? ORDER BY q.period_end", (ticker,)).fetchall()
    note = con.execute("SELECT pending_filing_note FROM companies WHERE ticker=?", (ticker,)).fetchone()[0]
    return [r[0] for r in rows], note

client = EdgarClient()
service = FinancialsService(edgar_client=client)

targets = ["CTSH", "HCA"] if pilot else sorted(scope.keys())
print(f"{'PILOT ' if pilot else ''}re-seeding {len(targets)} tickers")
results = []
for ticker in targets:
    before_ends, before_note = snapshot(ticker)
    try:
        service.fetch_and_persist(ticker, periods=8, enrich=False)
        after_ends, after_note = snapshot(ticker)
        gained = [d for d in after_ends if d not in before_ends]
        expected = scope.get(ticker, [])
        ok = all(d in after_ends for d in expected)
        results.append((ticker, gained, ok))
        print(f"  {ticker}: gained {gained} expected {expected} ok={ok} note_cleared={before_note is not None and after_note is None}")
        if not ok:
            print(f"    !! MISMATCH before_max={before_ends[-1] if before_ends else None} after_max={after_ends[-1] if after_ends else None}")
    except Exception as e:
        results.append((ticker, [], False))
        print(f"  {ticker}: ERROR {type(e).__name__}: {e}")

if not pilot:
    print("\nrecomputing pending notes for SEC-stale set (no financial writes)")
    for ticker in STALE:
        cik = cik_by_ticker[ticker]
        before_ends, before_note = snapshot(ticker)
        subs = client.submissions(cik, fresh=True)
        service._update_pending_filing_note(ticker, cik, subs)
        after_ends, after_note = snapshot(ticker)
        print(f"  {ticker}: ends unchanged={before_ends == after_ends} note={'set' if after_note else 'none'}")
        if after_note:
            print(f"    {after_note[:140]}")

bad = [r for r in results if not r[2]]
print(f"\ndone: {len(results) - len(bad)}/{len(results)} ok, {len(bad)} bad")
