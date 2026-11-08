"""Batch 213 repair: replace stored management-guidance rows truncated by
the old 4000-char cap with the complete 8000-cap extraction.

Gates (blast-pinned, like batch 212):
  * stored guidance ends with the truncation "…" (the cap defect);
  * the exhibit for (ticker, period_end) exists in the HTML cache;
  * stored text equals the blast g_old output for that exhibit — the row
    was produced by the current extractor at the 4000 cap, no other drift;
  * the blast g_new output starts with the stored text minus its "…"
    (pure extension) and does not itself end with "…".

Rows failing any gate are skipped and reported, never force-written.

Usage (dry run first):
  .venv/bin/python scripts/batch213_repair.py --dry-run
  .venv/bin/python scripts/batch213_repair.py
"""
import os
import sqlite3
import sys

sys.path.insert(0, "src")

BLAST_NEW = "hidden_files/blast213/g_new"
BLAST_OLD = "hidden_files/blast213/g_old"
DB = "tickerlens.db"

dry = "--dry-run" in sys.argv

con = sqlite3.connect(DB)
cur = con.cursor()
rows = cur.execute(
    """
    SELECT c.ticker, q.period_end, q.management_guidance
    FROM quarterly_financials q JOIN companies c ON c.cik = q.cik
    WHERE q.management_guidance IS NOT NULL
      AND q.management_guidance LIKE '%…'
    """
).fetchall()
print(f"{len(rows)} stored rows end with the truncation ellipsis")

repaired, skipped = [], []
for ticker, period_end, stored in rows:
    stem = f"{ticker}_{period_end}"
    old_path = os.path.join(BLAST_OLD, stem + ".txt")
    new_path = os.path.join(BLAST_NEW, stem + ".txt")
    if not os.path.exists(old_path):
        skipped.append((stem, "no cached exhibit"))
        continue
    old = open(old_path, encoding="utf-8").read()
    new = open(new_path, encoding="utf-8").read()
    if old == "None" or new == "None":
        skipped.append((stem, "blast output None"))
        continue
    if stored != old:
        skipped.append((stem, "stored != blast g_old (other drift)"))
        continue
    if not new.startswith(stored[:-1].rstrip()):
        skipped.append((stem, "new is not a pure extension of stored"))
        continue
    if new.endswith("…"):
        skipped.append((stem, "new still truncated"))
        continue
    if not dry:
        cur.execute(
            "UPDATE quarterly_financials SET management_guidance = ? "
            "WHERE cik = (SELECT cik FROM companies WHERE ticker = ?) "
            "AND period_end = ?",
            (new, ticker, period_end),
        )
    repaired.append((stem, len(stored), len(new)))

if not dry:
    con.commit()
print(f"repaired: {len(repaired)}")
for stem, old_len, new_len in repaired:
    print(f"  {stem}: {old_len} -> {new_len}")
print(f"skipped: {len(skipped)}")
for stem, why in skipped:
    print(f"  {stem}: {why}")

if not dry:
    # DB-verify every repaired row now equals the blast g_new output.
    bad = 0
    for stem, _, _ in repaired:
        ticker, period_end = stem.rsplit("_", 1)
        got = cur.execute(
            "SELECT management_guidance FROM quarterly_financials "
            "WHERE cik = (SELECT cik FROM companies WHERE ticker = ?) "
            "AND period_end = ?",
            (ticker, period_end),
        ).fetchone()[0]
        want = open(os.path.join(BLAST_NEW, stem + ".txt"), encoding="utf-8").read()
        if got != want:
            bad += 1
            print(f"  VERIFY FAIL: {stem}")
    print(f"DB-verified {len(repaired) - bad}/{len(repaired)} rows equal blast g_new")
con.close()
