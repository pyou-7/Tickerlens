"""Batch 263 probe 2: trace the lede loop for DIS_2025-09-27 and
EL_2025-03-31 with LEDE_DEBUG on."""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

for key in ("DIS_2025-09-27", "EL_2025-03-31"):
    print(f"===== {key} =====")
    html = open(f"{CACHE}/{key}.html", encoding="utf-8").read()
    live = extract_press_release_highlights(html)
    print(f"live lines: {len(live.splitlines()) if live else 0}")
    print()
