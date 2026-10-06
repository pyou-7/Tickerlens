from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tickerlens.models.base import Base
from tickerlens.models.company import Company
from tickerlens.services.peers import get_peers_for_company, PeerItem


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as sess:
        yield sess


def test_get_peers_curated() -> None:
    peers = get_peers_for_company("NVDA")
    assert len(peers) > 0
    tickers = [p.ticker for p in peers]
    assert "AMD" in tickers
    assert "NVDA" not in tickers  # does not include self


def test_get_peers_marks_stored_companies(session: Session) -> None:
    c1 = Company(cik="0001045810", name="NVIDIA CORP", ticker="NVDA", sic="3674")
    c2 = Company(cik="0000002488", name="ADVANCED MICRO DEVICES INC", ticker="AMD", sic="3674")
    c3 = Company(cik="0000050863", name="INTEL CORP", ticker="INTC", sic="3674")
    session.add_all([c1, c2, c3])
    session.commit()

    peers = get_peers_for_company("NVDA", sic="3674", session=session)
    amd_peer = next((p for p in peers if p.ticker == "AMD"), None)
    assert amd_peer is not None
    assert amd_peer.is_stored is True
    assert amd_peer.name == "ADVANCED MICRO DEVICES INC"


def test_get_peers_sic_discovery(session: Session) -> None:
    # Company with no curated peers, but other stored companies in same SIC
    c1 = Company(cik="0000000001", name="Custom Chip A", ticker="CHIP1", sic="3674")
    c2 = Company(cik="0000000002", name="Custom Chip B", ticker="CHIP2", sic="3674")
    session.add_all([c1, c2])
    session.commit()

    peers = get_peers_for_company("CHIP1", sic="3674", session=session)
    tickers = [p.ticker for p in peers]
    assert "CHIP2" in tickers
    assert "CHIP1" not in tickers


# --- Batch 20: peer-coverage gaps (12 stored companies had zero peers) ---

def test_curated_peers_new_flagships() -> None:
    cases = {
        "XOM": "CVX",
        "CAT": "DE",
        "LMT": "RTX",
        "BRK.B": "AIG",
        "T": "VZ",
        "DIS": "NFLX",
        "NFLX": "DIS",
        "HD": "LOW",
        "PG": "CL",
        "NKE": "DECK",
        "DPZ": "PZZA",
        "PLUG": "ENPH",
    }
    for ticker, expected in cases.items():
        peers = get_peers_for_company(ticker)
        tickers = [p.ticker for p in peers]
        assert expected in tickers, f"{ticker}: expected {expected} in {tickers}"
        assert ticker not in tickers, f"{ticker}: self must be excluded"


def test_sic_prefix_fallback_uncurated_ticker() -> None:
    # A ticker with no curated entry and no stored peers falls back to its
    # industry prefix list (verified gap: XOM/LMT/CAT/BRK.B got zero peers).
    peers = get_peers_for_company("OIL1", sic="1311")
    assert [p.ticker for p in peers] == ["XOM", "CVX", "COP", "EOG", "OXY"]


def test_sic_prefix_longest_match_wins() -> None:
    # 283 (pharma) must beat the new, more general 28 (chemicals) prefix.
    pharma = get_peers_for_company("RX1", sic="2836")
    assert [p.ticker for p in pharma] == ["LLY", "PFE", "JNJ", "ABBV"]
    # 367 (semis) must beat the new, more general 36 (electronics) prefix.
    semis = get_peers_for_company("CHIP9", sic="3674")
    assert [p.ticker for p in semis] == ["NVDA", "AMD", "INTC", "MRVL", "AVGO"]
    # ...but the general prefix applies when no specific one matches.
    chem = get_peers_for_company("CHEM1", sic="2819")
    assert [p.ticker for p in chem] == ["LIN", "SHW", "APD", "ECL", "DD"]
    elec = get_peers_for_company("ELC1", sic="3621")
    assert [p.ticker for p in elec] == ["APH", "TEL", "JBL", "FLEX", "TDY"]


def test_sic_prefix_insurance_and_telecom() -> None:
    ins = get_peers_for_company("INS1", sic="6331")
    assert [p.ticker for p in ins] == ["BRK.B", "AIG", "MET", "CB", "TRV"]
    tel = get_peers_for_company("TEL1", sic="4813")
    assert [p.ticker for p in tel] == ["T", "VZ", "TMUS", "CMCSA", "CHTR"]


def test_sic_prefix_curated_wins_over_prefix(session: Session) -> None:
    # Curated entries take precedence over the prefix fallback for the same
    # industry (BRK.B is in both the 63 list and the curated map).
    peers = get_peers_for_company("BRK.B", sic="6331", session=session)
    assert [p.ticker for p in peers] == ["AIG", "MET", "CB", "TRV", "PGR"]


def test_sic_prefix_limit_and_dedupe() -> None:
    peers = get_peers_for_company("OIL1", sic="1311", limit=3)
    assert len(peers) == 3
    assert len({p.ticker for p in peers}) == 3
