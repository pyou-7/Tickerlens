"""Balance-sheet mixed-filing basis reconciliation — batch 60.

Round-17 hunt found Darden's FY2025Q2 quarter rendering Assets !=
Liabilities + Equity by $421M: Darden's Q2 FY2026 10-Q tags its segment-note
"Consolidated" total-assets column (Nov 23, 2025: $12,940.2M) with a stale
2024-11-24 context, so per-metric latest-filed-wins picked Assets from the
FY2026-Q2 filing while Liabilities/Equity came from the original FY2025-Q2
filing. ``_reconcile_balance_sheet_identity`` repairs this by falling back
to the earliest-filed single filing whose own legs close the identity.
"""

import datetime as dt

from tickerlens.data.xbrl import (
    Metric,
    _balance_sheet_facts,
    _reconcile_balance_sheet_identity,
    extract_recent_quarterly_financials,
)

ACCN_A = "0000940944-25-000003"  # Darden Q2 FY2025 10-Q, filed 2025-01-02
ACCN_B = "0000940944-25-000071"  # Darden Q2 FY2026 10-Q, filed 2025-12-30


def _instant(end: str, val: float, filed: str, accn: str | None = None) -> dict:
    fact = {
        "end": end,
        "val": val,
        "fy": 2025,
        "fp": "Q2",
        "form": "10-Q",
        "filed": filed,
    }
    if accn is not None:
        fact["accn"] = accn
    return fact


def _rev(start: str, end: str, val: float) -> dict:
    return {
        "start": start,
        "end": end,
        "val": val,
        "fy": 2025,
        "fp": "Q2",
        "form": "10-Q",
        "filed": "2025-01-02",
    }


def _dri_shaped() -> dict:
    """Mirror Darden's 2024-11-24 quarter: original filing reports
    A=12,519.2M/L=10,448.3M/E=2,070.9M (closes); the later filing's
    misdated segment-note fact reports A=12,940.2M for the same end."""
    end = "2024-11-24"
    return {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {"USD": [_rev("2024-08-26", end, 2_900_000_000)]}
                },
                "Assets": {
                    "units": {
                        "USD": [
                            _instant(end, 12_519_200_000, "2025-01-02", ACCN_A),
                            _instant(end, 12_940_200_000, "2025-12-30", ACCN_B),
                        ]
                    }
                },
                "Liabilities": {
                    "units": {
                        "USD": [_instant(end, 10_448_300_000, "2025-01-02", ACCN_A)]
                    }
                },
                "StockholdersEquity": {
                    "units": {
                        "USD": [_instant(end, 2_070_900_000, "2025-01-02", ACCN_A)]
                    }
                },
            }
        }
    }


def test_mixed_filing_basis_reconciled_to_closing_filing() -> None:
    rows = extract_recent_quarterly_financials(
        _dri_shaped(), fiscal_year_end="0525", periods=4
    )
    assert len(rows) == 1
    row = rows[0]
    # The misdated $12,940.2M segment-note fact must not survive: the
    # original filing's self-consistent basis wins.
    assert row.total_assets == 12_519_200_000
    assert row.total_liabilities == 10_448_300_000
    assert row.total_equity == 2_070_900_000
    assert (
        row.total_assets
        == row.total_liabilities + row.total_equity
    )


def test_reconcile_prefers_earliest_closing_basis() -> None:
    """Two self-consistent bases exist; the earliest-filed one wins."""
    end = "2024-11-24"
    facts = _dri_shaped()
    usd = facts["facts"]["us-gaap"]["Assets"]["units"]["USD"]
    # A third filing (filed between) with its own closing basis.
    accn_c = "0000940944-25-000040"
    usd.append(_instant(end, 12_600_000_000, "2025-06-02", accn_c))
    facts["facts"]["us-gaap"]["Liabilities"]["units"]["USD"].append(
        _instant(end, 10_529_100_000, "2025-06-02", accn_c)
    )
    facts["facts"]["us-gaap"]["StockholdersEquity"]["units"]["USD"].append(
        _instant(end, 2_070_900_000, "2025-06-02", accn_c)
    )
    rows = extract_recent_quarterly_financials(
        facts, fiscal_year_end="0525", periods=4
    )
    # Latest-wins still picks the misdated B fact for Assets (filed
    # 2025-12-30), violating the identity; the earliest closing basis
    # (accn A, filed 2025-01-02) must win over accn C.
    assert rows[0].total_assets == 12_519_200_000


