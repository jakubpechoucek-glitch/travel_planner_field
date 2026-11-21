"""Event catalog and rules: readable by everyone with access, editable by administrators."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from . import catalog as cat
from .identity import Identity, resolve_identity
from .routes_org import require_roles

router = APIRouter(prefix="/api")


def any_access(identity: Identity = Depends(resolve_identity)) -> Identity:
    if not identity.has_access:
        raise HTTPException(status_code=403, detail="You do not have access yet.")
    return identity


admin = require_roles("administrator")


def _run(request: Request, fn, *args):
    """Run a catalog change in one transaction and turn catalog errors into HTTP errors."""
    with request.app.state.pool.connection() as conn:
        try:
            result = fn(conn, *args)
            conn.commit()
            return result
        except cat.CatalogError as exc:
            conn.rollback()
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
        except Exception:
            conn.rollback()
            raise


@router.get("/catalog")
def get_catalog(request: Request, plan_year: int | None = Query(default=None), _: Identity = Depends(any_access)):
    with request.app.state.pool.connection() as conn:
        return cat.load_catalog(conn, plan_year)


@router.post("/admin/event-types", status_code=201)
def create_event_type(body: cat.EventTypeIn, request: Request, who: Identity = Depends(admin)) -> dict:
    return {"id": _run(request, cat.save_event_type, None, body, who.person_id)}


@router.put("/admin/event-types/{event_id}")
def update_event_type(event_id: int, body: cat.EventTypeIn, request: Request, who: Identity = Depends(admin)) -> dict:
    return {"id": _run(request, cat.save_event_type, event_id, body, who.person_id)}


@router.post("/admin/rules", status_code=201)
def create_rule(body: cat.RuleIn, request: Request, who: Identity = Depends(admin)) -> dict:
    return {"rule_key": _run(request, cat.create_rule, body, who.person_id)}


@router.put("/admin/rules/{rule_key}")
def update_rule(rule_key: str, body: cat.RuleIn, request: Request, who: Identity = Depends(admin)) -> dict:
    return {"rule_key": rule_key, "version": _run(request, cat.new_rule_version, rule_key, body, who.person_id)}


@router.delete("/admin/rules/{rule_key}", status_code=204)
def delete_rule(rule_key: str, request: Request, who: Identity = Depends(admin)) -> None:
    _run(request, cat.deactivate_rule, rule_key, who.person_id)


@router.post("/admin/blackouts", status_code=201)
def create_blackout(body: cat.BlackoutIn, request: Request, who: Identity = Depends(admin)) -> dict:
    return {"id": _run(request, cat.save_blackout, None, body, who.person_id)}


@router.put("/admin/blackouts/{blackout_id}")
def update_blackout(blackout_id: int, body: cat.BlackoutIn, request: Request, who: Identity = Depends(admin)) -> dict:
    return {"id": _run(request, cat.save_blackout, blackout_id, body, who.person_id)}


@router.delete("/admin/blackouts/{blackout_id}", status_code=204)
def delete_blackout(blackout_id: int, request: Request, who: Identity = Depends(admin)) -> None:
    _run(request, cat.delete_blackout, blackout_id, who.person_id)
