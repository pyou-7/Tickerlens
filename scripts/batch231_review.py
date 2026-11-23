"""Batch 231 review dump: full stored vs live text for the probe's
strict-gate highlights candidates and the NULL-guidance fillables, so
the repair gates can be checked line-by-line before any write.

Reuses the probe's classification verbatim (same norm, same
predicates); prints STORED then LIVE for each candidate key.
Read-only.
Usage: .venv/bin/python scripts/batch231_review.py > /tmp/batch231_review.txt
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
    _is_trailing_row_label,
    _is_trailing_table_data_row,
    _is_trailing_table_header_orphan,
    _is_trailing_units_period_header,
    extract_management_guidance,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"


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


def is_tableish(ln: str) -> bool:
    return bool(
        _is_lede_table_line(ln)
        or _is_lede_data_row(ln)
        or _is_lede_period_header(ln)
        or _is_lede_table_header(ln)
        or _is_trailing_row_label(ln)
        or _is_trailing_units_period_header(ln)
        or _is_trailing_caps_line(ln)
        or _LEDE_BARE_UNITS_RE.match(ln)
        or _LEDE_BARE_UNITS_LOWER_RE.match(ln)
    )


def is_residue(ln: str) -> bool:
    if is_tableish(ln):
        return True
    if _is_trailing_table_data_row(ln):
        return True
    if _is_trailing_table_header_orphan(ln):
        return True
    if re.fullmatch(r"\(\d+\)", ln):
        return True
    if _footnote_def_block_len([ln], 0):
        return True
    return False


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


def strict_gate(s_lines, l_lines, live_set, s_datelines) -> bool:
    if first_line_relation(s_lines, l_lines) not in (
        "EQ",
        "STORED-SUFFIX",
        "LIVE-SUFFIX",
    ):
        return False
    if not all(d in live_set for d in s_datelines):
        return False
    missing_real = [x for x in s_lines if x not in live_set and not is_residue(x)]
    if missing_real:
        return False
    lfrac = sum(1 for x in l_lines if is_tableish(x)) / max(len(l_lines), 1)
    if lfrac >= 0.4:
        return False
    if has_dateline_table_shape(l_lines):
        return False
    return True


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights, "
        "q.management_guidance "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    strict_keys = []
    gfill = []
    for t, pe, stored, guidance in rows:
        key = f"{t}_{pe}"
        html_path = f"{CACHE}/{key}.html"
        if not os.path.exists(html_path):
            continue
        html = open(html_path, encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None or norm(stored) == norm(live):
            continue
        s_lines = non_empty(stored)
        l_lines = non_empty(live)
        live_set = set(l_lines)
        s_datelines = [x for x in s_lines if _DATED_DATELINE_LEAD_RE.match(x)]
        if strict_gate(s_lines, l_lines, live_set, s_datelines):
            strict_keys.append((key, stored, live))
        if guidance is None:
            lg = extract_management_guidance(html)
            if lg:
                gfill.append((key, lg))
    print(f"STRICT highlights candidates: {len(strict_keys)}")
    for key, stored, live in strict_keys:
        print(f"\n===== {key} =====")
        print("--- STORED ---")
        print(stored)
        print("--- LIVE ---")
        print(live)
    print(f"\n\nG-FILL guidance candidates: {len(gfill)}")
    for key, lg in gfill:
        print(f"\n===== {key} guidance =====")
        print(lg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