def test_reconcile_noop_when_identity_holds() -> None:
    facts = _dri_shaped()
    # Later filing restates the whole basis consistently: A=12,940.2M with
    # matching legs, so latest-wins stays self-consistent.
    end = "2024-11-24"
    facts["facts"]["us-gaap"]["Liabilities"]["units"]["USD"].append(
        _instant(end, 10_869_300_000, "2025-12-30", ACCN_B)
    )
    facts["facts"]["us-gaap"]["StockholdersEquity"]["units"]["USD"].append(
        _instant(end, 2_070_900_000, "2025-12-30", ACCN_B)
    )
    rows = extract_recent_quarterly_financials(
        facts, fiscal_year_end="0525", periods=4
    )
    assert rows[0].total_assets == 12_940_200_000
    assert rows[0].total_liabilities == 10_869_300_000


def test_reconcile_noop_when_single_filing_does_not_close() -> None:
    """The filer's own books don't balance — nothing to reconcile to."""
    facts = _dri_shaped()
    # Drop the original filing's Assets fact: only the misdated B fact
    # remains, so the single basis genuinely doesn't close.
    usd = facts["facts"]["us-gaap"]["Assets"]["units"]["USD"]
    facts["facts"]["us-gaap"]["Assets"]["units"]["USD"] = [
        f for f in usd if f["accn"] == ACCN_B
    ]
    rows = extract_recent_quarterly_financials(
        facts, fiscal_year_end="0525", periods=4
    )
    assert rows[0].total_assets == 12_940_200_000


def test_reconcile_keeps_mezzanine_from_closing_basis() -> None:
    """SPGI-shaped: mixed basis violates; the closing basis carries
    redeemable NCI, which must survive the switch."""
    end = "2026-03-31"
    accn_b = "0001340131-26-000099"
    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {"USD": [_rev("2026-01-01", end, 4_170_000_000)]}
                },
                "Assets": {
                    "units": {
                        "USD": [
                            _instant(end, 60_792_000_000, "2026-04-28", ACCN_A),
                            # Misdated note fact, like Darden's.
                            _instant(end, 65_000_000_000, "2026-07-28", accn_b),
                        ]
                    }
                },
                "Liabilities": {
                    "units": {
                        "USD": [_instant(end, 24_587_000_000, "2026-04-28", ACCN_A)]
                    }
                },
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": {
                    "units": {
                        "USD": [_instant(end, 31_288_000_000, "2026-04-28", ACCN_A)]
                    }
                },
                "RedeemableNoncontrollingInterestEquityCarryingAmount": {
                    "units": {
                        "USD": [_instant(end, 4_917_000_000, "2026-04-28", ACCN_A)]
                    }
                },
            }
        }
    }
    rows = extract_recent_quarterly_financials(
        facts, fiscal_year_end="1231", periods=4
    )
    row = rows[0]
    assert row.total_assets == 60_792_000_000
    assert row.redeemable_nci == 4_917_000_000
    assert (
        row.total_liabilities + row.redeemable_nci + row.total_equity
        == row.total_assets
    )


def test_reconcile_direct_unit_mixed_basis() -> None:
    """Direct unit test: chosen legs span two filings and violate the
    identity; the earliest closing filing's facts replace them."""
    facts = _dri_shaped()
    chosen = {
        m: _balance_sheet_facts(facts, m, "0525")
        for m in (
            Metric.TOTAL_ASSETS,
            Metric.TOTAL_LIABILITIES,
            Metric.TOTAL_EQUITY,
        )
    }
    end = dt.date(2024, 11, 24)
    assert chosen[Metric.TOTAL_ASSETS][end].val == 12_940_200_000
    _reconcile_balance_sheet_identity(chosen, facts, "0525")
    assert chosen[Metric.TOTAL_ASSETS][end].val == 12_519_200_000
    assert chosen[Metric.TOTAL_ASSETS][end].accn == ACCN_A
