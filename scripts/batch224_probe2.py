"""Batch 224 probe v2: classify the 91 live-cut hole rows by what the
next raw line looks like — the signal a next-line lookahead would see.

Classes:
  lowercase-continuation: next line starts with a lowercase letter —
      a wrapped sentence; the lookahead fix pulls it in.
  heading-tail: the live tail itself is a bare heading / table heading
      (AEP "Preliminary, unaudited results", ACN "Revenues by Type of
      Work") — the fix is dropping a trailing dangling heading.
  complete-item: next line is a new bullet / heading / capital-led new
      item — the tail is a complete bullet without terminal punctuation;
      NOT a defect, leave alone.
  other: capital-led prose continuation or anything else — needs a
      closer look per row.
"""
import os
import re
import sqlite3
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _BULLET_LEAD_RE,
    _html_to_text,
    _is_bare_highlights_heading,
    _is_lede_table_line,
    _is_sentence_terminated,
    _lede_item_still_unfinished,
    _lede_quote_is_open,
    _split_bullet_runs,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"


def classify(hl: str) -> str:
    lines = [ln for ln in hl.splitlines() if ln.strip()]
    if not lines:
        return "empty"
    if _lede_quote_is_open(lines):
        return "open-quote"
    last = lines[-1].strip()
    if _is_sentence_terminated(last):
        return "terminated"
    if last.endswith(","):
        return "comma-ended"
    return "unterminated"


def tail_line(hl: str) -> str:
    return [ln for ln in hl.splitlines() if ln.strip()][-1].strip()


def is_prose_tail(hl: str) -> bool:
    """Candidate tail: not a bullet, not a table line. Bare headings ARE
    included — a trailing heading is the heading-tail class, classified
    in the loop below."""
    last = tail_line(hl)
    if _BULLET_LEAD_RE.match(last):
        return False
    if _is_lede_table_line(last):
        return False
    return True


def find_raw_idx(raw, tail):
    for i, ln in enumerate(raw):
        if ln.strip() == tail:
            return i
    for i, ln in enumerate(raw):
        if tail[-40:] in ln:
            return i
    return None


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    cached = {f[:-5] for f in os.listdir(CACHE) if f.endswith(".html")}
    buckets: dict[str, list] = {}
    for t, pe, hl in rows:
        if classify(hl) != "unterminated":
            continue
        if not is_prose_tail(hl):
            continue
        if _lede_item_still_unfinished([ln for ln in hl.splitlines() if ln.strip()]):
            continue
        key = f"{t}_{pe}"
        if key not in cached:
            buckets.setdefault("no-cache", []).append((key, tail_line(hl)))
            continue
        html = open(f"{CACHE}/{key}.html", encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None or classify(live) == "terminated":
            continue
        tail = tail_line(live)
        # heading-tail class: the live tail itself is a bare heading
        if _is_bare_highlights_heading(tail):
            buckets.setdefault("heading-tail", []).append((key, tail))
            continue
        text = _html_to_text(html)
        raw = _split_bullet_runs([ln.strip() for ln in text.split("\n") if ln.strip()])
        idx = find_raw_idx(raw, tail)
        if idx is None or idx + 1 >= len(raw):
            buckets.setdefault("no-trace", []).append((key, tail))
            continue
        nxt = raw[idx + 1].strip()
        if nxt and nxt[0].islower():
            buckets.setdefault("lowercase-continuation", []).append((key, tail, nxt))
        elif _BULLET_LEAD_RE.match(nxt) or _is_bare_highlights_heading(nxt) or _is_lede_table_line(nxt):
            buckets.setdefault("complete-item", []).append((key, tail, nxt))
        elif nxt and nxt[0].isupper():
            buckets.setdefault("capital-continuation?", []).append((key, tail, nxt))
        else:
            buckets.setdefault("other", []).append((key, tail, nxt))
    for k in ("lowercase-continuation", "heading-tail", "complete-item",
              "capital-continuation?", "other", "no-trace", "no-cache"):
        items = buckets.get(k, [])
        print(f"{k}: {len(items)}")
        for it in items[:40]:
            if k == "lowercase-continuation":
                print(f"    {it[0]} tail={it[1][-60:]!r} next={it[2][:60]!r}")
            elif k in ("complete-item", "capital-continuation?", "other"):
                print(f"    {it[0]} tail={it[1][-60:]!r} next={it[2][:60]!r}")
            else:
                print(f"    {it[0]} tail={it[1][-70:]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
