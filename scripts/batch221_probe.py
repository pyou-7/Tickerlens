"""Batch 221 probe: stored press-release highlights rows that start with a
bare contact-name line (the CSCO "Robyn Blum Sami Badri" class).

The current extractor already drops Cisco's contact block (test
test_contact_block_names_before_phones_are_skipped), but three stored
CSCO rows predate that fix and still open with the names line. The
stored rows are the narrative section while the current extraction
serves the bullet highlights, so a swap would lose narrative — this
batch repairs them line-level (strip the leading names line only).

This probe:
  1. scans every stored highlights row for a leading bare-name line
     (2-4 capitalized words, no digits/$/%/punctuation) and for the
     literal "Robyn Blum Sami Badri" anywhere;
  2. runs the current extractor on the three cached CSCO exhibits to
     confirm live extraction drops the names line and to show what
     live serves vs what is stored (justifying line-level repair);
  3. checks the stored guidance rows for the same leading line.
"""
import re
import sqlite3
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"

# A bare person-name line: 2-4 capitalized words, nothing else.
NAME_LINE_RE = re.compile(r"^[A-Z][a-z]+(?: [A-Z][a-z]+){1,3}$")


def main() -> int:
    con = sqlite3.connect(DB)
    cur = con.cursor()

    print("== 1. stored highlights rows starting with a bare-name line ==")
    rows = cur.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL ORDER BY c.ticker, q.period_end"
    ).fetchall()
    print(f"{len(rows)} stored highlights rows")
    hits = 0
    for ticker, pe, hl in rows:
        first = next((ln for ln in hl.splitlines() if ln.strip()), "")
        if NAME_LINE_RE.match(first.strip()):
            print(f"  {ticker} {pe}: first line {first.strip()!r} len={len(hl)}")
            hits += 1
        if "Robyn Blum Sami Badri" in hl and not NAME_LINE_RE.match(first.strip()):
            print(f"  {ticker} {pe}: names line NOT first: {first.strip()[:80]!r}")
            hits += 1
    print(f"bare-name-leading rows: {hits}")

    print("== 2. live extraction of the three cached CSCO exhibits ==")
    for pe in ("2026-01-24", "2026-04-25", "2026-07-25"):
        html = open(f"{CACHE}/CSCO_{pe}.html", encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        stored = cur.execute(
            "SELECT press_release_highlights FROM quarterly_financials "
            "WHERE cik IN (SELECT cik FROM companies WHERE ticker='CSCO') "
            "AND period_end=?",
            (pe,),
        ).fetchone()[0]
        print(f"  CSCO {pe}: stored={len(stored)} live={len(live) if live else 0}")
        print(f"    live has names line: {'Robyn Blum' in (live or '')}")
        print(f"    live first para: {(live or '').split(chr(10)+chr(10))[0][:90]!r}")
        print(f"    stored minus names line == live prefix? "
              f"{stored[len('Robyn Blum Sami Badri')+2:][:60]!r} vs "
              f"{(live or '')[:60]!r}")
        # Show whether the stored narrative lines survive in live at all.
        stored_lines = [ln for ln in stored.splitlines() if ln.strip()][1:4]
        for ln in stored_lines:
            print(f"    stored line in live: {ln[:60]!r} -> {ln[:40] in (live or '')}")

    print("== 3. stored guidance rows starting with the names line ==")
    grows = cur.execute(
        "SELECT c.ticker, q.period_end FROM quarterly_financials q "
        "JOIN companies c ON c.cik = q.cik "
        "WHERE q.management_guidance LIKE 'Robyn Blum Sami Badri%'"
    ).fetchall()
    print(f"guidance rows starting with the names line: {len(grows)} {grows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
