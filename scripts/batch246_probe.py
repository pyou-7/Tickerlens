"""Batch 246 probe: the executive-quote coverage question.

Batch 245 closed the loss-cohort decomposition with a design question:
should the highlights extraction serve the executive quote that follows
the lede? ADI x7 are the cleanest test case (live otherwise
byte-identical to stored). This probe:

1. Re-censuses the SKIP-loss cohort (expect 202).
2. Buckets loss rows by what their lost lines are: quote-only rows
   (every lost line is a quote line), quote+dateline rows, quote+other.
3. For the quote-only rows, dumps stored vs live side by side and
   locates the quote in the source doc: is it inside the lede budget,
   right after the lede, or inside a Highlights section the collector
   cut short?

Usage: .venv/bin/python scripts/batch246_probe.py > /tmp/batch246_dump.txt
"""
import os
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import non_empty, norm
from batch242_repair import sweep_gate_s4
from batch244_repair import classify_s5
from batch245_probe import lost_lines, shape
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"

_QUOTE_RE = re.compile(r'[“"]([^”"]{20,})[”"]')
_QUOTE_VERB_RE = re.compile(
    r"\b(said|added|commented|noted|stated|remarked|observed|continued)\b",
    re.IGNORECASE,
)


def is_quote_line(ln: str) -> bool:
    """Strict executive-quote test (batch 246).

    A line is a quote line when it opens with a quote mark and closes
    one, or when it carries a quote-verb attribution (``said X, CEO`` /
    ``CFO X added, "..."``) alongside a quote mark. The loose test
    (any quoted span >= 20 chars) misfires on Ford's non-GAAP
    footnote (``"adjusted"`` inside a boilerplate bullet) and on
    APLD's non-GAAP definition sentence, which carry quoted terms
    but no quote.
    """
    s = ln.strip()
    if not re.search(r'[“”"]', s):
        return False
    if s.startswith(("“", '"')):
        return bool(re.search(r'[”"]', s[1:]))
    return bool(_QUOTE_VERB_RE.search(s))


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    totals: Counter[str] = Counter()
    quote_only: list[str] = []
    quote_plus: list[tuple[str, list[str]]] = []
    quote_rows: list[str] = []
    for t, pe, stored in rows:
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            continue
        html = open(path, encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None:
            totals["live-none"] += 1
            continue
        if norm(stored) == norm(live):
            totals["in-sync"] += 1
            continue
        r4 = sweep_gate_s4(stored, live)
        if r4 is None:
            totals["S4-repairable"] += 1
            continue
        cls5 = classify_s5(stored, live)
        if cls5:
            totals[f"S5-{cls5}"] += 1
            continue
        totals[f"SKIP-{r4}"] += 1
        if r4 != "loss":
            continue
        lost = lost_lines(stored, live)
        qlost = [x for x in lost if is_quote_line(x)]
        if not qlost:
            continue
        quote_rows.append(key)
        if len(qlost) == len(lost):
            quote_only.append(key)
        else:
            quote_plus.append((key, [shape(x) for x in lost if not is_quote_line(x)]))
    print("CENSUS (current extractor + gates S4/S5):")
    for k, n in sorted(totals.items()):
        print(f"  {k}: {n}")
    print(f"\nLOSS ROWS WITH >=1 QUOTE LINE: {len(quote_rows)}")
    print(f"QUOTE-ONLY ROWS: {len(quote_only)}")
    for k in quote_only:
        print(f"  {k}")
    print(f"\nQUOTE+OTHER ROWS: {len(quote_plus)}")
    other_shapes: Counter[str] = Counter()
    for k, shapes in quote_plus:
        for s in shapes:
            other_shapes[s] += 1
        print(f"  {k}: non-quote lost shapes {Counter(shapes)}")
    print(f"\nNON-QUOTE LOST SHAPES IN QUOTE+OTHER: {dict(other_shapes)}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
