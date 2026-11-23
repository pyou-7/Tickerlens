"""Batch 266 probe: the BNY x8 carry-forward (CEO-quote design question).

For each BNY quarter, print stored vs live: lengths, first lines, and a
line-level diff summary (stored-only lines vs live-only lines) so the
shape of the disagreement is visible before any design decision.
"""
import difflib
import sqlite3
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"


def main() -> None:
    con = sqlite3.connect(DB)
    pes = [r[0] for r in con.execute(
        "SELECT q.period_end FROM quarterly_financials q "
        "JOIN companies c ON c.cik = q.cik WHERE c.ticker = 'BNY' "
        "ORDER BY q.period_end"
    ).fetchall()]
    for pe in pes:
        stored = con.execute(
            "SELECT q.press_release_highlights FROM quarterly_financials q "
            "JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = 'BNY' AND q.period_end = ?",
            (pe,),
        ).fetchone()[0]
        html = open(f"{CACHE}/BNY_{pe}.html", encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        print(f"--- BNY_{pe} ---")
        print(f"stored {len(stored or '')} chars, {len((stored or '').splitlines())} lines; "
              f"live {len(live or '')} chars, {len((live or '').splitlines())} lines")
        print(f"  stored first 3: {[(stored or '').splitlines()[i][:90] for i in range(min(3, len((stored or '').splitlines())) )]}")
        print(f"  live first 3:   {[(live or '').splitlines()[i][:90] for i in range(min(3, len((live or '').splitlines())) )]}")
        if stored is None or live is None:
            print("  (one side is None)")
            continue
        sm = difflib.SequenceMatcher(None, stored.splitlines(), live.splitlines())
        s_only = [ln for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag == "delete"
                  for ln in stored.splitlines()[i1:i2]]
        l_only = [ln for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag == "insert"
                  for ln in live.splitlines()[j1:j2]]
        print(f"  stored-only lines ({len(s_only)}):")
        for ln in s_only[:12]:
            print(f"    - {ln[:120]}")
        print(f"  live-only lines ({len(l_only)}):")
        for ln in l_only[:12]:
            print(f"    + {ln[:120]}")
    con.close()


if __name__ == "__main__":
    main()
