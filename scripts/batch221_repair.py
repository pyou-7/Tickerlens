"""Batch 221 repair: strip the leading contact-names line from the three
stored CSCO highlights rows.

The stored rows for CSCO 2026-01-24 / 2026-04-25 / 2026-07-25 open
with "Robyn Blum Sami Badri" — the PR/IR contact names, a pre-batch-179
extraction artifact. A DB-wide scan of all 2,491 stored highlights
rows (scripts/batch221_probe.py) finds exactly these three rows with a
leading bare-name line, and no stored guidance row carries it.

The repair is line-level, not a re-extraction: the stored rows are the
narrative section (Revenue / Gross Margin / Balance Sheet prose) while
the current extractor serves headline + bullet highlights, so swapping
in the live text would lose the detailed narrative. Gates per row:

- stored starts with exactly "Robyn Blum Sami Badri\\n\\n";
- the current extractor on the cached exhibit serves highlights with
  no "Robyn Blum" (live is clean — the fix is already in the code);
- repaired == stored minus the 23-char prefix, starts with
  "Revenue -- ", and carries no email/phone/contact residue.

Dry-run by default; pass --write to update the DB. Idempotent: a
second run finds every in-scope row already repaired.
"""
import argparse
import sqlite3
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"

PREFIX = "Robyn Blum Sami Badri\n\n"
TARGETS = ("2026-01-24", "2026-04-25", "2026-07-25")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    con = sqlite3.connect(DB)
    cur = con.cursor()
    repaired = skipped_already = skipped_gate = 0
    for pe in TARGETS:
        stored = cur.execute(
            "SELECT press_release_highlights FROM quarterly_financials "
            "WHERE cik IN (SELECT cik FROM companies WHERE ticker='CSCO') "
            "AND period_end=?",
            (pe,),
        ).fetchone()[0]
        if stored is None:
            print(f"  SKIP (NULL): CSCO {pe}")
            skipped_gate += 1
            continue
        if "Robyn Blum Sami Badri" not in stored:
            skipped_already += 1
            continue
        # Gate 1: the names line is the leading line, nothing before it.
        if not stored.startswith(PREFIX):
            print(f"  SKIP (gate): CSCO {pe} names line is not leading")
            skipped_gate += 1
            continue
        # Gate 2: live extraction of the cached exhibit is clean.
        html = open(f"{CACHE}/CSCO_{pe}.html", encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        assert live is not None and "Robyn Blum" not in live, (
            f"gate 2 FAIL: live extraction still carries the names: CSCO {pe}"
        )
        new = stored[len(PREFIX) :]
        # Gate 3: the remainder is the intact narrative, no contact residue.
        assert new.startswith("Revenue -- "), (
            f"gate 3 FAIL: repaired row does not start with narrative: CSCO {pe}"
        )
        assert "@" not in new and "cisco.com" not in new, (
            f"gate 3 FAIL: contact residue in repaired row: CSCO {pe}"
        )
        assert stored[len(PREFIX) :] == new and len(stored) - len(new) == len(PREFIX)
        print(f"  target: CSCO {pe} stored={len(stored)} -> new={len(new)}")
        if not args.write:
            continue
        cur.execute(
            "UPDATE quarterly_financials SET press_release_highlights=? "
            "WHERE cik IN (SELECT cik FROM companies WHERE ticker='CSCO') "
            "AND period_end=?",
            (new, pe),
        )
        after = cur.execute(
            "SELECT press_release_highlights FROM quarterly_financials "
            "WHERE cik IN (SELECT cik FROM companies WHERE ticker='CSCO') "
            "AND period_end=?",
            (pe,),
        ).fetchone()[0]
        assert after == new, f"DB verification failed: CSCO {pe}"
        repaired += 1
        print(f"  DB-verified: CSCO {pe} now {len(after)} chars")
    if args.write:
        con.commit()
    print(
        f"repaired={repaired} already-new={skipped_already} gated={skipped_gate}"
    )
    if not args.write:
        print("dry run: pass --write to update the DB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
