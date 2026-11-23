"""Batch 299 regression tests: post-restore census repairs (stored rows).

The working DB was reverted to the 2026-11-16 committed snapshot and
batches 268-298 repairs replayed; the post-restore census found three
stored-row defects the replay could not fix on its own:

- WELL 2024-06-30 FFO (636,759,000) never subtracted disposition
  gains; fresh extraction derives Q2 gains (H1 YTD 171,150,000 - Q1
  4,707,000 = 166,443,000) for FFO 470,316,000.
- VRSK 2024-06-30 FCF (162,400,000) came from span-differenced OpCF;
  VRSK's filed standalone Q2 OpCF (211,700,000) gives FCF 153,900,000.
- APLD 2025-05-31 balance sheet did not foot by 136,037,000 — its
  dimensional temporary equity (batch 289's residual). The row is
  revenue-anchorless since batch 292, so the residual was restored
  directly, gated on the single-filing basis closing.

Also pins DOW/ED/EIX/URI 2026-06-30 balance sheets (NULL after the
restore replay; filled by the service-path re-seed) and the DB-wide
census gates batch 295 established (0 identity breaks, 0 EPS
anti-dilution violations).
"""
import os
import sqlite3

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB = os.path.join(REPO_ROOT, "tickerlens.db")


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


def test_well_ffo_subtracts_disposition_gains() -> None:
    (ffo,) = _row("WELL", "2024-06-30", "q.ffo")
    assert ffo == 470316000.0


def test_vrsk_fcf_uses_filed_standalone_opcf() -> None:
    (fcf,) = _row("VRSK", "2024-06-30", "q.free_cash_flow")
    assert fcf == 153900000.0


def test_apld_residual_temporary_equity_restored() -> None:
    ta, tl, te, rnci, temp = _row(
        "APLD", "2025-05-31",
        "q.total_assets, q.total_liabilities, q.total_equity, q.redeemable_nci, q.temporary_equity",
    )
    assert temp == 136037000.0
    assert ta == tl + te + (rnci or 0) + temp


def test_dow_group_q2_2026_balance_sheets_filled() -> None:
    for ticker in ("DOW", "ED", "EIX", "URI"):
        ta, tl, te = _row(
            ticker, "2026-06-30", "q.total_assets, q.total_liabilities, q.total_equity"
        )
        assert None not in (ta, tl, te), ticker


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
