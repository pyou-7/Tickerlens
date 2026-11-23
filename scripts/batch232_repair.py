"""Batch 232 repair: the dangling-intro rows batch 231 would not swap.

Batch 231 blocked 6 rows on the live extraction ending on a dangling
table intro (BRK.B x3, FAST 2025-03-31, FDX 2026-05-31, GILD
2026-06-30) and left the AZO/BMY/CNC/DIS rows stale because their
stored lines carry the same intro text the extractor now trims.
Batch 232 fixes the extractor, so the live text is clean and the
rows become swappable — under gate S2, which is batch 231's gate S
with the missing-line coverage extended:

  S2: highlights sweep. Cached exhibit, live extraction non-None,
     norm(stored) != norm(live), and ALL of gate S (first-line
     relation EQ / STORED-SUFFIX / LIVE-SUFFIX; live table fraction
     < 0.4 and no dateline+table shape; no ADDED live line is a
     hard-table line; the live tail is clean — not residue and not
     colon-ended when not already in stored; live's first body line
     does not start lowercase — where "first body line" is l_lines[0]
     when it starts lowercase, else l_lines[1] unless l_lines[0] ends
     mid-sentence (Berkshire's no-headline release opens on a wrapped
     paragraph whose continuation "judgment." is l_lines[1])) PLUS the coverage rule below for the
     two places gate S demands stored lines appear in live:
       - every stored dateline line is covered;
       - every stored line absent from live is covered.
     A stored line is COVERED when it is residue (gate S's
     hard/soft-table predicates), or it IS a dangling intro
     (Berkshire's "Net earnings includes:", Disney's "• Fiscal
     2025:" — the extractor now drops it), or it truncates via
     _truncate_trailing_dangling_intro to exactly a live line
     (AutoZone's dateline "...are as follows:", Bristol Myers'
     "...was largely driven by:", Centene's "...were as follows:").
     -> set press_release_highlights to the live extraction.
  G: guidance fill, unchanged from batch 231 (NULL stored guidance,
     live guidance >= 200 chars, post-heading table fraction < 0.2).
     The guidance extractor is byte-identical this batch, so no new
     fills are expected; the gate re-runs as a control.
  B: norm(stored) == norm(live) already -> already-new, no write.

SKIP reasons: same as batch 231 (loss / first-diff /
dateline-mismatch / tail / fragment / live-table / added-table /
nocache / live-none / G-table / too-short), with "loss" now meaning
a stored line is uncovered under the S2 rule.

Only cached rows can repair; rows with no cached exhibit stay as-is
(they serve complete highlights on refresh). Idempotent on re-run
(repaired rows become already-new / guidance-filled).

Usage: DRY_RUN=1 .venv/bin/python scripts/batch232_repair.py
       .venv/bin/python scripts/batch232_repair.py
"""
import os
import re
import sqlite3
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _DATED_DATELINE_LEAD_RE,
    _LEDE_BARE_UNITS_LOWER_RE,
    _LEDE_BARE_UNITS_RE,
    _footnote_def_block_len,
    _is_lede_data_row,
    _is_lede_period_header,
    _is_lede_table_header,
    _is_lede_table_line,
    _is_trailing_caps_line,
    _is_trailing_dangling_intro,
    _is_trailing_row_label,
    _is_trailing_table_data_row,
    _is_trailing_table_header_orphan,
    _is_trailing_units_period_header,
    _prev_line_unfinished,
    _truncate_trailing_dangling_intro,
    extract_management_guidance,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"
DRY = os.environ.get("DRY_RUN") == "1"


def norm(s: str) -> str:
    s = re.sub(r"•(?!\s)", "• ", s)
    lines = [ln.rstrip() for ln in s.split("\n")]
    out: list[str] = []
    for ln in lines:
        if ln == "" and out and out[-1] == "":
            continue
        out.append(ln)
    return "\n".join(out).strip()


def non_empty(s: str) -> list[str]:
    return [ln for ln in norm(s).split("\n") if ln.strip()]


def hard_table(ln: str) -> bool:
    return bool(
        _is_lede_data_row(ln)
        or _is_lede_table_header(ln)
        or _is_lede_period_header(ln)
        or _is_trailing_units_period_header(ln)
        or _is_trailing_table_data_row(ln)
        or _is_trailing_table_header_orphan(ln)
        or _LEDE_BARE_UNITS_RE.match(ln)
        or _LEDE_BARE_UNITS_LOWER_RE.match(ln)
    )


def soft_residue(ln: str) -> bool:
    return bool(
        _is_lede_table_line(ln)
        or _is_trailing_row_label(ln)
        or _is_trailing_caps_line(ln)
        or re.fullmatch(r"\(\d+\)", ln)
        or _footnote_def_block_len([ln], 0)
    )


def is_tableish(ln: str) -> bool:
    return hard_table(ln) or soft_residue(ln)


def is_residue(ln: str) -> bool:
    return is_tableish(ln)


