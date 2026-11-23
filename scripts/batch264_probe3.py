"""Batch 264 probe 3: measure _leading_bullet_block on the DIS_2025-09-27
lines with the CURRENT (fixed) code vs the HEAD (pre-fix) code, to pin
down exactly where the 18-line bound bit pre-fix.
"""
import subprocess
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _html_to_text,
    _leading_bullet_block,
    _split_bullet_runs,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

html = open(f"{CACHE}/DIS_2025-09-27.html", encoding="utf-8").read()
text = _html_to_text(html)
lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
lines = _split_bullet_runs(lines)
# The extractor passes body_lines (after the headline) to the block;
# the wrapped headline's tail line is not a bullet, so slice from the
# first bullet line instead.
bi = next(i for i, ln in enumerate(lines) if ln.startswith("• Revenues"))
lines = lines[bi:]
print("body lines before first bullet:", lines[0][:60])

cur = _leading_bullet_block(lines)
print("current code: block lines =", None if cur is None else len(cur))
if cur:
    for x in cur[-4:]:
        print("  tail:", repr(x))

# Pre-fix module from HEAD
src = subprocess.run(
    ["git", "show", "HEAD:src/tickerlens/data/filings.py"],
    capture_output=True, text=True, check=True,
).stdout
open("/tmp/batch264_filings_head.py", "w", encoding="utf-8").write(src)
sys.path.insert(0, "/tmp")
import batch264_filings_head as F0

old = F0._leading_bullet_block(lines)
print("HEAD code:    block lines =", None if old is None else len(old))
if old:
    for x in old[-4:]:
        print("  tail:", repr(x))
