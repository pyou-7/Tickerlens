"""Batch 276 probe 2: where do CEG stored vs live lines come from in the
exhibit? Dump the exhibit's plain-text lines with indices, plus a figure
diff (stored-only vs live-only $/% figures) per SKIP-loss row."""
import re
import sqlite3
import sys

sys.path.insert(0, "src")
from tickerlens.data import filings as F

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"

FIG_RE = re.compile(r"\$[\d,]+(?:\.\d+)?(?:\s*(?:billion|million|trillion))?|\d+(?:\.\d+)?%")

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
    s_figs = set(FIG_RE.findall(stored or ""))
    l_figs = set(FIG_RE.findall(live or ""))
    print("=" * 100)
    print(key, "stored_len", len(stored or ""), "live_len", len(live or ""))
    print("  stored-only figures:", sorted(s_figs - l_figs)[:25])
    print("  live-only figures:", sorted(l_figs - s_figs)[:25])
    print("  stored tail:", repr((stored or "")[-120:]))
    print("  live tail:", repr((live or "")[-120:]))
    print("  stored has reconciliation residue:",
          "GAAP/Adjusted (non-GAAP) Operating Earnings Reconciliation" in (stored or ""))
    print("  stored bullet count:", (stored or "").count("\u2022"),
          " live bullet count:", (live or "").count("\u2022"))
