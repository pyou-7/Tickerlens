"""Batch 224 repair: sync the 15 stored highlights rows whose live
extraction changed in blast224/h_new to the current extractor.

The fix (next-line lookahead + termination lookahead) completes
sentences the old extractor cut mid-way. Every repaired row is a pure
extension of its stored text — the new highlights add the sentence's
completion (and, for GEV, the full CEO quote) after the old tail:

- Gate A (9 rows): stored == blast224-old and stored is a strict
  prefix of blast224-new; new terminates.
  ABNB_2024-09-30, AJG_2024-12-31, CI_2024-12-31, DG_2025-01-31,
  GEV_2025-03-31, GEV_2025-09-30, GEV_2026-03-31, GPC_2026-09-30,
  HAL_2025-12-31.
- Gate B (3 rows, truncated headline): stored == blast224-old except
  the headline line, which is a suffix of the full headline (the
  batch-223 DG shape: "General Corporation Reports ..." / "Reports
  Strong Fourth Quarter ..."); new headline == old headline and new
  terminates.
  DG_2025-05-02, DG_2025-10-31, DG_2026-01-30.
- Gate C (3 rows, bullet spacing): stored == blast224-old modulo
  bullet spacing, and new is a pure extension of old modulo spacing;
  new terminates.
  GEV_2026-06-30, HAL_2025-03-31, HAL_2025-06-30.

Not repaired here (no stored row — they serve the new extraction live
on refresh): ABNB_2023-12-31, ABNB_2024-06-30, CI_2023-09-30,
DG_2024-05-03, DG_2024-08-02, ETN_2023-12-31. DAL_2024-09-30 has no
stored row either and is unchanged (complete bullet, not a hole row).

Dry-run by default; pass --write to update the DB. Idempotent: a
second run finds every in-scope row already equal to blast224-new.
"""
import argparse
import os
import re
import sqlite3

BLAST224 = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast224"
DB = "tickerlens.db"

GATE_A = [
    "ABNB_2024-09-30",
    "AJG_2024-12-31",
    "CI_2024-12-31",
    "DG_2025-01-31",
    "GEV_2025-03-31",
    "GEV_2025-09-30",
    "GEV_2026-03-31",
    "GPC_2026-09-30",
    "HAL_2025-12-31",
]
GATE_B = ["DG_2025-05-02", "DG_2025-10-31", "DG_2026-01-30"]
GATE_C = ["GEV_2026-06-30", "HAL_2025-03-31", "HAL_2025-06-30"]


def _read(sub, key):
    with open(os.path.join(BLAST224, sub, key + ".txt"), encoding="utf-8") as fh:
        return fh.read()


def _norm(text):
    return re.sub(r"•\s*", "• ", text)


def _terminated(text):
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    last = lines[-1].strip().rstrip("”\"'’)]}\")")
    return last.endswith((".", "!", "?", "…"))


def _headline(text):
    return text.split("\n\n")[0].strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    con = sqlite3.connect(DB)
    cur = con.cursor()
    repaired = 0
    already = 0
    skipped = 0
    for key in GATE_A + GATE_B + GATE_C:
        ticker, pe = key.split("_")
        row = cur.execute(
            "SELECT q.press_release_highlights FROM quarterly_financials q "
            "JOIN companies c ON c.cik = q.cik WHERE c.ticker=? AND q.period_end=?",
            (ticker, pe),
        ).fetchone()
        old = _read("h_old", key)
        new = _read("h_new", key)
        if row is None or row[0] is None:
            print(f"  {key}: SKIP no stored row")
            skipped += 1
            continue
        stored = row[0]
        if stored == new:
            print(f"  {key}: already-new")
            already += 1
            continue
        gate = None
        if key in GATE_A:
            if stored == old and new.startswith(stored) and _terminated(new):
                gate = "A stored==old, pure extension, new terminates"
        elif key in GATE_B:
            stored_lines = stored.splitlines()
            old_lines = old.splitlines()
            if (
                len(stored_lines) == len(old_lines)
                and stored_lines[1:] == old_lines[1:]
                and _headline(new).endswith(_headline(stored))
                and _headline(new) == _headline(old)
                and _terminated(new)
            ):
                gate = "B truncated headline, body==old, new terminates"
        elif key in GATE_C:
            if (
                _norm(stored) == _norm(old)
                and _norm(new).startswith(_norm(old))
                and _terminated(new)
            ):
                gate = "C bullet-spacing norm, pure extension, new terminates"
        if gate is None:
            print(f"  {key}: SKIP gate failed (stored={len(stored)} old={len(old)} new={len(new)})")
            skipped += 1
            continue
        print(f"  {key}: REPAIR [{gate}] {len(stored)}->{len(new)}")
        repaired += 1
        if args.write:
            cur.execute(
                "UPDATE quarterly_financials SET press_release_highlights=? "
                "WHERE cik=(SELECT cik FROM companies WHERE ticker=?) "
                "AND period_end=?",
                (new, ticker, pe),
            )
    if args.write:
        con.commit()
        # DB-verify every repaired row reads back as blast-new.
        bad = 0
        for key in GATE_A + GATE_B + GATE_C:
            ticker, pe = key.split("_")
            row = cur.execute(
                "SELECT q.press_release_highlights FROM quarterly_financials q "
                "JOIN companies c ON c.cik = q.cik WHERE c.ticker=? AND q.period_end=?",
                (ticker, pe),
            ).fetchone()
            if row is None or row[0] != _read("h_new", key):
                print(f"  {key}: VERIFY FAILED")
                bad += 1
        print(f"repaired={repaired} already-new={already} skipped={skipped} verify-bad={bad}")
        return 1 if bad else 0
    print(f"dry-run: would repair {repaired} (already-new={already} skipped={skipped})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
