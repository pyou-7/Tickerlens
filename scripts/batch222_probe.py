"""Batch 222 probe: stored press-release highlights rows that end
mid-sentence / mid-quote — the finish-rule cutoff wart carried from
batches 188/220/221 (e.g. C 2025-12-31 ends "We have excellent",
CI 2025-06-30 ends "said David M. Cordani,").

The lede finish rule pulls at most 4 overrun lines past the 6-line
budget when the budget item is unfinished (wrap tail, quote
attribution, open quote). When the quote/sentence is longer than the
cap allows, the stored highlights end mid-sentence — a visible
defect on the company page.

This probe:
  1. scans every stored highlights row and classifies its ending:
     terminated (clean), open-quote, wrap-tail/comma-ended, or other
     unterminated;
  2. for the unfinished rows that have a cached exhibit, runs the
     current extractor to confirm the cut is live (not just stale
     stored data) and measures how many more lines the sentence/quote
     needs to complete (how far past the current end the termination
     sits in the raw exhibit text).
"""
import os
import re
import sqlite3
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _is_sentence_terminated,
    _lede_quote_is_open,
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


def main() -> int:
    con = sqlite3.connect(DB)
    cur = con.cursor()
    rows = cur.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    print(f"{len(rows)} stored highlights rows")
    buckets: dict[str, list] = {}
    for ticker, pe, hl in rows:
        buckets.setdefault(classify(hl), []).append((ticker, pe, hl))
    for k in ("terminated", "open-quote", "comma-ended", "unterminated", "empty"):
        print(f"{k}: {len(buckets.get(k, []))}")
    print()
    print("== unfinished rows (open-quote / comma-ended / unterminated) ==")
    unfinished = buckets.get("open-quote", []) + buckets.get("comma-ended", []) + buckets.get("unterminated", [])
    for ticker, pe, hl in unfinished:
        last = [ln for ln in hl.splitlines() if ln.strip()][-1].strip()
        print(f"  {ticker} {pe} [{classify(hl)}] len={len(hl)} tail={last[-90:]!r}")
    print()
    print("== live check: unfinished rows with a cached exhibit ==")
    cached = {f[:-5] for f in os.listdir(CACHE) if f.endswith(".html")}
    live_cut = 0
    live_ok = 0
    no_cache = 0
    for ticker, pe, hl in unfinished:
        key = f"{ticker}_{pe}"
        if key not in cached:
            no_cache += 1
            continue
        html = open(f"{CACHE}/{key}.html", encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None:
            print(f"  {key}: live None")
            continue
        live_last = [ln for ln in live.splitlines() if ln.strip()][-1].strip()
        stored_last = [ln for ln in hl.splitlines() if ln.strip()][-1].strip()
        if classify(live) == "terminated":
            live_ok += 1
            print(f"  {key}: live TERMINATES (stored cut is stale) tail={live_last[-70:]!r}")
        else:
            live_cut += 1
            print(
                f"  {key}: live ALSO cut [{classify(live)}] stored tail={stored_last[-60:]!r} "
                f"live tail={live_last[-60:]!r} live_len={len(live)} stored_len={len(hl)}"
            )
    print(f"live also cut: {live_cut}, live terminates: {live_ok}, no cached exhibit: {no_cache}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
