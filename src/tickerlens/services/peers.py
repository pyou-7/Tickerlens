from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from tickerlens.models.company import Company
from tickerlens.data.sic import sector_for_sic

# Curated high-conviction peer maps for common public companies / industries
_CURATED_PEERS: dict[str, list[str]] = {
    # Tech / Semis
    "NVDA": ["AMD", "INTC", "MRVL", "AVGO", "QCOM", "TSM"],
    "AMD": ["NVDA", "INTC", "MRVL", "QCOM", "AVGO"],
    "INTC": ["NVDA", "AMD", "MRVL", "QCOM", "AVGO"],
    "MRVL": ["NVDA", "AMD", "AVGO", "QCOM", "INTC"],
    "AAPL": ["MSFT", "GOOGL", "AMZN", "META", "DELL"],
    "MSFT": ["GOOGL", "AMZN", "AAPL", "ORCL", "PLTR"],
    "GOOGL": ["META", "MSFT", "AMZN", "AAPL"],
    "GOOG": ["META", "MSFT", "AMZN", "AAPL"],
    "META": ["GOOGL", "MSFT", "AMZN", "AAPL", "PLTR"],
    "ORCL": ["MSFT", "PLTR", "CRM", "SAP", "IBM"],
    "PLTR": ["MSFT", "ORCL", "SNOW", "CRM", "AI"],
    "APLD": ["GLXY", "MARA", "RIOT", "CLSK", "NVDA"],
    "GLXY": ["APLD", "COIN", "MARA", "RIOT", "MS"],
    # Auto / Aerospace
    "TSLA": ["RIVN", "F", "GM", "LCID", "BYD"],
    "RKLB": ["BA", "LMT", "RTX", "NOC", "SPCE"],
    # Retail / E-commerce
    "AMZN": ["MSFT", "GOOGL", "WMT", "COST", "TGT"],
    "WMT": ["TGT", "COST", "AMZN", "DG"],
    "COST": ["WMT", "TGT", "AMZN", "BJ"],
    # Financials
    "JPM": ["BAC", "WFC", "C", "GS", "MS"],
    "BAC": ["JPM", "WFC", "C", "GS", "MS"],
    "WFC": ["JPM", "BAC", "C", "GS", "MS"],
    "GS": ["MS", "JPM", "BAC", "C"],
    "MS": ["GS", "JPM", "BAC", "C"],
    # Healthcare
    "LLY": ["JNJ", "PFE", "ABBV", "MRK", "NVO"],
    "JNJ": ["LLY", "PFE", "ABBV", "MRK", "BMY"],
    "ABBV": ["LLY", "PFE", "JNJ", "MRK", "BIIB"],
    "PFE": ["JNJ", "ABBV", "MRK", "LLY", "BMY"],
    # Consumer & Others
    "KO": ["PEP", "MNST", "KDP", "CELH"],
    "NEE": ["DUK", "SO", "AEP", "SRE"],
    "AMT": ["CCI", "SBAC", "PLD", "EQIX"],
    "DUOL": ["CHGG", "COUR", "EDTK", "RBLX"],
    "UBER": ["LYFT", "DASH", "ABNB", "GRUB"],
    "RBLX": ["U", "EA", "TTWO", "SONY"],
    "SOFI": ["UPST", "AFRM", "LC", "HOOD"],
}

# Industry fallbacks by SIC prefix
_SIC_PREFIX_PEERS: dict[str, list[str]] = {
    "367": ["NVDA", "AMD", "INTC", "MRVL", "AVGO"],  # Semiconductors
    "737": ["MSFT", "GOOGL", "META", "ORCL", "PLTR"],  # Software & Services
    "357": ["AAPL", "HPQ", "DELL", "HPE"],  # Computer hardware
    "60": ["JPM", "BAC", "WFC", "C"],  # Commercial banking
    "62": ["GS", "MS", "GLXY", "COIN"],  # Security brokers
    "283": ["LLY", "PFE", "JNJ", "ABBV"],  # Pharma
    "371": ["TSLA", "F", "GM", "RIVN"],  # Motor vehicles
    "596": ["AMZN", "EBAY", "ETSY"],  # Electronic shopping
    "491": ["NEE", "DUK", "SO"],  # Electric services
    "679": ["AMT", "PLD", "CCI", "O"],  # REITs
}


@dataclass
class PeerItem:
    ticker: str
    name: str | None = None
    is_stored: bool = False
    sector: str | None = None


def get_peers_for_company(
    ticker: str,
    sic: str | None = None,
    session: Session | None = None,
    limit: int = 5,
) -> list[PeerItem]:
    """Return top industry/sector peers for a given company.

    Considers:
    1. Curated peer map for known companies.
    2. Other companies currently stored in the database sharing the same SIC.
    3. Industry fallback mappings.

    Deduplicates, excludes the company itself, and checks which peers are
    already stored in the local SQLite database.
    """
    ticker_clean = ticker.upper().strip()
    candidates: list[str] = []

    # 1. Curated peers
    if ticker_clean in _CURATED_PEERS:
        candidates.extend(_CURATED_PEERS[ticker_clean])

    # 2. Database peers with same SIC
    stored_peers_map: dict[str, Company] = {}
    if session is not None:
        if sic:
            same_sic = session.scalars(
                select(Company).where(Company.sic == str(sic), Company.ticker != ticker_clean)
            ).all()
            for c in same_sic:
                if c.ticker:
                    candidates.append(c.ticker)

        # Build map of all stored companies for quick lookup
        all_stored = session.scalars(select(Company)).all()
        for c in all_stored:
            if c.ticker:
                stored_peers_map[c.ticker.upper()] = c

    # 3. SIC prefix fallback
    if sic:
        sic_str = str(sic).strip()
        for prefix, peers in _SIC_PREFIX_PEERS.items():
            if sic_str.startswith(prefix):
                candidates.extend(peers)
                break

    # Deduplicate while preserving order, exclude self
    seen = {ticker_clean}
    unique_candidates: list[str] = []
    for cand in candidates:
        cand_up = cand.upper().strip()
        if cand_up and cand_up not in seen:
            seen.add(cand_up)
            unique_candidates.append(cand_up)

    result: list[PeerItem] = []
    for cand in unique_candidates[:limit]:
        stored_co = stored_peers_map.get(cand)
        if stored_co:
            sec = sector_for_sic(stored_co.sic)
            result.append(
                PeerItem(
                    ticker=cand,
                    name=stored_co.name,
                    is_stored=True,
                    sector=sec,
                )
            )
        else:
            result.append(
                PeerItem(
                    ticker=cand,
                    name=None,
                    is_stored=False,
                    sector=None,
                )
            )

    return result
