"""Batch 291 probe 3: AEP/C/D deep check — submissions vs companyfacts, cache mtimes."""
import os, sys, logging
logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tickerlens.data.edgar import EdgarClient, SEC_COMPANYFACTS_URL, SEC_SUBMISSIONS_URL, normalize_cik
import sqlite3, hashlib
from pathlib import Path

con = sqlite3.connect("tickerlens.db")
cik_by_ticker = dict(con.execute("SELECT ticker, cik FROM companies").fetchall())
client = EdgarClient()
print("cache_dir:", client.cache_dir)

for ticker in ["AEP", "C", "D", "KO"]:
    cik = cik_by_ticker[ticker]
    print(f"\n===== {ticker} CIK {cik} =====")
    for label, url in [("companyfacts", SEC_COMPANYFACTS_URL.format(cik=normalize_cik(cik))),
                       ("submissions", SEC_SUBMISSIONS_URL.format(cik=normalize_cik(cik)))]:
        key = hashlib.sha256(url.encode()).hexdigest()[:16]
        f = Path(client.cache_dir) / f"{key}.json"
        print(f"  {label} cache exists={f.exists()}", end="")
        if f.exists():
            import datetime as dt
            print(f" mtime={dt.datetime.fromtimestamp(f.stat().st_mtime)} size={f.stat().st_size}", end="")
        print()
    subs = client.submissions(cik, fresh=True)
    recent = subs.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accns = recent.get("accessionNumber", [])
    print("  recent 10-Q/10-K filings:")
    shown = 0
    for form, date, accn in zip(forms, dates, accns):
        if form in ("10-Q", "10-K") and shown < 8:
            print(f"    {form} filed {date} accn {accn}")
            shown += 1
    facts = client.companyfacts(cik, fresh=True)
    print("  companyfacts entityName:", facts.get("entityName"))
    us = facts.get("facts", {}).get("us-gaap", {})
    for tag in ["Revenues", "NetIncomeLoss", "Assets"]:
        node = us.get(tag)
        if not node:
            print(f"    {tag}: absent")
            continue
        ends = sorted({f.get("end", "") for arr in node.get("units", {}).values() for f in arr})
        print(f"    {tag}: max end {ends[-1] if ends else None}, n_ends={len(ends)}")
