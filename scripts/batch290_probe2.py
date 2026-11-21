"""Batch 290 probe 2: EPS diluted-vs-basic inversion census + NULL EPS census."""
import sqlite3

con = sqlite3.connect("tickerlens.db")
con.row_factory = sqlite3.Row
cur = con.cursor()
J = "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik"

print("=== Diluted < Basic (any sign) — GAAP: diluted EPS >= basic EPS when loss; diluted <= basic when profit ===")
rows = cur.execute(f"""
    SELECT c.ticker, q.period_end, q.fiscal_period, q.eps_basic, q.eps_diluted, q.net_income
    {J}
    WHERE q.eps_basic IS NOT NULL AND q.eps_diluted IS NOT NULL
      AND q.eps_diluted < q.eps_basic - 0.0001
    ORDER BY c.ticker, q.period_end
""").fetchall()
for r in rows:
    print(dict(r))
print(f"Total diluted<basic: {len(rows)}")

print("\n=== Diluted > Basic (profit quarters — also impossible: diluted shares >= basic shares) ===")
rows = cur.execute(f"""
    SELECT c.ticker, q.period_end, q.fiscal_period, q.eps_basic, q.eps_diluted, q.net_income
    {J}
    WHERE q.eps_basic IS NOT NULL AND q.eps_diluted IS NOT NULL
      AND q.eps_diluted > q.eps_basic + 0.0001
    ORDER BY c.ticker, q.period_end
""").fetchall()
for r in rows:
    print(dict(r))
print(f"Total diluted>basic: {len(rows)}")

print("\n=== NULL EPS rows by ticker ===")
rows = cur.execute(f"""
    SELECT c.ticker, q.period_end, q.fiscal_period, q.eps_basic, q.eps_diluted, q.net_income
    {J}
    WHERE q.eps_basic IS NULL OR q.eps_diluted IS NULL
    ORDER BY c.ticker, q.period_end
""").fetchall()
for r in rows:
    print(dict(r))
print(f"Total NULL-EPS rows: {len(rows)}")

print("\n=== APLD: is Q4 revenue Q4-derived? Check fiscal periods ===")
rows = cur.execute(f"""
    SELECT c.ticker, q.period_end, q.fiscal_year, q.fiscal_period, q.revenue
    {J} WHERE c.ticker IN ('APLD','AGNC') ORDER BY c.ticker, q.period_end
""").fetchall()
for r in rows:
    print(dict(r))

print("\n=== APLD FY2025 sum check: Q1+Q2+Q3+Q4 ===")
rows = cur.execute(f"""
    SELECT q.fiscal_year, SUM(q.revenue) AS fy_sum, COUNT(*) AS n
    {J} WHERE c.ticker='APLD' GROUP BY q.fiscal_year
""").fetchall()
for r in rows:
    print(dict(r))

print("\n=== Stale cohort: skipped-quarters notes ===")
rows = cur.execute("""
    SELECT ticker, xbrl_skipped_quarters, pending_filing_note, xbrl_filings_processed
    FROM companies
    WHERE ticker IN ('C','AEP','CTSH','D','DLR','DUK','ETR','HCA','HUM','MDLZ','NEE','PLD','PPL','SO','SRE','VMC','VRSK')
""").fetchall()
for r in rows:
    print(dict(r))

con.close()
