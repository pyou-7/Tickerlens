from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from tickerlens.data.sic import sector_for_sic
from tickerlens.models.company import Company
from tickerlens.models.database import get_session
from tickerlens.models.quarterly_financial import QuarterlyFinancial
from tickerlens.services.financials import (
    CompanyNotFoundError,
    FinancialsService,
    _compute_yoy,
    _pct_change,
)

logger = logging.getLogger(__name__)

PEER_COLORS = [
    "#6366f1",  # Indigo
    "#10b981",  # Emerald
    "#f59e0b",  # Amber
    "#ec4899",  # Rose
    "#06b6d4",  # Cyan
]

DEFAULT_TICKERS = ["NVDA", "INTC", "MRVL"]

PRESETS = [
    {
        "name": "Semiconductors",
        "slug": "semis",
        "tickers": ["NVDA", "INTC", "MRVL"],
    },
    {
        "name": "Mega-Cap Tech",
        "slug": "big-tech",
        "tickers": ["AAPL", "MSFT", "GOOGL", "AMZN", "META"],
    },
    {
        "name": "Enterprise Cloud",
        "slug": "cloud",
        "tickers": ["MSFT", "ORCL", "AMZN"],
    },
    {
        "name": "AI Ecosystem",
        "slug": "ai",
        "tickers": ["NVDA", "MSFT", "GOOGL", "MRVL"],
    },
]


class PeerQuarter(BaseModel):
    date: str
    label: str
    fiscal_year: int
    fiscal_period: str
    revenue: float | None = None
    revenue_yoy: float | None = None
    net_income: float | None = None
    net_income_yoy: float | None = None
    eps_diluted: float | None = None
    eps_yoy: float | None = None
    free_cash_flow: float | None = None
    free_cash_flow_yoy: float | None = None
    net_margin: float | None = None
    fcf_margin: float | None = None
    operating_cash_flow: float | None = None
    capex: float | None = None


class PeerCompany(BaseModel):
    ticker: str
    name: str
    cik: str
    color: str
    sector: str | None = None
    last_price: float | None = None
    market_cap: float | None = None
    latest_period: str
    latest_period_end: dt.date
    # Latest KPIs
    revenue: float | None = None
    revenue_yoy: float | None = None
    net_income: float | None = None
    net_income_yoy: float | None = None
    eps_diluted: float | None = None
    eps_yoy: float | None = None
    free_cash_flow: float | None = None
    free_cash_flow_yoy: float | None = None
    operating_cash_flow: float | None = None
    capex: float | None = None
    # Profitability Margins
    net_margin: float | None = None
    fcf_margin: float | None = None
    ocf_margin: float | None = None
    # Balance Sheet
    total_assets: float | None = None
    total_liabilities: float | None = None
    total_equity: float | None = None
    cash_and_equivalents: float | None = None
    debt_to_equity: float | None = None
    cash_to_assets: float | None = None
    # Historical quarters for charting
    quarters: list[PeerQuarter] = []


class ComparisonLeaderboard(BaseModel):
    top_revenue_growth: str | None = None
    top_net_margin: str | None = None
    top_fcf_margin: str | None = None
    top_fcf_growth: str | None = None
    top_market_cap: str | None = None
    top_cash: str | None = None
    lowest_debt_to_equity: str | None = None


class ComparisonContext(BaseModel):
    peers: list[PeerCompany]
    metric: str
    tickers_str: str
    selected_tickers: list[str]
    presets: list[dict[str, Any]]
    leaderboard: ComparisonLeaderboard
    chart_payload_json: str


