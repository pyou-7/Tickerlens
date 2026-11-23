"""Batch 211 survey: find cached exhibits where a line matches
_CONFERENCE_CALL_NOTICE_RE with the match starting past 120 chars
(the tail-match hazard the guidance collector fixed in batch 193 with
a 120-char start guard, and batch 209 with _notice_starts_sentence).

For each such line print ticker/period, match start, and the line.
Also count matches starting <=120 (real notices the guard must keep).
"""
import os
import re
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import _CONFERENCE_CALL_NOTICE_RE, _html_to_text

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

late = []
early = []
for name in sorted(os.listdir(CACHE)):
    if not name.endswith(".html"):
        continue
    html = open(os.path.join(CACHE, name), encoding="utf-8").read()
    try:
        text = _html_to_text(html)
    except Exception as exc:  # noqa: BLE001
        print(f"{name} TEXT FAILED: {exc}")
        continue
    for ln in text.splitlines():
        m = _CONFERENCE_CALL_NOTICE_RE.search(ln)
        if not m:
            continue
        rec = (name[: -len(".html")], m.start(), ln.strip())
        if m.start() > 120:
            late.append(rec)
        else:
            early.append(rec)

print(f"early (<=120, notice-shaped): {len(early)}")
print(f"late (>120, tail-match hazard): {len(late)}")
for ticker, start, ln in late:
    print(f"\n{ticker} start={start}\n  {ln[:400]}")
