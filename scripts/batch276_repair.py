"""Batch 276 repair: re-run the full gate chain (S4/S5/S6/S7/S8/S9/S10/
S11/S12/S13) and re-sync the rows the gates bless, plus the deliberate
CEG x5 override.

CEG's stored rows for 5 quarters are stale snapshots of the seed-era
extractor: headline + the "Operational Highlights" section (the long
"Nuclear Operations" / "Natural Gas, Oil, and Renewables Operations"
bullets) plus, in 4 of the 5, the GAAP/Adjusted reconciliation table --
and every one of the 5 is truncated mid-sentence or mid-table by the
old seed-era capture (2024-09-30 ends mid-table on "30 0.10";
2024-12-31 ends mid-sentence on "in the fourth..."; 2025-03-31 ends
mid-table on "11 0.03"; 2025-09-30 ends mid-table on "(5) (0.02)";
2026-03-31 ends mid-sentence on "comparable to..."). The current
extractor serves the release's own highlights block for these rows:
headline + 3-7 short figure bullets (GAAP/adjusted EPS, guidance
range, the quarter's deals condensed) + dateline + CEO/CFO quotes.

The three CEG siblings (2025-06-30, 2025-12-31, 2026-06-30) already
store the live shape (stored == live under norm) -- the consistency
cross-check. Their live shape is the long operational bullets, not
the short lede, because those releases have no short lede at all:
their leading bullet block IS the operational highlights. The
extractor is consistent in every quarter -- it serves the release's
leading highlights block -- and the 5 stored rows are simply stale
captures of a later section, not the leading block.

The design question is the one settled in batches 266-270 (BNY, BKR,
AMZN, COR, V) and 273 (AXON): the highlights card's job is the
quarter's key financial figures. Live carries the headline EPS and
guidance figures the stored rows lack as bullets; the stored rows'
unique figures fall into three droppable classes, pinned per row
below as an exact allowlist: (a) reconciliation-table tax rates and
tax amounts (25.x%/54.x%, $72/$10/$169/$4/$32/$2) -- table residue;
(b) operational percentages from the Nuclear/Natural-Gas bullets
(capacity factor, dispatch match rate, renewable capture, EFOF) --
operating metrics, not quarterly financial figures; (c) deal figures
whose topic live covers condensed ($1.6B Crane restart capex,
$4.5B Calpine cash consideration, $900M green bond). No stored-only
figure is an EPS, revenue, or net-income figure.

The AZO x5, EBAY x5, and MU x5 groups were probed in this batch
and are NOT re-synced here -- each needs its own batch. AZO x5:
stored is SHORTER than live (664-1512 chars vs 2434-3052), i.e. the
stored rows look like truncated ledes and live the fuller lede, so
the S12 refusal is a line-matching question, not a content loss --
needs its own probe of the dateline paragraph. EBAY x5: the same
narrative-bullets-vs-figure-bullets shape as CEG/AXON (stored holds
the long eBay Live / anniversary / Depop narrative bullets, live
serves Revenue/GMV/net-income figure bullets; the 2026-09-30 sibling
is already live-shape) -- the natural next batch. MU x5: small length
deltas (~70 chars) with first-loss line "Quarterly Financial
Results" -- needs its own probe.

Usage: DRY_RUN=1 .venv/bin/python scripts/batch276_repair.py
       .venv/bin/python scripts/batch276_repair.py
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
#          exact stored-only $/% figure set).
CEG_KEYS = {
    "CEG_2024-09-30": (
        "Nuclear Operations:",
        "GAAP Net Income of $3.82 per share",
        {
            "$1.6 billion", "$10", "$72", "25.1%", "25.5%", "52.6%",
            "54.6%", "95.0%", "96.0%", "96.6%", "97.2%", "98.2%", "98.5%",
        },
    ),
    "CEG_2024-12-31": (
        "Nuclear Operations:",
        "GAAP Net Income of $2.71 per share",
        {"$4.5 billion", "$900 million", "94.8%", "95.1%"},
    ),
    "CEG_2025-03-31": (
        "Nuclear Operations:",
        "GAAP Net Income of $0.38 per share",
        {
            "$169", "$4", "25.1%", "25.5%", "54.8%", "55.3%", "93.3%",
            "96.2%", "96.3%", "97.9%",
        },
    ),
    "CEG_2025-09-30": (
        "Nuclear Operations:",
        "GAAP Net Income of $2.97 per share",
        {
            "$2", "$32", "25.5%", "25.6%", "54.6%", "54.9%", "95.0%",
            "95.5%", "96.0%", "96.8%", "98.2%",
        },
    ),
    "CEG_2026-03-31": (
        "Nuclear Operations:",
        "GAAP Net Income of $4.49 per share",
        {"4.5%", "92.3%", "94.1%", "96.2%", "96.7%"},
    ),
}
CEG_SIBLINGS = ("CEG_2025-06-30", "CEG_2025-12-31", "CEG_2026-06-30")


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

    # --- Batch 276 CEG override (deliberate, gated; see docstring) ---
    # The sweep above repairs 0 (baseline: B 1126, SKIP-loss 80).
    sib_ok = []
    for sib in CEG_SIBLINGS:
        sib_pe = sib.split("_", 1)[1]
        sib_stored = con.execute(
            "SELECT q.press_release_highlights "
            "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = 'CEG' AND q.period_end = ?",
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
    for key, (s_frag, l_frag, figs_allowed) in CEG_KEYS.items():
        pe = key.split("_", 1)[1]
        row = con.execute(
            "SELECT q.press_release_highlights, q.cik "
            "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = 'CEG' AND q.period_end = ?",
            (pe,),
        ).fetchone()
        stored, cik = row
        live = _live(key)
        s_lines = [ln for ln in stored.split("\n") if ln.strip()] if stored else []
        l_lines = [ln for ln in live.split("\n") if ln.strip()] if live else []
        live_bullets = [ln for ln in l_lines if ln.startswith("\u2022")]
        s_figs = set(FIG_RE.findall(stored or ""))
        l_figs = set(FIG_RE.findall(live or ""))
        gates = {
            "stored-is-operational-section": (
                stored is not None and s_frag in stored
            ),
            "stored-is-truncated": (
                stored is not None
                and stored.rstrip()[-1] not in ".!?"
            ),
            "live-is-lede-figure-bullets": (
                live is not None
                and len(live_bullets) >= 3
                and sum(1 for b in live_bullets if "$" in b) >= 2
                and l_frag in live
                and "per share" in live
            ),
            "same-headline": (
                stored is not None
                and live is not None
                and s_lines
                and l_lines
                and s_lines[0] == l_lines[0]
            ),
            "stored-only-figures-allowlisted": (
                s_figs - l_figs == figs_allowed
            ),
            "live-gains-figures": len(l_figs - s_figs) >= 2,
            "siblings-already-live-shape": all(sib_ok),
        }
        failed = [g for g, ok in gates.items() if not ok]
        if failed:
            print(f"  CEG-override SKIP {key}: failed gates {failed}")
            continue
        print(f"  CEG-override {'WOULD-RESYNC' if DRY else 'RESYNC'} {key} "
              f"{len(stored)}->{len(live)} (operational section -> live lede)")
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
