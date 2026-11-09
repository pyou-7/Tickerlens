"""Batch 222 repair: sync stored highlights to the current extractor.

The batch-222 extractor fix completes or cleanly drops mid-sentence
highlights tails (completion allowance + _trim_unfinished_tail).
The 31 blast-diff exhibits (hidden_files/blast222) are the repair
candidates: for each, the stored row is synced to blast-new when the
gate holds:

- stored == blast-old exactly (the common case: the row was extracted
  by the pre-222 code and nothing else drifted), or
- stored is a strict prefix of blast-new (the old extractor truncated
  the same item earlier — e.g. CI 2025-06-30's stored row is the old
  856-char truncation of the same quote), or
- stored == blast-old modulo standalone bullet-glyph lines and
  footnote-key spacing (the batch-220 drift shape, for rows that
  predate those fixes too).

Rows whose stored text matches neither shape are SKIPPED with a
reason — they carry other drift and need their own investigation,
not a blind overwrite. Rows with no cached exhibit are skipped
(they refill on refresh). Dry-run by default; pass --write to
update the DB. Idempotent: a second run finds every in-scope row
already equal to blast-new.
"""
import argparse
import os
import re
import sqlite3

BLAST = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast222"
DB = "tickerlens.db"


def _read(path: str) -> str:
    with open(os.path.join(BLAST, path), encoding="utf-8") as fh:
        return fh.read()


def _spaceless(ln: str) -> str:
    return re.sub(r"\s+", "", ln)


def _norm(text: str) -> list[str]:
    """Drop standalone bullet-glyph lines; spacing-insensitive lines."""
    out = []
    for ln in text.splitlines():
        if ln.strip() in ("•", "◦", "▪", "●", "-"):
            continue
        s = _spaceless(ln)
        if s:
            out.append(s)
    return out


def _gate(stored: str, old: str, new: str) -> str | None:
    """Return the gate name that holds, or None."""
    if stored == old:
        return "exact-old"
    if new.startswith(stored):
        return "prefix-of-new"
    if _norm(stored) == _norm(old):
        return "norm-old"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    diffs = sorted(
        f[:-4]
        for f in os.listdir(os.path.join(BLAST, "h_new"))
        if f.endswith(".txt")
        and open(os.path.join(BLAST, "h_old", f), encoding="utf-8").read()
        != open(os.path.join(BLAST, "h_new", f), encoding="utf-8").read()
    )
    print(f"{len(diffs)} blast-diff exhibits")
    con = sqlite3.connect(DB)
    cur = con.cursor()
    repaired = 0
    already = 0
    skipped: list[tuple[str, str]] = []
    for key in diffs:
        ticker, pe = key.rsplit("_", 1)
        row = cur.execute(
            "SELECT q.press_release_highlights FROM quarterly_financials q "
            "JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = ? AND q.period_end = ?",
            (ticker, pe),
        ).fetchone()
        if row is None or row[0] is None:
            skipped.append((key, "no stored row"))
            continue
        stored = row[0]
        old = _read(f"h_old/{key}.txt")
        new = _read(f"h_new/{key}.txt")
        if stored == new:
            already += 1
            print(f"  {key}: already new")
            continue
        gate = _gate(stored, old, new)
        if gate is None:
            skipped.append((key, "stored matches neither old nor new"))
            print(f"  {key}: SKIP stored matches neither old nor new "
                  f"(stored={len(stored)} old={len(old)} new={len(new)})")
            continue
        print(f"  {key}: {gate} stored={len(stored)} -> new={len(new)}")
        if args.write:
            cur.execute(
                "UPDATE quarterly_financials SET press_release_highlights = ? "
                "WHERE cik = (SELECT cik FROM companies WHERE ticker = ?) "
                "AND period_end = ?",
                (new, ticker, pe),
            )
            repaired += 1
    if args.write:
        con.commit()
    print(f"repaired: {repaired} (write={args.write}), "
          f"already-new: {already}, skipped: {len(skipped)}")
    for key, why in skipped:
        print(f"  skip {key}: {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
