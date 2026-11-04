"""Batch 191 probe: AJG pretax-paragraph wrap-tail wart.

The batch-186 note says the pretax paragraph's wrapped lines are
table-mode residue (unterminated), so only its terminated tail is
served alongside the CEO quote. Dump the flattened body lines around
"pretax" for every cached AJG quarter plus the live extract, to see
the exact shape of the wart.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _html_to_text,
    _split_bullet_runs,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

names = sorted(f for f in os.listdir(CACHE) if f.startswith("AJG_") and f.endswith(".html"))
print(f"{len(names)} AJG exhibits")
for name in names:
    html = open(os.path.join(CACHE, name), encoding="utf-8").read()
    text = _html_to_text(html)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    lines = _split_bullet_runs(lines)
    hits = [i for i, ln in enumerate(lines) if "pretax" in ln.lower()]
    print(f"\n===== {name[:-5]}: {len(lines)} lines, pretax hits at {hits} =====")
    for idx in hits:
        start = max(0, idx - 3)
        for j in range(start, min(len(lines), idx + 8)):
            print(f"{j:4d} | {lines[j][:170]}")
        print("---")
    print("--- live extract ---")
    print(extract_press_release_highlights(html))
    print("=== end extract ===")
