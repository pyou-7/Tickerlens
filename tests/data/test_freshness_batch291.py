"""Batch 291 regression tests: freshness re-seed + MTD label repair.

The stored DB had drifted behind EDGAR: 122 tickers gained 127 quarters
(Q3 FY2026 for 117; Q2+Q3 for CTSH/HCA/HUM/VMC/VRSK) on re-seed, KVUE's
final quarter landed via stored CIK after its delisting removed it from
SEC's company_tickers.json, and the 11 tickers SEC's companyfacts feed
itself is stale for (AEP/C/D/DLR/DUK/ETR/NEE/PLD/PPL/SO/SRE) carry the
pending-filing honesty note. The re-seed also exposed an MTD fiscal-label
regression (2025-09-30 flipped to FY2024 Q3 by _dedupe_period_labels),
fixed in xbrl.py and pinned here at the stored-row level.
"""
import os
import sqlite3

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB = os.path.join(REPO_ROOT, "tickerlens.db")

SEC_STALE = {"AEP", "C", "D", "DLR", "DUK", "ETR", "NEE", "PLD", "PPL", "SO", "SRE"}


def _con() -> sqlite3.Connection:
    return sqlite3.connect(DB)


def _quarters(ticker: str):
    con = _con()
    try:
        return con.execute(
            "SELECT q.period_end, q.fiscal_year, q.fiscal_period, q.revenue "
            "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = ? ORDER BY q.period_end",
            (ticker,),
        ).fetchall()
    finally:
        con.close()


def test_refreshed_tickers_carry_q3_2026() -> None:
    ko = {r[0]: r for r in _quarters("KO")}
    assert ko["2026-10-02"][3] == 13380000000.0
    ctsh = [r[0] for r in _quarters("CTSH")]
    assert ctsh[-2:] == ["2026-06-30", "2026-09-30"]


def test_kvue_final_quarter_landed() -> None:
    kvue = _quarters("KVUE")
    assert kvue[-1][0] == "2026-09-27"
    assert kvue[-1][3] == 3886000000.0


def test_mtd_labels_unique_and_correct() -> None:
    mtd = _quarters("MTD")
    labels = [(r[1], r[2]) for r in mtd]
    assert len(labels) == len(set(labels))
    by_end = {r[0]: (r[1], r[2]) for r in mtd}
    assert by_end["2025-09-30"] == (2025, "Q3")
    assert by_end["2026-09-30"] == (2026, "Q3")


def test_delisted_ticker_resolves_via_stored_mapping() -> None:
    """KVUE dropped out of SEC's company_tickers.json after delisting;
    _resolve_cik falls back to the stored ticker->CIK mapping so the
    historical page stays servable, while truly unknown tickers 404."""
    import sys

    sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
    from unittest.mock import MagicMock

    from tickerlens.services.financials import (
        CompanyNotFoundError,
        _resolve_cik,
        _stored_cik_for_ticker,
    )

    assert _stored_cik_for_ticker("KVUE") == "0001944048"
    client = MagicMock()
    client.cik_for_ticker.side_effect = KeyError("not in SEC list")
    assert _resolve_cik(client, "KVUE") == "0001944048"
    try:
        _resolve_cik(client, "ZZZZNOTREAL")
        raise AssertionError("expected CompanyNotFoundError")
    except CompanyNotFoundError:
        pass


def test_only_sec_stale_set_remains_stale() -> None:
    con = _con()
    try:
        stale = {
            t
            for t, m in con.execute(
                "SELECT c.ticker, MAX(q.period_end) FROM quarterly_financials q "
                "JOIN companies c ON c.cik = q.cik GROUP BY c.ticker"
            ).fetchall()
            if m <= "2026-03-31"
        }
        assert stale == SEC_STALE
        notes = dict(
            con.execute(
                "SELECT ticker, pending_filing_note FROM companies "
                "WHERE ticker IN ('AEP','C','D','DLR','DUK','ETR','NEE','PLD','PPL','SO','SRE')"
            ).fetchall()
        )
        assert all(notes[t] for t in SEC_STALE)
    finally:
        con.close()
