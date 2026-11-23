"""Batch 279 repair: re-run the full gate chain (S4/S5/S6/S7/S8/S9/S10/
S11/S12/S13) and re-sync the rows the gates bless, plus the deliberate
AZO x5 override.

AZO's 5 SKIP-loss rows are stale snapshots of the seed-era extractor.
The releases open with a headline carrying the comp-sales figures
("Total Company Same Store Sales Increase X%; Domestic Same Store
Sales Increase Y%"), then a dateline lede paragraph that ends with
"Same store sales ... are as follows:" (one Q4 row phrases it "are
computed on a 16-week and 52-week basis and are as follows:") and a
same-store-sales table.
The seed-era extractor kept the full lede (table-intro sentence
included) plus the table flattened into lines; the current extractor
serves the clean shape: the lede cut at the sentence boundary, the
table dropped, and the full narrative set (gross profit, operating
profit, buyback, inventory, CEO quote) instead:

    stored: headline + lede-with-table-intro + table lines
            (+ 2 narrative paragraphs on 4 of the 5 rows)
    live:   headline + clean lede + 6-7 narrative paragraphs

The 4 other AZO siblings (2024-08-31, 2024-11-23, 2025-02-15,
2025-11-22) already store the live shape (stored == live under norm)
even though their releases have the same comp table -- the consistency
cross-check. The headline preserves the headline comp figures (total
+ domestic) in live.

One acknowledged loss, pinned by the gates: the 2025-05-10 row's
stored table carries 3 data rows the live shape drops --

    Domestic 5.0 % 5.0 % 2.4 % 2.4 %
    International (9.2 %) 8.1 % (5.7 %) 10.4 %
    Total Company 3.2 % 5.4 % 1.4 % 3.4 %

i.e. the international and 36-week comp breakdowns. The total (5.4%)
and domestic (5.0%) figures survive in the headline, and the other
4 rows' stored tables carry no data rows at all (headers + footnote
only), so the stored shape is strictly worse there. The flattened
table is unreadable as highlights and the gate chain deliberately
keeps tables out of highlights (S12's added-table / live-table
policing), so the re-sync trades the detailed breakdown for the full
narrative set, matching the 4 siblings.

No extractor change: the current extractor already serves the clean
shape; the defect is purely the stored seed-era snapshots.

Usage: DRY_RUN=1 .venv/bin/python scripts/batch279_repair.py
       .venv/bin/python scripts/batch279_repair.py
"""
import os
import re
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import norm
from batch242_repair import sweep_gate_s4
from batch244_repair import classify_s5
from batch247_repair import sweep_gate_s6
from batch248_repair import sweep_gate_s7
from batch250_repair import sweep_gate_s8
from batch251_repair import sweep_gate_s9
from batch253_repair import sweep_gate_s10
from batch254_repair import sweep_gate_s11
from batch255_repair import sweep_gate_s12
from batch261_repair import sweep_gate_s13
from tickerlens.data import filings as F

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"
DRY = os.environ.get("DRY_RUN") == "1"

FIG_RE = re.compile(r"\$[\d,]+(?:\.\d+)?(?:\s*(?:billion|million|trillion))?|\d+(?:\.\d+)?%")

AZO_KEYS = [
    "AZO_2025-05-10",
    "AZO_2025-08-30",
    "AZO_2026-02-14",
    "AZO_2026-05-09",
    "AZO_2026-08-29",
]
AZO_SIBLINGS = (
    "AZO_2024-08-31",
    "AZO_2024-11-23",
    "AZO_2025-02-15",
    "AZO_2025-11-22",
)
TABLE_INTRO = (" Same store sales, or sales for our domestic and "
               "international stores open at least one year, are as follows:")
# Q4 rows vary the intro: 2025-08-30 says "are computed on a 16-week
# and 52-week basis and are as follows:" (2026-08-29 uses the plain
# form above).
TABLE_INTRO_Q4 = (" Same store sales, or sales for our domestic and "
                  "international stores open at least one year, are "
                  "computed on a 16-week and 52-week basis and are as follows:")
