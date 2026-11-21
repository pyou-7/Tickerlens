"""Batch 291 probe 2: for every stale ticker, does fresh extraction beat stored?
Also check whether companyfacts has ANY 2026-06-30/09-30 facts (AEP/D/NEE/C)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tickerlens.data.edgar import EdgarClient, companyfacts_with_predecessors
from tickerlens.data.xbrl import extract_recent_quarterly_financials
import sqlite3

con = sqlite3.connect("tickerlens.db")
rows = con.execute(
    "SELECT c.ticker, c.cik, c.sic, c.fiscal_year_end, MAX(q.period_end) "
    "FROM companies c JOIN quarterly_financials q ON q.cik=c.cik "
    "GROUP BY c.ticker ORDER BY MAX(q.period_end) LIMIT 30"
).fetchall()

client = EdgarClient()
for ticker, cik, sic, fye, stored_max in rows:
    try:
        facts = companyfacts_with_predecessors(client, cik, fresh=True)
        qs = extract_recent_quarterly_financials(facts, fiscal_year_end=fye, periods=12, sic=sic)
        fresh_max = str(max(q.end for q in qs)) if qs else None
        # any-concept freshness: latest end across all us-gaap USD facts
        us = facts.get("facts", {}).get("us-gaap", {})
        latest_any = ""
        for tag, node in us.items():
            for unit, arr in node.get("units", {}).items():
                for f in arr:
                    e = f.get("end", "")
                    if e > latest_any:
                        latest_any = e
        flag = "FRESHER" if fresh_max and fresh_max > stored_max else "same"
        print(f"{ticker:6s} stored={stored_max} fresh_extract={fresh_max} any_concept_latest={latest_any} {flag}")
    except Exception as e:
        print(f"{ticker:6s} ERROR {type(e).__name__}: {e}")
