"""Batch 192 guidance blast: old-vs-new management-guidance extraction over
every cached exhibit. Mirrors scripts/batch175_cache_blast.py but runs
extract_management_guidance instead of extract_press_release_highlights.

Usage:
  .venv/bin/python scripts/batch192_guidance_blast.py /tmp/gblast192/new
  git stash -- src/tickerlens tests
  .venv/bin/python scripts/batch192_guidance_blast.py /tmp/gblast192/base
  git stash pop
  diff -r /tmp/gblast192/base /tmp/gblast192/new
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_management_guidance

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

out_dir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/gblast192/new"
os.makedirs(out_dir, exist_ok=True)

files = sorted(f for f in os.listdir(CACHE) if f.endswith(".html"))
print(f"{len(files)} cached exhibits")
n_guid = 0
for name in files:
    html = open(os.path.join(CACHE, name), encoding="utf-8").read()
    try:
        full = extract_management_guidance(html)
    except Exception as exc:  # noqa: BLE001
        print(f"{name} EXTRACT FAILED: {exc}")
        continue
    if full is None:
        continue
    n_guid += 1
    out_path = os.path.join(out_dir, name[: -len(".html")] + ".txt")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(full)
print(f"wrote {n_guid} guidance outputs to {out_dir}")
