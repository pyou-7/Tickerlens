"""Batch 291 probe: stale tickers + APLD negative revenue.

For each stale ticker, fetch fresh companyfacts and list revenue-concept
facts with end dates in 2026, then run the extractor to see what quarters
it produces. Also dump APLD revenue facts around FY2025.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tickerlens.data.edgar import EdgarClient, companyfacts_with_predecessors
from tickerlens.data.xbrl import CONCEPTS, Metric, extract_recent_quarterly_financials

REVENUE_TAGS = CONCEPTS[Metric.REVENUE].tags
import sqlite3

con = sqlite3.connect("tickerlens.db")
cik_by_ticker = dict(con.execute("SELECT ticker, cik FROM companies").fetchall())

client = EdgarClient()

def revenue_facts_2026(cik):
    facts = companyfacts_with_predecessors(client, cik, fresh=True)
    us = facts.get("facts", {}).get("us-gaap", {})
    out = []
    for tag in REVENUE_TAGS:
        node = us.get(tag)
        if not node:
            continue
        for unit, arr in node.get("units", {}).items():
            for f in arr:
                end = f.get("end", "")
                if end >= "2026-01-01":
                    out.append((tag, unit, f.get("start"), end, f.get("val"), f.get("form"), f.get("filed"), f.get("frame")))
    return facts, sorted(out, key=lambda x: (x[3], x[0]))

for ticker in ["AEP", "C", "D", "KO", "MDLZ", "NEE"]:
    cik = cik_by_ticker[ticker]
    print(f"\n===== {ticker} CIK {cik} =====")
    facts, rows = revenue_facts_2026(cik)
    for r in rows:
        print(r)
    qs = extract_recent_quarterly_financials(facts, periods=12)
    print("extractor quarters:", [(str(q.end), q.revenue) for q in qs])

print("\n===== APLD revenue facts (FY2025 window) =====")
cik = cik_by_ticker["APLD"]
facts = companyfacts_with_predecessors(client, cik, fresh=True)
us = facts.get("facts", {}).get("us-gaap", {})
for tag in REVENUE_TAGS:
    node = us.get(tag)
    if not node:
        continue
    for unit, arr in node.get("units", {}).items():
        for f in sorted(arr, key=lambda x: x.get("end", "")):
            end = f.get("end", "")
            if "2024-06-01" <= end <= "2026-09-30":
                print(tag, unit, f.get("start"), end, f.get("val"), f.get("form"), f.get("filed"), f.get("frame"), f.get("accn"))
qs = extract_recent_quarterly_financials(facts, periods=12)
print("APLD extractor quarters:", [(str(q.end), q.revenue, q.net_income) for q in qs])
