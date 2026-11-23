"""Batch 192 probe 4: which section candidate wins for APD 2026-03-31."""
import sys
sys.path.insert(0, "src")
from tickerlens.data.filings import (
    _html_to_text, _extract_highlights_section, _extract_highlights_sections,
    _leading_bullet_block, _split_bullet_runs, _HIGHLIGHTS_SECTION_ANCHOR_RE,
)

html = open("/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html/APD_2026-03-31.html", encoding="utf-8").read()
text = _html_to_text(html)
lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
lines = _split_bullet_runs(lines)
print("leading bullet block:")
for ln in (_leading_bullet_block(lines) or []):
    print(f"  {ln[:90]!r}")
print("sections:")
for s in _extract_highlights_sections(lines):
    print(f"  --- section {len(s)} lines ---")
    for ln in s:
        print(f"  {ln[:90]!r}")
print("chosen:")
for ln in (_extract_highlights_section(lines) or []):
    print(f"  {ln[:90]!r}")
print("anchor matches:")
for i, ln in enumerate(lines[:40]):
    if _HIGHLIGHTS_SECTION_ANCHOR_RE.search(ln):
        print(f"  idx {i}: {ln[:100]!r}")
