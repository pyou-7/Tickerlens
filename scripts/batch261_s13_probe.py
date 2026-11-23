"""Batch 261 probe: candidate gate S13 (bullet-superset + quote-tail
truncation) for the CINF Q1/Q2 sub-class.

Shape: stored carries the Investment-section bullets + a long CEO-quote
run; live carries the Insurance + Investment bullets (strict bullet
superset) and only the first 3 quote lines (the designed batch-246/249
quote cap). The removed stored lines are quote lines and their group
headings, all after the last stored bullet; the added live lines are
financial bullets and the heading that introduces them.

S13 blesses re-sync iff:
  1. headlines align (same preamble as S4)
  2. every stored bullet line is present in live (normalized)
  3. live has strictly more bullet lines than stored
  4. every stored line not in live is a quote line, or a heading
     adjacent to a quote line, and all removed lines sit after the
     last stored bullet (quote-tail truncation)
  5. every live line not in stored is a financial bullet, or a
     figure-free heading immediately followed by a bullet

Narrowness (full-census simulation): S13 blesses exactly the 4 CINF
Q1/Q2 rows. The CINF Q3 lede rows refuse (stored bullets lost) and
BKR 2024-12-31 refuses (its removed dateline is a 30-word dated
sentence, not a quote-group heading, so the heading-shape bound
stops it; the dateline guard is defense-in-depth).

Usage: .venv/bin/python scripts/batch261_s13_probe.py [--cinf-only]
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import norm
from batch242_repair import sweep_gate_s4
from batch244_repair import classify_s5
from batch247_repair import sweep_gate_s6
from batch248_repair import sweep_gate_s7
from batch250_repair import sweep_gate_s8
from batch251_repair import sweep_gate_s9
from batch253_repair import sweep_gate_s10
from batch254_repair import sweep_gate_s11
from batch255_repair import sweep_gate_s12
from tickerlens.data import filings as F

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"

_BULLET_FIRST = "•●–—◾◦▪■·○*"


def _is_bullet(ln: str) -> bool:
    s = ln.strip()
    return bool(s) and (s[0] in _BULLET_FIRST or F._BULLET_LEAD_RE.match(s))


def _is_financial(ln: str) -> bool:
    return bool(F._FINANCIAL_LINE_RE.search(ln))


from batch261_repair import sweep_gate_s13


def _classify(stored, live, html):
    if live is None:
        return "SKIP-live-none"
    if norm(stored) == norm(live):
        return "B in-sync"
    if sweep_gate_s4(stored, live) is None:
        return "S4"
    cls5 = classify_s5(stored, live)
    if cls5 is not None:
        return f"SKIP-S5-{cls5}"
    if sweep_gate_s6(stored, live, html) is None:
        return "S6"
    if sweep_gate_s7(stored, live) is None:
        return "S7"
    if sweep_gate_s8(stored, live, html) is None:
        return "S8"
    if sweep_gate_s9(stored, live, html) is None:
        return "S9"
    if sweep_gate_s10(stored, live) is None:
        return "S10"
    if sweep_gate_s11(stored, live) is None:
        return "S11"
    if sweep_gate_s12(stored, live) is None:
        return "S12"
    return "SKIP-loss"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cinf-only", action="store_true")
    args = ap.parse_args()

    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()

    if args.cinf_only:
        for t, pe, stored in rows:
            if t != "CINF":
                continue
            key = f"{t}_{pe}"
            path = f"{CACHE}/{key}.html"
            if not os.path.exists(path):
                print(f"{key}: no cached exhibit")
                continue
            html = open(path, encoding="utf-8").read()
            live = F.extract_press_release_highlights(html)
            print(f"{key}: class={_classify(stored, live, html)} S13={sweep_gate_s13(stored, live, html)}")
        return

    counts: dict[str, int] = {}
    s13_blessed = []
    for t, pe, stored in rows:
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            counts["SKIP-nocache"] = counts.get("SKIP-nocache", 0) + 1
            continue
        html = open(path, encoding="utf-8").read()
        live = F.extract_press_release_highlights(html)
        cls = _classify(stored, live, html)
        counts[cls] = counts.get(cls, 0) + 1
        if cls == "SKIP-loss":
            r13 = sweep_gate_s13(stored, live, html)
            if r13 is None:
                s13_blessed.append(key)
    print("census counts (current extractor + gates S4-S12):")
    for k in sorted(counts):
        print(f"  {k}: {counts[k]}")
    print(f"\nS13 would bless {len(s13_blessed)} SKIP-loss rows:")
    for k in s13_blessed:
        print(f"  {k}")


if __name__ == "__main__":
    main()
