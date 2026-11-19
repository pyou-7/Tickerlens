"""Batch 280 repair: re-run the full gate chain (S4/S5/S6/S7/S8/S9/S10/
S11/S12/S13) and re-sync the rows the gates bless, plus the deliberate
DGX x4 override.

DGX's stored rows for 4 quarters are stale snapshots of the seed-era
extractor: a truncated headline (cut at the first ";" -- the guidance /
dividend clause is missing) + the "Serving ..." strategic-narrative
section only -- the long Corewell / Fresenius / WHOOP / OURA / Epic /
Haystack bullets under the "Serving Clinicians and Health Systems" /
"Serving Consumers" / "Delivering Clinical Innovations" /
"Driving Operational Excellence" headings -- with no financial-figure
bullet, no dateline, and no CEO quote at all. Two rows also carry
trailing financial-table header residue ("Three Months Ended ...",
"2025 2024 Change ...", "(dollars in millions, except per share
data)", "Reported:"). The current extractor serves the release's
leading block for these rows: full headline + 3-7 figure bullets
(revenues, reported + adjusted diluted EPS, cash from operations,
guidance) + dateline + CEO quote.

Why the seed-era extractor captured only the strategic section: in
these 4 releases the layout is headline -> a short teaser figure
bullet block -> dateline paragraph -> CEO quote -> the "Serving ..."
strategic sections -> the financial tables. The seed-era capture took
the strategic section (and, on 2 rows, ran into the table header);
the current extractor anchors on the leading block. (The 2025-09-30
raw lines show the shape: teaser bullet at line 10, dateline at 17,
CEO quote at 18, table header at 43.)

The five DGX siblings (2024-09-30, 2024-12-31, 2025-03-31,
2025-06-30, 2026-09-30) already store the live shape (stored == live
under norm) -- the consistency cross-check.

The design question is the one settled in batches 266-270 (BNY, BKR,
AMZN, COR, V), 273 (AXON), 276 (CEG) and 277 (EBAY): the highlights
card's job is the quarter's key financial figures. Live carries every
one of them; the stored rows lack them entirely. The stored rows'
unique $/% figures fall into one droppable class, pinned per row
below as an exact allowlist: the Co-Lab forward revenue expectation
("approximately $1 billion next year" -- 2025-09-30 only). The other
3 rows have no stored-only $/% figure at all. The stored rows'
unique non-figure content is operational counts (200,000 dialysis
patients, 150+ tests, 85+ biomarkers, 350,000 AI Companion uses) --
none of them EPS, revenue, margin, cash-flow, or guidance figures.

The DHI x4 and GPC x4 groups were probed in the batch-280 census and
are NOT re-synced here -- each needs its own batch. DHI x4: first-loss
lines are the dateline lede paragraphs themselves (net income / EPS
lede) -- a line-matching question, not a section swap. GPC x4: mixed
shapes (headline-only row, guidance bullets, segment narrative,
section heading) -- needs its own probe.

Open, noted not fixed: the remaining SKIP-loss rows after this batch
(largest groups DHI x4, GPC x4).

Usage: DRY_RUN=1 .venv/bin/python scripts/batch280_repair.py
       .venv/bin/python scripts/batch280_repair.py
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

# key -> (stored distinctive fragment, live distinctive fragment,
#          exact stored-only $/% figure set, exact stored-only
#          non-bullet non-headline line set).
DGX_KEYS = {
    "DGX_2025-09-30": (
        "Entered into an agreement with Corewell Health",
        "Third quarter revenues of $2.82 billion",
        {"$1 billion"},
        {
            "Three Months Ended September 30, Nine Months Ended September 30,",
            "2025 2024 Change 2025 2024 Change",
            "(dollars in millions, except per share data)",
        },
    ),
    "DGX_2025-12-31": (
        "Serving Clinicians and Health Systems",
        "Fourth quarter revenues of $2.81 billion",
        set(),
        {
            "Serving Clinicians and Health Systems",
            "Serving Consumers",
            "Delivering Clinical Innovations",
        },
    ),
    "DGX_2026-03-31": (
        "Serving Clinicians and Health Systems",
        "First quarter revenues of $2.90 billion",
        set(),
        {
            "Serving Clinicians and Health Systems",
            "Serving Consumers",
            "Delivering Diagnostic Innovations",
            "Driving Operational Excellence",
        },
    ),
    "DGX_2026-06-30": (
        "Serving Customers and Delivering Innovations",
        "Second quarter revenues of $3.04 billion",
        set(),
        {
            "Serving Customers and Delivering Innovations",
            "Driving Operational Excellence",
            "Three Months Ended June 30, Six Months Ended June 30,",
            "2026 2025 Change 2026 2025 Change",
            "(dollars in millions, except per share data)",
            "Reported:",
        },
    ),
}
DGX_SIBLINGS = (
    "DGX_2024-09-30",
    "DGX_2024-12-31",
    "DGX_2025-03-31",
    "DGX_2025-06-30",
    "DGX_2026-09-30",
)


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

    # --- Batch 280 DGX override (deliberate, gated; see docstring) ---
    # The sweep above repairs 0 (baseline: B 1146, SKIP-loss 60).
    sib_ok = []
    for sib in DGX_SIBLINGS:
        sib_pe = sib.split("_", 1)[1]
        sib_stored = con.execute(
            "SELECT q.press_release_highlights "
            "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = 'DGX' AND q.period_end = ?",
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
    for key, (s_frag, l_frag, figs_allowed, nb_allowed) in DGX_KEYS.items():
        pe = key.split("_", 1)[1]
        row = con.execute(
            "SELECT q.press_release_highlights, q.cik "
            "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = 'DGX' AND q.period_end = ?",
            (pe,),
        ).fetchone()
        stored, cik = row
        live = _live(key)
        s_lines = [ln for ln in stored.split("\n") if ln.strip()] if stored else []
        l_lines = [ln for ln in live.split("\n") if ln.strip()] if live else []
        live_bullets = [ln for ln in l_lines if ln.startswith("\u2022")]
        s_figs = set(FIG_RE.findall(stored or ""))
        l_figs = set(FIG_RE.findall(live or ""))
        s_nonbullet = [
            ln for ln in s_lines[1:] if not ln.startswith("\u2022")
        ]
        gates = {
            "stored-is-strategic-section": (
                stored is not None and s_frag in stored
            ),
            "stored-is-narrative-only": (
                stored is not None
                and "revenues of $" not in stored
                and "diluted earnings per share" not in stored
                and "SECAUCUS, N.J." not in stored
            ),
            "live-is-financial-figure-bullets": (
                live is not None
                and len(live_bullets) >= 3
                and sum(1 for b in live_bullets if "$" in b) >= 2
                and l_frag in live
                and "diluted earnings per share" in live
                and "SECAUCUS, N.J." in live
                and "Jim Davis" in live
            ),
            "headline-prefix": (
                stored is not None
                and live is not None
                and s_lines
                and l_lines
                and l_lines[0].startswith(s_lines[0])
                and s_lines[0].endswith(";")
            ),
            "stored-only-figures-allowlisted": (
                s_figs - l_figs == figs_allowed
            ),
            "stored-only-nonbullet-lines-allowlisted": (
                set(s_nonbullet) <= nb_allowed
                and len(s_nonbullet) == len(nb_allowed)
            ),
            "live-gains-figures": len(l_figs - s_figs) >= 2,
            "siblings-already-live-shape": all(sib_ok),
        }
        failed = [g for g, ok in gates.items() if not ok]
        if failed:
            print(f"  DGX-override SKIP {key}: failed gates {failed}")
            continue
        print(f"  DGX-override {'WOULD-RESYNC' if DRY else 'RESYNC'} {key} "
              f"{len(stored)}->{len(live)} (strategic section -> live leading block)")
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
