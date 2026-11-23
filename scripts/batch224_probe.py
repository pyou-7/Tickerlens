"""Batch 224 probe v2: the noun/number-ending hole, narrowed to live cuts.

v1's classifier was too broad (288 rows — mostly table headings,
footnote lines and metric fragments). The hole is the narrow class
batch 222 named: a PROSE highlights row whose last line ends in a
noun or figure, carries no unfinished signal (no wrap tail / comma /
open quote), and is STILL cut live — i.e. the sentence continues in
the raw exhibit but neither the finish rule nor the trim can see it.

This probe:
  1. reuses the batch-222 ending classification over all 2,492 stored
     rows, then keeps only "unterminated" rows whose tail is prose
     (not bullet / table line / bare heading) and not unfinished by
     _lede_item_still_unfinished;
  2. for each with a cached exhibit, checks whether live extraction
     is also unterminated (a live cut, not a stale stored row);
  3. traces the live-cut rows in the raw exhibit: prints the stored
     tail's raw line plus the next 10 lines, marking the first
     sentence-terminated line — what a next-line lookahead must see.
"""
import os
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
KNOWN = {("HAL", "2025-12-31"), ("DAL", "2024-09-30"),
         ("DG", "2025-01-31"), ("AEP", "2024-09-30")}


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
    last = tail_line(hl)
    if _BULLET_LEAD_RE.match(last):
        return False
    if _is_lede_table_line(last) or _is_bare_highlights_heading(last):
        return False
    return True


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    print(f"{len(rows)} stored highlights rows")
    unterminated = [(t, pe, hl) for t, pe, hl in rows if classify(hl) == "unterminated"]
    print(f"unterminated: {len(unterminated)}")
    hole = [(t, pe, hl) for t, pe, hl in unterminated
            if is_prose_tail(hl) and not _lede_item_still_unfinished(
                [ln for ln in hl.splitlines() if ln.strip()])]
    print(f"hole-class (prose tail, no unfinished signal): {len(hole)}")
    cached = {f[:-5] for f in os.listdir(CACHE) if f.endswith(".html")}
    live_cut = []
    for t, pe, hl in hole:
        key = f"{t}_{pe}"
        mark = "KNOWN" if (t, pe) in KNOWN else "     "
        if key not in cached:
            print(f"  {mark} {t} {pe} no-cache tail={tail_line(hl)[-70:]!r}")
            continue
        html = open(f"{CACHE}/{key}.html", encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None:
            print(f"  {mark} {t} {pe} live-None tail={tail_line(hl)[-70:]!r}")
            continue
        if classify(live) == "terminated":
            print(f"  {mark} {t} {pe} live-TERMINATES (stale stored)")
            continue
        live_cut.append((t, pe, hl, live))
        print(f"  {mark} {t} {pe} LIVE-CUT stored={tail_line(hl)[-70:]!r} "
              f"live={tail_line(live)[-70:]!r}")
    print(f"\nlive-cut hole rows: {len(live_cut)}")
    print("\n== trace: raw lines after the live tail ==")
    for t, pe, hl, live in live_cut:
        key = f"{t}_{pe}"
        html = open(f"{CACHE}/{key}.html", encoding="utf-8").read()
        text = _html_to_text(html)
        raw = _split_bullet_runs([ln.strip() for ln in text.split("\n") if ln.strip()])
        tail = tail_line(live)
        idx = None
        for i, ln in enumerate(raw):
            if ln.strip() == tail:
                idx = i
        if idx is None:
            for i, ln in enumerate(raw):
                if tail[-40:] in ln:
                    idx = i
        if idx is None:
            print(f"  --- {key}: tail not found in raw lines ---")
            continue
        print(f"  --- {key} (live tail at raw line {idx}) ---")
        for j in range(idx, min(idx + 11, len(raw))):
            marker = "TAIL>" if j == idx else "     "
            term = " [TERMINATES]" if _is_sentence_terminated(raw[j]) else ""
            print(f"    {marker} [{j}] {raw[j][:120]!r}{term}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
