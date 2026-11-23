"""Batch 287 repair: re-run the full gate chain (S4/S5/S6/S7/S8/S9/S10/
S11/S12/S13) and re-sync the rows the gates bless, plus the deliberate
BLK x3 + CSCO x1 overrides (wrong-block stored highlights replaced by
the live headline-figures blocks; siblings already live-shape).

BLK_2024-09-30 + BLK_2025-06-30 + BLK_2025-09-30: the stored rows serve
the release's expense-detail MD&A bullets (employee compensation,
sales/asset/account expense, G&A, amortization deltas + footnote).
Live serves the headline summary block (net inflows, AUM, revenue and
operating-income growth): headline identical, live gains the quarter's
headline figures, and the stored rows' unique $ figures are expense-
detail deltas (allowlisted below) — none of them EPS, revenue, AUM, or
inflow headlines. All 5 cached BLK siblings already store the live
shape (BLK_2026-09-30 has no cache).

CSCO_2025-10-25: the stored row serves the balance-sheet section
(cash/investments, RPO, deferred revenue, capital allocation,
acquisitions) and carries no revenue, EPS, or margin figure at all.
Live serves the earnings highlights (revenue $14.9B, GAAP/non-GAAP
EPS, gross/operating margins, product orders): headline identical,
live gains the quarter's headline figures, and the stored row's unique
$/% figures are balance-sheet / capital-allocation figures
(allowlisted below). All 7 cached CSCO siblings already store the
live shape.

No extractor change in batch 287: the re-syncs are DB repairs. The
design question is the one settled in batches 266-286: the highlights
card's job is the quarter's key financial figures, and live carries
strictly more of them here. The stored rows' unique content is
expense-detail deltas (BLK) and balance-sheet/capital-allocation
figures (CSCO) — none of it EPS, revenue, margin, AUM, or inflow
headlines.

Open, noted not fixed: the remaining SKIP-loss rows after this batch
(largest groups DHI x4, GPC x4, APH x3, CSX x3, DASH x3, EQIX x3 —
all lose stored figures on re-sync; DASH x3 + EQIX x3 held as
trade-offs since batch 286; CSX x3 held as a group since batch 285;
SPG 2024-09-30 held). META_2025-09-30 figure-probed this batch: the
stored row is flattened table residue carrying EPS/net income the
live bullets drop — held as a trade-off (needs an extractor fix, not
a re-sync). DHI x4 + GPC x4 + APH x3 figure-probed this batch: stored
rows are the live block plus guidance/body tails — held (re-sync
loses guidance figures).

Usage: DRY_RUN=1 .venv/bin/python scripts/batch287_repair.py
       .venv/bin/python scripts/batch287_repair.py
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

BLK_SIBLINGS = (
    "BLK_2024-12-31",
    "BLK_2025-03-31",
    "BLK_2025-12-31",
    "BLK_2026-03-31",
    "BLK_2026-06-30",
)
CSCO_SIBLINGS = (
    "CSCO_2024-10-26",
    "CSCO_2025-01-25",
    "CSCO_2025-04-26",
    "CSCO_2025-07-26",
    "CSCO_2026-01-24",
    "CSCO_2026-04-25",
    "CSCO_2026-07-25",
)

# Stored-only $/% figures allowed to be dropped by each override:
# expense-detail deltas (BLK) and balance-sheet / capital-allocation
# figures (CSCO). None is an EPS, revenue, margin, AUM, or inflow
# headline figure.
BLK_2024_ALLOWLIST = {
    "$149 million", "$154 million", "$155 million", "$167 million",
    "$224 million", "$318 million", "$349 million", "$4 million",
    "$8 million",
}
BLK_2025Q2_ALLOWLIST = {
    "$134 million", "$155 million", "$20 million", "$22 million",
    "$23 million", "$261 million", "$39 million", "$54 million",
    "$98 million",
}
BLK_2025Q3_ALLOWLIST = {
    "$116 million", "$164 million", "$200 million", "$220 million",
    "$39 million", "$50 million", "$593 million", "$779 million",
    "$93 million", "$99 million",
}
CSCO_ALLOWLIST = {
    "$0.41", "$1.6 billion", "$11.8 billion", "$12.2 billion",
    "$15.7 billion", "$16.1 billion", "$2.0 billion", "$28.0 billion",
    "$3.6 billion", "$42.9 billion", "$68.28", "1%", "2%", "4%", "7%",
}


def _live(key):
    return F.extract_press_release_highlights(
        open(f"{CACHE}/{key}.html", encoding="utf-8").read()
    )


def _siblings_live_shape(con, ticker, siblings):
    ok_all = []
    for sib in siblings:
        sib_pe = sib.split("_", 1)[1]
        sib_stored = con.execute(
            "SELECT q.press_release_highlights "
            "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = ? AND q.period_end = ?",
            (ticker, sib_pe),
        ).fetchone()[0]
        sib_live = _live(sib)
        ok = (
            sib_stored is not None
            and sib_live is not None
            and norm(sib_stored) == norm(sib_live)
        )
        ok_all.append(ok)
        print(f"  sibling {sib} already-live-shape: {ok}")
    return ok_all


def _fetch(con, ticker, pe):
    return con.execute(
        "SELECT q.press_release_highlights, q.cik "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE c.ticker = ? AND q.period_end = ?",
        (ticker, pe),
    ).fetchone()


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

    # --- Batch 287 overrides (deliberate, gated; see docstring) ---
    # The sweep above repairs 0 (baseline: B 1167, SKIP-loss 39).
    overrides = []

    # BLK_2024-09-30: stored expense-detail bullets -> live summary.
    blk_sib_ok = _siblings_live_shape(con, "BLK", BLK_SIBLINGS)
    pe = "2024-09-30"
    stored, cik = _fetch(con, "BLK", pe)
    live = _live("BLK_2024-09-30")
    s_lines = [ln for ln in stored.split("\n") if ln.strip()] if stored else []
    l_lines = [ln for ln in live.split("\n") if ln.strip()] if live else []
    s_figs = set(FIG_RE.findall(stored or ""))
    l_figs = set(FIG_RE.findall(live or ""))
    gates = {
        "headline-identical": (
            s_lines and l_lines and s_lines[0] == l_lines[0]
        ),
        "stored-is-expense-detail": (
            stored is not None
            and "Investment advisory and administration fees" in stored
            and "Securities lending revenue of $149 million" in stored
            and "Investment advisory and administration fees" not in (live or "")
        ),
        "stored-lacks-inflow-headlines": (
            stored is not None
            and "$360 billion" not in stored
            and "$221 billion" not in stored
        ),
        "stored-only-figures-allowlisted": (
            (s_figs - l_figs) <= BLK_2024_ALLOWLIST
        ),
        "live-is-summary-block": (
            live is not None
            and "$360 billion of year-to-date total net inflows" in live
            and "Record $221 billion of quarterly total net inflows" in live
            and "$11.5 trillion in AUM" in live
            and len(l_lines) == 7
        ),
        "live-gains-figures": len(l_figs - s_figs) >= 1,
        "siblings-already-live-shape": all(blk_sib_ok),
    }
    overrides.append(("BLK_2024-09-30", "BLK", pe, stored, cik, live, gates))

    # BLK_2025-06-30: stored expense-detail bullets -> live summary.
    pe = "2025-06-30"
    stored, cik = _fetch(con, "BLK", pe)
    live = _live("BLK_2025-06-30")
    s_lines = [ln for ln in stored.split("\n") if ln.strip()] if stored else []
    l_lines = [ln for ln in live.split("\n") if ln.strip()] if live else []
    s_figs = set(FIG_RE.findall(stored or ""))
    l_figs = set(FIG_RE.findall(live or ""))
    gates = {
        "headline-identical": (
            s_lines and l_lines and s_lines[0] == l_lines[0]
        ),
        "stored-is-expense-detail": (
            stored is not None
            and "Employee compensation and benefits expense increased $261 million" in stored
            and "Employee compensation and benefits expense increased $261 million" not in (live or "")
        ),
        "stored-lacks-inflow-headlines": (
            stored is not None
            and "$152 billion" not in stored
            and "$68 billion" not in stored
        ),
        "stored-only-figures-allowlisted": (
            (s_figs - l_figs) <= BLK_2025Q2_ALLOWLIST
        ),
        "live-is-summary-block": (
            live is not None
            and "$152 billion of year-to-date total net inflows" in live
            and "$68 billion of quarterly total net inflows" in live
            and "13% increase in revenue year-over-year" in live
            and len(l_lines) == 7
        ),
        "live-gains-figures": len(l_figs - s_figs) >= 1,
        "siblings-already-live-shape": all(blk_sib_ok),
    }
    overrides.append(("BLK_2025-06-30", "BLK", pe, stored, cik, live, gates))

    # BLK_2025-09-30: stored expense-detail bullets -> live summary.
    pe = "2025-09-30"
    stored, cik = _fetch(con, "BLK", pe)
    live = _live("BLK_2025-09-30")
    s_lines = [ln for ln in stored.split("\n") if ln.strip()] if stored else []
    l_lines = [ln for ln in live.split("\n") if ln.strip()] if live else []
    s_figs = set(FIG_RE.findall(stored or ""))
    l_figs = set(FIG_RE.findall(live or ""))
    gates = {
        "headline-identical": (
            s_lines and l_lines and s_lines[0] == l_lines[0]
        ),
        "stored-is-expense-detail": (
            stored is not None
            and "Employee compensation and benefits expense increased $779 million" in stored
            and "Employee compensation and benefits expense increased $779 million" not in (live or "")
        ),
        "stored-lacks-inflow-headlines": (
            stored is not None and "$205 billion" not in stored
        ),
        "stored-only-figures-allowlisted": (
            (s_figs - l_figs) <= BLK_2025Q3_ALLOWLIST
        ),
        "live-is-summary-block": (
            live is not None
            and "$205 billion of quarterly total net inflows" in live
            and "10% annualized organic base fee growth" in live
            and "25% increase in revenue year-over-year" in live
            and len(l_lines) == 7
        ),
        "live-gains-figures": len(l_figs - s_figs) >= 1,
        "siblings-already-live-shape": all(blk_sib_ok),
    }
    overrides.append(("BLK_2025-09-30", "BLK", pe, stored, cik, live, gates))

    # CSCO_2025-10-25: stored balance-sheet section -> live earnings
    # highlights.
    csco_sib_ok = _siblings_live_shape(con, "CSCO", CSCO_SIBLINGS)
    pe = "2025-10-25"
    stored, cik = _fetch(con, "CSCO", pe)
    live = _live("CSCO_2025-10-25")
    s_lines = [ln for ln in stored.split("\n") if ln.strip()] if stored else []
    l_lines = [ln for ln in live.split("\n") if ln.strip()] if live else []
    s_figs = set(FIG_RE.findall(stored or ""))
    l_figs = set(FIG_RE.findall(live or ""))
    gates = {
        "headline-identical": (
            s_lines and l_lines and s_lines[0] == l_lines[0]
        ),
        "stored-is-balance-sheet-section": (
            stored is not None
            and "Cash and Cash Equivalents and Investments" in stored
            and "Remaining Performance Obligations (RPO)" in stored
            and "Deferred Revenue" in stored
            and "Cash and Cash Equivalents and Investments" not in (live or "")
        ),
        "stored-lacks-revenue-eps": (
            stored is not None
            and "Revenue of $14.9 billion" not in stored
            and "GAAP EPS of $0.72" not in stored
        ),
        "stored-only-figures-allowlisted": (
            (s_figs - l_figs) <= CSCO_ALLOWLIST
        ),
        "live-is-earnings-highlights": (
            live is not None
            and "Revenue of $14.9 billion, up 8% year over year" in live
            and "GAAP EPS of $0.72" in live
            and "Non-GAAP EPS of $1.00" in live
            and "GAAP gross margin of 65.5%" in live
            and len(l_lines) == 9
        ),
        "live-gains-figures": len(l_figs - s_figs) >= 1,
        "siblings-already-live-shape": all(csco_sib_ok),
    }
    overrides.append(("CSCO_2025-10-25", "CSCO", pe, stored, cik, live, gates))

    for key, ticker, pe, stored, cik, live, gates in overrides:
        failed = [g for g, ok in gates.items() if not ok]
        if failed:
            print(f"  batch287-override SKIP {key}: failed gates {failed}")
            continue
        print(f"  batch287-override {'WOULD-RESYNC' if DRY else 'RESYNC'} {key} "
              f"{len(stored)}->{len(live)} (stored wrong-block -> live headline figures)")
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
