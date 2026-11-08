"""Batch 212 classify: for every guidance-heading candidate in every cached
exhibit, print the distance to the next dateline line after it, and whether
the candidate is the current extraction's anchor (first heading). This
picks the teaser-skip window: false anchors (teaser/headline/bullet
fragments) sit a few lines above the dateline; true anchors sit far from
any following dateline (or the dateline is a false table-row match).
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _DATELINE_LEAD_RE,
    _html_to_text,
    _is_guidance_heading,
    _is_toc_entry,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

rows = []
for name in sorted(os.listdir(CACHE)):
    if not name.endswith(".html"):
        continue
    key = name[: -len(".html")]
    html = open(os.path.join(CACHE, name), encoding="utf-8").read()
    try:
        text = _html_to_text(html)
    except Exception:
        continue
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    datelines = [i for i, ln in enumerate(lines) if _DATELINE_LEAD_RE.match(ln)]
    if not datelines:
        continue
    first = True
    for i, ln in enumerate(lines):
        if not _is_guidance_heading(ln):
            continue
        nxt = next((d for d in datelines if d > i), None)
        if nxt is None:
            continue
        dist = nxt - i
        toc = _is_toc_entry(lines, i)
        rows.append((dist, key, i, ln, first, toc))
        first = False

rows.sort()
print(f"{len(rows)} heading candidates with a dateline after them")
print("\n--- distance <= 40 (teaser window candidates) ---")
for dist, key, i, ln, is_first, toc in rows:
    if dist <= 40:
        print(f"  d={dist:3d} {'FIRST' if is_first else '     '} {'TOC' if toc else '   '} {key}@{i} {ln[:90]!r}")
print("\n--- distance 41..100 (margin check) ---")
for dist, key, i, ln, is_first, toc in rows:
    if 41 <= dist <= 100:
        print(f"  d={dist:3d} {'FIRST' if is_first else '     '} {'TOC' if toc else '   '} {key}@{i} {ln[:90]!r}")
