"""FastAPI application: API under /api, built web UI served from frontend/dist."""

from __future__ import annotations

import hmac
import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from .config import Settings, get_settings
from .db import create_pool
from .identity import SESSION_COOKIE, Identity, key_hash, make_session, resolve_identity
from .migrate import apply_migrations
from .routes_catalog import router as catalog_router
from .routes_org import router as org_router
from .routes_plan import router as plan_router
from .routes_users import router as users_router

log = logging.getLogger("travel_planner")


class Login(BaseModel):
    email: str
    passcode: str


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
    app.include_router(org_router)
    app.include_router(catalog_router)
    app.include_router(plan_router)
    app.include_router(users_router)

    @app.exception_handler(RequestValidationError)
    async def friendly_validation_error(_: Request, exc: RequestValidationError):
        parts = [f"{'.'.join(str(x) for x in e['loc'][1:]) or 'request'}: {e['msg']}" for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": "Please check the form. " + "; ".join(parts)})

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
            "person_id": identity.person_id,
            "roles": list(identity.roles),
        }

    failures: list[float] = []  # timestamps of recent failed sign-ins (in memory, demo only)

    @app.get("/api/auth/mode")
    def auth_mode() -> dict:
        return {"mode": "passcode" if settings.app_env == "demo" else "sso"}

    @app.post("/api/auth/login")
    def login(body: Login, response: Response, request: Request) -> dict:
        if settings.app_env != "demo":
            raise HTTPException(status_code=404)
        now = time.time()
        failures[:] = [t for t in failures if now - t < 60]
        if len(failures) >= 10:
            raise HTTPException(status_code=429, detail="Too many attempts. Please wait a minute.")
        if not hmac.compare_digest(body.passcode, settings.demo_passcode):
            failures.append(now)
            time.sleep(1)
            raise HTTPException(status_code=401, detail="The access code is not correct.")
        kh = key_hash(body.email, settings.identity_key)  # the e-mail itself is dropped here
        if settings.demo_first_login_admin:
            with app.state.pool.connection() as conn:
                has_admin = conn.execute("SELECT 1 FROM user_role WHERE role = 'administrator'").fetchone()
                if not has_admin:
                    row = conn.execute(
                        "INSERT INTO person(full_name, sso_key_hash) VALUES ('Demo Administrator', %s) "
                        "ON CONFLICT (sso_key_hash) DO UPDATE SET active = true RETURNING id",
                        (kh,),
                    ).fetchone()
                    conn.execute(
                        "INSERT INTO user_role(person_id, role) VALUES (%s, 'administrator')", (row["id"],)
                    )
        response.set_cookie(
            SESSION_COOKIE, make_session(settings, kh), max_age=settings.session_hours * 3600,
            httponly=True, secure=request.url.scheme == "https", samesite="lax",
        )
        return {"ok": True}

    @app.post("/api/auth/logout")
    def logout(response: Response) -> dict:
        response.delete_cookie(SESSION_COOKIE)
        return {"ok": True}

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

