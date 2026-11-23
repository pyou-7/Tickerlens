"""Batch 212 survey: two GPC guidance defects across the cached exhibits.

1. Teaser anchor: a guidance-heading candidate that occurs BEFORE the
   release dateline is a highlights-area teaser (GPC 2024-12-31: the bare
   "2025 Outlook" heading above 3 teaser bullets, dateline 4 lines later;
   the real "2025 Outlook" section is ~30 lines on). List every exhibit
   where the FIRST guidance-heading candidate precedes the first dateline.

2. Post-table bleed: current guidance extraction that contains a
   "Non-GAAP Information" heading, or that runs to the 4000-char cap.
   List ticker/period + length + the first bleed line.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _DATELINE_LEAD_RE,
    _html_to_text,
    _is_guidance_heading,
    extract_management_guidance,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

teasers = []
bleeds = []
for name in sorted(os.listdir(CACHE)):
    if not name.endswith(".html"):
        continue
    key = name[: -len(".html")]
    html = open(os.path.join(CACHE, name), encoding="utf-8").read()
    try:
        text = _html_to_text(html)
    except Exception as exc:  # noqa: BLE001
        print(f"{name} TEXT FAILED: {exc}")
        continue
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    first_heading = None
    first_dateline = None
    for i, ln in enumerate(lines):
        if first_heading is None and _is_guidance_heading(ln):
            first_heading = (i, ln)
        if first_dateline is None and _DATELINE_LEAD_RE.match(ln):
            first_dateline = (i, ln)
        if first_heading is not None and first_dateline is not None:
            break
    if (
        first_heading is not None
        and first_dateline is not None
        and first_heading[0] < first_dateline[0]
    ):
        teasers.append((key, first_heading, first_dateline))
    try:
        g = extract_management_guidance(html)
    except Exception as exc:  # noqa: BLE001
        print(f"{name} GUIDANCE FAILED: {exc}")
        continue
    if g:
        glines = g.split("\n\n")
        bleed_idx = next(
            (i for i, b in enumerate(glines) if b.strip() == "Non-GAAP Information"),
            None,
        )
        if bleed_idx is not None or len(g) >= 4000:
            bleeds.append((key, len(g), len(glines), bleed_idx))

print(f"teaser-anchor candidates (first heading before first dateline): {len(teasers)}")
for key, h, d in teasers:
    print(f"  {key}: heading@{h[0]} {h[1][:80]!r} dateline@{d[0]} {d[1][:60]!r}")

print(f"\nguidance extractions with Non-GAAP bleed or 4000-char cap: {len(bleeds)}")
for key, nchars, nblocks, bleed_idx in bleeds:
    print(f"  {key}: {nchars} chars, {nblocks} blocks, Non-GAAP heading at block {bleed_idx}")
