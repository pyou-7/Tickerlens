"""Batch 238 blast: old-vs-new extract_management_guidance over all 1,699
cached exhibits. Dumps {file: guidance-or-None} to
hidden_files/blast238_guidance_<tag>.json. Run once per code version:

  .venv/bin/python scripts/batch238_guidance_blast.py old   # pre-fix code
  .venv/bin/python scripts/batch238_guidance_blast.py new   # post-fix code
"""
import json
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_management_guidance

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
OUT = "hidden_files"

tag = sys.argv[1] if len(sys.argv) > 1 else "new"
out = {}
errors = []
for f in sorted(os.listdir(CACHE)):
    if not f.endswith(".html"):
        continue
    html = open(os.path.join(CACHE, f), encoding="utf-8", errors="replace").read()
    try:
        out[f] = extract_management_guidance(html)
    except Exception as e:  # noqa: BLE001 - blast must not die on one exhibit
        errors.append((f, repr(e)))
        out[f] = None
with open(f"{OUT}/blast238_guidance_{tag}.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh)
print(f"{tag}: {len(out)} exhibits, {sum(1 for v in out.values() if v)} non-None, errors={errors}")
