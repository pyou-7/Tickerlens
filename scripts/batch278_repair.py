"""Batch 278 repair: re-run the full gate chain (S4/S5/S6/S7/S8/S9/S10/
S11/S12/S13) and re-sync the rows the gates bless, plus the deliberate
MU x5 override.

MU's 5 SKIP-loss rows are stale snapshots of the seed-era extractor: the
figure bullets are byte-identical to live modulo a missing space after
the bullet glyph (stored "•Revenue of ..." vs live "• Revenue of ..."),
and the stored rows carry a trailing table-header residue the current
extractor stops before:

    Quarterly Financial Results
    (in millions, except per share amounts) GAAP(1)
    Non-GAAP(2)                      (Q1-Q3 rows only)

The residue lines carry no $/% figure at all. Live is the strictly
cleaner shape: the same 4 figure bullets (Q4 rows: 8, quarter + full
year) with no table residue. The 4 newer MU siblings (2025-11-27,
2026-02-26, 2026-05-28, 2026-09-03) already store the live shape
(stored == live under norm) -- the consistency cross-check. The 3
oldest cached MU releases (2023-11-30, 2024-02-29, 2024-05-30) have no
stored highlights row at all, so nothing to re-sync there.

No extractor change: the current extractor already serves the clean
shape; the defect is purely the stored seed-era snapshots.

Usage: DRY_RUN=1 .venv/bin/python scripts/batch278_repair.py
       .venv/bin/python scripts/batch278_repair.py
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

MU_KEYS = [
    "MU_2024-08-29",
    "MU_2024-11-28",
    "MU_2025-02-27",
    "MU_2025-05-29",
    "MU_2025-08-28",
]
MU_SIBLINGS = (
    "MU_2025-11-27",
    "MU_2026-02-26",
    "MU_2026-05-28",
    "MU_2026-09-03",
)
# Exact stored-only lines allowed: the trailing table-header residue.
MU_RESIDUE = {
    "Quarterly Financial Results",
    "(in millions, except per share amounts) GAAP(1)",
    "Non-GAAP(2)",
}


def _live(key):
    return F.extract_press_release_highlights(
        open(f"{CACHE}/{key}.html", encoding="utf-8").read()
    )


def _bullets(text):
    """Bullet bodies with the leading glyph/space stripped, for
    content comparison across the seed-era '•X' vs live '• X' spacing."""
    out = []
    for ln in text.split("\n"):
        ln = ln.strip()
        if ln.startswith("\u2022"):
            out.append(ln[1:].strip())
    return out


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

    # --- Batch 278 MU override (deliberate, gated; see docstring) ---
    sib_ok = []
    for sib in MU_SIBLINGS:
        sib_pe = sib.split("_", 1)[1]
        sib_stored = con.execute(
            "SELECT q.press_release_highlights "
            "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = 'MU' AND q.period_end = ?",
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
    for key in MU_KEYS:
        pe = key.split("_", 1)[1]
        row = con.execute(
            "SELECT q.press_release_highlights, q.cik "
            "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = 'MU' AND q.period_end = ?",
            (pe,),
        ).fetchone()
        stored, cik = row
        live = _live(key)
        s_lines = [ln for ln in stored.split("\n") if ln.strip()] if stored else []
        l_lines = [ln for ln in live.split("\n") if ln.strip()] if live else []
        s_figs = set(FIG_RE.findall(stored or ""))
        l_figs = set(FIG_RE.findall(live or ""))
        # Bullet lines differ only by the seed-era missing space after the
        # glyph; they are covered by the bullets-identical gate, so exclude
        # them here and pin only the non-bullet stored-only lines.
        stored_only = [
            ln for ln in s_lines
            if ln not in l_lines and not ln.startswith("\u2022")
        ]
        gates = {
            "stored-is-seed-era-bullet-spacing": (
                stored is not None and "\u2022Revenue" in stored
            ),
            "stored-has-table-residue": (
                stored is not None
                and "Quarterly Financial Results" in stored
                and "(in millions, except per share amounts)" in stored
            ),
            "live-has-no-residue": (
                live is not None
                and "Quarterly Financial Results" not in live
                and "(in millions, except per share amounts)" not in live
            ),
            "bullets-identical-modulo-spacing": (
                stored is not None
                and live is not None
                and _bullets(stored) == _bullets(live)
                and len(_bullets(live)) in (4, 8)
            ),
            "stored-only-lines-are-exact-residue": (
                stored is not None
                and live is not None
                and set(stored_only) <= MU_RESIDUE
                and len(stored_only) >= 2
            ),
            "no-stored-only-figures": s_figs - l_figs == set(),
            "no-live-only-figures": l_figs - s_figs == set(),
            "same-headline": (
                stored is not None
                and live is not None
                and s_lines
                and l_lines
                and s_lines[0] == l_lines[0]
            ),
            "siblings-already-live-shape": all(sib_ok),
        }
        failed = [g for g, ok in gates.items() if not ok]
        if failed:
            print(f"  MU-override SKIP {key}: failed gates {failed}")
            continue
        print(f"  MU-override {'WOULD-RESYNC' if DRY else 'RESYNC'} {key} "
              f"{len(stored)}->{len(live)} (seed-era bullets + table residue -> live)")
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
