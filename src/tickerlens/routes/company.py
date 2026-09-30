from __future__ import annotations

import io
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from tickerlens.services.financials import (
    CompanyNotFoundError,
    DetailContext,
    FinancialsService,
    build_history_zip,
    build_period_csv,
    download_filename,
)
from tickerlens.services.search import get_search_entries, search_companies

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
_svc = FinancialsService()


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request, name="index.html", context={"watchlist": _svc.get_watchlist()}
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
            overview = _svc.get_overview(ticker)
        except Exception as exc:
            raise HTTPException(status_code=404, detail=f"Could not fetch data for {ticker}: {exc}") from exc
    return templates.TemplateResponse(
        request=request,
        name="company/overview.html",
        context={
            "overview": overview,
            "valuation": _svc.get_valuation(ticker),
            "signal_change": _svc.get_signal_change(ticker),
            "watching": _svc.is_watching(ticker),
        },
    )


@router.post("/company/{ticker}/watch", response_class=HTMLResponse)
def watch_company(request: Request, ticker: str):
    """Pin a company to the watchlist. HTMX swaps the button in place."""
    ticker = ticker.upper()
    try:
        _svc.watch_ticker(ticker)
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request=request,
            name="partials/watch_button.html",
            context={"ticker": ticker, "watching": True},
        )
    return RedirectResponse(url=f"/company/{ticker}", status_code=303)


@router.post("/company/{ticker}/watch/remove", response_class=HTMLResponse)
def unwatch_company(request: Request, ticker: str):
    """Remove a company from the watchlist.

    HTMX swaps the watch button in place; the home-page pin form passes
    ``?next=home`` so HTMX re-renders the pins section instead and plain
    form POSTs redirect back home.
    """
    ticker = ticker.upper()
    _svc.unwatch_ticker(ticker)
    from_home = request.query_params.get("next") == "home"
    if request.headers.get("HX-Request"):
        if from_home:
            return templates.TemplateResponse(
                request=request,
                name="partials/watchlist.html",
                context={"watchlist": _svc.get_watchlist()},
            )
        return templates.TemplateResponse(
            request=request,
            name="partials/watch_button.html",
            context={"ticker": ticker, "watching": False},
        )
    return RedirectResponse(
        url="/" if from_home else f"/company/{ticker}", status_code=303
    )


@router.post("/watchlist/refresh", response_class=HTMLResponse)
def refresh_watchlist(request: Request):
    """Refresh Yahoo quotes for every watched company (PRD §4.6, slice 2).

    HTMX swaps the pins section in place; plain form POST redirects home.
    """
    _svc.refresh_watchlist_quotes()
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request=request,
            name="partials/watchlist.html",
            context={"watchlist": _svc.get_watchlist()},
        )
    return RedirectResponse(url="/", status_code=303)


@router.get("/company/{ticker}/detail", response_class=HTMLResponse)
def company_detail(
    request: Request,
    ticker: str,
    granularity: Literal["quarterly", "yearly"] = "quarterly",
    quarter: str | None = None,
    year: int | None = None,
    chart_from: str | None = None,
    chart_to: str | None = None,
) -> HTMLResponse:
    ticker = ticker.upper()
    try:
        ctx = _svc.get_detail(
            ticker, granularity=granularity, selected_quarter=quarter, selected_year=year,
            chart_from=chart_from, chart_to=chart_to,
        )
    except CompanyNotFoundError:
        try:
            _svc.fetch_and_persist(ticker, periods=8)
            _svc.enrich_company(ticker)
            ctx = _svc.get_detail(
                ticker, granularity=granularity, selected_quarter=quarter, selected_year=year,
                chart_from=chart_from, chart_to=chart_to,
            )
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request=request,
        name="company/detail.html",
        context={"ctx": ctx},
    )


@router.get("/company/{ticker}/compare", response_class=HTMLResponse)
def company_compare(
    request: Request,
    ticker: str,
    period_a: str | None = None,
    period_b: str | None = None,
    preset: Literal["yoy", "qoq", "5y"] | None = None,
    mode: Literal["quarterly", "yearly"] = "quarterly",
    year_a: int | None = None,
    year_b: int | None = None,
) -> HTMLResponse:
    """Side-by-side compare of two quarters or two fiscal years (PRD §4.2)."""
    ticker = ticker.upper()
    try:
        ctx = _svc.get_compare(
            ticker, period_a=period_a, period_b=period_b, preset=preset,
            mode=mode, year_a=year_a, year_b=year_b,
        )
    except CompanyNotFoundError:
        try:
            _svc.fetch_and_persist(ticker, periods=8)
            _svc.enrich_company(ticker)
            ctx = _svc.get_compare(
                ticker, period_a=period_a, period_b=period_b, preset=preset,
                mode=mode, year_a=year_a, year_b=year_b,
            )
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request=request,
        name="company/compare.html",
        context={"ctx": ctx},
    )


