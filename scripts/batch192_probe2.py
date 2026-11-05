"""Batch 192 probe 2: live extraction from cached exhibits for BBY/APD/CSX."""
import os, sys
sys.path.insert(0, "src")
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
for name in sorted(os.listdir(CACHE)):
    if not (name.startswith(("BBY_", "APD_", "CSX_")) and name.endswith(".html")):
        continue
    html = open(os.path.join(CACHE, name), encoding="utf-8").read()
    out = extract_press_release_highlights(html)
    print(f"===== {name} len={len(out or '')} =====")
    for i, line in enumerate((out or "None").splitlines()):
        print(f"  {i:02d}: {line!r}")
