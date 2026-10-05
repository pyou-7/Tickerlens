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
        request=request,
        name="index.html",
        context={
            "watchlist": _svc.get_watchlist(),
            "benchmarks": _svc.get_benchmarks(),
            "popular_stocks": _svc.get_popular_stocks(),
            "upcoming_earnings": _svc.get_upcoming_earnings()[:4],
        },
    )


@router.get("/calendar", response_class=HTMLResponse)
def earnings_calendar(
    request: Request,
    filter: Literal["all", "watchlist"] = "all",
) -> HTMLResponse:
    """Earnings calendar view of upcoming reporting dates (PRD §4.5)."""
    events = _svc.get_upcoming_earnings(watchlist_only=(filter == "watchlist"))
    return templates.TemplateResponse(
        request=request,
        name="calendar.html",
        context={
            "events": events,
            "filter": filter,
        },
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
            "note": _svc.get_watchlist_note(ticker),
            "tags": _svc.get_watchlist_tags(ticker),
            "also_trades_as": _svc.get_sibling_tickers(ticker),
            "peers": _svc.get_peers(ticker),
            "ai_analysis": _svc.get_ai_analysis(ticker),
        },
    )


@router.post("/company/{ticker}/watch", response_class=HTMLResponse)
def watch_company(request: Request, ticker: str):
    """Pin a company to the watchlist. HTMX swaps the button or pins section in place."""
    ticker = ticker.upper()
    try:
        _svc.watch_ticker(ticker)
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    from_home = request.query_params.get("next") == "home"
    if request.headers.get("HX-Request"):
        if from_home:
            return templates.TemplateResponse(
                request=request,
                name="partials/watchlist.html",
                context={
                    "watchlist": _svc.get_watchlist(),
                    "benchmarks": _svc.get_benchmarks(),
                },
            )
        return templates.TemplateResponse(
            request=request,
            name="partials/watch_button.html",
            context={"ticker": ticker, "watching": True},
        )
    return RedirectResponse(
        url="/" if from_home else f"/company/{ticker}", status_code=303
    )


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
                context={
                    "watchlist": _svc.get_watchlist(),
                    "benchmarks": _svc.get_benchmarks(),
                },
            )
        return templates.TemplateResponse(
            request=request,
            name="partials/watch_button.html",
            context={"ticker": ticker, "watching": False},
        )
    return RedirectResponse(
        url="/" if from_home else f"/company/{ticker}", status_code=303
    )


@router.post("/company/{ticker}/watch/note", response_class=HTMLResponse)
async def save_watch_note(request: Request, ticker: str):
    """Save (or clear) the personal note on a watched company (PRD §4.6).

    HTMX swaps the note partial in place; plain form POSTs redirect back to
    the company page. 404 when the ticker is not on the watchlist. The form
    body is parsed directly (no python-multipart dependency — plain and
    HTMX forms both send application/x-www-form-urlencoded by default).
    """
    from urllib.parse import parse_qs

    ticker = ticker.upper()
    body = (await request.body()).decode("utf-8", "replace")
    note = parse_qs(body, keep_blank_values=True).get("note", [""])[0]
    try:
        saved = _svc.set_watchlist_note(ticker, note)
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request=request,
            name="partials/watch_note.html",
            context={"ticker": ticker, "note": saved},
        )
    return RedirectResponse(url=f"/company/{ticker}", status_code=303)


