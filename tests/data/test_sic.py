from __future__ import annotations

from tickerlens.data.sic import sector_for_sic


def test_sector_for_sic_insurance_brokers() -> None:
    """Batch 88: SIC 6400-6499 (Insurance Agents, Brokers, and Service)
    maps to "Insurance" — AON (6411) fell in the unmapped gap, so its
    overview sector was None while the valuation model priced it on the
    insurer path (batch 70)."""
    assert sector_for_sic("6411") == "Insurance"
    assert sector_for_sic(6400) == "Insurance"
    assert sector_for_sic("6499") == "Insurance"


def test_sector_for_sic_boundaries() -> None:
    assert sector_for_sic("6798") == "Real Estate"
    assert sector_for_sic("6000") == "Banking"
    assert sector_for_sic("6300") == "Insurance"
    assert sector_for_sic(None) is None
    assert sector_for_sic("not-a-sic") is None
