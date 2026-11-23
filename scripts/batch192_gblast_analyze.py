"""Analyze the guidance blast diff: every removed line must be a footnote-def
or asterisk-note line; no line may be added."""
import os, sys, difflib
sys.path.insert(0, "src")
from tickerlens.data.filings import (
    _footnote_def_block_len, _asterisk_note_block_len, _FOOTNOTE_DEF_RE,
    _ASTERISK_NOTE_LEAD_RE,
)

base_d = "/tmp/gblast192/base"
new_d = "/tmp/gblast192/new"
diff_files = []
for name in sorted(os.listdir(base_d)):
    b = open(os.path.join(base_d, name), encoding="utf-8").read()
    n = open(os.path.join(new_d, name), encoding="utf-8").read()
    if b != n:
        diff_files.append(name)
print(f"diff files: {len(diff_files)}")
bad_removed = []
added_total = 0
removed_total = 0
for name in diff_files:
    b_lines = [l for l in open(os.path.join(base_d, name), encoding="utf-8").read().split("\n\n")]
    n_lines = [l for l in open(os.path.join(new_d, name), encoding="utf-8").read().split("\n\n")]
    sm = difflib.SequenceMatcher(a=b_lines, b=n_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("delete", "replace"):
            for ln in b_lines[i1:i2]:
                removed_total += 1
                # A removed line must open a footnote-def block or an
                # asterisk-note block (or be the wrapped continuation of
                # one — checked via the block machinery below).
                if _footnote_def_block_len([ln], 0) or _asterisk_note_block_len([ln], 0):
                    continue
                bad_removed.append((name, ln[:120]))
        if tag in ("insert", "replace"):
            for ln in n_lines[j1:j2]:
                added_total += 1
                print(f"ADDED in {name}: {ln[:120]!r}")
print(f"removed lines: {removed_total}, added lines: {added_total}")
print(f"removed lines NOT opening a footnote/asterisk block: {len(bad_removed)}")
for name, ln in bad_removed[:40]:
    print(f"  {name}: {ln!r}")