TABLE_INTROS = (TABLE_INTRO, TABLE_INTRO_Q4)
# Exact stored-only lines allowed: table chrome, plus (2025-05-10
# only) the 3 comp data rows.
AZO_TABLE_CHROME = {
    "Constant Currency Constant Currency",
    "12 Weeks 12 Weeks* 24 Weeks 24 Weeks*",
    "12 Weeks 12 Weeks* 36 Weeks 36 Weeks*",
    "16 Weeks 16 Weeks* 52 Weeks 52 Weeks*",
    "* Excludes impacts from fluctuations of foreign exchange rates.",
}
AZO_COMP_DATA_ROWS = {
    "Domestic 5.0 % 5.0 % 2.4 % 2.4 %",
    "International (9.2 %) 8.1 % (5.7 %) 10.4 %",
    "Total Company 3.2 % 5.4 % 1.4 % 3.4 %",
}


def _live(key):
    return F.extract_press_release_highlights(
        open(f"{CACHE}/{key}.html", encoding="utf-8").read()
    )


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

    def _resync(key, stored, live, cik, pe):
        repaired.append(key)
        if not DRY:
            con.execute(
                "UPDATE quarterly_financials "
                "SET press_release_highlights = ? "
                "WHERE cik = ? AND period_end = ?",
                (live, cik, pe),
            )
        print(f"    {key} {len(stored)}->{len(live)}")

    for t, pe, stored, cik in rows:
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            counts["SKIP-nocache"] = counts.get("SKIP-nocache", 0) + 1
            continue
        html = open(path, encoding="utf-8").read()
        live = F.extract_press_release_highlights(html)
        if live is None:
            counts["SKIP-live-none"] = counts.get("SKIP-live-none", 0) + 1
            continue
        if norm(stored) == norm(live):
            counts["B"] = counts.get("B", 0) + 1
            continue
        if sweep_gate_s4(stored, live) is None:
            counts["S4"] = counts.get("S4", 0) + 1
            _resync(key, stored, live, cik, pe)
            continue
        cls5 = classify_s5(stored, live)
        if cls5 is not None:
            rk = f"S5-{cls5}"
            counts[rk] = counts.get(rk, 0) + 1
            skip_lists.setdefault(rk, []).append(key)
            continue
        r6 = sweep_gate_s6(stored, live, html)
        if r6 is None:
            counts["S6"] = counts.get("S6", 0) + 1
            continue
        r7 = sweep_gate_s7(stored, live)
        if r7 is None:
            counts["S7"] = counts.get("S7", 0) + 1
            continue
        r8 = sweep_gate_s8(stored, live, html)
        if r8 is None:
            counts["S8"] = counts.get("S8", 0) + 1
            continue
        r9 = sweep_gate_s9(stored, live, html)
        if r9 is None:
            counts["S9"] = counts.get("S9", 0) + 1
            _resync(key, stored, live, cik, pe)
            continue
        r10 = sweep_gate_s10(stored, live)
        if r10 is None:
            counts["S10"] = counts.get("S10", 0) + 1
            _resync(key, stored, live, cik, pe)
            continue
        r11 = sweep_gate_s11(stored, live)
        if r11 is None:
            counts["S11"] = counts.get("S11", 0) + 1
            _resync(key, stored, live, cik, pe)
            continue
        r12 = sweep_gate_s12(stored, live)
        if r12 is None:
            counts["S12"] = counts.get("S12", 0) + 1
            continue
        r13 = sweep_gate_s13(stored, live, html)
        if r13 is None:
            counts["S13"] = counts.get("S13", 0) + 1
            _resync(key, stored, live, cik, pe)
            continue
        rk = f"SKIP-{r12}"
        counts[rk] = counts.get(rk, 0) + 1
        skip_lists.setdefault(rk, []).append(key)

    # --- Batch 279 AZO override (deliberate, gated; see docstring) ---
    sib_ok = []
    for sib in AZO_SIBLINGS:
        sib_pe = sib.split("_", 1)[1]
        sib_stored = con.execute(
            "SELECT q.press_release_highlights "
            "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = 'AZO' AND q.period_end = ?",
            (sib_pe,),
        ).fetchone()[0]
        sib_live = _live(sib)
        ok = (
            sib_stored is not None
            and sib_live is not None
            and norm(sib_stored) == norm(sib_live)
        )
        sib_ok.append(ok)
        print(f"  sibling {sib} already-live-shape: {ok}")
    for key in AZO_KEYS:
        pe = key.split("_", 1)[1]
        row = con.execute(
            "SELECT q.press_release_highlights, q.cik "
            "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = 'AZO' AND q.period_end = ?",
            (pe,),
        ).fetchone()
        stored, cik = row
        live = _live(key)
        s_lines = [ln for ln in stored.split("\n") if ln.strip()] if stored else []
        l_lines = [ln for ln in live.split("\n") if ln.strip()] if live else []
        l_set = set(l_lines)
        # Stored lede: the line starting with the dateline; live lede is
        # its strict prefix, the remainder being the table-intro sentence.
        s_lede = next((ln for ln in s_lines if ln.startswith("MEMPHIS, Tenn.")), None)
        l_lede = next((ln for ln in l_lines if ln.startswith("MEMPHIS, Tenn.")), None)
        stored_only = [ln for ln in s_lines if ln not in l_set]
        non_lede_stored_only = [ln for ln in stored_only if ln != s_lede]
        comp_rows_present = [ln for ln in non_lede_stored_only
                             if ln in AZO_COMP_DATA_ROWS]
        # Figures in stored-only lines outside the (allowed) comp data
        # rows and outside the lede trailer must be empty.
        fig_lines = [ln for ln in non_lede_stored_only
                     if ln not in AZO_COMP_DATA_ROWS]
        figs_outside = set()
        for ln in fig_lines:
            figs_outside |= set(FIG_RE.findall(ln))
        narrative_stored = [ln for ln in s_lines
                            if ln != s_lede and ln not in AZO_TABLE_CHROME
                            and ln not in AZO_COMP_DATA_ROWS]
        gates = {
            "same-headline": (
                stored is not None and live is not None and s_lines
                and l_lines and s_lines[0] == l_lines[0]
            ),
            "headline-carries-comps": (
                s_lines and "Total Company Same Store Sales Increase" in s_lines[0]
                and "Domestic Same Store Sales Increase" in s_lines[0]
            ),
            "stored-lede-is-live-lede-plus-table-intro": (
                s_lede is not None and l_lede is not None
                and any(s_lede == l_lede + intro for intro in TABLE_INTROS)
            ),
            "live-has-no-table-chrome": (
                live is not None
                and "Constant Currency" not in live
                and "are as follows:" not in live
            ),
            "stored-only-lines-are-table-chrome-or-comp-rows": (
                stored is not None and live is not None
                and set(non_lede_stored_only) <= (
                    AZO_TABLE_CHROME | AZO_COMP_DATA_ROWS)
            ),
            "comp-data-rows-only-2025-05-10": (
                not comp_rows_present or key == "AZO_2025-05-10"
            ),
            "no-stored-only-figures-outside-comp-rows": figs_outside == set(),
            "stored-narrative-lines-preserved-in-live": all(
                ln in l_set for ln in narrative_stored
            ),
            "siblings-already-live-shape": all(sib_ok),
        }
        failed = [g for g, ok in gates.items() if not ok]
        if failed:
            print(f"  AZO-override SKIP {key}: failed gates {failed}")
            continue
        print(f"  AZO-override {'WOULD-RESYNC' if DRY else 'RESYNC'} {key} "
              f"{len(stored)}->{len(live)} (seed-era lede + flattened comp "
              f"table -> live narrative set)")
        if not DRY:
            con.execute(
                "UPDATE quarterly_financials "
                "SET press_release_highlights = ? "
                "WHERE cik = ? AND period_end = ?",
                (live, cik, pe),
            )
            repaired.append(f"{key} (override)")
            check = con.execute(
                "SELECT press_release_highlights FROM quarterly_financials "
                "WHERE cik = ? AND period_end = ?",
                (cik, pe),
            ).fetchone()[0]
            assert check == live, f"post-write mismatch for {key}"
            print(f"    {key} DB-verified byte-identical to live")
    if not DRY:
        con.commit()
    print(f"\nDRY_RUN={DRY} counts: {counts}")
    print(f"repaired: {len(repaired)}: {', '.join(repaired)}")
    for rk in sorted(skip_lists):
        keys = skip_lists[rk]
        if rk == "SKIP-loss":
            print(f"  {rk} ({len(keys)}): {', '.join(keys)}")
        else:
            print(f"  {rk} ({len(keys)})")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
