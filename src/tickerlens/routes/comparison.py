from __future__ import annotations

from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from tickerlens.services.comparison import ComparisonService

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
_comparison_svc = ComparisonService()


@router.get("/compare", response_class=HTMLResponse)
def compare_page(
    request: Request,
    tickers: str = "NVDA,INTC,MRVL",
    metric: str = "revenue_yoy",
) -> HTMLResponse:
    """Full-page view for comparing 2-5 companies side-by-side."""
    ctx = _comparison_svc.get_comparison(tickers=tickers, metric=metric)
    return templates.TemplateResponse(
        request=request,
        name="company/compare.html",
        context={"ctx": ctx, "metric": metric},
    )


@router.get("/compare/chart", response_class=HTMLResponse)
def compare_chart_partial(
    request: Request,
    tickers: str = "NVDA,INTC,MRVL",
    metric: str = "revenue_yoy",
) -> HTMLResponse:
    """HTMX endpoint — returns updated chart container with new metric."""
    ctx = _comparison_svc.get_comparison(tickers=tickers, metric=metric)
    return templates.TemplateResponse(
        request=request,
        name="partials/compare_chart.html",
        context={"ctx": ctx, "metric": metric},
    )
