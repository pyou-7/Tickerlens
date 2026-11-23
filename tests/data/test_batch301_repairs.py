"""Batch 301 regression tests: multi-class EPS recovery (stored rows).

V, BRK.B, HSY, KKR, STZ and BKR tag EPS only per share class
(dimensional StatementClassOfStockAxis facts), which companyfacts never
carries — every stored quarter's EPS was NULL. Batch 301 recovers the
traded class's EPS from the filings (``parse_class_eps_facts`` +
``_augment_with_class_eps``) and re-seeded the six tickers: 99 EPS cells
filled, no other cell changed (one dead-data BRK.B FFO fill reverted,
batch-300 precedent). Spot values below are the filed traded-class
figures from the probed 10-Q/10-Ks (scripts/batch301_probe2/3.py).
BRK.B diluted stays NULL: Berkshire tags basic only, and batch 298's
fill requires filed equality evidence that does not exist.
"""
import os
import sqlite3

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB = os.path.join(REPO_ROOT, "tickerlens.db")

TICKERS = ["V", "BRK.B", "HSY", "KKR", "STZ", "BKR"]


def _row(ticker, period_end, cols):
    con = sqlite3.connect(DB)
    try:
        return con.execute(
            f"SELECT {cols} FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = ? AND q.period_end = ?",
            (ticker, period_end),
        ).fetchone()
    finally:
        con.close()


def test_visa_class_a_eps():
    # Filed Class A (10-Q 2026-06-30): basic 2.97 / diluted 2.97 —
    # not Class C's 11.87/11.86.
    basic, diluted = _row("V", "2026-06-30", "q.eps_basic, q.eps_diluted")
    assert (basic, diluted) == (2.97, 2.97)


def test_berkshire_class_b_eps_basic_only():
    # Filed equivalent Class B (10-Q 2026-09-30): basic 10.33 —
    # not Class A's 15,502. Diluted is never tagged; stays NULL.
    basic, diluted = _row("BRK.B", "2026-09-30", "q.eps_basic, q.eps_diluted")
    assert basic == 10.33
    assert diluted is None


def test_hershey_common_eps():
    # Filed common (Class A) 10-Q 2026-09-27: 2.96 / 2.88 —
    # not Class B's 2.69 / 2.69.
    basic, diluted = _row("HSY", "2026-09-27", "q.eps_basic, q.eps_diluted")
    assert (basic, diluted) == (2.96, 2.88)


def test_kkr_eps():
    basic, diluted = _row("KKR", "2026-09-30", "q.eps_basic, q.eps_diluted")
    assert (basic, diluted) == (1.25, 1.19)


def test_constellation_class_a_eps():
    basic, diluted = _row("STZ", "2026-08-31", "q.eps_basic, q.eps_diluted")
    assert (basic, diluted) == (3.32, 3.32)


def test_baker_hughes_class_a_eps():
    basic, diluted = _row("BKR", "2026-09-30", "q.eps_basic, q.eps_diluted")
    assert (basic, diluted) == (0.41, 0.41)


def test_no_null_eps_remains_except_brk_diluted():
    con = sqlite3.connect(DB)
    try:
        for ticker in TICKERS:
            n, basic_null, diluted_null = con.execute(
                "SELECT COUNT(*), SUM(q.eps_basic IS NULL), SUM(q.eps_diluted IS NULL) "
                "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
                "WHERE c.ticker = ?",
                (ticker,),
            ).fetchone()
            assert basic_null == 0, ticker
            if ticker == "BRK.B":
                assert diluted_null == n  # basic-only filer, honest NULL
            else:
                assert diluted_null == 0, ticker
    finally:
        con.close()


def test_db_wide_census_clean() -> None:
    import sys

    sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
    from tickerlens.models.quarterly_financial import identity_tolerance

    con = sqlite3.connect(DB)
    try:
        breaks = [
            (cik, pe)
            for cik, pe, ta, tl, te, rn, tp in con.execute(
                "SELECT cik, period_end, total_assets, total_liabilities, total_equity, "
                "redeemable_nci, temporary_equity FROM quarterly_financials "
                "WHERE total_assets IS NOT NULL AND total_liabilities IS NOT NULL "
                "AND total_equity IS NOT NULL"
            )
            if abs(ta - (tl + te + (rn or 0) + (tp or 0))) > identity_tolerance(ta)
        ]
        anti = con.execute(
            "SELECT COUNT(*) FROM quarterly_financials WHERE eps_basic IS NOT NULL "
            "AND eps_diluted IS NOT NULL AND ((eps_basic < 0 AND eps_diluted < eps_basic - 1e-9) "
            "OR (eps_basic > 0 AND eps_diluted > eps_basic + 0.005))"
        ).fetchone()[0]
    finally:
        con.close()
    assert breaks == []
    assert anti == 0
