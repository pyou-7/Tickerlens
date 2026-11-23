"""Batch 290 probe 3: GAAP-impossible EPS relations, counts + rows."""
import sqlite3

con = sqlite3.connect("tickerlens.db")
con.row_factory = sqlite3.Row
cur = con.cursor()
J = "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik"

print("=== LOSS quarters where diluted < basic (more negative) — GAAP anti-dilution violation ===")
rows = cur.execute(f"""
    SELECT c.ticker, q.period_end, q.fiscal_period, q.eps_basic, q.eps_diluted, q.net_income
    {J}
    WHERE q.net_income < 0 AND q.eps_basic IS NOT NULL AND q.eps_diluted IS NOT NULL
      AND q.eps_diluted < q.eps_basic - 0.0001
    ORDER BY c.ticker, q.period_end
""").fetchall()
for r in rows:
    print(dict(r))
print(f"Total: {len(rows)}")

print("\n=== PROFIT quarters where diluted > basic — impossible (diluted shares >= basic) ===")
rows = cur.execute(f"""
    SELECT c.ticker, q.period_end, q.fiscal_period, q.eps_basic, q.eps_diluted, q.net_income
    {J}
    WHERE q.net_income > 0 AND q.eps_basic IS NOT NULL AND q.eps_diluted IS NOT NULL
      AND q.eps_diluted > q.eps_basic + 0.0001
    ORDER BY c.ticker, q.period_end
""").fetchall()
for r in rows:
    print(dict(r))
print(f"Total: {len(rows)}")

print("\n=== NULL EPS rows (compact) ===")
rows = cur.execute(f"""
    SELECT c.ticker, q.period_end, q.fiscal_period, q.eps_basic, q.eps_diluted
    {J}
    WHERE q.eps_basic IS NULL OR q.eps_diluted IS NULL
    ORDER BY c.ticker, q.period_end
""").fetchall()
from collections import Counter
print(Counter(r["ticker"] for r in rows))
for r in rows:
    if r["ticker"] != "BKR":
        print(dict(r))
print(f"Total NULL-EPS rows: {len(rows)}")

print("\n=== Q4-derived check: which impossible rows are Q4? ===")
print("(see above fiscal_period)")

print("\n=== APLD FY sums ===")
rows = cur.execute(f"""
    SELECT q.fiscal_year, SUM(q.revenue) AS fy_sum, COUNT(*) AS n
    {J} WHERE c.ticker='APLD' GROUP BY q.fiscal_year
""").fetchall()
for r in rows:
    print(dict(r))

print("\n=== AGNC quarters ===")
rows = cur.execute(f"""
    SELECT q.period_end, q.fiscal_period, q.revenue, q.net_income
    {J} WHERE c.ticker='AGNC' ORDER BY q.period_end
""").fetchall()
for r in rows:
    print(dict(r))

con.close()
