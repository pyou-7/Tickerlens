"""Batch 231 probe: the source-verified stale-row sweep carried from
batches 228-230. Stored highlights rows that are stale (stored != the
current live extraction from the cached exhibit) fall into cohorts the
earlier batches counted but would not blanket-swap:

  * 45 stale dateline+table rows (batch 228 skip list) — live already
    clean, stored source unverified.
  * 28 live-clean flattened-table bodies (batch 228 probe2) — stored
    body is a table, live serves real highlights.

This probe enumerates every stored row whose live extraction differs,
and for each reports the source-identity and no-content-loss signals a
sweep gate would need:

  source: first-line relation (EQ / STORED-SUFFIX / LIVE-SUFFIX /
    DIFF), whether a dated-dateline line in stored also appears in
    live, shared-prefix length of the non-empty normed lines.
  loss: stored non-empty lines absent from live, split into residue
    (table/footnote per the batch-228 predicates) vs real content.
  live-clean: live table fraction and the dateline+table shape flag.

It also counts NULL-guidance rows whose live guidance extraction is
non-null (a possible secondary gate, same source verification).

Read-only: prints a report, writes nothing.
Usage: .venv/bin/python scripts/batch231_probe.py
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


def first_line_relation(stored_lines: list[str], live_lines: list[str]) -> str:
    if not stored_lines or not live_lines:
        return "EMPTY"
    s, l = stored_lines[0], live_lines[0]  # noqa: E741
    if s == l:
        return "EQ"
    if l.endswith(s) and len(s) >= 20:
        return "STORED-SUFFIX"  # seed-era wrapped headline lost its lead
    if s.endswith(l) and len(l) >= 20:
        return "LIVE-SUFFIX"
    return "DIFF"


def shared_prefix_len(a: list[str], b: list[str]) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights, "
        "q.management_guidance "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    cached = {f[:-5] for f in os.listdir(CACHE) if f.endswith(".html")}
    print(f"stored rows: {len(rows)}  cached exhibits: {len(cached)}")

    stale = []  # (key, info dict)
    already_new = 0
    not_cached = 0
    live_none = 0
    null_guidance_fillable = []
    for t, pe, stored, guidance in rows:
        key = f"{t}_{pe}"
        if key not in cached:
            not_cached += 1
            continue
        html = open(f"{CACHE}/{key}.html", encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None:
            live_none += 1
            continue
        if norm(stored) == norm(live):
            already_new += 1
            continue
        s_lines = non_empty(stored)
        l_lines = non_empty(live)
        lfrac = sum(1 for x in l_lines if is_tableish(x)) / max(len(l_lines), 1)
        sfrac = sum(1 for x in s_lines if is_tableish(x)) / max(len(s_lines), 1)
        live_set = set(l_lines)
        missing = [x for x in s_lines if x not in live_set]
        missing_real = [x for x in missing if not is_residue(x)]
        # footnote-definition blocks: a bare "(1)" key + its definition
        # line count as one residue unit; the definition line alone is
        # not residue, so re-check missing lines in block context.
        s_datelines = [x for x in s_lines if _DATED_DATELINE_LEAD_RE.match(x)]
        dateline_ok = all(d in live_set for d in s_datelines)
        stale.append(
            {
                "key": key,
                "s_lines": len(s_lines),
                "l_lines": len(l_lines),
                "s_frac": sfrac,
                "l_frac": lfrac,
                "live_shape": has_dateline_table_shape(l_lines),
                "stored_shape": has_dateline_table_shape(s_lines),
                "first_rel": first_line_relation(s_lines, l_lines),
                "prefix": shared_prefix_len(s_lines, l_lines),
                "missing": len(missing),
                "missing_real": len(missing_real),
                "missing_real_lines": missing_real[:4],
                "dateline_ok": dateline_ok,
                "s_datelines": len(s_datelines),
            }
        )
        if guidance is None:
            lg = extract_management_guidance(html)
            if lg:
                null_guidance_fillable.append(key)

    print(f"already-new: {already_new}  not-cached: {not_cached}  "
          f"live-none: {live_none}  stale: {len(stale)}")
    print(f"NULL-guidance rows with live guidance: {len(null_guidance_fillable)}")
    for k in null_guidance_fillable:
        print(f"    G-FILL {k}")

    # Cohort split for the stale rows.
    def cohort(info: dict) -> str:
        if info["stored_shape"]:
            return "dateline+table"
        if info["s_frac"] >= 0.4:
            return "flat-table-body"
        return "other-stale"

    from collections import Counter

    print("\nstale cohorts:", dict(Counter(cohort(i) for i in stale)))
    # Gate-shape summary: how many stale rows satisfy the strict sweep
    # signals (source identity + no real content loss + live clean).
    strict = [
        i
        for i in stale
        if i["first_rel"] in ("EQ", "STORED-SUFFIX", "LIVE-SUFFIX")
        and i["dateline_ok"]
        and i["missing_real"] == 0
        and i["l_frac"] < 0.4
        and not i["live_shape"]
    ]
    print(f"strict-gate candidates: {len(strict)}")
    for i in stale:
        flag = "STRICT" if i in strict else "     "
        print(
            f"  {flag} {i['key']} cohort={cohort(i)} "
            f"s={i['s_lines']} l={i['l_lines']} "
            f"sfrac={i['s_frac']:.2f} lfrac={i['l_frac']:.2f} "
            f"first={i['first_rel']} prefix={i['prefix']} "
            f"missing={i['missing']} real={i['missing_real']} "
            f"dateline_ok={i['dateline_ok']}({i['s_datelines']}) "
            f"live_shape={i['live_shape']}"
        )
        for ln in i["missing_real_lines"]:
            print(f"         MISSING-REAL: {ln[:130]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