@router.get("/company/{ticker}/detail/data", response_class=HTMLResponse)
def company_detail_data(
    request: Request,
    ticker: str,
    granularity: Literal["quarterly", "yearly"] = "quarterly",
    quarter: str | None = None,
    year: int | None = None,
    chart_from: str | None = None,
    chart_to: str | None = None,
) -> HTMLResponse:
    """HTMX endpoint — returns only the swappable data section of the detail page."""
    ticker = ticker.upper()
    try:
        ctx = _svc.get_detail(
            ticker, granularity=granularity, selected_quarter=quarter, selected_year=year,
            chart_from=chart_from, chart_to=chart_to,
        )
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request=request,
        name="partials/detail_data.html",
        context={"ctx": ctx},
    )


@router.get("/company/{ticker}/detail/download")
def download_period_csv(
    request: Request,
    ticker: str,
    granularity: Literal["quarterly", "yearly"] = "quarterly",
    quarter: str | None = None,
    year: int | None = None,
) -> StreamingResponse:
    """Per-period CSV export of the selected period's financials (PRD §4.3 #7)."""
    ticker = ticker.upper()
    try:
        ctx = _svc.get_detail(
            ticker, granularity=granularity, selected_quarter=quarter, selected_year=year
        )
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    payload = build_period_csv(ctx).encode("utf-8")
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{download_filename(ctx)}"'},
    )


@router.get("/company/{ticker}/download/history.zip")
def download_history_zip(ticker: str) -> StreamingResponse:
    """Full-history ZIP of per-period CSVs (PRD §4.8, first slice).

    One ``{TICKER}/{TICKER}_{PERIOD}.csv`` per stored quarter. Synchronous,
    in-memory — fine at personal-use scale. CSV-only for now (no PDFs yet).
    """
    ticker = ticker.upper()
    try:
        zip_ticker, entries = _svc.get_history_zip_entries(ticker)
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    payload = build_history_zip(zip_ticker, entries)
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_ticker}_history.zip"'},
    )


@router.get("/company/{ticker}/compare/download")
def download_compare_zip(
    ticker: str,
    period_a: str | None = None,
    period_b: str | None = None,
    preset: Literal["yoy", "qoq", "5y"] | None = None,
    mode: Literal["quarterly", "yearly"] = "quarterly",
    year_a: int | None = None,
    year_b: int | None = None,
) -> StreamingResponse:
    """Compare-view ZIP: both periods' CSVs + summary CSV (PRD §4.8, second slice).

    Mirrors the compare page's parameters so the archive matches the screen.
    """
    ticker = ticker.upper()
    try:
        zip_ticker, entries = _svc.get_compare_zip_entries(
            ticker,
            period_a=period_a,
            period_b=period_b,
            preset=preset,
            mode=mode,
            year_a=year_a,
            year_b=year_b,
        )
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    payload = build_history_zip(zip_ticker, entries)
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_ticker}_compare.zip"'},
    )
@router.get("/company/{ticker}/download/range.zip")
def download_range_zip(
    ticker: str,
    chart_from: str | None = None,
    chart_to: str | None = None,
) -> StreamingResponse:
    """Range-view ZIP: per-quarter CSVs for the chart window + summary CSV.

    Mirrors the detail view's ``chart_from``/``chart_to`` range selectors
    (PRD §4.8, third slice) so the archive matches the chart on screen.
    """
    ticker = ticker.upper()
    try:
        zip_ticker, entries = _svc.get_range_zip_entries(
            ticker, chart_from=chart_from, chart_to=chart_to
        )
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    payload = build_history_zip(zip_ticker, entries)
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_ticker}_range.zip"'},
    )


@router.get("/api/search")
def api_search(q: str = "") -> dict:
    """Autocomplete suggestions for the search combobox (PRD §4.10).

    Matches ticker and company name with ranked suggestions; the client
    navigates to ``/company/{ticker}``, which resolves the CIK live.
    """
    entries = get_search_entries(_svc.edgar_client)
    return {"results": [r.model_dump() for r in search_companies(q, entries)]}


@router.post("/company/{ticker}/refresh", response_class=HTMLResponse)
def refresh_company(request: Request, ticker: str) -> HTMLResponse:
    """Re-fetch EDGAR data and enrich from Yahoo + Wikipedia."""
    ticker = ticker.upper()
    try:
        _svc.fetch_and_persist(ticker, periods=8)
        _svc.enrich_company(ticker)
        overview = _svc.get_overview(ticker)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request=request,
        name="company/overview.html",
        context={
            "overview": overview,
            "valuation": _svc.get_valuation(ticker),
            "signal_change": _svc.get_signal_change(ticker),
            "watching": _svc.is_watching(ticker),
        },
    )
