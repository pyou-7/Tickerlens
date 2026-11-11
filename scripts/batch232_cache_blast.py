"""Batch 232 highlights blast: old-vs-new live highlights extraction
over every cached exhibit. The changed function is highlights-only
(the fragmented-bullet-opener join), so the guidance blast must be
byte-identical and every highlights diff is the fix itself, verified
line-by-line.

Usage:
  .venv/bin/python scripts/batch232_cache_blast.py /home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast232/h_new
  git stash -- src/tickerlens tests
  .venv/bin/python scripts/batch232_cache_blast.py /home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast232/h_old
  git stash pop
  diff -r /home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast232/h_old /home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast232/h_new
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

out_dir = sys.argv[1] if len(sys.argv) > 1 else "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast232/h_new"
os.makedirs(out_dir, exist_ok=True)

files = sorted(f for f in os.listdir(CACHE) if f.endswith(".html"))
print(f"{len(files)} cached exhibits")
for name in files:
    html = open(os.path.join(CACHE, name), encoding="utf-8").read()
    try:
        full = extract_press_release_highlights(html)
    except Exception as exc:  # noqa: BLE001
        print(f"{name} EXTRACT FAILED: {exc}")
        continue
    out_path = os.path.join(out_dir, name[: -len(".html")] + ".txt")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(full or "None")
print(f"wrote {len(files)} outputs to {out_dir}")
