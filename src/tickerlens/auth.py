"""Shared-passcode gate for the publicly hosted site.

When ``TICKERLENS_PASSCODE`` is set (Railway), every route except ``/login``,
``/logout``, ``/healthz`` and ``/static/*`` requires the visitor to know the
passcode. A correct passcode sets a signed cookie (HMAC of a fixed label,
keyed by the passcode itself, so changing the passcode invalidates old
cookies); the future iOS client can instead send
``Authorization: Bearer <passcode>``. When the env var is unset (local dev)
the gate is inactive and the site stays open — see the startup warning in
``tickerlens.main``.

Known limits (deliberate, keep scope tight): no brute-force throttling and
no CSRF token on the login form — a login CSRF can only log the victim in,
it grants nothing else. Revisit if the link is ever shared beyond friends.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from pathlib import Path
from urllib.parse import quote, unquote

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from tickerlens.config import get_settings

logger = logging.getLogger(__name__)

COOKIE_NAME = "tickerlens_auth"
COOKIE_MAX_AGE = 30 * 24 * 3600  # 30 days — friends should not re-enter often
_TOKEN_LABEL = b"tickerlens-auth-v1"

# Paths the gate never blocks. Exact match, or a prefix match on a segment
# boundary (so /login-other is not exempt, but /static/js/x.js is).
_EXEMPT = ("/login", "/logout", "/healthz", "/static")
_EXEMPT_EXACT = ("/favicon.ico",)

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
router = APIRouter()


def make_token(passcode: str) -> str:
    """Signed cookie value for a passcode (HMAC, keyed by the passcode)."""
    return hmac.new(passcode.encode(), _TOKEN_LABEL, hashlib.sha256).hexdigest()


def _safe_next(raw: str | None) -> str:
    """Return a redirect target, restricted to in-app paths (no open redirect)."""
    if not raw:
        return "/"
    target = unquote(raw)
    if target.startswith("/") and not target.startswith("//"):
        return target
    return "/"


def _is_authenticated(request: Request, passcode: str) -> bool:
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie and hmac.compare_digest(cookie, make_token(passcode)):
        return True
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return hmac.compare_digest(auth[7:].strip(), passcode)
    return False


def _is_exempt(path: str) -> bool:
    if path in _EXEMPT_EXACT:
        return True
    return any(path == p or path.startswith(p + "/") for p in _EXEMPT)


class PasscodeGateMiddleware(BaseHTTPMiddleware):
    """Redirect unauthenticated visitors to /login when the gate is on."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        passcode = get_settings().tickerlens_passcode
        if not passcode:
            return await call_next(request)
        if _is_exempt(request.url.path):
            return await call_next(request)
        if _is_authenticated(request, passcode):
            return await call_next(request)
        nxt = quote(request.url.path, safe="/%")
        if request.url.query:
            nxt += "?" + request.url.query
        return RedirectResponse(url=f"/login?next={quote(nxt, safe='')}", status_code=307)


@router.get("/login")
async def login_page(request: Request, next: str = "/"):  # noqa: A002 - `next` is the query param name
    """Render the passcode form (or bounce to / when the gate is off)."""
    if not get_settings().tickerlens_passcode:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"next": _safe_next(next), "error": False},
    )


@router.post("/login")
async def login_submit(request: Request):
    """Check the submitted passcode; on success set the auth cookie."""
    form = await request.form()
    nxt = _safe_next(str(form.get("next", "/")))
    passcode = get_settings().tickerlens_passcode
    if not passcode:
        return RedirectResponse(url="/", status_code=303)
    submitted = str(form.get("passcode", "")).strip()
    if submitted and hmac.compare_digest(submitted, passcode):
        response = RedirectResponse(url=nxt, status_code=303)
        response.set_cookie(
            COOKIE_NAME,
            make_token(passcode),
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
            path="/",
        )
        return response
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"next": nxt, "error": True},
        status_code=401,
    )


@router.get("/logout")
async def logout():
    """Clear the auth cookie and return to the login page."""
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@router.get("/healthz")
async def healthz():
    """Unauthenticated liveness probe for the host (Railway healthcheck)."""
    return JSONResponse({"status": "ok"})


def warn_if_gate_off() -> None:
    """Log a loud warning at startup when the public site has no passcode."""
    if not get_settings().tickerlens_passcode:
        logger.warning(
            "TICKERLENS_PASSCODE is not set — the passcode gate is OFF and "
            "the site is open to anyone with the URL."
        )
