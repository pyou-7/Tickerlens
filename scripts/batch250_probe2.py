"""Batch 250 probe 2: test two candidate rules across the whole 172-row
loss cohort and report coverage.

Rule A (trailing-guidance): every lost stored line lies in a trailing
run that starts with a guidance-section heading (\"Full Year YYYY
Financial Guidance\" / \"... Guidance\" / \"... Outlook\") and the stored
prefix equals live under norm.

Rule B (truncated-seed prefix): stored is 3990-4000 chars (the seed-era
4000-char cap fingerprint) and every lost stored line is a strict
prefix of some live line (the stored text was chopped mid-line by the
cap), with all other stored lines present in live.

Usage: .venv/bin/python scripts/batch250_probe2.py
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
from batch247_repair import sweep_gate_s6
from batch248_repair import sweep_gate_s7
from batch245_probe import lost_lines
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"

GUIDANCE_HEAD_RE = re.compile(
    r"(full year \d{4} financial guidance|financial guidance|"
    r"full year \d{4} .*?guidance|fiscal \d{4} .*?guidance|"
    r"full year \d{4} .*?outlook|fiscal \d{4} .*?outlook)$",
    re.IGNORECASE,
)


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
    return "loss"


def rule_a(stored, live):
    """Trailing-guidance: stored == live lines + trailing tail whose
    first line is a guidance heading."""
    sl = non_empty(stored)
    ll = non_empty(live)
    if len(sl) <= len(ll):
        return None
    if [norm(x) for x in sl[: len(ll)]] != [norm(x) for x in ll]:
        return None
    tail = sl[len(ll):]
    if not GUIDANCE_HEAD_RE.search(tail[0].strip()):
        return None
    return tail


def rule_b(stored, live):
    """Truncated-seed prefix: stored is ~4000 chars and every lost
    line is a strict prefix of a live line."""
    if not (3990 <= len(stored) <= 4000):
        return None
    sl = non_empty(stored)
    ll = non_empty(live)
    lost = [x for x in sl if x not in set(ll)]
    if not lost:
        return None
    for x in lost:
        if not any(y.startswith(x) and len(y) > len(x) for y in ll):
            return None
    return lost


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    a_hits: list[tuple[str, list[str]]] = []
    b_hits: list[tuple[str, list[str]]] = []
    a_tail_shapes: Counter[str] = Counter()
    for t, pe, stored in rows:
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            continue
        html = open(path, encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None or norm(stored) == norm(live):
            continue
        if classify(stored, live, html) != "loss":
            continue
        ra = rule_a(stored, live)
        if ra is not None:
            a_hits.append((key, ra))
            a_tail_shapes[(len(ra), ra[0][:60])] += 1
        rb = rule_b(stored, live)
        if rb is not None:
            b_hits.append((key, rb))
    print(f"RULE A (trailing-guidance): {len(a_hits)} rows")
    for key, tail in a_hits:
        print(f"  {key}: tail {len(tail)} lines, head={tail[0][:80]!r}")
        for x in tail[1:]:
            print(f"      + {x[:100]!r}")
    print(f"\nRULE B (truncated-seed prefix): {len(b_hits)} rows")
    for key, lost in b_hits:
        print(f"  {key}: {len(lost)} lost line(s), lens={[len(x) for x in lost]}")
        for x in lost:
            print(f"      prefix {x[:100]!r} ... tail {x[-40:]!r}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
