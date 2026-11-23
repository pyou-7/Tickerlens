"""Batch 214 survey: uncapped vs 4000-char-capped press-release highlights
over every cached exhibit. Reports the uncapped length distribution and
which capped rows are genuine long sections vs table bleed.

Usage:
  .venv/bin/python scripts/batch214_survey.py
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

files = sorted(f for f in os.listdir(CACHE) if f.endswith(".html"))
print(f"{len(files)} cached exhibits")

uncapped_lens = []
diffs = []
trunc_still = []
for name in files:
    html = open(os.path.join(CACHE, name), encoding="utf-8").read()
    try:
        new = extract_press_release_highlights(html, max_chars=10**9)
        old = extract_press_release_highlights(html)
    except Exception as exc:  # noqa: BLE001
        print(f"{name} EXTRACT FAILED: {exc}")
        continue
    if new is None:
        continue
    uncapped_lens.append((len(new), name))
    if (new or "None") != (old or "None"):
        diffs.append((name, len(old or ""), len(new)))
        if new.endswith("…"):
            trunc_still.append(name)

uncapped_lens.sort(reverse=True)
print(f"non-None uncapped: {len(uncapped_lens)}")
print(f"diffs vs 4000 cap: {len(diffs)}")
print(f"diffs still truncated uncapped (should be 0): {len(trunc_still)} {trunc_still[:10]}")
import statistics
lens = [l for l, _ in uncapped_lens]
print(f"uncapped len: max={max(lens)} p99={sorted(lens)[int(len(lens)*0.99)]} p95={sorted(lens)[int(len(lens)*0.95)]} median={statistics.median(lens)}")
print("top 25 longest uncapped:")
for l, name in uncapped_lens[:25]:
    print(f"  {l:6d}  {name}")
print("over-4000 uncapped count:", sum(1 for l in lens if l > 4000))
print("over-8000 uncapped count:", sum(1 for l in lens if l > 8000))
print("over-6000 uncapped count:", sum(1 for l in lens if l > 6000))
