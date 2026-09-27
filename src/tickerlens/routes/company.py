from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from tickerlens.data.yahoo import PriceHistory, PriceRange
from tickerlens.services.financials import CompanyNotFoundError, FinancialsService, DetailContext
from tickerlens.services.watchlist import WatchlistService

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
_svc = FinancialsService()
_watchlist_svc = WatchlistService()


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    pinned_companies = _watchlist_svc.get_watchlist(pinned_only=True)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"pinned_companies": pinned_companies},
    )


@router.get("/company/{ticker}", response_class=HTMLResponse)
def company_overview(request: Request, ticker: str) -> HTMLResponse:
    ticker = ticker.upper()
    try:
        overview = _svc.get_overview(ticker)
    except CompanyNotFoundError:
        # No local data yet — fetch on first visit
        try:
            _svc.fetch_and_persist(ticker, periods=8)
            _svc.enrich_company(ticker)
            _svc.enrich_press_releases(ticker, periods=8)
            overview = _svc.get_overview(ticker)
        except Exception as exc:
            raise HTTPException(status_code=404, detail=f"Could not fetch data for {ticker}: {exc}") from exc

    is_pinned = _watchlist_svc.is_pinned(ticker)
    return templates.TemplateResponse(
        request=request,
        name="company/overview.html",
        context={"overview": overview, "is_pinned": is_pinned},
    )



@router.get("/company/{ticker}/detail", response_class=HTMLResponse)
def company_detail(
    request: Request,
    ticker: str,
    granularity: Literal["quarterly", "yearly"] = "quarterly",
    quarter: str | None = None,
    year: int | None = None,
    mode: Literal["single", "range"] = "single",
    range_start: str | None = None,
    range_end: str | None = None,
) -> HTMLResponse:
    ticker = ticker.upper()
    try:
        ctx = _svc.get_detail(
            ticker,
            granularity=granularity,
            selected_quarter=quarter,
            selected_year=year,
            mode=mode,
            range_start=range_start,
            range_end=range_end,
        )
    except CompanyNotFoundError:
        try:
            _svc.fetch_and_persist(ticker, periods=8)
            _svc.enrich_company(ticker)
            _svc.enrich_press_releases(ticker, periods=8)
            ctx = _svc.get_detail(
                ticker,
                granularity=granularity,
                selected_quarter=quarter,
                selected_year=year,
                mode=mode,
                range_start=range_start,
                range_end=range_end,
            )
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    is_pinned = _watchlist_svc.is_pinned(ticker)
    return templates.TemplateResponse(
        request=request,
        name="company/detail.html",
        context={"ctx": ctx, "exported_on": dt.date.today(), "is_pinned": is_pinned},
    )



@router.get("/company/{ticker}/detail/data", response_class=HTMLResponse)
def company_detail_data(
    request: Request,
    ticker: str,
    granularity: Literal["quarterly", "yearly"] = "quarterly",
    quarter: str | None = None,
    year: int | None = None,
    mode: Literal["single", "range"] = "single",
    range_start: str | None = None,
    range_end: str | None = None,
) -> HTMLResponse:
    """HTMX endpoint — returns only the swappable data section of the detail page."""
    ticker = ticker.upper()
    try:
        ctx = _svc.get_detail(
            ticker,
            granularity=granularity,
            selected_quarter=quarter,
            selected_year=year,
            mode=mode,
            range_start=range_start,
            range_end=range_end,
        )
    except CompanyNotFoundError as exc:
        try:
            _svc.fetch_and_persist(ticker, periods=8)
            _svc.enrich_company(ticker)
            _svc.enrich_press_releases(ticker, periods=8)
            ctx = _svc.get_detail(
                ticker,
                granularity=granularity,
                selected_quarter=quarter,
                selected_year=year,
                mode=mode,
                range_start=range_start,
                range_end=range_end,
            )
        except Exception:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request=request,
        name="partials/detail_data.html",
        context={"ctx": ctx},
    )


@router.get("/company/{ticker}/export-zip")
def company_export_zip(
    ticker: str,
    range_start: str | None = None,
    range_end: str | None = None,
) -> Response:
    """Download an organized ZIP archive of financial statements CSV, press releases, and filings README."""
    ticker = ticker.upper()
    try:
        zip_bytes = _svc.export_zip(ticker, range_start=range_start, range_end=range_end)
    except CompanyNotFoundError:
        try:
            _svc.fetch_and_persist(ticker, periods=8)
            _svc.enrich_company(ticker)
            _svc.enrich_press_releases(ticker, periods=8)
            zip_bytes = _svc.export_zip(ticker, range_start=range_start, range_end=range_end)
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    filename = f"{ticker}_earnings_export.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )



@router.get("/company/{ticker}/price-history", response_model=PriceHistory)
def company_price_history(
    ticker: str,
    range_key: PriceRange = "1y",
) -> PriceHistory:
    """Return adjusted Yahoo price history for the interactive stock chart."""
    return _svc.price_history(ticker.upper(), range_key)


@router.post("/company/{ticker}/refresh", response_class=HTMLResponse)
def refresh_company(request: Request, ticker: str) -> HTMLResponse:
    """Re-fetch EDGAR data and enrich from Yahoo + Wikipedia."""
    ticker = ticker.upper()
    try:
        _svc.fetch_and_persist(ticker, periods=8)
        _svc.enrich_company(ticker)
        # Adds up to ~16 serial EDGAR fetches (8-K index + exhibit per quarter,
        # throttled and disk-cached). Keep further enrichment off this hot path.
        _svc.enrich_press_releases(ticker, periods=8)
        overview = _svc.get_overview(ticker)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request=request,
        name="company/overview.html",
        context={"overview": overview},
    )
