"""Batch 240 probe: the remaining new-residue cohort + EMR's wrapped tail.

Batch 239 closed the diff-figures-added and unexplained-diff cohorts
and left 5 new-residue rows (the live extraction still carries residue
the repair gates refuse to adopt) plus EMR's 4-word wrapped tail:

  EL 2025-12-31, ELV 2024-12-31, ELV 2025-12-31 — "(Unaudited)"
  reconciliation-table labels, suspected probe false positives
  (section labels, not footnote defs)
  GE 2025-06-30 — interleaved "FCF* Conversion-b)" row
  SKYD 2026-06-30 — NULL guidance, fragmentary date-header table
  EMR — "Acquisition / Divestiture" + "Fees and Related Costs"
  4-word wrapped tail still unfused

This probe dumps, for each target row, the stored-vs-new diff and
the exact residue lines the probe flags, so the fix can be scoped
line-by-line before any extractor change.

Usage: .venv/bin/python scripts/batch240_probe.py
"""
import difflib
import json
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch236_repair import _figures, _residue

DB = "tickerlens.db"
NEW_JSON = "hidden_files/blast239_guidance_new.json"

TARGETS = [
    ("EL", "2025-12-31"),
    ("ELV", "2024-12-31"),
    ("ELV", "2025-12-31"),
    ("GE", "2025-06-30"),
    ("SKYD", "2026-06-30"),
]


def _show(ticker: str, period: str, stored: str, new_text: str) -> None:
    s_lines = [ln for ln in stored.splitlines() if ln.strip()]
    n_lines = [ln for ln in new_text.splitlines() if ln.strip()]
    print(f"===== {ticker} {period} =====")
    print(f"  stored lines: {len(s_lines)}, new lines: {len(n_lines)}")
    probs = _residue(n_lines)
    print(f"  residue problems ({len(probs)}):")
    for p in probs:
        print(f"    * {p}")
    print(f"  added figures: {dict(_figures(new_text) - _figures(stored))}")
    print(f"  removed figures: {dict(_figures(stored) - _figures(new_text))}")
    print("  --- new text (full) ---")
    for ln in n_lines:
        print(f"  N {ln[:200]}")
    print("  --- diff stored -> new ---")
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
        a=s_lines, b=n_lines, autojunk=False
    ).get_opcodes():
        if tag == "equal":
            continue
        for ln in s_lines[i1:i2]:
            print(f"  - {ln[:200]}")
        for ln in n_lines[j1:j2]:
            print(f"  + {ln[:200]}")
    print()


def main() -> None:
    with open(NEW_JSON) as f:
        new_map = json.load(f)
    con = sqlite3.connect(DB)

    for ticker, period in TARGETS:
        row = con.execute(
            "SELECT q.management_guidance FROM quarterly_financials q "
            "JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = ? AND q.period_end = ?",
            (ticker, period),
        ).fetchone()
        stored = row[0] if row else None
        key = f"{ticker}_{period}.html"
        new_text = new_map.get(key)
        print(f"--- {ticker} {period}: stored={'NULL' if stored is None else len(stored)} new={'MISSING' if new_text is None else len(new_text)}")
        if stored is None or new_text is None:
            print()
            continue
        _show(ticker, period, stored, new_text)

    # EMR: find rows whose new extraction still carries the wrapped tail
    print("===== EMR wrapped-tail survey =====")
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.management_guidance "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE c.ticker = 'EMR' AND q.management_guidance IS NOT NULL "
        "ORDER BY q.period_end"
    ).fetchall()
    for ticker, period, stored in rows:
        key = f"{ticker}_{period}.html"
        new_text = new_map.get(key)
        if new_text is None:
            continue
        n_lines = [ln for ln in new_text.splitlines() if ln.strip()]
        tail_hits = [
            (i, ln)
            for i, ln in enumerate(n_lines)
            if "Acquisition" in ln or "Fees and Related" in ln
        ]
        probs = _residue(n_lines)
        print(f"  {ticker} {period}: new={len(new_text)} chars, "
              f"tail-hits={tail_hits}, residue={probs}")
    con.close()


if __name__ == "__main__":
    main()
