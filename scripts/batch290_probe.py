"""Batch 290 probe: audit open defect classes from batch 289 carry-forward."""
import sqlite3

DB = "tickerlens.db"
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
cur = con.cursor()

J = "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik"

print("=== EPS sign mismatches (EPS sign != net income sign) ===")
rows = cur.execute(f"""
    SELECT c.ticker, q.period_end, q.fiscal_period, q.eps_basic, q.eps_diluted, q.net_income
    {J}
    WHERE q.net_income IS NOT NULL AND q.net_income != 0
      AND ((q.eps_basic IS NOT NULL AND q.eps_basic != 0 AND (q.eps_basic < 0) != (q.net_income < 0))
        OR (q.eps_diluted IS NOT NULL AND q.eps_diluted != 0 AND (q.eps_diluted < 0) != (q.net_income < 0)))
    ORDER BY c.ticker, q.period_end
""").fetchall()
for r in rows:
    print(dict(r))
print(f"Total EPS sign mismatches: {len(rows)}")

print("\n=== Negative-EPS rows (count by ticker) ===")
rows = cur.execute(f"""
    SELECT c.ticker, COUNT(*) AS n
    {J}
    WHERE q.eps_basic < 0 OR q.eps_diluted < 0
    GROUP BY c.ticker ORDER BY n DESC
""").fetchall()
for r in rows:
    print(dict(r))

print("\n=== CRWD + GPC all quarters ===")
for tk in ("CRWD", "GPC"):
    rows = cur.execute(f"""
        SELECT c.ticker, q.period_end, q.fiscal_year, q.fiscal_period, q.eps_basic, q.eps_diluted, q.net_income, q.revenue
        {J} WHERE c.ticker=? ORDER BY q.period_end
    """, (tk,)).fetchall()
    for r in rows:
        print(dict(r))

print("\n=== Non-positive revenue ===")
rows = cur.execute(f"""
    SELECT c.ticker, q.period_end, q.fiscal_period, q.revenue, q.net_income
    {J}
    WHERE q.revenue IS NOT NULL AND q.revenue <= 0
    ORDER BY c.ticker, q.period_end
""").fetchall()
for r in rows:
    print(dict(r))
print(f"Total: {len(rows)}")

print("\n=== APLD all quarters ===")
rows = cur.execute(f"""
    SELECT c.ticker, q.period_end, q.fiscal_year, q.fiscal_period, q.revenue, q.net_income, q.eps_basic, q.eps_diluted
    {J} WHERE c.ticker='APLD' ORDER BY q.period_end
""").fetchall()
for r in rows:
    print(dict(r))

print("\n=== Stale tickers (latest <= 2026-03-31) ===")
rows = cur.execute(f"""
    SELECT c.ticker, MAX(q.period_end) AS latest, COUNT(*) AS nq
    {J} GROUP BY c.ticker HAVING latest <= '2026-03-31'
    ORDER BY latest, c.ticker
""").fetchall()
for r in rows:
    print(dict(r))
print(f"Total stale: {len(rows)}")

print("\n=== Latest-period distribution ===")
rows = cur.execute(f"""
    SELECT latest, COUNT(*) AS n FROM (
        SELECT c.ticker, MAX(q.period_end) AS latest {J} GROUP BY c.ticker
    ) GROUP BY latest ORDER BY latest
""").fetchall()
for r in rows:
    print(dict(r))

print("\n=== Missing-assets rows ===")
rows = cur.execute(f"""
    SELECT c.ticker, q.period_end, q.fiscal_period, q.total_assets, q.total_liabilities, q.total_equity
    {J} WHERE q.total_assets IS NULL
    ORDER BY c.ticker, q.period_end
""").fetchall()
for r in rows:
    print(dict(r))
print(f"Total: {len(rows)}")

print("\n=== Identity breaks >1M (incl mezzanine) ===")
rows = cur.execute(f"""
    SELECT c.ticker, q.period_end, q.total_assets, q.total_liabilities, q.total_equity, q.temporary_equity, q.redeemable_nci
    {J}
    WHERE q.total_assets IS NOT NULL AND q.total_liabilities IS NOT NULL AND q.total_equity IS NOT NULL
      AND ABS(q.total_assets - (q.total_liabilities + q.total_equity
            + COALESCE(q.temporary_equity,0) + COALESCE(q.redeemable_nci,0))) > 1000000
    ORDER BY c.ticker, q.period_end
""").fetchall()
for r in rows:
    print(dict(r))
print(f"Total: {len(rows)}")

print("\n=== NULL revenue / NULL net income / NULL EPS counts ===")
for col in ("revenue", "net_income", "eps_basic", "eps_diluted", "free_cash_flow", "total_assets", "cash_and_equivalents"):
    n = cur.execute(f"SELECT COUNT(*) FROM quarterly_financials WHERE {col} IS NULL").fetchone()[0]
    print(col, n)

con.close()
