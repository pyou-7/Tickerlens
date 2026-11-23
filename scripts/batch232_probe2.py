"""Batch 232 probe 2: FAST flattened lines around the stray SG&A row."""
import sys

sys.path.insert(0, "src")
from tickerlens.data.filings import _html_to_text

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
html = open(f"{CACHE}/FAST_2025-03-31.html", encoding="utf-8").read()
text = _html_to_text(html)
lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
for i, ln in enumerate(lines):
    if "Selling, general" in ln or "Three-month" in ln or "Net sales $" in ln or "Business days" in ln or "Note – Daily" in ln or "WINONA" in ln:
        print(f"{i:4d}| {ln[:200]}")
print("---- context 0..40 ----")
for i, ln in enumerate(lines[:40]):
    print(f"{i:4d}| {ln[:160]}")
