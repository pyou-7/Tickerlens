"""Batch 262 probe 3: full stored vs live text for DIS 2024-12-28, plus a
cache-wide survey of ◦-led lines (how many exhibits carry them, and
whether the current extractor serves them)."""
import glob
import os
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

con = sqlite3.connect("tickerlens.db")
stored = con.execute(
    "SELECT q.press_release_highlights FROM quarterly_financials q "
    "JOIN companies c ON c.cik = q.cik "
    "WHERE c.ticker='DIS' AND q.period_end='2024-12-28'"
).fetchone()[0]
html = open(f"{CACHE}/DIS_2024-12-28.html", encoding="utf-8").read()
live = extract_press_release_highlights(html)
print("=== STORED (DIS 2024-12-28) ===")
print(stored)
print("=== LIVE (DIS 2024-12-28) ===")
print(live)

print()
print("=== cache survey: exhibits whose live highlights contain a ◦-led line ===")
served = []
for f in sorted(glob.glob(os.path.join(CACHE, "*.html"))):
    key = os.path.basename(f)[:-5]
    h = open(f, encoding="utf-8", errors="replace").read()
    try:
        hl = extract_press_release_highlights(h)
    except Exception:
        continue
    if hl and any(ln.startswith("◦") for ln in hl.split("\n")):
        served.append(key)
print(f"live-served ◦ lines in {len(served)} exhibits: {served}")
