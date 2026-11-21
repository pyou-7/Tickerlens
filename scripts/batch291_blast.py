"""Batch 291 blast (dry-run): fresh extraction vs stored for all 303 tickers.

Reports per ticker: new quarters gained, changed values on existing quarters
(with magnitude), and alarming patterns (value -> None, sign flips on revenue,
identity breaks in fresh rows, EPS anti-dilution violations in fresh rows).
No writes.
"""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tickerlens.data.edgar import EdgarClient, companyfacts_with_predecessors
from tickerlens.data.xbrl import extract_recent_quarterly_financials
from tickerlens.models.quarterly_financial import identity_tolerance
import sqlite3

con = sqlite3.connect("tickerlens.db")
companies = con.execute("SELECT ticker, cik FROM companies ORDER BY ticker").fetchall()
stored = {}
for cik, pe, rev, ni, eb, ed, fcf, ta, tl, te, cash, rnci, temp, ffo in con.execute(
    "SELECT cik, period_end, revenue, net_income, eps_basic, eps_diluted, free_cash_flow,"
    " total_assets, total_liabilities, total_equity, cash_and_equivalents, redeemable_nci,"
    " temporary_equity, ffo FROM quarterly_financials"
):
    stored[(cik, pe)] = dict(revenue=rev, net_income=ni, eps_basic=eb, eps_diluted=ed,
                             free_cash_flow=fcf, total_assets=ta, total_liabilities=tl,
                             total_equity=te, cash_and_equivalents=cash, redeemable_nci=rnci,
                             temporary_equity=temp, ffo=ffo)

client = EdgarClient()
summary = {"tickers": 0, "errors": [], "gaining": [], "changed_only": [], "unchanged": 0,
           "new_quarters_total": 0, "changed_cells": 0, "alarms": []}

def close(a, b):
    if a is None or b is None:
        return a is b
    return abs(a - b) <= max(1.0, abs(b) * 1e-9)

for ticker, cik in companies:
    summary["tickers"] += 1
    try:
        subs = client.submissions(cik, fresh=True)
        facts = companyfacts_with_predecessors(client, cik, fresh=True)
        rows = extract_recent_quarterly_financials(
            facts, fiscal_year_end=subs.get("fiscalYearEnd"), periods=12, sic=subs.get("sic"))
    except Exception as e:
        summary["errors"].append((ticker, f"{type(e).__name__}: {e}"))
        continue
    new_q = []
    changed = []
    for r in rows:
        key = (cik, r.end.isoformat())
        fresh = dict(revenue=r.revenue, net_income=r.net_income, eps_basic=r.eps_basic,
                     eps_diluted=r.eps_diluted, free_cash_flow=r.free_cash_flow,
                     total_assets=r.total_assets, total_liabilities=r.total_liabilities,
                     total_equity=r.total_equity, cash_and_equivalents=r.cash_and_equivalents,
                     redeemable_nci=r.redeemable_nci, temporary_equity=r.temporary_equity, ffo=r.ffo)
        # identity check on fresh row
        if None not in (r.total_assets, r.total_liabilities, r.total_equity):
            lhs = r.total_assets
            rhs = r.total_liabilities + (r.redeemable_nci or 0) + (r.temporary_equity or 0) + r.total_equity
            if abs(lhs - rhs) > identity_tolerance(lhs):
                summary["alarms"].append((ticker, r.end.isoformat(), "identity break in fresh row", lhs, rhs))
        # EPS anti-dilution
        if r.eps_basic is not None and r.eps_diluted is not None:
            if r.eps_diluted > r.eps_basic or (r.eps_basic < 0 and r.eps_diluted < r.eps_basic):
                summary["alarms"].append((ticker, r.end.isoformat(), "EPS violation in fresh row", r.eps_basic, r.eps_diluted))
        if key not in stored:
            new_q.append(r.end.isoformat())
        else:
            for col, fv in fresh.items():
                sv = stored[key][col]
                if not close(fv, sv):
                    changed.append((r.end.isoformat(), col, sv, fv))
                    summary["changed_cells"] += 1
                    if sv is not None and fv is None:
                        summary["alarms"].append((ticker, r.end.isoformat(), f"{col} -> None", sv, fv))
                    if col == "revenue" and sv is not None and fv is not None and (sv < 0) != (fv < 0):
                        summary["alarms"].append((ticker, r.end.isoformat(), "revenue sign flip", sv, fv))
    if new_q:
        summary["gaining"].append((ticker, new_q, len(changed)))
        summary["new_quarters_total"] += len(new_q)
    elif changed:
        summary["changed_only"].append((ticker, len(changed), changed[:5]))
    else:
        summary["unchanged"] += 1

print(f"tickers={summary['tickers']} errors={len(summary['errors'])} unchanged={summary['unchanged']}")
print(f"gaining new quarters: {len(summary['gaining'])} tickers, {summary['new_quarters_total']} quarters")
print(f"changed-only tickers: {len(summary['changed_only'])}, changed cells total: {summary['changed_cells']}")
print(f"alarms: {len(summary['alarms'])}")
for a in summary["alarms"][:40]:
    print("  ALARM", a)
for e in summary["errors"]:
    print("  ERROR", e)
print("\n--- gaining ---")
for t, nq, nc in summary["gaining"]:
    print(f"  {t}: +{len(nq)} {nq} (changed cells on existing: {nc})")
print("\n--- changed-only ---")
for t, nc, sample in summary["changed_only"]:
    print(f"  {t}: {nc} cells, e.g. {sample}")
with open("/tmp/batch291_blast.json", "w") as f:
    json.dump(summary, f, indent=1, default=str)
print("\nwrote /tmp/batch291_blast.json")
