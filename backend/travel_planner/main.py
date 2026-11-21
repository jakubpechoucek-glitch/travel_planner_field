"""FastAPI application: API under /api, built web UI served from frontend/dist."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import Settings, get_settings
from .db import create_pool
from .identity import Identity, resolve_identity
from .migrate import apply_migrations

log = logging.getLogger("travel_planner")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        pool = create_pool(settings)
        pool.open(wait=True, timeout=30)
        app.state.pool = pool
        if settings.run_migrations:
            apply_migrations(pool, settings.migrations_dir)
        try:
            yield
        finally:
            pool.close()

    app = FastAPI(title="Travel Planner for Field Teams", version=__version__, lifespan=lifespan)
    app.state.settings = settings

    @app.get("/api/health")
    def health() -> dict:
        with app.state.pool.connection() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "version": __version__, "env": settings.app_env}

    @app.get("/api/me")
    def me(identity: Identity = Depends(resolve_identity)) -> dict:
        return {
            "signed_in": True,
            "linked": identity.person_id is not None,
            "has_access": identity.has_access,
            "name": identity.full_name,
            "roles": list(identity.roles),
        }

    dist = settings.frontend_dist
    if dist.is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(status_code=404)
            candidate = (dist / path).resolve()
            if path and candidate.is_file() and dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app

