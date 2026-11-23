"""Batch 281 repair: re-run the full gate chain (S4/S5/S6/S7/S8/S9/S10/
S11/S12/S13) and re-sync the rows the gates bless, plus the deliberate
BRO x3 override.

Brown & Brown's releases open with a headline, a dateline paragraph,
a "For the ... quarter ended ..., the Company achieved:" lead-in,
then figure bullets (total revenues, income before income taxes,
EBITDAC - Adjusted, net income, diluted EPS), and on Q4/Q2 rows a
second year-to-date bullet block. The 3 stored rows are truncated
snapshots: each stops mid-list -- the diluted-EPS bullet is missing
on all 3, and the year-to-date block is missing on the Q4 2025 and
Q2 2026 rows -- and each carries the "achieved:" lead-in line the
current extractor drops. Live is a strict superset: every stored
bullet appears verbatim in live, the headline and dateline are
identical, and the only stored-only line is the lead-in furniture,
which carries no $/% figure.

The 6 BRO siblings (2024-09-30, 2024-12-31, 2025-03-31,
2025-06-30, 2025-09-30, 2026-09-30) already store the live shape
(stored == live under norm) -- the consistency cross-check.

No extractor change in batch 281: the re-sync is a DB repair. The
design question is the one settled in batches 266-280: the
highlights card's job is the quarter's key financial figures, and
live carries strictly more of them here at zero figure loss.

Open, noted not fixed: the remaining SKIP-loss rows after this
batch (largest groups DHI x4, GPC x4).

Usage: DRY_RUN=1 .venv/bin/python scripts/batch281_repair.py
       .venv/bin/python scripts/batch281_repair.py
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

# key -> (exact stored-only lead-in line, live distinctive fragment,
#          exact stored-only $/% figure set).
BRO_KEYS = {
    "BRO_2025-12-31": (
        "For the fourth quarter ended December 31, 2025, the Company achieved:",
        "• Diluted net income per share of $3.16",
        set(),
    ),
    "BRO_2026-03-31": (
        "For the first quarter ended March 31, 2026, the Company achieved:",
        "• Diluted net income per share of $1.06, a decrease of 7.8%",
        set(),
    ),
    "BRO_2026-06-30": (
        "For the second quarter ended June 30, 2026, the Company achieved:",
        "• Diluted net income per share of $1.90",
        set(),
    ),
}
BRO_SIBLINGS = (
    "BRO_2024-09-30",
    "BRO_2024-12-31",
    "BRO_2025-03-31",
    "BRO_2025-06-30",
    "BRO_2025-09-30",
    "BRO_2026-09-30",
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

    # --- Batch 281 BRO override (deliberate, gated; see docstring) ---
    # The sweep above repairs 0 (baseline: B 1150, SKIP-loss 56).
    sib_ok = []
    for sib in BRO_SIBLINGS:
        sib_pe = sib.split("_", 1)[1]
        sib_stored = con.execute(
            "SELECT q.press_release_highlights "
            "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = 'BRO' AND q.period_end = ?",
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
    for key, (lead_in, l_frag, figs_allowed) in BRO_KEYS.items():
        pe = key.split("_", 1)[1]
        row = con.execute(
            "SELECT q.press_release_highlights, q.cik "
            "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = 'BRO' AND q.period_end = ?",
            (pe,),
        ).fetchone()
        stored, cik = row
        live = _live(key)
        s_lines = [ln for ln in stored.split("\n") if ln.strip()] if stored else []
        l_lines = [ln for ln in live.split("\n") if ln.strip()] if live else []
        s_bullets = [ln for ln in s_lines if ln.startswith("\u2022")]
        l_bullets = [ln for ln in l_lines if ln.startswith("\u2022")]
        s_figs = set(FIG_RE.findall(stored or ""))
        l_figs = set(FIG_RE.findall(live or ""))
        s_only_lines = [ln for ln in s_lines if ln not in set(l_lines)]
        gates = {
            "stored-carries-lead-in": (
                stored is not None and lead_in in s_lines
            ),
            "stored-bullets-subset-of-live": (
                set(s_bullets) <= set(l_bullets)
                and len(s_bullets) < len(l_bullets)
            ),
            "stored-only-lines-exactly-lead-in": s_only_lines == [lead_in],
            "stored-only-figures-allowlisted": (
                s_figs - l_figs == figs_allowed
            ),
            "headline-identical": (
                s_lines and l_lines and s_lines[0] == l_lines[0]
            ),
            "live-is-full-bullet-block": (
                live is not None
                and len(l_bullets) >= 5
                and l_frag in live
                and "Diluted net income per share" in live
                and "DAYTONA BEACH, Fla." in live
            ),
            # >=1, not >=2: on BRO_2026-03-31 the gained EPS bullet's
            # $ figures already appear in the headline and its two
            # 7.8% mentions dedupe to one set entry.
            "live-gains-figures": len(l_figs - s_figs) >= 1,
            "siblings-already-live-shape": all(sib_ok),
        }
        failed = [g for g, ok in gates.items() if not ok]
        if failed:
            print(f"  BRO-override SKIP {key}: failed gates {failed}")
            continue
        print(f"  BRO-override {'WOULD-RESYNC' if DRY else 'RESYNC'} {key} "
              f"{len(stored)}->{len(live)} (truncated list -> live full block)")
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
