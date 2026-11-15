"""Batch 258 probe: DLR's "Table of Contents" headline wart.

All 8 DLR stored highlights rows start with the literal line
"Table of Contents" as their headline (live and stored agree — the
census counts them in-sync, so the wart is invisible to the gate
chain). Batch 253 fixed the TOC-only live extraction (the TOC junk
body is gone); what remains is the headline: the TOC heading itself
is picked as the headline.

For one DLR quarter (2025-06-30), dump the cached exhibit's opening
lines, run the live extractor, and trace why the headline pass lands
on "Table of Contents" instead of the real release headline — does
_skip_toc fire and roll back, does it return i unchanged (pages < 2),
or does the headline pass never reach the TOC branch?

Usage: .venv/bin/python scripts/batch258_probe.py
"""
import glob
import os
import sqlite3
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _TOC_HEADING_RE,
    _TOC_PAGE_RE,
    _skip_toc,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"


def main():
    c = sqlite3.connect(DB)
    cik = c.execute("SELECT cik FROM companies WHERE ticker='DLR'").fetchone()[0]
    rows = c.execute(
        "SELECT period_end, press_release_highlights FROM quarterly_financials"
        " WHERE cik=? ORDER BY period_end",
        (cik,),
    ).fetchall()
    print(f"DLR rows: {len(rows)}")
    for pe, hl in rows:
        first = (hl or "").split("\n")[0]
        print(f"  {pe} headline={first!r}")

    # One quarter's cached exhibit.
    pat = os.path.join(CACHE, "*DLR*")
    files = sorted(glob.glob(pat))
    print(f"\ncached DLR files: {len(files)}")
    for f in files[:3]:
        print(" ", os.path.basename(f))

    # Find the 2025-06-30 exhibit: match by period in filename or by
    # scanning for the quarter's FFO figure.
    target = None
    for f in files:
        with open(f, encoding="utf-8", errors="replace") as fh:
            html = fh.read()
        if "1.75 in 2Q25" in html and "2.94 per share" in html:
            target = f
            break
    if target is None and files:
        target = files[0]
    print(f"\nprobe exhibit: {os.path.basename(target or '')}")
    if not target:
        print("NO CACHED EXHIBIT FOUND")
        return
    with open(target, encoding="utf-8", errors="replace") as fh:
        html = fh.read()
    hl = extract_press_release_highlights(html)
    print(f"live headline: {(hl or '').splitlines()[0] if hl else None!r}")
    print(f"live first 3 lines: {(hl or '').splitlines()[:3]}")

    # Rebuild the flattened text lines the headline pass sees.
    from tickerlens.data.filings import _html_to_text

    lines = [ln.strip() for ln in _html_to_text(html).split("\n") if ln.strip()]
    toc_idx = [i for i, ln in enumerate(lines) if _TOC_HEADING_RE.match(ln)]
    print(f"\nTOC heading lines at: {toc_idx} (of {len(lines)} lines)")
    for ti in toc_idx[:1]:
        lo, hi = max(0, ti - 3), min(len(lines), ti + 25)
        for i in range(lo, hi):
            mark = ""
            if _TOC_PAGE_RE.match(lines[i]):
                mark = "  <-- PAGE"
            print(f"  {i:4d}: {lines[i]!r}{mark}")
        print(f"\n_skip_toc(lines, {ti}) -> {_skip_toc(lines, ti)}")


if __name__ == "__main__":
    main()
