from __future__ import annotations

from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from tickerlens.services.filing_watcher import FilingWatcherService

router = APIRouter(prefix="/watcher", tags=["watcher"])
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
_svc = FilingWatcherService()


@router.post("/check", response_class=HTMLResponse)
def check_filings(request: Request) -> HTMLResponse:
    """Check pinned companies for new SEC filings and return notification alert."""
    summary = _svc.check_watchlist(pinned_only=True, auto_refresh=True)
    return templates.TemplateResponse(
        request=request,
        name="partials/watcher_alert.html",
        context={"summary": summary},
    )


@router.get("/status", response_class=JSONResponse)
def watcher_status() -> JSONResponse:
    """Return JSON status of recent filing events."""
    events = _svc.get_recent_filings(limit=15)
    return JSONResponse(
        {
            "count": len(events),
            "recent_events": [
                {
                    "ticker": e.ticker,
                    "cik": e.cik,
                    "form": e.form,
                    "accession_number": e.accession_number,
                    "filing_date": str(e.filing_date),
                    "report_date": str(e.report_date) if e.report_date else None,
                    "description": e.description,
                    "is_processed": e.is_processed,
                }
                for e in events
            ],
        }
    )

