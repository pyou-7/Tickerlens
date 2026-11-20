"""Batch 284 repair: re-run the full gate chain (S4/S5/S6/S7/S8/S9/S10/
S11/S12/S13) and re-sync the rows the gates bless, plus the deliberate
ENPH x2 override.

Enphase releases carry a financial figure block (revenue, margins,
operating/net income, EPS, cash flow) followed by a "Recent Business
Highlights" section of dated operational announcements. The 2 stored
rows serve ONLY the operational announcements — every bullet is a
dated "•On <date>, Enphase Energy announced..." line — and carry zero
$/% figures; they also carry the seed-era no-space bullet defect
("•On" for "• On"). Live serves the financial figure block (the same
shape all 8 cached ENPH siblings already store): headline identical,
no stored $/% figure is missing from live (stored has none), and live
gains 15 figures (2026-06-30: $291.9M revenue, 60.0% GAAP margin,
$0.27/$0.46 EPS) and 12 figures (2026-09-30: $293.3M revenue, 43.3%
margin, $0.17/$0.41 EPS).

No extractor change in batch 284: the re-sync is a DB repair. The
design question is the one settled in batches 266-283 (DGX batch 280
is the closest precedent — a stored strategic-narrative section
replaced by the live figure block): the highlights card's job is the
quarter's key financial figures, and live carries strictly more of
them here at zero figure loss (the stored rows have no figures at
all). The stored rows' unique content is dated product/operational
announcements — none of them EPS, revenue, margin, or cash-flow
figures.

Open, noted not fixed: the remaining SKIP-loss rows after this batch
(largest groups DHI x4, GPC x4, APH x3, BLK x3, CSX x3, DASH x3,
EQIX x3 — DHI/GPC/APH/BLK lose stored figures on re-sync; CSX needs
its own probe; remaining zero-figure-loss candidates: CB x1, CLX x2,
DG x1, EXPE x1, MCO x1, SPG 2025-09-30).

Usage: DRY_RUN=1 .venv/bin/python scripts/batch284_repair.py
       .venv/bin/python scripts/batch284_repair.py
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

# key -> (live distinctive revenue bullet fragment,
#          live distinctive EPS bullet fragment,
#          exact stored-only $/% figure set,
#          exact live line count).
ENPH_KEYS = {
    "ENPH_2026-06-30": (
        "• Revenue of $291.9 million",
        "• GAAP diluted earnings per share of $0.27; non-GAAP diluted earnings per share of $0.46",
        set(),
        11,
    ),
    "ENPH_2026-09-30": (
        "• Revenue of $293.3 million",
        "• GAAP diluted earnings per share (EPS) of $0.17; non-GAAP diluted EPS of $0.41",
        set(),
        11,
    ),
}
ENPH_SIBLINGS = (
    "ENPH_2024-06-30",
    "ENPH_2024-09-30",
    "ENPH_2024-12-31",
    "ENPH_2025-03-31",
    "ENPH_2025-06-30",
    "ENPH_2025-09-30",
    "ENPH_2025-12-31",
    "ENPH_2026-03-31",
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

    # --- Batch 284 ENPH override (deliberate, gated; see docstring) ---
    # The sweep above repairs 0 (baseline: B 1158, SKIP-loss 48).
    sib_ok = []
    for sib in ENPH_SIBLINGS:
        sib_pe = sib.split("_", 1)[1]
        sib_stored = con.execute(
            "SELECT q.press_release_highlights "
            "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = 'ENPH' AND q.period_end = ?",
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
    for key, (rev_frag, eps_frag, figs_allowed, n_live_lines) in ENPH_KEYS.items():
        pe = key.split("_", 1)[1]
        row = con.execute(
            "SELECT q.press_release_highlights, q.cik "
            "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = 'ENPH' AND q.period_end = ?",
            (pe,),
        ).fetchone()
        stored, cik = row
        live = _live(key)
        s_lines = [ln for ln in stored.split("\n") if ln.strip()] if stored else []
        l_lines = [ln for ln in live.split("\n") if ln.strip()] if live else []
        s_bullets = [ln for ln in s_lines if ln.startswith("•")]
        s_figs = set(FIG_RE.findall(stored or ""))
        l_figs = set(FIG_RE.findall(live or ""))
        gates = {
            "headline-identical": (
                s_lines and l_lines and s_lines[0] == l_lines[0]
            ),
            "stored-is-operational-announcements-only": (
                stored is not None
                and len(s_bullets) >= 10
                and all(b.startswith("•On ") for b in s_bullets)
                and "Revenue of $" not in stored
                and "diluted earnings per share" not in stored
            ),
            "stored-has-zero-figures": len(s_figs) == 0,
            "stored-bullet-spacing-defect": (
                stored is not None and "•On" in stored
                and "•On" not in (live or "")
            ),
            "stored-only-figures-allowlisted": (
                s_figs - l_figs == figs_allowed
            ),
            "live-is-financial-figure-block": (
                live is not None
                and rev_frag in live
                and eps_frag in live
                and "Our revenue and earnings" in live
                and len(l_lines) == n_live_lines
            ),
            "live-gains-figures": len(l_figs - s_figs) >= 10,
            "siblings-already-live-shape": all(sib_ok),
        }
        failed = [g for g, ok in gates.items() if not ok]
        if failed:
            print(f"  ENPH-override SKIP {key}: failed gates {failed}")
            continue
        print(f"  ENPH-override {'WOULD-RESYNC' if DRY else 'RESYNC'} {key} "
              f"{len(stored)}->{len(live)} (operational announcements -> live financial block)")
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
