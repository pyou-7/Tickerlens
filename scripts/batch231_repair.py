"""Batch 231 repair: the source-verified stale-row sweep carried from
batches 228-230. 528 stored highlights rows differ from the current
live extraction; the earlier batches would not blanket-swap them
because the stored source was unverified. This script swaps only
rows whose source exhibit is verified and whose swap loses nothing.

Gates (printed per row; a row repairs under exactly one gate per
field — highlights and guidance repair independently):
  S: highlights sweep. Cached exhibit, live extraction non-None,
     norm(stored) != norm(live), and ALL of:
       - first-line relation is EQ, STORED-SUFFIX (seed-era wrapped
         headline lost its lead word, batch 230 A2) or LIVE-SUFFIX;
       - every dated-dateline line in stored also appears in live;
       - every stored line absent from live is residue (a hard-table
         line — data row / table header / period header / units-period
         header / trailing data row / trailing header orphan / bare
         units — or a soft-residue line — table line / row label /
         caps line / bare footnote key / footnote definition);
       - live table-ish fraction < 0.4 and no dateline+table shape
         in live;
       - no ADDED live line is a hard-table line (an added
         flattened-table row means the live extraction itself
         carries a table — Ford's key-metrics table rides inside a
         fused paragraph line, so this guard is line-level only);
       - the live tail is clean: if live's last line is not already
         in stored, it must not be residue and must not end with ":"
         (a dangling table intro — Berkshire's "Net earnings
         includes:", Fastenal's "...were as follows:", FedEx's
         "...have been adjusted for:", Gilead's "...primarily
         driven by:"). A tail line already in stored is pre-existing
         (Enphase's "...compared with the prior quarter:") and does
         not block;
       - live's first body line does not start with a lowercase
         letter (a continuation fragment — Airbnb 2024-12-31's live
         body opens "driven by the growth of nights ...", mid-sentence
         out of its flattened shareholder-letter table).
     -> set press_release_highlights to the live extraction.
  G: guidance fill. Stored management_guidance IS NULL, live
     guidance non-null, >= 200 chars, and its table-ish fraction
     over the lines AFTER the heading line is < 0.2 (the heading
     itself is tableish in every case — all-caps "OUTLOOK" or a
     "Financial Outlook" line — so it is excluded from the fraction).
     Admits Darden x8 and Enphase x10 (real outlook prose + ranges);
     blocks AppLovin x7 and DuPont x4 (the guidance section is a
     flattened "Guidance Summary" table with footnote furniture) and
     Skyworks 2026-06-30 (an "Outlook" heading over table residue).
     -> set management_guidance to the live guidance text.
  B: norm(stored) == norm(live) already -> already-new, no write.

SKIP reasons (counts printed; near-miss keys listed): loss (stored
carries real lines live drops — the Netflix shareholder-letter rows,
Visa's prose rows, Genuine Parts' segment prose), first-diff
(headline does not match — a different exhibit or a drifted row),
tail (added dangling/residue tail — BRK.B x3, FAST, FDX, GILD),
fragment (lowercase body start — ABNB 2024-12-31), live-table (live
is table-heavy), nocache (no cached exhibit — unverifiable live),
live-none (extraction returns None).

Only cached rows can repair; 1,312 rows have no cached exhibit and
stay as-is (they serve complete highlights on refresh). Idempotent
on re-run (repaired rows become already-new / guidance-filled).

Usage: DRY_RUN=1 .venv/bin/python scripts/batch231_repair.py
       .venv/bin/python scripts/batch231_repair.py
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
DRY = os.environ.get("DRY_RUN") == "1"


def norm(s: str) -> str:
    # Batch 241: canonicalize flattening spacing before comparing, so
    # the sweep compares content, not seed-era formatting. The legacy
    # rule only covered "•" — seed-era rows also carry "◦"/"▪"/"■"/"●"/"–"
    # bullets without the space the current extractor emits ("◦New AMD
    # ..." vs "◦ New AMD ...", 105 rows), trademark spacing ("Apple ®"
    # vs "Apple®"), and a footnote key spaced off its comma or period
    # ("$1.64, 1 up" vs "$1.64,1 up"; "basis. 1" vs "basis.1"). Each
    # rule only removes spacing; the digit / word it touches is
    # preserved, so two lines that differ in content still differ
    # after norm (the footnote-key rule only fires on a single digit
    # followed by space or end-of-line, so a year or a decimal never
    # collapses). The bullet rule is line-start-anchored; the legacy
    # mid-line "•" rule stays for flattened bullet runs.
    s = re.sub(r"(?m)^(\s*[•◦▪■●–—‣·○◆▸►])(?!\s)", r"\1 ", s)
    s = re.sub(r"\s+([®™©])", r"\1", s)
    s = re.sub(r"([,.])\s+(\d)(?=\s|$)", r"\1\2", s)
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
    if not all(d in live_set for d in s_datelines):
        return "dateline-mismatch"
    if any(x not in live_set and not is_residue(x) for x in s_lines):
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
    if len(l_lines) > 1 and l_lines[1][:1].islower():
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
                counts["S"] = counts.get("S", 0) + 1
                repaired_h.append(key)
                if not DRY:
                    con.execute(
                        "UPDATE quarterly_financials "
                        "SET press_release_highlights = ? "
                        "WHERE cik = ? AND period_end = ?",
                        (live, cik, pe),
                    )
                print(f"    S {key} {len(stored)}->{len(live)}")
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
    print(f"highlights repaired (S): {len(repaired_h)}")
    print(f"guidance filled (G): {len(repaired_g)}")
    for rk in sorted(skip_lists):
        keys = skip_lists[rk]
        if rk in ("SKIP-tail", "SKIP-fragment", "SKIP-G-table", "SKIP-too-short"):
            print(f"  {rk} ({len(keys)}): {', '.join(keys)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
