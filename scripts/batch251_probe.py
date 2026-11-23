"""Batch 251 probe: re-census the 169 SKIP-loss rows left after batch 250
and dump stored-vs-live for the next named candidates: F x6 (flattened
page-image mega-lines + truncated seed lines), CINF x6 (lede bullets
vs section bullets), AXON x6 (shareholder-letter prose), BKR 2024-12-31
(quote after the FY-bullets section), BIIB 2026-06-30 (product vs
financial bullets), AMZN x8 (business bullets). The question: which
loss cohort is a single provable extractor change or gate away?

Usage: .venv/bin/python scripts/batch251_probe.py > /tmp/batch251_dump.txt
"""
import os
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import non_empty, norm
from batch242_repair import sweep_gate_s4
from batch244_repair import classify_s5
from batch245_probe import lost_lines
from batch245_probe2 import bucket
from batch247_repair import sweep_gate_s6
from batch248_repair import sweep_gate_s7
from batch250_repair import sweep_gate_s8
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"

DUMP_TICKERS = ("F", "CINF", "AXON", "BKR", "BIIB", "AMZN")


def classify(stored, live, html):
    if sweep_gate_s4(stored, live) is None:
        return "s4"
    c5 = classify_s5(stored, live)
    if c5 is not None:
        return f"s5-{c5}"
    if sweep_gate_s6(stored, live, html) is None:
        return "s6"
    if sweep_gate_s7(stored, live) is None:
        return "s7"
    if sweep_gate_s8(stored, live, html) is None:
        return "s8"
    return "loss"


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    totals: Counter[str] = Counter()
    loss_rows: list[tuple[str, list[str]]] = []
    bucket_count: Counter[str] = Counter()
    ticker_count: Counter[str] = Counter()
    for t, pe, stored in rows:
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            totals["nocache"] += 1
            continue
        html = open(path, encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None:
            totals["live-none"] += 1
            continue
        if norm(stored) == norm(live):
            totals["in-sync"] += 1
            continue
        cls = classify(stored, live, html)
        totals[cls] += 1
        if cls != "loss":
            continue
        lost = lost_lines(stored, live)
        l_lines = non_empty(live)
        live_set = set(l_lines)
        buckets = [bucket(x, "", live_set) for x in lost]
        for b in buckets:
            bucket_count[b] += 1
        ticker_count[t] += 1
        loss_rows.append((key, lost))
    print("CENSUS (current extractor + gates S4-S8):")
    for k, n in sorted(totals.items()):
        print(f"  {k}: {n}")
    print(f"\nLOSS ROWS: {len(loss_rows)}")
    print("\nLOSS ROWS BY TICKER:")
    for t, n in ticker_count.most_common():
        print(f"  {t}: {n}")
    print("\nLOST-LINE BUCKETS:")
    for b, n in bucket_count.most_common():
        print(f"  {b}: {n}")

    for t in DUMP_TICKERS:
        for t2, pe, stored in rows:
            if t2 != t:
                continue
            key = f"{t2}_{pe}"
            path = f"{CACHE}/{key}.html"
            if not os.path.exists(path):
                continue
            html = open(path, encoding="utf-8").read()
            live = extract_press_release_highlights(html)
            if live is None or norm(stored) == norm(live):
                continue
            if classify(stored, live, html) != "loss":
                continue
            print(f"\n{'=' * 100}\n{key}  stored {len(stored)} chars / live {len(live)} chars")
            print("--- STORED ---")
            for i, x in enumerate(non_empty(stored)):
                print(f"  S{i:02d} {x[:240]}")
            print("--- LIVE ---")
            for i, x in enumerate(non_empty(live)):
                print(f"  L{i:02d} {x[:240]}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
