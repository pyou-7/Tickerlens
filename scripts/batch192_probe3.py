"""Batch 192 probe 3: which path serves APD 2026-03-31, and why the footnote defs survive."""
import sys
sys.path.insert(0, "src")
from tickerlens.data.filings import (
    _html_to_text, _extract_highlights_section, _footnote_def_block_len,
    _asterisk_note_block_len, _split_bullet_runs, _FOOTNOTE_DEF_RE,
)

html = open("/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html/APD_2026-03-31.html", encoding="utf-8").read()
text = _html_to_text(html)
lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
lines = _split_bullet_runs(lines)
print("section found:", _extract_highlights_section(lines) is not None)
for i, ln in enumerate(lines):
    if ln.startswith(("# Per", "* Certain", "-more-", "Fiscal")) or "Fiscal 2026 Second Quarter Consolidated" in ln:
        print(f"idx {i}: {ln[:80]!r}")
        print(f"   footnote_def_block_len={_footnote_def_block_len(lines, i)} asterisk_note_block_len={_asterisk_note_block_len(lines, i)}")
        print(f"   FOOTNOTE_DEF_RE match={bool(_FOOTNOTE_DEF_RE.match(ln))}")