def covered(ln: str, live_set: set[str]) -> bool:
    """True when a stored line is accounted for by the live text:
    present as-is, table/footnote residue, a dangling intro the
    extractor now drops, or a line that truncates (dangling-intro
    fragment cut) to exactly a live line."""
    if ln in live_set:
        return True
    if is_residue(ln):
        return True
    if _is_trailing_dangling_intro(ln):
        return True
    trunc = _truncate_trailing_dangling_intro(ln)
    return trunc is not None and trunc in live_set


def has_dateline_table_shape(lines: list[str]) -> bool:
    for i, ln in enumerate(lines):
        if _DATED_DATELINE_LEAD_RE.match(ln):
            if any(_is_lede_table_line(x) for x in lines[i + 1 :]):
                return True
    return False


def first_line_relation(s_lines: list[str], l_lines: list[str]) -> str:
    if not s_lines or not l_lines:
        return "EMPTY"
    s, l = s_lines[0], l_lines[0]  # noqa: E741
    if s == l:
        return "EQ"
    if l.endswith(s) and len(s) >= 20:
        return "STORED-SUFFIX"
    if s.endswith(l) and len(l) >= 20:
        return "LIVE-SUFFIX"
    return "DIFF"


def sweep_gate(stored: str, live: str) -> str | None:
    """Return None if the highlights swap is allowed, else a SKIP reason."""
    s_lines = non_empty(stored)
    l_lines = non_empty(live)
    if first_line_relation(s_lines, l_lines) not in (
        "EQ",
        "STORED-SUFFIX",
        "LIVE-SUFFIX",
    ):
        return "first-diff"
    live_set = set(l_lines)
    s_datelines = [x for x in s_lines if _DATED_DATELINE_LEAD_RE.match(x)]
    if not all(covered(d, live_set) for d in s_datelines):
        return "dateline-mismatch"
    if any(not covered(x, live_set) for x in s_lines):
        return "loss"
    lfrac = sum(1 for x in l_lines if is_tableish(x)) / max(len(l_lines), 1)
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
    if l_lines and l_lines[0][:1].islower():
        return "fragment"
    if (
        len(l_lines) > 1
        and l_lines[1][:1].islower()
        and not _prev_line_unfinished(l_lines[0])
    ):
        # Batch 232: the body start is l_lines[1] when l_lines[0] is
        # a headline, but l_lines[0] itself when the extractor
        # returned no headline (Berkshire: the release opens on the
        # operating-results paragraph, whose wrapped continuation
        # "judgment." is l_lines[1]). A lowercase second line is a
        # fragment only when the first line does not end
        # mid-sentence. Airbnb 2024-12-31 still blocks: its headline
        # ends on "Results", not mid-sentence.
        return "fragment"
    return None


def guidance_gate(live_guidance: str) -> str | None:
    """Return None if the guidance fill is allowed, else a SKIP reason."""
    if len(live_guidance) < 200:
        return "too-short"
    gl = non_empty(live_guidance)
    body = gl[1:] if len(gl) > 1 else []
    frac = sum(1 for x in body if is_tableish(x)) / max(len(body), 1)
    if frac >= 0.2:
        return "G-table"
    return None


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights, "
        "q.management_guidance, q.cik "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    counts: dict[str, int] = {}
    repaired_h: list[str] = []
    repaired_g: list[str] = []
    skip_lists: dict[str, list[str]] = {}
    for t, pe, stored, guidance, cik in rows:
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
            reason = sweep_gate(stored, live)
            if reason is None:
                counts["S2"] = counts.get("S2", 0) + 1
                repaired_h.append(key)
                if not DRY:
                    con.execute(
                        "UPDATE quarterly_financials "
                        "SET press_release_highlights = ? "
                        "WHERE cik = ? AND period_end = ?",
                        (live, cik, pe),
                    )
                print(f"    S2 {key} {len(stored)}->{len(live)}")
            else:
                rk = f"SKIP-{reason}"
                counts[rk] = counts.get(rk, 0) + 1
                skip_lists.setdefault(rk, []).append(key)
        if guidance is None:
            lg = extract_management_guidance(html)
            if lg is not None:
                greason = guidance_gate(lg)
                if greason is None:
                    counts["G"] = counts.get("G", 0) + 1
                    repaired_g.append(key)
                    if not DRY:
                        con.execute(
                            "UPDATE quarterly_financials "
                            "SET management_guidance = ? "
                            "WHERE cik = ? AND period_end = ?",
                            (lg, cik, pe),
                        )
                    print(f"    G {key} guidance {len(lg)} chars")
                else:
                    rk = f"SKIP-{greason}"
                    counts[rk] = counts.get(rk, 0) + 1
                    skip_lists.setdefault(rk, []).append(key)
    if not DRY:
        con.commit()
    print(f"\nDRY_RUN={DRY} counts: {counts}")
    print(f"highlights repaired (S2): {len(repaired_h)}")
    print(f"guidance filled (G): {len(repaired_g)}")
    for rk in sorted(skip_lists):
        keys = skip_lists[rk]
        if rk in ("SKIP-tail", "SKIP-fragment", "SKIP-G-table", "SKIP-too-short"):
            print(f"  {rk} ({len(keys)}): {', '.join(keys)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
