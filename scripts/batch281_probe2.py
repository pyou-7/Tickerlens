"""Batch 281 probe2: full stored vs live dump for BRO x3 + sibling check."""
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import norm
from tickerlens.data import filings as F

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT q.period_end, q.press_release_highlights FROM quarterly_financials q "
        "JOIN companies c ON c.cik = q.cik WHERE c.ticker = 'BRO' "
        "ORDER BY q.period_end"
    ).fetchall()
    for pe, stored in rows:
        key = f"BRO_{pe}"
        try:
            html = open(f"{CACHE}/{key}.html", encoding="utf-8").read()
        except FileNotFoundError:
            print(f"{key}: no cache, stored={'None' if stored is None else len(stored)}")
            continue
        live = F.extract_press_release_highlights(html)
        same = stored is not None and live is not None and norm(stored) == norm(live)
        print(f"{key}: stored={'None' if stored is None else len(stored)} live={'None' if live is None else len(live)} norm-equal={same}")
        if stored is not None and live is not None and not same:
            print("----- STORED -----")
            print(stored)
            print("----- LIVE -----")
            print(live)
            print("----- END -----")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
