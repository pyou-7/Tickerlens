"""Batch 285 repair: re-run the full gate chain (S4/S5/S6/S7/S8/S9/S10/
S11/S12/S13) and re-sync the rows the gates bless, plus the deliberate
MCO x1 + CB x1 overrides (the two largest remaining zero-figure-loss
re-syncs, same class: stored truncated, live fuller, siblings already
live-shape).

MCO_2026-09-30: the stored row serves the dateline paragraph + CEO
quote + "Third Quarter 2026 Highlights" heading + only the first 2
highlight bullets (revenue, operating margin), with the seed-era
no-space bullet defect ("•MCO"). Live serves the full 6-bullet
highlight block (revenue, margin, EPS, cash flow, capital return,
guidance): headline identical, no stored $/% figure is missing from
live, and live gains 11 figures (EPS +18%/+6%, operating cash flow
$2,471M, Free Cash Flow $2,200M, $3.1B returned, $16.00-$16.50
guidance). All 8 cached MCO siblings already store the live shape.

CB_2024-06-30: the stored row carries a stray standalone "●" bullet-
marker line and is truncated mid-release (it ends after the Global
P&C premiums paragraph; the P&C underwriting income paragraph is
missing). Live serves the full block: headline identical, no stored
$/% figure is missing from live, and live gains 8 figures (P&C
underwriting income $1.42B, record $1.81B ex-catastrophe, 83.2%
combined ratio, $2.82B/$3.43B six-month figures). All 9 cached CB
siblings already store the live shape.

No extractor change in batch 285: the re-syncs are DB repairs. The
design question is the one settled in batches 266-284: the
highlights card's job is the quarter's key financial figures, and
live carries strictly more of them here at zero figure loss. The
stored rows' unique content is a CEO quote + dateline (MCO) and a
stray bullet marker (CB) — none of it EPS, revenue, margin, or
cash-flow figures.

Open, noted not fixed: the remaining SKIP-loss rows after this batch
(largest groups DHI x4, GPC x4, APH x3, BLK x3, CSX x3, DASH x3,
EQIX x3 — DHI/GPC/APH/BLK lose stored figures on re-sync; CSX x3
probed in batch 285: two Q4 rows gain figures at zero loss but the
2026-06-30 row's live is shorter than stored (drops the volume
paragraph + CEO quote), so CSX stays held as a group; remaining
zero-figure-loss candidates: CLX x2 (+1 each), DG x1 (headline
defect, equal figures), EXPE x1 (equal figures), SPG 2025-09-30
(equal); SPG 2024-09-30 loses figures and stays held).

Usage: DRY_RUN=1 .venv/bin/python scripts/batch285_repair.py
       .venv/bin/python scripts/batch285_repair.py
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

MCO_KEY = "MCO_2026-09-30"
MCO_SIBLINGS = (
    "MCO_2024-09-30",
    "MCO_2024-12-31",
    "MCO_2025-03-31",
    "MCO_2025-06-30",
    "MCO_2025-09-30",
    "MCO_2025-12-31",
    "MCO_2026-03-31",
    "MCO_2026-06-30",
)
CB_KEY = "CB_2024-06-30"
CB_SIBLINGS = (
    "CB_2024-09-30",
    "CB_2024-12-31",
    "CB_2025-03-31",
    "CB_2025-06-30",
    "CB_2025-09-30",
    "CB_2025-12-31",
    "CB_2026-03-31",
    "CB_2026-06-30",
    "CB_2026-09-30",
)


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

    # --- Batch 285 overrides (deliberate, gated; see docstring) ---
    # The sweep above repairs 0 (baseline: B 1160, SKIP-loss 46).
    overrides = []

    # MCO_2026-09-30: stored dateline + CEO quote + 2 bullets -> live
    # full 6-bullet highlight block.
    mco_sib_ok = _siblings_live_shape(con, "MCO", MCO_SIBLINGS)
    pe = MCO_KEY.split("_", 1)[1]
    stored, cik = _fetch(con, "MCO", pe)
    live = _live(MCO_KEY)
    s_lines = [ln for ln in stored.split("\n") if ln.strip()] if stored else []
    l_lines = [ln for ln in live.split("\n") if ln.strip()] if live else []
    s_bullets = [ln for ln in s_lines if ln.startswith("•")]
    l_bullets = [ln for ln in l_lines if ln.startswith("•")]
    s_figs = set(FIG_RE.findall(stored or ""))
    l_figs = set(FIG_RE.findall(live or ""))
    gates = {
        "headline-identical": (
            s_lines and l_lines and s_lines[0] == l_lines[0]
        ),
        "stored-is-dateline-quote-truncated": (
            stored is not None
            and "NEW YORK, NY - October 21, 2026" in stored
            and "Moody’s delivered another quarter" in stored
            and "Third Quarter 2026 Highlights" in stored
            and len(s_bullets) == 2
            and "Diluted EPS" not in stored
        ),
        "stored-bullet-spacing-defect": (
            stored is not None and "•MCO" in stored
            and "•MCO" not in (live or "")
        ),
        "stored-only-figures-allowlisted": (s_figs - l_figs == set()),
        "live-is-full-highlight-block": (
            live is not None
            and "• MCO revenue of $2.0 billion" in live
            and "• Diluted EPS and Adjusted Diluted EPS1 increased 18% and 6%" in live
            and "operating cash flow was $2,471 million" in live
            and "Diluted EPS range of $16.00 to $16.50" in live
            and len(l_lines) == 7
            and len(l_bullets) == 6
        ),
        "live-gains-figures": len(l_figs - s_figs) >= 10,
        "siblings-already-live-shape": all(mco_sib_ok),
    }
    overrides.append((MCO_KEY, "MCO", pe, stored, cik, live, gates))

    # CB_2024-06-30: stored stray "●" line + truncated -> live full block.
    cb_sib_ok = _siblings_live_shape(con, "CB", CB_SIBLINGS)
    pe = CB_KEY.split("_", 1)[1]
    stored, cik = _fetch(con, "CB", pe)
    live = _live(CB_KEY)
    s_lines = [ln for ln in stored.split("\n") if ln.strip()] if stored else []
    l_lines = [ln for ln in live.split("\n") if ln.strip()] if live else []
    s_figs = set(FIG_RE.findall(stored or ""))
    l_figs = set(FIG_RE.findall(live or ""))
    gates = {
        "headline-identical": (
            s_lines and l_lines and s_lines[0] == l_lines[0]
        ),
        "stored-has-stray-bullet-line": (
            "●" in s_lines and "●" not in l_lines
        ),
        "stored-is-truncated": (
            stored is not None
            and "P&C underwriting income was $1.42 billion" not in stored
            and "Both were records." not in stored
        ),
        "stored-only-figures-allowlisted": (s_figs - l_figs == set()),
        "live-is-full-block": (
            live is not None
            and "P&C underwriting income was $1.42 billion" in live
            and "record low combined ratio of 83.2%" in live
            and "Both were records." in live
            and len(l_lines) == 9
        ),
        "live-gains-figures": len(l_figs - s_figs) >= 8,
        "siblings-already-live-shape": all(cb_sib_ok),
    }
    overrides.append((CB_KEY, "CB", pe, stored, cik, live, gates))

    for key, ticker, pe, stored, cik, live, gates in overrides:
        failed = [g for g, ok in gates.items() if not ok]
        if failed:
            print(f"  batch285-override SKIP {key}: failed gates {failed}")
            continue
        print(f"  batch285-override {'WOULD-RESYNC' if DRY else 'RESYNC'} {key} "
              f"{len(stored)}->{len(live)} (stored truncated -> live full block)")
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
