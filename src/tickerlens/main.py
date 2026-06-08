from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from tickerlens.routes import company

app = FastAPI(title="Tickerlens")

_BASE = Path(__file__).parent
app.mount("/static", StaticFiles(directory=_BASE / "static"), name="static")

templates = Jinja2Templates(directory=_BASE / "templates")

app.include_router(company.router)
