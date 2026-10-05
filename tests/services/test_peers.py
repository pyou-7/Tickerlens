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
