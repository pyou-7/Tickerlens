from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from tickerlens.models.database import create_tables, ensure_schema
from tickerlens.routes import company
from tickerlens.routes.company import resolve_renamed_ticker
from tickerlens.services.search import get_search_entries, search_companies

@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Idempotent: creates any missing tables (e.g. after a model is added)
    # and adds any missing columns (e.g. after a feature extends a table).
    create_tables()
    ensure_schema()
    yield


app = FastAPI(title="Tickerlens", lifespan=_lifespan)

_BASE = Path(__file__).parent
app.mount("/static", StaticFiles(directory=_BASE / "static"), name="static")

templates = Jinja2Templates(directory=_BASE / "templates")

app.include_router(company.router)


@app.middleware("http")
async def renamed_ticker_redirect(request: Request, call_next):
    """Redirect retired symbols to their current ticker (batch 119).

    A renamed symbol's SEC listing is gone, so /company/MMC can never
    resolve — without this it 404s even though the company is in the DB
    under MRSH. Only GET/HEAD are redirected: POST forms (watch/unwatch)
    keep their own semantics, and a renamed ticker there still 404s
    rather than silently acting on a different company. The full subpath
    and query string are preserved, so /company/MMC/detail?granularity=
    yearly lands on /company/MRSH/detail?granularity=yearly. 301 because
    a ticker rename is permanent.
    """
    if request.method in ("GET", "HEAD"):
        parts = request.url.path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "company":
            new_ticker = resolve_renamed_ticker(parts[1])
            if new_ticker:
                rest = "/".join(parts[2:])
                target = f"/company/{new_ticker}"
                if rest:
                    target += f"/{rest}"
                if request.url.query:
                    target += f"?{request.url.query}"
                return RedirectResponse(url=target, status_code=301)
    return await call_next(request)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc) -> HTMLResponse:
    """Render a friendly HTML 404 page instead of FastAPI's default JSON.

    For /company/{ticker} misses, suggest close matches from the same
    ranking the search box uses (PRD §4.9: an unknown ticker is never a
    dead end). Suggestion lookup is best-effort — a failure still renders
    the plain 404 page.
    """
    detail = exc.detail if hasattr(exc, "detail") else None
    suggestions: list = []
    ticker = request.path_params.get("ticker")
    if ticker:
        try:
            entries = get_search_entries(company._svc.edgar_client)
            suggestions = search_companies(str(ticker), entries)[:5]
        except Exception:
            suggestions = []
    return templates.TemplateResponse(
        request=request,
        name="404.html",
        context={"detail": detail, "suggestions": suggestions},
        status_code=404,
    )
