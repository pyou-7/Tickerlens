"""Batch 111: build the repair target list (contact-class junk headlines)."""
import json
import re
import sqlite3

con = sqlite3.connect("tickerlens.db")
con.row_factory = sqlite3.Row
rows = con.execute(
    "SELECT c.ticker, q.period_end, q.press_release_highlights "
    "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
    "WHERE q.press_release_highlights IS NOT NULL "
    "AND q.press_release_highlights != '' "
    "ORDER BY c.ticker, q.period_end DESC"
).fetchall()

targets: dict[str, list[str]] = {}
for r in rows:
    head = (r["press_release_highlights"].split("\n\n")[0] or "").strip()
    t, pe = r["ticker"], r["period_end"]
    bad = (
        not head
        or re.match(r"^(EX-?99|Exhibit)", head, re.I)
        or (len(head.split()) <= 2 and not re.search(r"[.!?]\s*$", head))
    )
    if bad and t in ("QCOM", "BLK", "HCA", "HLT", "DUK", "RMD"):
        targets.setdefault(t, []).append(pe)

json.dump(targets, open("/tmp/batch111_targets.json", "w"), indent=1)
for t, pes in targets.items():
    print(t, len(pes), pes)
print("wrote /tmp/batch111_targets.json")