class ComparisonService:
    def __init__(self, session: Session | None = None) -> None:
        self._session = session
        self._financials_svc = FinancialsService(session=session)

    def get_comparison(
        self,
        tickers: list[str] | str | None = None,
        metric: str = "revenue_yoy",
    ) -> ComparisonContext:
        """Fetch and assemble side-by-side financial comparison and charting data for peer tickers."""
        # Sanitize and parse ticker list
        cleaned_tickers: list[str] = []
        if isinstance(tickers, str):
            cleaned_tickers = [t.strip().upper() for t in tickers.split(",") if t.strip()]
        elif isinstance(tickers, list):
            cleaned_tickers = [t.strip().upper() for t in tickers if t and t.strip()]

        # Filter out duplicates while preserving order
        seen: set[str] = set()
        deduped: list[str] = []
        for t in cleaned_tickers:
            if t not in seen:
                seen.add(t)
                deduped.append(t)

        if not deduped:
            deduped = list(DEFAULT_TICKERS)

        # Enforce max 5 peers
        selected_tickers = deduped[:5]
        valid_metric = metric if metric in {
            "revenue_yoy",
            "net_margin",
            "fcf_margin",
            "revenue",
            "net_income",
            "free_cash_flow",
            "eps_diluted",
        } else "revenue_yoy"

        peers: list[PeerCompany] = []
        db = self._session or get_session()

        try:
            for idx, ticker in enumerate(selected_tickers):
                color = PEER_COLORS[idx % len(PEER_COLORS)]
                peer = self._build_peer(db, ticker, color)
                if peer is not None:
                    peers.append(peer)
        finally:
            if self._session is None:
                db.close()

        # Compute leaderboard highlights
        leaderboard = self._compute_leaderboard(peers)

        # Build chart payload JSON
        chart_payload = {
            "activeMetric": valid_metric,
            "peers": [
                {
                    "ticker": p.ticker,
                    "name": p.name,
                    "color": p.color,
                    "quarters": [
                        {
                            "date": q.date,
                            "label": q.label,
                            "revenue": q.revenue,
                            "revenue_yoy": q.revenue_yoy,
                            "net_income": q.net_income,
                            "net_income_yoy": q.net_income_yoy,
                            "eps_diluted": q.eps_diluted,
                            "eps_yoy": q.eps_yoy,
                            "free_cash_flow": q.free_cash_flow,
                            "free_cash_flow_yoy": q.free_cash_flow_yoy,
                            "net_margin": q.net_margin,
                            "fcf_margin": q.fcf_margin,
                            "operating_cash_flow": q.operating_cash_flow,
                            "capex": q.capex,
                        }
                        for q in p.quarters
                    ],
                }
                for p in peers
            ],
        }

        return ComparisonContext(
            peers=peers,
            metric=valid_metric,
            tickers_str=",".join(p.ticker for p in peers),
            selected_tickers=[p.ticker for p in peers],
            presets=PRESETS,
            leaderboard=leaderboard,
            chart_payload_json=json.dumps(chart_payload),
        )

    def _build_peer(self, db: Session, ticker: str, color: str) -> PeerCompany | None:
        """Build peer data for a ticker, fetching from EDGAR/Yahoo if not yet cached."""
        company = db.execute(
            select(Company).where(Company.ticker == ticker)
        ).scalar_one_or_none()

        if company is None:
            # Attempt to fetch and persist on demand (12 quarters = 3 full years for clean YoY)
            try:
                self._financials_svc.fetch_and_persist(ticker, periods=12, session=db)
                self._financials_svc.enrich_company(ticker, session=db)
                company = db.execute(
                    select(Company).where(Company.ticker == ticker)
                ).scalar_one_or_none()
            except Exception as exc:
                logger.warning(f"Could not load data for peer {ticker}: {exc}")
                return None

        if company is None:
            return None

        # Fetch quarterly financials in ascending chronological order
        all_rows: list[QuarterlyFinancial] = (
            db.execute(
                select(QuarterlyFinancial)
                .where(QuarterlyFinancial.cik == company.cik)
                .order_by(QuarterlyFinancial.period_end.asc())
            )
            .scalars()
            .all()
        )

        if not all_rows:
            return None

        latest = all_rows[-1]
        latest_label = f"{latest.fiscal_period} FY{latest.fiscal_year}"
        latest_yoy = _compute_yoy(latest, all_rows)

        # Standardize peer comparison chart to the recent 8 quarters (2-year window)
        # while using the entire history (all_rows) to accurately compute YoY
        recent_rows = all_rows[-8:]
        quarters: list[PeerQuarter] = []
        for row in recent_rows:
            row_yoy = _compute_yoy(row, all_rows)
            net_marg = (
                (row.net_income / row.revenue * 100)
                if (row.revenue and row.revenue > 0 and row.net_income is not None)
                else None
            )
            fcf_marg = (
                (row.free_cash_flow / row.revenue * 100)
                if (row.revenue and row.revenue > 0 and row.free_cash_flow is not None)
                else None
            )
            quarters.append(
                PeerQuarter(
                    date=row.period_end.isoformat(),
                    label=f"{row.fiscal_period} FY{row.fiscal_year}",
                    fiscal_year=row.fiscal_year,
                    fiscal_period=row.fiscal_period,
                    revenue=row.revenue,
                    revenue_yoy=row_yoy.revenue,
                    net_income=row.net_income,
                    net_income_yoy=row_yoy.net_income,
                    eps_diluted=row.eps_diluted,
                    eps_yoy=row_yoy.eps_diluted,
                    free_cash_flow=row.free_cash_flow,
                    free_cash_flow_yoy=row_yoy.free_cash_flow,
                    net_margin=net_marg,
                    fcf_margin=fcf_marg,
                    operating_cash_flow=row.operating_cash_flow,
                    capex=row.capex,
                )
            )

        # Latest margins
        latest_net_margin = (
            (latest.net_income / latest.revenue * 100)
            if (latest.revenue and latest.revenue > 0 and latest.net_income is not None)
            else None
        )
        latest_fcf_margin = (
            (latest.free_cash_flow / latest.revenue * 100)
            if (latest.revenue and latest.revenue > 0 and latest.free_cash_flow is not None)
            else None
        )
        latest_ocf_margin = (
            (latest.operating_cash_flow / latest.revenue * 100)
            if (latest.revenue and latest.revenue > 0 and latest.operating_cash_flow is not None)
            else None
        )

        # Balance sheet derived ratios
        debt_to_equity = (
            (latest.total_liabilities / latest.total_equity)
            if (latest.total_equity and latest.total_equity > 0 and latest.total_liabilities is not None)
            else None
        )
        cash_to_assets = (
            (latest.cash_and_equivalents / latest.total_assets * 100)
            if (latest.total_assets and latest.total_assets > 0 and latest.cash_and_equivalents is not None)
            else None
        )

        return PeerCompany(
            ticker=company.ticker or ticker,
            name=company.name,
            cik=company.cik,
            color=color,
            sector=sector_for_sic(company.sic),
            last_price=company.last_price,
            market_cap=company.market_cap,
            latest_period=latest_label,
            latest_period_end=latest.period_end,
            revenue=latest.revenue,
            revenue_yoy=latest_yoy.revenue,
            net_income=latest.net_income,
            net_income_yoy=latest_yoy.net_income,
            eps_diluted=latest.eps_diluted,
            eps_yoy=latest_yoy.eps_diluted,
            free_cash_flow=latest.free_cash_flow,
            free_cash_flow_yoy=latest_yoy.free_cash_flow,
            operating_cash_flow=latest.operating_cash_flow,
            capex=latest.capex,
            net_margin=latest_net_margin,
            fcf_margin=latest_fcf_margin,
            ocf_margin=latest_ocf_margin,
            total_assets=latest.total_assets,
            total_liabilities=latest.total_liabilities,
            total_equity=latest.total_equity,
            cash_and_equivalents=latest.cash_and_equivalents,
            debt_to_equity=debt_to_equity,
            cash_to_assets=cash_to_assets,
            quarters=quarters,
        )

    def _compute_leaderboard(self, peers: list[PeerCompany]) -> ComparisonLeaderboard:
        """Find the outperformer in key financial dimensions."""
        if not peers:
            return ComparisonLeaderboard()

        def _max_peer(attr: str) -> str | None:
            valid = [(getattr(p, attr), p.ticker) for p in peers if getattr(p, attr) is not None]
            if not valid:
                return None
            return max(valid, key=lambda x: x[0])[1]

        def _min_positive_peer(attr: str) -> str | None:
            valid = [(getattr(p, attr), p.ticker) for p in peers if getattr(p, attr) is not None and getattr(p, attr) > 0]
            if not valid:
                return None
            return min(valid, key=lambda x: x[0])[1]

        return ComparisonLeaderboard(
            top_revenue_growth=_max_peer("revenue_yoy"),
            top_net_margin=_max_peer("net_margin"),
            top_fcf_margin=_max_peer("fcf_margin"),
            top_fcf_growth=_max_peer("free_cash_flow_yoy"),
            top_market_cap=_max_peer("market_cap"),
            top_cash=_max_peer("cash_and_equivalents"),
            lowest_debt_to_equity=_min_positive_peer("debt_to_equity"),
        )
