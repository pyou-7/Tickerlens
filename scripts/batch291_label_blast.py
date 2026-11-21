"""Batch 291 label blast: dump (ticker -> [(end, fy, fp)]) for all 303
tickers at periods=8 from cached companyfacts. Run before/after the
_dedupe_period_labels change and diff the JSONs."""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tickerlens.data.edgar import EdgarClient, companyfacts_with_predecessors
from tickerlens.data.xbrl import extract_recent_quarterly_financials
import sqlite3

out_path = sys.argv[1]
con = sqlite3.connect("tickerlens.db")
companies = con.execute("SELECT ticker, cik FROM companies ORDER BY ticker").fetchall()
client = EdgarClient()
result = {}
for ticker, cik in companies:
    try:
        subs = client.submissions(cik)
        facts = companyfacts_with_predecessors(client, cik)
        rows = extract_recent_quarterly_financials(
            facts, fiscal_year_end=subs.get("fiscalYearEnd"), periods=8, sic=subs.get("sic"))
        result[ticker] = [(str(r.end), r.fy, r.fp) for r in rows]
    except Exception as e:
        result[ticker] = f"ERROR {type(e).__name__}: {e}"
json.dump(result, open(out_path, "w"), indent=1)
print(f"wrote {out_path} ({len(result)} tickers)")
