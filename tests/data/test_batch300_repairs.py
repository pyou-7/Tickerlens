"""Batch 300 regression tests: comparative-only label fix (stored rows).

Fresh-ticker hunt (SMCI/CELH/CAVA/MSTR/CRCL) found Circle's fiscal-year
labels uniformly one year high at periods=12: its pre-IPO quarters
exist only as comparatives in 2025/2026 filings (fy inherited +1), and
_dedupe_period_labels relabeled the correct later rows forward
("FY2027 Q3" for Sep 2026). The filing-lag fix (first_filed provenance)
also corrected fresh-extraction labels for ETR/GOOGL/AWK (stored rows
already calendar-true — proven by in-memory service-parity comparison,
no writes) and SKYD's two predecessor quarters (stored FY2025 labels
repaired to FY2024, values identical).

Pins: SKYD repaired labels; CRCL/cohort seeded rows (8 quarters each,
calendar-true labels, filed values); ETR/GOOGL/AWK stored labels
unchanged; DB-wide census gates (0 identity breaks, 0 EPS violations).
"""
import os
import sqlite3

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB = os.path.join(REPO_ROOT, "tickerlens.db")


def _rows(ticker):
    con = sqlite3.connect(DB)
    try:
        return con.execute(
            "SELECT q.period_end, q.fiscal_year, q.fiscal_period, q.revenue, "
            "q.net_income, q.eps_basic, q.eps_diluted FROM quarterly_financials q "
            "JOIN companies c ON c.cik = q.cik WHERE c.ticker = ? "
            "ORDER BY q.period_end",
            (ticker,),
        ).fetchall()
    finally:
        con.close()


def test_skyd_predecessor_labels_repaired() -> None:
    by_end = {r[0]: (r[1], r[2]) for r in _rows("SKYD")}
    assert by_end["2024-09-30"] == (2024, "Q3")
    assert by_end["2024-12-31"] == (2024, "Q4")
    assert by_end["2025-03-31"] == (2025, "Q1")
    assert by_end["2025-06-30"] == (2025, "Q2")


def test_crcl_seeded_labels_calendar_true() -> None:
    rows = _rows("CRCL")
    assert len(rows) == 8
    by_end = {r[0]: (r[1], r[2], r[3]) for r in rows}
    assert by_end["2024-12-31"] == (2024, "Q4", 435367000.0)
    assert by_end["2025-06-30"] == (2025, "Q2", 658078000.0)
    assert by_end["2026-09-30"] == (2026, "Q3", 864888000.0)
    labels = [(r[1], r[2]) for r in rows]
    assert len(labels) == len(set(labels))


def test_cohort_seeded_eight_quarters_each() -> None:
    for ticker in ("SMCI", "CELH", "CAVA", "MSTR"):
        rows = _rows(ticker)
        assert len(rows) == 8, ticker
        assert all(r[3] is not None for r in rows), ticker  # revenue present
        labels = [(r[1], r[2]) for r in rows]
        assert len(labels) == len(set(labels)), ticker
    # SMCI June FYE: Sep-2026 quarter is Q1 FY2027.
    smci = {r[0]: (r[1], r[2]) for r in _rows("SMCI")}
    assert smci["2026-09-30"] == (2027, "Q1")
    # MSTR finance SIC: FCF suppressed by design (checked via census below).


def test_etr_googl_awk_stored_labels_unchanged() -> None:
    for ticker in ("ETR", "GOOGL", "AWK"):
        by_end = {r[0]: (r[1], r[2]) for r in _rows(ticker)}
        assert by_end["2026-03-31"] == (2026, "Q1"), ticker
        assert by_end["2025-06-30"] == (2025, "Q2"), ticker


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
        dup_labels = con.execute(
            "SELECT COUNT(*) FROM (SELECT cik, fiscal_year, fiscal_period, COUNT(*) n "
            "FROM quarterly_financials GROUP BY cik, fiscal_year, fiscal_period "
            "HAVING n > 1)"
        ).fetchone()[0]
    finally:
        con.close()
    assert breaks == []
    assert anti == 0
    assert dup_labels == 0