@router.post("/company/{ticker}/watch/tags", response_class=HTMLResponse)
async def save_watch_tags(request: Request, ticker: str):
    """Save (or clear) the tags on a watched company (PRD §4.6).

    Same contract as the note route: HTMX swaps the tags partial in place,
    plain form POSTs redirect back to the company page, 404 when the ticker
    is not on the watchlist. Tags arrive as one comma-separated field.
    """
    from urllib.parse import parse_qs

    ticker = ticker.upper()
    body = (await request.body()).decode("utf-8", "replace")
    tags = parse_qs(body, keep_blank_values=True).get("tags", [""])[0]
    try:
        saved = _svc.set_watchlist_tags(ticker, tags)
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request=request,
            name="partials/watch_tags.html",
            context={"ticker": ticker, "tags": saved},
        )
    return RedirectResponse(url=f"/company/{ticker}", status_code=303)


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
            context={
                "watchlist": _svc.get_watchlist(),
                "benchmarks": _svc.get_benchmarks(),
            },
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
        context={
            "ctx": ctx,
            "also_trades_as": _svc.get_sibling_tickers(ticker),
            "peers": _svc.get_peers(ticker),
        },
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
        context={"ctx": ctx, "also_trades_as": _svc.get_sibling_tickers(ticker)},
    )


@router.get("/company/{ticker}/vs/{other}", response_class=HTMLResponse)
def company_vs(request: Request, ticker: str, other: str) -> HTMLResponse:
    """Side-by-side latest-quarter comparison of two companies (PRD §4.2).

    Either side is fetched on first visit when not stored yet; 404 when a
    ticker cannot be loaded at all.
    """
    ticker, other = ticker.upper(), other.upper()
    for t in (ticker, other):
        try:
            _svc.get_detail(t)
        except CompanyNotFoundError:
            try:
                _svc.fetch_and_persist(t, periods=8)
                _svc.enrich_company(t)
            except Exception as exc:
                raise HTTPException(
                    status_code=404, detail=f"Could not fetch data for {t}: {exc}"
                ) from exc
    try:
        vs = _svc.get_company_vs(ticker, other)
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request=request,
        name="company/vs.html",
        context={"vs": vs},
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


@router.get("/company/{ticker}/download/year.zip")
def download_year_zip(
    ticker: str,
    year: int | None = None,
) -> StreamingResponse:
    """Single-year ZIP: per-quarter CSVs for one fiscal year + summary CSV.

    ``year`` is a fiscal year (e.g. 2025); an unknown year falls back to the
    latest stored fiscal year (PRD §4.8, fourth slice).
    """
    ticker = ticker.upper()
    try:
        zip_ticker, resolved_year, entries = _svc.get_year_zip_entries(
            ticker, year=year
        )
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    payload = build_history_zip(zip_ticker, entries)
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_ticker}_year_FY{resolved_year}.zip"'
        },
    )


@router.get("/company/{ticker}/tearsheet", response_class=HTMLResponse)
def company_tearsheet(request: Request, ticker: str) -> HTMLResponse:
    """Printable institutional research tearsheet / PDF export (PRD §4.8, §5.5)."""
    import datetime as dt

    ticker = ticker.upper()
    try:
        overview = _svc.get_overview(ticker)
        detail = _svc.get_detail(ticker)
        val = _svc.get_valuation(ticker)
    except CompanyNotFoundError:
        try:
            _svc.fetch_and_persist(ticker, periods=8)
            _svc.enrich_company(ticker)
            overview = _svc.get_overview(ticker)
            detail = _svc.get_detail(ticker)
            val = _svc.get_valuation(ticker)
        except Exception as exc:
            raise HTTPException(status_code=404, detail=f"Could not load {ticker}: {exc}") from exc

    now_utc = dt.datetime.now(dt.timezone.utc).strftime("%B %d, %Y at %H:%M UTC")

    return templates.TemplateResponse(
        request=request,
        name="company/tearsheet.html",
        context={
            "overview": overview,
            "detail": detail,
            "valuation": val,
            "rows": _svc.get_stored_quarters(ticker),
            "ai_analysis": _svc.get_ai_analysis(ticker),
            "as_of_date": now_utc,
        },
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
            "note": _svc.get_watchlist_note(ticker),
            "tags": _svc.get_watchlist_tags(ticker),
            "also_trades_as": _svc.get_sibling_tickers(ticker),
            "peers": _svc.get_peers(ticker),
            "ai_analysis": _svc.get_ai_analysis(ticker),
        },
    )
