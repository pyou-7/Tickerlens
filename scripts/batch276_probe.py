"""Batch 276 probe: CEG stored vs live highlights for the 5 SKIP-loss rows."""
import sqlite3
import sys

sys.path.insert(0, "src")
from tickerlens.data import filings as F

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"

con = sqlite3.connect(DB)
rows = con.execute(
    "SELECT q.period_end, q.press_release_highlights "
    "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
    "WHERE c.ticker='CEG' AND q.press_release_highlights IS NOT NULL "
    "ORDER BY q.period_end"
).fetchall()

for period_end, stored in rows:
    key = f"CEG_{period_end}"
    html = open(f"{CACHE}/{key}.html", encoding="utf-8").read()
    live = F.extract_press_release_highlights(html)
    print("=" * 100)
    print(key, "stored_len", len(stored or ""), "live_len", len(live or ""))
    print("--- STORED ---")
    print(stored or "")
    print("--- LIVE ---")
    print(live or "")
