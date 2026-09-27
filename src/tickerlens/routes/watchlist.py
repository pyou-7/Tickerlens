from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from tickerlens.services.watchlist import WatchlistService

router = APIRouter(prefix="/watchlist", tags=["watchlist"])
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
_svc = WatchlistService()


@router.get("/dashboard", response_class=HTMLResponse)
def get_dashboard(request: Request) -> HTMLResponse:
    pinned_companies = _svc.get_watchlist(pinned_only=True)
    return templates.TemplateResponse(
        request=request,
        name="partials/pinned_dashboard.html",
        context={"pinned_companies": pinned_companies},
    )


@router.post("/pin/{ticker}", response_class=HTMLResponse)
def pin_company(
    request: Request,
    ticker: str,
    view: Literal["button", "dashboard"] = "button",
) -> HTMLResponse:
    ticker = ticker.upper()
    try:
        _svc.add(ticker, pinned=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if view == "dashboard":
        pinned_companies = _svc.get_watchlist(pinned_only=True)
        return templates.TemplateResponse(
            request=request,
            name="partials/pinned_dashboard.html",
            context={"pinned_companies": pinned_companies},
        )

    return templates.TemplateResponse(
        request=request,
        name="partials/watchlist_button.html",
        context={"ticker": ticker, "is_pinned": True},
    )


@router.post("/toggle/{ticker}", response_class=HTMLResponse)

def toggle_watchlist(
    request: Request,
    ticker: str,
    view: Literal["button", "dashboard"] = "button",
) -> HTMLResponse:
    ticker = ticker.upper()
    try:
        is_pinned = _svc.toggle_pin(ticker)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if view == "dashboard":
        pinned_companies = _svc.get_watchlist(pinned_only=True)
        return templates.TemplateResponse(
            request=request,
            name="partials/pinned_dashboard.html",
            context={"pinned_companies": pinned_companies},
        )

    # Return button fragment
    return templates.TemplateResponse(
        request=request,
        name="partials/watchlist_button.html",
        context={"ticker": ticker, "is_pinned": is_pinned},
    )


@router.delete("/{ticker}", response_class=HTMLResponse)
def remove_watchlist(
    request: Request,
    ticker: str,
    view: Literal["button", "dashboard"] = "dashboard",
) -> HTMLResponse:
    ticker = ticker.upper()
    _svc.remove(ticker)

    if view == "dashboard":
        pinned_companies = _svc.get_watchlist(pinned_only=True)
        return templates.TemplateResponse(
            request=request,
            name="partials/pinned_dashboard.html",
            context={"pinned_companies": pinned_companies},
        )

    return templates.TemplateResponse(
        request=request,
        name="partials/watchlist_button.html",
        context={"ticker": ticker, "is_pinned": False},
    )
