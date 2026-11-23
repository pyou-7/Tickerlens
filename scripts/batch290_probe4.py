"""Batch 290 probe 4: live-verify the 3 EPS anti-dilution violations.

For CRWD 2025-01-31, GPC 2025-12-31, KMX 2026-02-28: pull live
companyfacts, run the EPS legs through quarterly_income_metric
(pre-clamp), and print the derived Q4 basic/diluted pair plus the
FY/9M inputs. Also dump LEN's EPS legs (diluted NULL stored).
"""
import sqlite3
import sys

sys.path.insert(0, "src")

from tickerlens.data.edgar import EdgarClient
from tickerlens.data.xbrl import Metric, quarterly_income_metric

con = sqlite3.connect("tickerlens.db")
con.row_factory = sqlite3.Row

TARGETS = {
    "CRWD": "2025-01-31",
    "GPC": "2025-12-31",
    "KMX": "2026-02-28",
    "LEN": "2025-11-30",
}

client = EdgarClient()

for ticker, end in TARGETS.items():
    row = con.execute(
        "SELECT cik, fiscal_year_end FROM companies WHERE ticker=?", (ticker,)
    ).fetchone()
    cik, fye = row["cik"], row["fiscal_year_end"]
    print(f"\n===== {ticker} cik={cik} fye={fye} target_end={end} =====")
    facts = client.companyfacts(cik)
    for metric in (Metric.EPS_BASIC, Metric.EPS_DILUTED, Metric.NET_INCOME):
        legs = quarterly_income_metric(facts, metric, fye)
        print(f"-- {metric.value} (pre-clamp quarterly legs) --")
        for m in legs:
            marker = " <== TARGET" if str(m.end) == end else ""
            print(f"   {m.end} FY{m.fy} {m.fp} = {m.value} [{m.source_tag}]{marker}")

con.close()
