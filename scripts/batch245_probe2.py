"""Batch 245 probe 2: size the gateable subclasses inside the 203
SKIP-loss rows.

For each loss row, recompute the lost lines under the S4 pipeline and
bucket each lost line:
  dateline-ci  -- dateline sentence with an ALL-CAPS month
                 ("SAN FRANCISCO, MAY 22, 2025 -- ...", ADSK x7)
  dateline-paren -- parenthesized-date dateline
                 ("HOUSTON & LONDON (January 30, 2025) - ...", BKR;
                  "LEHIGH VALLEY, Pa. (November 6, 2025) - ...", APD)
  boilerplate  -- non-GAAP definition sentence, GAAP-guidance
                 disclaimer, webcast boilerplate
  table-furn   -- reconciliation / guidance-table furniture lines
  quote        -- CEO/CFO quote lines
  subhead      -- period / section subheading (already S3 residue,
                 counted here only when the S3 guard refused it)
  content      -- everything else (real highlights content live drops)

Then count rows whose lost lines are ALL chrome (dateline-ci /
dateline-paren / boilerplate / table-furn / subhead): those are the
gate-S6 candidates. Rows with any content lost line stay blocked.

Also dumps stored-vs-live for ADSK_2025-01-31 and ADI_2024-11-02 so
the mechanism (why live drops those lines) is visible.

Usage: .venv/bin/python scripts/batch245_probe2.py > /tmp/batch245_dump2.txt
"""
import os
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import non_empty, norm
from batch241_repair import (
    _is_period_subheading,
    _is_section_subheading,
    _is_table_section_header,
    is_residue_s3,
)
from batch242_repair import (
    _align_headline,
    _split_flattened,
    _strip_leading_chrome,
    sweep_gate_s4,
)
from batch245_probe import lost_lines
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"

_MONTHS = (
    "January|February|March|April|May|June|July|August|September|"
    "October|November|December|Jan\\.?|Feb\\.?|Mar\\.?|Apr\\.?|Jun\\.?|"
    "Jul\\.?|Aug\\.?|Sep\\.?|Sept\\.?|Oct\\.?|Nov\\.?|Dec\\.?"
)
_DATELINE_CI_RE = re.compile(
    r"^[A-Z][A-Za-z .'\\-]*,\s+(?:" + _MONTHS + r")\s+\d{1,2},\s+\d{4}\s+[–—-]{1,2}\s",
    re.IGNORECASE,
)
_DATELINE_PAREN_RE = re.compile(
    r"^[A-Z][A-Z .'\\-]*,?\s*[A-Z][A-Za-z.]*\s*\([A-Za-z]+ \d{1,2}, \d{4}\)\s*[–—-]"
    r"|^[A-Z][A-Z .'\\-]*\s*&\s*[A-Z][A-Za-z .'\-]*\s*\([A-Za-z]+ \d{1,2}, \d{4}\)\s*[–—-]"
)
_NONGAAP_DEF_RE = re.compile(
    r"are non-GAAP (financial )?measures\.?\s*A reconciliation",
    re.IGNORECASE,
)
_GAAP_GUIDANCE_RE = re.compile(
    r"does not provide forward-looking guidance on a GAAP basis",
    re.IGNORECASE,
)
_WEBCAST_RE = re.compile(
    r"live webcast will be accessible|presentation materials will be posted",
    re.IGNORECASE,
)
_TABLE_FURN_RES = (
    re.compile(r"reconciliation$", re.IGNORECASE),
    re.compile(r"^(Prior|Updated)\s+FY\s+\d{4}\s+Guidance", re.IGNORECASE),
    re.compile(r"^Approx\. impact from", re.IGNORECASE),
    re.compile(r"\(net of taxes of \$\d+\)$", re.IGNORECASE),
    re.compile(r"^Earnings Per Common Share of \$", re.IGNORECASE),
)
_QUOTE_RE = re.compile(r'[“"]')


def bucket(ln: str, nxt: str, live_set: set) -> str:
    s = ln.strip()
    if _DATELINE_CI_RE.match(s):
        return "dateline-ci"
    if _DATELINE_PAREN_RE.match(s):
        return "dateline-paren"
    if _NONGAAP_DEF_RE.search(s) or _GAAP_GUIDANCE_RE.search(s) or _WEBCAST_RE.search(s):
        return "boilerplate"
    if any(rx.search(s) for rx in _TABLE_FURN_RES):
        return "table-furn"
    if _QUOTE_RE.search(s):
        return "quote"
    if _is_period_subheading(s) or _is_table_section_header(s, nxt) or _is_section_subheading(s, nxt, live_set):
        return "subhead"
    return "content"


CHROME = {"dateline-ci", "dateline-paren", "boilerplate", "table-furn", "subhead"}


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    bucket_count: Counter[str] = Counter()
    chrome_only_rows: list[str] = []
    chrome_only_detail: list[tuple[str, list[str]]] = []
    content_rows = 0
    for t, pe, stored in rows:
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            continue
        html = open(path, encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None or norm(stored) == norm(live):
            continue
        if sweep_gate_s4(stored, live) != "loss":
            continue
        lost = lost_lines(stored, live)
        s_lines = non_empty(stored)
        l_lines = non_empty(live)
        live_set = set(l_lines)
        buckets = []
        for i, x in enumerate(lost):
            # next line in the S4-pipelined stored order
            buckets.append(bucket(x, "", live_set))
        for b in buckets:
            bucket_count[b] += 1
        if buckets and all(b in CHROME for b in buckets):
            chrome_only_rows.append(key)
            chrome_only_detail.append((key, buckets))
        else:
            content_rows += 1
    print("LOST-LINE BUCKETS (203 loss rows):")
    for b, n in bucket_count.most_common():
        print(f"  {b}: {n}")
    print(f"\nCHROME-ONLY ROWS (all lost lines chrome): {len(chrome_only_rows)}")
    for key, buckets in chrome_only_detail:
        print(f"  {key}: {Counter(buckets)}")
    print(f"ROWS WITH >=1 CONTENT LOST LINE: {content_rows}")

    for key in ("ADSK_2025-01-31", "ADI_2024-11-02"):
        t, pe = key.split("_")[0], key.split("_", 1)[1]
        stored = con.execute(
            "SELECT q.press_release_highlights FROM quarterly_financials q "
            "JOIN companies c ON c.cik = q.cik WHERE c.ticker = ? "
            "AND q.period_end = ?",
            (t, pe),
        ).fetchone()[0]
        html = open(f"{CACHE}/{key}.html", encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        print(f"\n{'=' * 100}\n{key}  stored {len(stored)} chars / live {len(live)} chars")
        print("--- STORED ---")
        for i, x in enumerate(non_empty(stored)):
            print(f"  S{i:02d} {x[:180]}")
        print("--- LIVE ---")
        for i, x in enumerate(non_empty(live)):
            print(f"  L{i:02d} {x[:180]}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
