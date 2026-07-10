from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from tickerlens.services.financials import CompanyNotFoundError, FinancialsService, DetailContext

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
_svc = FinancialsService()


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="index.html")


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
            overview = _svc.get_overview(ticker)
        except Exception as exc:
            raise HTTPException(status_code=404, detail=f"Could not fetch data for {ticker}: {exc}") from exc
    return templates.TemplateResponse(
        request=request,
        name="company/overview.html",
        context={"overview": overview},
    )


@router.get("/company/{ticker}/detail", response_class=HTMLResponse)
def company_detail(
    request: Request,
    ticker: str,
    granularity: Literal["quarterly", "yearly"] = "quarterly",
    quarter: str | None = None,
    year: int | None = None,
) -> HTMLResponse:
    ticker = ticker.upper()
    try:
        ctx = _svc.get_detail(
            ticker, granularity=granularity, selected_quarter=quarter, selected_year=year
        )
    except CompanyNotFoundError:
        try:
            _svc.fetch_and_persist(ticker, periods=8)
            _svc.enrich_company(ticker)
            ctx = _svc.get_detail(
                ticker, granularity=granularity, selected_quarter=quarter, selected_year=year
            )
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request=request,
        name="company/detail.html",
        context={"ctx": ctx},
    )


@router.get("/company/{ticker}/detail/data", response_class=HTMLResponse)
def company_detail_data(
    request: Request,
    ticker: str,
    granularity: Literal["quarterly", "yearly"] = "quarterly",
    quarter: str | None = None,
    year: int | None = None,
) -> HTMLResponse:
    """HTMX endpoint — returns only the swappable data section of the detail page."""
    ticker = ticker.upper()
    try:
        ctx = _svc.get_detail(
            ticker, granularity=granularity, selected_quarter=quarter, selected_year=year
        )
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request=request,
        name="partials/detail_data.html",
        context={"ctx": ctx},
    )


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
