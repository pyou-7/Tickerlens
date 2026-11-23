"""Batch 222 probe v2: precisely count stored highlights rows that end
genuinely mid-sentence (prose last line, not terminated, wrap tail /
open quote / comma), excluding bullets, table residue and headings;
then measure, for the ones with cached exhibits, how many further
raw lines the sentence/quote needs to complete.
"""
import os
import re
import sqlite3
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _BULLET_LEAD_RE,
    _LEDE_WRAP_TAIL_RE,
    _html_to_text,
    _is_sentence_terminated,
    _lede_quote_is_open,
    _split_bullet_runs,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"


def last_line(hl: str) -> str:
    lines = [ln for ln in hl.splitlines() if ln.strip()]
    return lines[-1].strip() if lines else ""


def is_tableish(s: str) -> bool:
    # Table headers / data rows / standalone footnote markers.
    if re.fullmatch(r"[¹²³⁴⁵⁶⁷⁸⁹*†‡() ]+", s):
        return True
    if re.search(r"\d{4}\s+\d{4}", s) and len(s.split()) <= 12:
        return True
    if s.lower().startswith(("metric ", "financial summary")):
        return True
    return False


def classify_last(hl: str) -> str:
    lines = [ln for ln in hl.splitlines() if ln.strip()]
    if not lines:
        return "empty"
    last = lines[-1].strip()
    if _is_sentence_terminated(last):
        return "terminated"
    if _BULLET_LEAD_RE.match(last):
        return "bullet"
    if is_tableish(last):
        return "tableish"
    if _LEDE_WRAP_TAIL_RE.search(last) or last.endswith(",") or _lede_quote_is_open(lines):
        return "mid-sentence"
    return "other-unterminated"


def completion_distance(html: str, live: str) -> int | None:
    """Lines past the live tail until a terminated, quote-closed line,
    in the raw exhibit line stream. None if the tail is not found."""
    text = _html_to_text(html)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    lines = _split_bullet_runs(lines)
    tail = last_line(live)
    # Find the live tail's last line in the stream (search from the end
    # of the first 40 lines to avoid boilerplate repeats).
    idx = None
    for j in range(min(60, len(lines))):
        if tail[:60] in lines[j] or lines[j][:60] in tail:
            idx = j
    if idx is None:
        return None
    seen: list[str] = []
    for k in range(idx + 1, min(idx + 12, len(lines))):
        seen.append(lines[k])
        if _is_sentence_terminated(lines[k]) and not _lede_quote_is_open(seen):
            return k - idx
    return None  # not completed within 11 further lines


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    buckets: dict[str, list] = {}
    for ticker, pe, hl in rows:
        buckets.setdefault(classify_last(hl), []).append((ticker, pe, hl))
    for k in ("terminated", "bullet", "tableish", "mid-sentence", "other-unterminated", "empty"):
        print(f"{k}: {len(buckets.get(k, []))}")
    print()
    mids = buckets.get("mid-sentence", [])
    print("== mid-sentence rows ==")
    for ticker, pe, hl in mids:
        print(f"  {ticker} {pe} len={len(hl)} tail={last_line(hl)[-90:]!r}")
    print()
    print("== completion distance for mid-sentence rows with cached exhibits ==")
    cached = {f[:-5] for f in os.listdir(CACHE) if f.endswith(".html")}
    dists: dict[int | str, int] = {}
    for ticker, pe, hl in mids:
        key = f"{ticker}_{pe}"
        if key not in cached:
            dists["no-cache"] = dists.get("no-cache", 0) + 1
            continue
        html = open(f"{CACHE}/{key}.html", encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None:
            dists["live-none"] = dists.get("live-none", 0) + 1
            continue
        if classify_last(live) != "mid-sentence":
            dists["live-clean"] = dists.get("live-clean", 0) + 1
            print(f"  {key}: live CLEAN (stored cut stale) tail={last_line(live)[-60:]!r}")
            continue
        d = completion_distance(html, live)
        dk = d if d is not None else ">11"
        dists[dk] = dists.get(dk, 0) + 1
        print(f"  {key}: live ALSO mid-sentence, completion in {dk} line(s) tail={last_line(live)[-70:]!r}")
    print(f"completion-distance histogram: {dists}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
