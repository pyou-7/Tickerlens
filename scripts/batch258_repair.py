"""Batch 258 repair: re-sync the 8 stored DLR highlights rows whose
headline is the literal "Table of Contents".

Cause (see tests/data/test_filings_batch258.py): _skip_toc's
admin-break fired on the "Exhibit 99.1" line DLR repeats inside
its table of contents, so the TOC heading became the headline.
The extractor now serves the real headline ("Digital Realty
Reports ... Results") with the same body. The repair is strict
by construction: a row is updated only when

  * its stored first line is exactly "Table of Contents",
  * live extraction from its cached exhibit succeeds, and
  * the stored body (everything after the first line) is
    byte-identical to the live body.

Anything else is left untouched and reported. The full-cache
blast moves exactly the 12 DLR exhibits (8 stored + 4
pre/post-window cached quarters with no stored row); EOG and
all other exhibits are byte-identical. Idempotent: a re-run
finds 0 rows with the wart.

Usage: DRY_RUN=1 .venv/bin/python scripts/batch258_repair.py
       .venv/bin/python scripts/batch258_repair.py
"""
import os
import sqlite3
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"
DRY = os.environ.get("DRY_RUN") == "1"


def main() -> int:
    con = sqlite3.connect(DB)
    cik = con.execute(
        "SELECT cik FROM companies WHERE ticker='DLR'"
    ).fetchone()[0]
    rows = con.execute(
        "SELECT period_end, press_release_highlights FROM quarterly_financials"
        " WHERE cik=? ORDER BY period_end",
        (cik,),
    ).fetchall()
    repaired: list[str] = []
    skipped: list[str] = []
    for pe, stored in rows:
        key = f"DLR_{pe}"
        if not stored or stored.splitlines()[0] != "Table of Contents":
            skipped.append(f"{key} (no wart)")
            continue
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            skipped.append(f"{key} (no cached exhibit)")
            continue
        html = open(path, encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None:
            skipped.append(f"{key} (live None)")
            continue
        stored_body = stored.split("\n\n", 1)[1] if "\n\n" in stored else ""
        live_body = live.split("\n\n", 1)[1] if "\n\n" in live else ""
        if stored_body != live_body:
            skipped.append(f"{key} (body differs)")
            continue
        repaired.append(key)
        print(f"  {key}: {stored.splitlines()[0]!r} -> {live.splitlines()[0]!r}")
        if not DRY:
            con.execute(
                "UPDATE quarterly_financials "
                "SET press_release_highlights = ? "
                "WHERE cik = ? AND period_end = ?",
                (live, cik, pe),
            )
    if not DRY:
        con.commit()
    print(f"repaired: {len(repaired)}  skipped: {len(skipped)}  dry={DRY}")
    for s in skipped:
        print(f"  SKIP {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
