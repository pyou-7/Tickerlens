"""Batch 303 stored-row tests: CapEx recovery repairs.

LYFT and Dominion tag CapEx under extension concepts companyfacts
never carries; the batch-303 filing augment recovers the cash-flow
line and FCF now renders for every stored quarter. Verizon's total
capex line sits under PaymentsToAcquireOtherProductiveAssets, now in
the CAPEX chain. Values below are the service-parity re-extraction
results written by ``scripts/batch303_repair.py --apply`` (targeted
FCF-only update; census re-verified clean after).
"""
import sqlite3
import sys

sys.path.insert(0, "src")

from tickerlens.models.quarterly_financial import identity_tolerance

DB = "tickerlens.db"


def fcf(ticker):
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT q.period_end, q.free_cash_flow FROM quarterly_financials q "
        "JOIN companies c ON c.cik = q.cik WHERE c.ticker = ? "
        "ORDER BY q.period_end", (ticker,)).fetchall()
    con.close()
    return dict(rows)


def test_lyft_fcf_recovered():
    assert fcf("LYFT") == {
        "2024-12-31": 139951000.0,
        "2025-03-31": 280734000.0,
        "2025-06-30": 329442000.0,
        "2025-09-30": 277817000.0,
        "2025-12-31": 227623000.0,
        "2026-03-31": 287256000.0,
        "2026-06-30": 319630000.0,
        "2026-09-30": 294678000.0,
    }


def test_dominion_fcf_recovered():
    series = fcf("D")
    assert len(series) == 10
    assert all(v is not None for v in series.values())
    # Utility build cycle: capex exceeds OpCF every quarter.
    assert series["2026-09-30"] == -546000000.0
    assert series["2024-12-31"] == -2838000000.0


def test_verizon_fcf_recovered():
    series = fcf("VZ")
    assert len(series) == 9
    assert all(v is not None for v in series.values())
    assert series["2026-09-30"] == 7801000000.0
    assert series["2025-03-31"] == 3637000000.0


def test_db_census_gates():
    con = sqlite3.connect(DB)
    bad_identity = bad_eps = 0
    for ta, tl, te, rnci, temp, eb, ed in con.execute(
            "SELECT total_assets, total_liabilities, total_equity, "
            "redeemable_nci, temporary_equity, eps_basic, eps_diluted "
            "FROM quarterly_financials"):
        if None not in (ta, tl, te):
            mezz = (rnci or 0) + (temp or 0)
            if abs(ta - (tl + te + mezz)) > identity_tolerance(ta):
                bad_identity += 1
        if eb is not None and ed is not None and (
                (eb < 0 and ed < eb - 1e-9) or (eb > 0 and ed > eb + 0.005)):
            bad_eps += 1
    n_companies = con.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    n_quarters = con.execute(
        "SELECT COUNT(*) FROM quarterly_financials").fetchone()[0]
    con.close()
    assert bad_identity == 0
    assert bad_eps == 0
    assert n_companies == 314
    assert n_quarters == 2868
