"""Batch 262 probe 4: show the before/after live-text diff for one exhibit
per changed ticker group, to verify the added lines are genuine bullets."""
import difflib
import json
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

# Recompute "before" by monkeypatching the regex back to the old form.
import re
import tickerlens.data.filings as F

OLD = re.compile(r"^(?:[•●–—◾]\s?|-\s|l\s|n\s)")
NEW = F._BULLET_LEAD_RE


def extract_with(regex, html):
    F._BULLET_LEAD_RE = regex
    try:
        return extract_press_release_highlights(html)
    finally:
        F._BULLET_LEAD_RE = NEW


SAMPLES = [
    "AMGN_2024-03-31",
    "APLD_2024-11-30",
    "BSX_2024-03-31",
    "CARR_2026-06-30",
    "CCI_2026-03-31",
    "COF_2024-03-31",
    "ET_2023-12-31",
    "GILD_2025-09-30",
]

for key in SAMPLES:
    html = open(f"{CACHE}/{key}.html", encoding="utf-8", errors="replace").read()
    before = extract_with(OLD, html) or ""
    after = extract_with(NEW, html) or ""
    print(f"########## {key} ##########")
    for line in difflib.unified_diff(
        before.split("\n"), after.split("\n"), lineterm="", n=1
    ):
        print(line)
    print()
