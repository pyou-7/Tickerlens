"""Batch 241 repair: the highlights sweep, gate S3.

The batch 231/232 source-verified stale-row sweep left 345 SKIP-loss
rows: the live extraction drops stored lines the gate does not
recognize as residue, so a naive overwrite would lose content. The
batch-241 probe decomposes the 345 into:

  spacing-only (105) -- stored and live differ only in flattening
      spacing (bullet glyph without a following space, trademark
      spacing, footnote key spaced off its comma). The batch-241
      norm() extension in scripts/batch231_repair.py canonicalizes
      all of those, so these rows now classify as already-new (B) —
      no write, they were never stale in substance.
  dateline-sentence rows -- the stored row carries the release's
      dateline sentence ("FORT WORTH, Texas — American Airlines ..."
      / "BURBANK, Calif. – The Walt Disney Company today reported
      ..."), which the live extraction drops by design (the bullet /
      lede path never carries it). The sentence matches
      _DATELINE_LEAD_RE, the extractor's own dateline predicate.
  period-subheading rows -- "Third Quarter 2025 Results" /
      "Third Quarter 2025 Financial Results" / "Third Quarter Total
      Company Results (GAAP)" — a section subheading the live
      extraction drops; the bullets/table beneath it are kept.
  table-section-header rows -- Broadcom's "Net revenue by segment":
      a short figure-less header immediately before a hard-table
      block the gate already calls residue.
  section-subheading rows -- "CEO Commentary" (CVS): a short
      title-case heading whose following line (the quote) live keeps.

Gate S3 is gate S with the residue notion extended by those four
chrome classes, plus a dateline-presence exemption: a stored dateline
line is excused when the live text carries NO dateline line at all
(the live extraction dropped datelines wholesale, its bullet path) —
a live text carrying a different dateline still blocks, so a drifted
row from another exhibit cannot slip through. Every other gate-S
condition is unchanged: first-line EQ / STORED-SUFFIX / LIVE-SUFFIX,
live table fraction < 0.4, no added hard-table line, clean live tail,
no lowercase body start.

Still blocked by design (NOT repaired here): the Visa / Amazon /
Autodesk / Akamai section-selection rows (stored prose or a different
bullet block live does not carry — a design question, not a gate
question), the CEO-quote tail rows (live drops a quote the stored row
keeps — overwriting would lose content), and the 1,318 nocache rows.

Usage: DRY_RUN=1 .venv/bin/python scripts/batch241_repair.py
       .venv/bin/python scripts/batch241_repair.py
"""
import os
import re
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import (
    first_line_relation,
    hard_table,
    has_dateline_table_shape,
    is_residue,
    non_empty,
    norm,
)
from tickerlens.data.filings import (
    _BULLET_LEAD_RE,
    _DATED_DATELINE_LEAD_RE,
    _DATELINE_LEAD_RE,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"
DRY = os.environ.get("DRY_RUN") == "1"

_PERIOD_SUBHEAD_RE = re.compile(
    r"^(?:First|Second|Third|Fourth)\s+Quarter(?:\s+\d{4})?\s+"
    r"(?:Financial\s+|Total\s+Company\s+)?Results"
    r"(?:\s*\([^)]*\))?\*?$"
)

_SMALL_WORDS = {
    "by", "of", "and", "the", "for", "to", "in", "on", "with",
    "per", "vs", "a", "an",
}

# Two-comma dated dateline ("WOONSOCKET, RHODE ISLAND, November 6,
# 2024 - ..."): the extractor's _DATED_DATELINE_LEAD_RE allows only
# one comma before the month, so this wire-service form never
# matches it. Same anchors as that regex (city/state with no digits,
# spelled-out month, day, year, dash), so prose cannot match.
_DATED_DATELINE_TWO_COMMA_RE = re.compile(
    r"^[A-Z][A-Za-z .'\-]*,\s+[A-Za-z .'\-]*,\s+"
    r"(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December|Jan\.?|Feb\.?|Mar\.?|Apr\.?|Jun\.?|"
    r"Jul\.?|Aug\.?|Sep\.?|Sept\.?|Oct\.?|Nov\.?|Dec\.?)"
    r"\s+\d{1,2},\s+\d{4}\s+[–—-]{1,2}\s"
)


def _is_period_subheading(ln: str) -> bool:
    """"Third Quarter 2025 Results" / "Third Quarter Total Company
    Results (GAAP)" — a section subheading over the results bullets /
    table, dropped by the live extraction. The quarter word + "Results"
    anchor keeps prose out ("Fourth quarter highlights" is lowercase
    and ends on "highlights", so it never matches)."""
    return bool(_PERIOD_SUBHEAD_RE.match(ln.strip()))


def _is_table_section_header(ln: str, next_ln: str) -> bool:
    """A short figure-less header immediately before a hard-table
    block ("Net revenue by segment" over Broadcom's segment table).
    The next-line condition is the guard: the same shape before a
    bullet ("Creating shareholder value") is a bullet-group label,
    not table chrome, and stays blocked."""
    s = ln.strip()
    if not s or len(s.split()) > 6:
        return False
    if re.search(r"[\d.!?;:]", s):
        return False
    if _BULLET_LEAD_RE.match(s):
        return False
    if _DATELINE_LEAD_RE.match(s) or _DATED_DATELINE_LEAD_RE.match(s):
        return False
    return bool(next_ln) and hard_table(next_ln)


def _is_section_subheading(ln: str, next_ln: str, live_set: set) -> bool:
    """A short title-case heading whose following line live keeps
    ("CEO Commentary" over a quote the live extraction carries). The
    next-line-in-live condition is the guard: a heading over content
    live drops ("Creating shareholder value" over Air Products'
    segment bullets) is not chrome, and stays blocked."""
    s = ln.strip()
    words = s.split()
    if not 1 <= len(words) <= 4:
        return False
    if re.search(r"[.!?;:]", s):
        return False
    if _BULLET_LEAD_RE.match(s):
        return False
    if _DATELINE_LEAD_RE.match(s) or _DATED_DATELINE_LEAD_RE.match(s):
        return False
    for w in words:
        if re.fullmatch(r"\d{4}", w):
            continue  # a year token, not a word
        if w.lower().strip("()*,") in _SMALL_WORDS:
            continue
        if not w[:1].isupper():
            return False
    return bool(next_ln) and next_ln in live_set


def _is_dateline_sentence(ln: str) -> bool:
    """The release's dateline sentence, which the live extraction drops
    by design. Uses the extractor's own dateline predicates, plus the
    two-comma dated form the extractor's _DATED_DATELINE_LEAD_RE does
    not cover ("WOONSOCKET, RHODE ISLAND, November 6, 2024 - CVS
    Health Corporation ... today announced ..."): city + state + full
    month/day/year + dash. The full date + dash anchor keeps prose
    out — a bullet continuation never opens with a city/state/date."""
    return bool(
        _DATELINE_LEAD_RE.match(ln)
        or _DATED_DATELINE_LEAD_RE.match(ln)
        or _DATED_DATELINE_TWO_COMMA_RE.match(ln)
    )


def is_residue_s3(ln: str, next_ln: str, live_set: set) -> bool:
    """Gate-S3 residue: gate-S residue plus the four chrome classes."""
    if is_residue(ln):
        return True
    if _is_dateline_sentence(ln):
        return True
    if _is_period_subheading(ln):
        return True
    if _is_table_section_header(ln, next_ln):
        return True
    if _is_section_subheading(ln, next_ln, live_set):
        return True
    return False


def sweep_gate_s3(stored: str, live: str) -> str | None:
    """Gate S with the S3 residue notion. Returns None when the swap
    is allowed, else the SKIP reason (same vocabulary as gate S)."""
    s_lines = non_empty(stored)
    l_lines = non_empty(live)
    if first_line_relation(s_lines, l_lines) not in (
        "EQ",
        "STORED-SUFFIX",
        "LIVE-SUFFIX",
    ):
        return "first-diff"
    live_set = set(l_lines)
    # Dateline-presence check, with the S3 exemption: a stored
    # dateline line must appear in live (compared under norm, so a
    # spacing-only drift does not false-mismatch) — UNLESS live
    # carries NO dateline line at all, in which case the live
    # extraction dropped datelines wholesale and every stored
    # dateline is chrome. A live text carrying a different dateline
    # still blocks, so a drifted row from another exhibit cannot
    # slip through. The check uses the same dateline-sentence notion
    # as the residue (all three forms, including the two-comma
    # dated form): the old gate's _DATED_DATELINE_LEAD_RE-only
    # collection could not see a two-comma dateline on either side,
    # so a stored Nov 6 dateline and a live Feb 12 dateline both
    # looked like droppable chrome.
    live_has_dateline = any(_is_dateline_sentence(x) for x in l_lines)
    s_datelines = [x for x in s_lines if _is_dateline_sentence(x)]
    if not live_has_dateline:
        s_datelines = []
    live_norm_set = {norm(x) for x in l_lines}
    if not all(norm(d) in live_norm_set for d in s_datelines):
        return "dateline-mismatch"
    for i, x in enumerate(s_lines):
        nxt = s_lines[i + 1] if i + 1 < len(s_lines) else ""
        if x not in live_set and not is_residue_s3(x, nxt, live_set):
            return "loss"
    lfrac = sum(1 for x in l_lines if is_residue(x)) / max(len(l_lines), 1)
    if lfrac >= 0.4 or has_dateline_table_shape(l_lines):
        return "live-table"
    s_set = set(s_lines)
    if any(hard_table(x) for x in l_lines if x not in s_set):
        return "added-table"
    last = l_lines[-1] if l_lines else ""
    if last not in s_set and (
        is_residue(last) or last.rstrip().endswith(":")
    ):
        return "tail"
    if len(l_lines) > 1 and l_lines[1][:1].islower():
        return "fragment"
    return None


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights, q.cik "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    counts: dict[str, int] = {}
    repaired: list[str] = []
    skip_lists: dict[str, list[str]] = {}
    for t, pe, stored, cik in rows:
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            counts["SKIP-nocache"] = counts.get("SKIP-nocache", 0) + 1
            continue
        html = open(path, encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None:
            counts["SKIP-live-none"] = counts.get("SKIP-live-none", 0) + 1
            continue
        if norm(stored) == norm(live):
            counts["B"] = counts.get("B", 0) + 1
        else:
            reason = sweep_gate_s3(stored, live)
            if reason is None:
                counts["S3"] = counts.get("S3", 0) + 1
                repaired.append(key)
                if not DRY:
                    con.execute(
                        "UPDATE quarterly_financials "
                        "SET press_release_highlights = ? "
                        "WHERE cik = ? AND period_end = ?",
                        (live, cik, pe),
                    )
                print(f"    S3 {key} {len(stored)}->{len(live)}")
            else:
                rk = f"SKIP-{reason}"
                counts[rk] = counts.get(rk, 0) + 1
                skip_lists.setdefault(rk, []).append(key)
    if not DRY:
        con.commit()
    print(f"\nDRY_RUN={DRY} counts: {counts}")
    print(f"highlights repaired (S3): {len(repaired)}")
    for rk in sorted(skip_lists):
        keys = skip_lists[rk]
        if rk in ("SKIP-tail", "SKIP-fragment", "SKIP-live-table",
                  "SKIP-added-table", "SKIP-dateline-mismatch"):
            print(f"  {rk} ({len(keys)}): {', '.join(keys)}")
        else:
            print(f"  {rk} ({len(keys)})")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
