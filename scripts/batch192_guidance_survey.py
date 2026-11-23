"""Batch 192 guidance survey: which cached exhibits' guidance text carries
#-led or '* Certain'-led footnote lines, and what follows them."""
import os, sys
sys.path.insert(0, "src")
from tickerlens.data.filings import extract_management_guidance, _FOOTNOTE_DEF_RE, _ASTERISK_NOTE_LEAD_RE

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
n_guid = 0
hits = []
for name in sorted(os.listdir(CACHE)):
    if not name.endswith(".html"):
        continue
    html = open(os.path.join(CACHE, name), encoding="utf-8").read()
    out = extract_management_guidance(html)
    if not out:
        continue
    n_guid += 1
    lines = [l for l in out.split("\n\n") if l.strip()]
    for i, ln in enumerate(lines):
        if _FOOTNOTE_DEF_RE.match(ln) or _ASTERISK_NOTE_LEAD_RE.match(ln):
            hits.append((name, i, len(lines), ln[:90]))
print(f"exhibits with guidance: {n_guid}")
print(f"guidance texts carrying a batch-192 footnote line: {len(hits)}")
for h in hits:
    print(h)
