"""Batch 246 probe 3: verify every blast-changed row's diff is quote-only.

For each of the 48 rows whose blast status changed after the quote
pull-in, list the live lines that are not in stored (under norm) and
check each one against the extractor's own _is_executive_quote_line;
and list the stored lines that are not in live and are not S3 residue
(the remaining loss). A row passes when every added line is a quote
line and every remaining lost line is residue (dateline / chrome).

Also reports the pre/post line counts so a row that gained anything
else is visible.

Usage: .venv/bin/python scripts/batch246_probe3.py > /tmp/batch246_dump3.txt
"""
import os
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import non_empty, norm
from batch241_repair import is_residue_s3
from tickerlens.data.filings import (
    _is_executive_quote_line,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"

CHANGED = """ABBV_2024-09-30 ABBV_2024-12-31 ABBV_2025-03-31 ABBV_2025-06-30
ABBV_2025-09-30 ABBV_2025-12-31 ABBV_2026-03-31 ABBV_2026-06-30
ADI_2024-11-02 ADI_2025-02-01 ADI_2025-05-03 ADI_2025-08-02
ADI_2025-11-01 ADI_2026-01-31 ADI_2026-05-02 ADI_2026-08-01
AEP_2025-03-31 AMAT_2025-04-27
AVGO_2024-11-03 AVGO_2025-02-02 AVGO_2025-05-04 AVGO_2025-08-03
AVGO_2025-11-02 AVGO_2026-02-01 AVGO_2026-05-03 AVGO_2026-08-02
CARR_2024-06-30 CARR_2025-03-31 CARR_2025-06-30 CARR_2025-09-30 CARR_2026-03-31
CI_2026-03-31
CTSH_2024-06-30 CTSH_2024-09-30 CTSH_2024-12-31 CTSH_2025-03-31 CTSH_2025-06-30 CTSH_2025-09-30
CVS_2026-03-31 CVS_2026-06-30
DD_2025-03-31
DECK_2024-09-30 DECK_2024-12-31 DECK_2025-03-31 DECK_2025-09-30
DECK_2025-12-31 DECK_2026-03-31 DECK_2026-06-30 DECK_2026-09-30
DGX_2024-09-30 DGX_2024-12-31 DGX_2025-03-31 DGX_2025-06-30 DGX_2026-09-30
DLTR_2024-11-02 DLTR_2025-02-01 DLTR_2025-05-03 DLTR_2025-08-02
DLTR_2025-11-01 DLTR_2026-01-31 DLTR_2026-05-02
D_2024-12-31
ELV_2024-09-30 ELV_2024-12-31 ELV_2025-03-31 ELV_2025-06-30
ELV_2025-12-31 ELV_2026-03-31 ELV_2026-06-30 ELV_2026-09-30
EQIX_2026-09-30
FIS_2024-09-30 FIS_2024-12-31 FIS_2025-03-31 FIS_2025-06-30 FIS_2025-09-30 FIS_2026-03-31 FIS_2026-06-30
GD_2024-06-30 GD_2024-09-29 GD_2025-06-29 GD_2025-09-28
GD_2026-04-05 GD_2026-07-05 GD_2026-10-04""".split()


def main() -> int:
    con = sqlite3.connect(DB)
    n_pass = 0
    for key in CHANGED:
        t, pe = key.rsplit("_", 1)
        stored = con.execute(
            "SELECT q.press_release_highlights FROM quarterly_financials q "
            "JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = ? AND q.period_end = ?",
            (t, pe),
        ).fetchone()[0]
        html = open(f"{CACHE}/{key}.html", encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        s_lines, l_lines = non_empty(stored), non_empty(live)
        s_norm, l_norm = {norm(x) for x in s_lines}, {norm(x) for x in l_lines}
        added = [x for x in l_lines if norm(x) not in s_norm]
        lost = [
            x
            for i, x in enumerate(s_lines)
            if norm(x) not in l_norm
            and not is_residue_s3(
                x, s_lines[i + 1] if i + 1 < len(s_lines) else "", set(l_lines)
            )
        ]
        bad_added = [x for x in added if not _is_executive_quote_line(x)]
        ok = not bad_added and not lost
        n_pass += ok
        print(f"{key}: stored={len(s_lines)} live={len(l_lines)} "
              f"added={len(added)} (non-quote: {len(bad_added)}) "
              f"lost-nonresidue={len(lost)} {'PASS' if ok else 'CHECK'}")
        for x in bad_added:
            print(f"    NON-QUOTE ADDED: {x[:200]}")
        for x in lost:
            print(f"    LOST: {x[:200]}")
        for x in added:
            if x not in bad_added:
                print(f"    +quote: {x[:120]}")
    print(f"\nPASS {n_pass}/{len(CHANGED)}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
