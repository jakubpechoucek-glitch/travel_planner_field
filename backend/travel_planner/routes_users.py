"""User administration (administrators only). E-mail addresses are hashed and never stored, logged or returned."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from . import users as u
from .catalog import CatalogError
from .identity import Identity
from .routes_org import require_roles

router = APIRouter(prefix="/api/admin/users")
admin = require_roles("administrator")


def _run(request: Request, fn, *args, commit: bool = True):
    """One transaction per request; catalog errors become HTTP errors, a preview rolls back."""
    with request.app.state.pool.connection() as conn:
        try:
            result = fn(conn, *args)
            conn.commit() if commit else conn.rollback()
            return result
        except CatalogError as exc:
            conn.rollback()
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
        except Exception:
            conn.rollback()
            raise


def _secret(request: Request) -> str:
    return request.app.state.settings.identity_key


def _bootstrap(request: Request) -> bool:
    return bool(request.app.state.settings.bootstrap_hashes)


@router.get("/meta")
def meta(request: Request, _: Identity = Depends(admin)) -> dict:
    return _run(request, u.meta, _bootstrap(request), commit=False)


@router.get("")
def list_users(request: Request, q: str | None = Query(None, max_length=80), role: str | None = None,
               login: Literal["linked", "unlinked"] | None = None, active: bool | None = True,
               limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
               _: Identity = Depends(admin)) -> dict:
    return _run(request, u.list_users, q, role, login, active, limit, offset, commit=False)


@router.post("", status_code=201)
def create_user(body: u.PersonIn, request: Request, who: Identity = Depends(admin)) -> dict:
    return _run(request, u.create_user, body, who.person_id)


@router.post("/bulk-login")
def bulk_login(body: u.BulkIn, request: Request, commit: bool = Query(False), who: Identity = Depends(admin)) -> dict:
    """Link many sign-ins from pasted lines. The preview (default) changes nothing."""
    return _run(request, u.bulk_login, body, _secret(request), commit, who.person_id, commit=commit)


@router.post("/suggest-roles")
def suggest_roles(request: Request, commit: bool = Query(False), who: Identity = Depends(admin)) -> dict:
    return _run(request, u.suggest_roles, commit, who.person_id, commit=commit)


@router.get("/{person_id}")
def get_user(person_id: int, request: Request, _: Identity = Depends(admin)) -> dict:
    return _run(request, u.get_user, person_id, commit=False)


@router.put("/{person_id}")
def update_user(person_id: int, body: u.PersonUpdate, request: Request, who: Identity = Depends(admin)) -> dict:
    return _run(request, u.update_user, person_id, body, who.person_id, _bootstrap(request))


@router.post("/{person_id}/login")
def link_login(person_id: int, body: u.LoginIn, request: Request, who: Identity = Depends(admin)) -> dict:
    return _run(request, u.link_login, person_id, body, _secret(request), who.person_id)


@router.delete("/{person_id}/login")
def unlink_login(person_id: int, request: Request, who: Identity = Depends(admin)) -> dict:
    return _run(request, u.unlink_login, person_id, who.person_id, _bootstrap(request))


@router.post("/{person_id}/roles", status_code=201)
def add_role(person_id: int, body: u.RoleIn, request: Request, who: Identity = Depends(admin)) -> dict:
    return _run(request, u.add_role, person_id, body, who.person_id)


@router.delete("/{person_id}/roles/{role_id}")
def remove_role(person_id: int, role_id: int, request: Request, who: Identity = Depends(admin)) -> dict:
    return _run(request, u.remove_role, person_id, role_id, who.person_id, _bootstrap(request))
