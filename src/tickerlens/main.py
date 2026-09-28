from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from tickerlens.models.database import create_tables
from tickerlens.routes import company

@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Idempotent: creates any missing tables (e.g. after a model is added).
    create_tables()
    yield


app = FastAPI(title="Tickerlens", lifespan=_lifespan)

_BASE = Path(__file__).parent
app.mount("/static", StaticFiles(directory=_BASE / "static"), name="static")

templates = Jinja2Templates(directory=_BASE / "templates")

app.include_router(company.router)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc) -> HTMLResponse:
    """Render a friendly HTML 404 page instead of FastAPI's default JSON."""
    detail = exc.detail if hasattr(exc, "detail") else None
    return templates.TemplateResponse(
        request=request,
        name="404.html",
        context={"detail": detail},
        status_code=404,
    )
