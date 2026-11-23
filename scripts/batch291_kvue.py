"""Batch 291: land KVUE's final quarter via stored CIK.

Kenvue was acquired (8-K + EFFECT 2026-11-04, 15-12G deregistration
2026-11-12) and SEC removed KVUE from company_tickers.json, so
fetch_and_persist's ticker->CIK resolution raises CompanyNotFoundError.
The Q3 FY2026 10-Q facts are in companyfacts; upsert them directly by CIK
so the (now historical) company page carries the final quarter.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tickerlens.data.edgar import EdgarClient, companyfacts_with_predecessors
from tickerlens.data.xbrl import extract_recent_quarterly_financials
from tickerlens.services.financials import _upsert_financial, get_session
import sqlite3

CIK = "0001944048"
client = EdgarClient()
subs = client.submissions(CIK, fresh=True)
facts = companyfacts_with_predecessors(client, CIK, fresh=True)
rows = extract_recent_quarterly_financials(
    facts, fiscal_year_end=subs.get("fiscalYearEnd"), periods=8, sic=subs.get("sic"))
print("extracted:", [(str(r.end), r.revenue) for r in rows])

db = get_session()
try:
    for row in rows:
        _upsert_financial(db, CIK, row)
    db.commit()
finally:
    db.close()

con = sqlite3.connect("tickerlens.db")
print("stored now:", con.execute(
    "SELECT q.period_end, q.revenue FROM quarterly_financials q WHERE q.cik=? ORDER BY q.period_end",
    (CIK,)).fetchall())
