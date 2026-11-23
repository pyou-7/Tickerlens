"""Batch 302 stored-row tests: EPS repairs + fresh cohort seed.

The rounding-uncertainty guard (see test_xbrl_batch302.py) rejected
34 stored EPS cells whose share-implied Q4 derivations were
rounding-unreliable; they now carry the subtraction-fallback values
from service-parity re-extraction. The fresh cohort GM/MRVL/DKNG/
LYFT/ETSY/CHWY is seeded at 8 quarters; DKNG's Q4 2025 EPS is the
guard's motivating case (0.28/0.26, was 14.55/0.26 pre-fix).
"""
import sqlite3
import sys

sys.path.insert(0, "src")

from tickerlens.models.quarterly_financial import identity_tolerance

DB = "tickerlens.db"


def eps(ticker, period_end):
    con = sqlite3.connect(DB)
    row = con.execute(
        "SELECT q.eps_basic, q.eps_diluted FROM quarterly_financials q "
        "JOIN companies c ON c.cik = q.cik WHERE c.ticker = ? AND q.period_end = ?",
        (ticker, period_end)).fetchone()
    con.close()
    return row


def test_dkng_q4_2025_eps_repaired():
    assert eps("DKNG", "2025-12-31") == (0.28, 0.26)


def test_material_eps_repairs():
    assert eps("DASH", "2024-12-31") == (0.34, 0.33)
    assert eps("SOFI", "2024-12-31")[0] == 0.32
    assert eps("TEAM", "2026-06-30") == (0.52, 0.52)
    assert eps("LUV", "2025-12-31")[0] == 0.61
    assert eps("AAL", "2025-12-31") == (0.15, 0.15)
    assert eps("MU", "2024-08-29") == (0.8, 0.8)
    assert eps("ON", "2025-12-31") == (0.44, 0.44)
    assert eps("AFRM", "2025-06-30") == (0.21, 0.2)


def test_fresh_cohort_seeded():
    con = sqlite3.connect(DB)
    for ticker in ("GM", "MRVL", "DKNG", "LYFT", "ETSY", "CHWY"):
        n = con.execute(
            "SELECT COUNT(*) FROM quarterly_financials q JOIN companies c "
            "ON c.cik = q.cik WHERE c.ticker = ?", (ticker,)).fetchone()[0]
        assert n == 8, f"{ticker} quarters {n}"
    con.close()


def test_lyft_fcf_honest_none():
    # LYFT tags cash CapEx only under a filer-extension concept that
    # companyfacts does not carry; FCF stays NULL (source limit).
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT q.free_cash_flow FROM quarterly_financials q JOIN companies c "
        "ON c.cik = q.cik WHERE c.ticker = 'LYFT'").fetchall()
    con.close()
    assert rows and all(r[0] is None for r in rows)


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
    con.close()
    assert bad_identity == 0
    assert bad_eps == 0
    assert n_companies == 314
