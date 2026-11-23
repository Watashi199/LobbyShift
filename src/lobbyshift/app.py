"""FastAPI application factory."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api.routes import public, router
from .auth import Auth
from .core.geoip import GeoIP
from .runner import CommandError, Runner, SubprocessRunner
from .service import LobbyShift, ServiceError
from .settings import Settings
from .store import Store

log = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent / "web"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: https://cdn.jsdelivr.net",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "frame-ancestors 'none'",
    "form-action 'self'",
])


def create_app(settings: Settings | None = None, runner: Runner | None = None,
               *, background: bool = True) -> FastAPI:
    settings = settings or Settings()
    runner = runner or SubprocessRunner()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        data = settings.data_dir
        data.mkdir(parents=True, exist_ok=True)
        os.chmod(data, 0o700)
        store = Store(data / "state.db")
        auth = Auth(store, data / "cli-token")
        initial_file = data / "initial-password"
        generated = auth.ensure_initialized(settings.admin_password)
        if generated:
            fd = os.open(initial_file, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(generated + "\n")
            log.warning("Initial admin password: %s  (also in %s; change it in Settings)",
                        generated, initial_file)
        service = LobbyShift(settings, store, runner, GeoIP(data / "dbip-country-lite.mmdb"))
        app.state.store = store
        app.state.auth = auth
        app.state.service = service
        app.state.initial_password_file = initial_file
        await service.start(background=background)
        try:
            yield
        finally:
            await service.shutdown()
            store.close()

    app = FastAPI(title="LobbyShift", version=__version__, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def security(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.method in UNSAFE_METHODS:
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "Cross-origin request refused"}, status_code=403)
        response: Response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ServiceError)
    async def service_error(_: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=exc.status)

    @app.exception_handler(CommandError)
    async def command_error(_: Request, exc: CommandError) -> JSONResponse:
        log.error("%s", exc)
        return JSONResponse({"detail": str(exc)}, status_code=500)

    app.include_router(public)
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(WEB_DIR / "templates" / "index.html")

    return app
