"""FastAPI app factory.

Routes:
  GET /api/health            (open, smoke-test target)
  /api/* everything else     (behind the shared-secret auth gate + rate limit)
Built SPA (frontend/dist) is served at / when present.
"""

from __future__ import annotations

import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from .deps import require_auth
from .repo import ReadRepo
from .routers import address, comps, meta, neighborhood, report, trends
from .settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Franklin Housing", version="1.0.0")
    app.state.settings = settings
    app.state.repo = ReadRepo(settings.db_path)

    # let auth dependency see the (possibly test-injected) settings
    app.dependency_overrides[get_settings] = lambda: settings

    # rate limiting (per-IP)
    limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    origins = ["*"] if settings.cors_origins.strip() == "*" else \
        [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"],
                       allow_headers=["*"])

    @app.get("/api/health", tags=["meta"])
    def health():
        return {"ok": True}

    # all other /api routes require the shared secret
    for r in (meta.router, address.router, report.router, comps.router,
              neighborhood.router, trends.router):
        app.include_router(r, prefix="/api", dependencies=[Depends(require_auth)])

    _mount_spa(app, settings.spa_dir)
    return app


def _mount_spa(app: FastAPI, spa_dir: str) -> None:
    if not os.path.isdir(spa_dir):
        return
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=os.path.join(spa_dir, "assets")),
              name="assets")
    index = os.path.join(spa_dir, "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        candidate = os.path.join(spa_dir, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(index)


app = create_app()
