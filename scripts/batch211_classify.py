"""Batch 211 classifier probe: for every late (>120) _CONFERENCE_CALL_NOTICE_RE
match in the cached exhibits, print the containing sentence plus the two
candidate discriminator verdicts:
  sent_guard = match starts within 120 chars of its sentence start
  verb_arm   = containing sentence carries a scheduling verb before/around
               "conference call" (will host/hosting/hold/conduct/discuss)
"""
import os
import re
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _CONFERENCE_CALL_NOTICE_RE,
    _html_to_text,
    _notice_sentence_start,
    _notice_starts_sentence,
)

VERB_RE = re.compile(
    r"will (?:be )?(?:host|hosting|hold|conduct|discuss)\b[^.]*?conference call\b",
    re.IGNORECASE,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

seen_sent = set()
for name in sorted(os.listdir(CACHE)):
    if not name.endswith(".html"):
        continue
    html = open(os.path.join(CACHE, name), encoding="utf-8").read()
    try:
        text = _html_to_text(html)
    except Exception:  # noqa: BLE001
        continue
    for ln in text.splitlines():
        m = _CONFERENCE_CALL_NOTICE_RE.search(ln)
        if not m or m.start() <= 120:
            continue
        s0 = _notice_sentence_start(ln, m)
        # sentence end: first ". " after the match end, else line end
        idx = ln.find(". ", m.end())
        s1 = idx + 1 if idx >= 0 else len(ln)
        sent = ln[s0:s1].strip()
        key = sent[:120]
        guard = _notice_starts_sentence(ln, m)
        verb = VERB_RE.search(sent) is not None
        print(
            f"{name[:-5]} guard={int(guard)} verb={int(verb)} :: {sent[:220]}"
        )
