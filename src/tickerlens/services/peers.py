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
    # Energy / Industrials / Defense / Insurance / Telecom
    "XOM": ["CVX", "COP", "EOG", "SLB", "SHEL"],
    "CAT": ["DE", "AGCO", "TEX", "PCAR", "CMI"],
    "LMT": ["RTX", "NOC", "GD", "BA", "HII"],
    "BRK.B": ["AIG", "MET", "CB", "TRV", "PGR"],
    "T": ["VZ", "TMUS", "CMCSA", "CHTR", "LUMN"],
    # Media / Retail / Consumer staples
    "DIS": ["NFLX", "WBD", "PARA", "CMCSA", "FOX"],
    "NFLX": ["DIS", "WBD", "PARA", "ROKU", "AMZN"],
    "HD": ["LOW", "WMT", "COST", "TGT", "BBY"],
    "PG": ["CL", "KMB", "UL", "EL", "CHD"],
    "NKE": ["DECK", "CROX", "SKX", "LULU", "WWW"],
    "DPZ": ["PZZA", "QSR", "YUM", "MCD", "WEN"],
    "PLUG": ["ENPH", "FSLR", "BE", "FCEL", "BLDP"],
}

# Industry fallbacks by SIC prefix. Longer (more specific) prefixes win —
# get_peers_for_company matches the longest prefix first.
_SIC_PREFIX_PEERS: dict[str, list[str]] = {
    # Tech / Semis
    "367": ["NVDA", "AMD", "INTC", "MRVL", "AVGO"],  # Semiconductors
    "737": ["MSFT", "GOOGL", "META", "ORCL", "PLTR"],  # Software & Services
    "357": ["AAPL", "HPQ", "DELL", "HPE"],  # Computer hardware
    "36": ["APH", "TEL", "JBL", "FLEX", "TDY"],  # Electronics (non-semis)
    "738": ["V", "MA", "PYPL", "FIS", "GPN"],  # Business/payment services
    "73": ["V", "PYPL", "UBER", "SHOP", "SQ"],  # Services (general)
    # Financials / Insurance
    "60": ["JPM", "BAC", "WFC", "C"],  # Commercial banking
    "61": ["SOFI", "SYF", "COF", "AXP", "DFS"],  # Credit institutions
    "62": ["GS", "MS", "GLXY", "COIN"],  # Security brokers
    "63": ["BRK.B", "AIG", "MET", "CB", "TRV"],  # Insurance carriers
    # Energy
    "131": ["XOM", "CVX", "COP", "EOG", "OXY"],  # Crude petroleum & gas
    "138": ["SLB", "HAL", "BKR", "NOV", "FTI"],  # Oil & gas field services
    "291": ["MPC", "VLO", "PSX", "XOM", "CVX"],  # Petroleum refining
    # Industrials / Defense
    "353": ["CAT", "DE", "TEX", "AGCO", "PCAR"],  # Construction machinery
    "35": ["CAT", "DE", "HON", "GE", "MMM"],  # Industrial machinery (general)
    "372": ["BA", "LMT", "RTX", "NOC", "GD"],  # Aircraft & parts
    "376": ["LMT", "RTX", "NOC", "GD", "HII"],  # Guided missiles / space
    "371": ["TSLA", "F", "GM", "RIVN"],  # Motor vehicles
    # Healthcare
    "283": ["LLY", "PFE", "JNJ", "ABBV"],  # Pharma
    "284": ["PG", "CL", "KMB", "EL", "CHD"],  # Household/consumer products
    "28": ["LIN", "SHW", "APD", "ECL", "DD"],  # Chemicals (general)
    # Consumer / Retail
    "208": ["KO", "PEP", "MNST", "KDP", "STZ"],  # Beverages
    "20": ["KO", "PEP", "HSY", "GIS", "KHC"],  # Food (general)
    "30": ["NKE", "DECK", "CROX", "SKX", "SHOO"],  # Rubber & plastics (footwear)
    "52": ["HD", "LOW", "BLDR", "TT", "WSM"],  # Building materials retail
    "53": ["WMT", "COST", "TGT", "DG", "DLTR"],  # General merchandise
    "56": ["TJX", "ROST", "BURL", "GPS", "ANF"],  # Apparel retail
    "59": ["AMZN", "BBY", "DKS", "TSCO", "ULTA"],  # Misc retail
    "596": ["AMZN", "EBAY", "ETSY"],  # Electronic shopping
    # Telecom / Media / Transport / Wholesale
    "48": ["T", "VZ", "TMUS", "CMCSA", "CHTR"],  # Telecom
    "781": ["DIS", "NFLX", "WBD", "PARA", "EA"],  # Motion pictures
    "784": ["DIS", "NFLX", "WBD", "PARA", "EA"],  # Video rental/entertainment
    "799": ["DIS", "NFLX", "WBD", "PARA", "EA"],  # Amusement & recreation
    "45": ["DAL", "UAL", "AAL", "LUV", "ALK"],  # Air transportation
    "47": ["FDX", "UPS", "XPO", "JBHT", "CHRW"],  # Transport services
    "50": ["GWW", "FAST", "WSO", "MSM", "POOL"],  # Durable wholesale
    "51": ["SYY", "USFD", "PFGC", "CHEF", "UNFI"],  # Nondurable wholesale
    # Utilities / REITs
    "491": ["NEE", "DUK", "SO"],  # Electric services
    "49": ["NEE", "DUK", "SO", "D", "AEP"],  # Utilities (general)
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

    # 3. SIC prefix fallback — longest (most specific) prefix wins
    if sic:
        sic_str = str(sic).strip()
        for prefix in sorted(_SIC_PREFIX_PEERS, key=len, reverse=True):
            if sic_str.startswith(prefix):
                candidates.extend(_SIC_PREFIX_PEERS[prefix])
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
