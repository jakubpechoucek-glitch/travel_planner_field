"""Plan endpoints: generate (administrator, national planner) and read the plan (the same roles for now)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from . import plan_store as store
from .catalog import CatalogError
from .identity import Identity
from .routes_org import require_roles

router = APIRouter(prefix="/api")
planner = require_roles("administrator", "national_planner")


def _db(request: Request, fn, *args, commit: bool = False):
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


@router.post("/admin/plan/{year}/generate")
def generate(year: int, request: Request, commit: bool = Query(default=False),
             who: Identity = Depends(planner)) -> dict:
    """Preview (default) or save the generated plan. Untouched generated trips are replaced; edited ones stay."""
    return _db(request, store.generate_plan, year, commit, who.person_id, commit=commit)


@router.get("/plan/{year}/summary")
def summary(year: int, request: Request, _: Identity = Depends(planner)) -> dict:
    return _db(request, store.plan_summary, year)


@router.get("/plan/{year}/trips")
def trips(year: int, request: Request, unit_id: int | None = None, month: int | None = Query(None, ge=1, le=12),
          event_type_id: int | None = None, nationwide: bool = False, _: Identity = Depends(planner)) -> list[dict]:
    return _db(request, store.plan_trips, year, unit_id, month, event_type_id, nationwide)


@router.get("/plan/trips/{trip_id}")
def trip(trip_id: int, request: Request, _: Identity = Depends(planner)) -> dict:
    return _db(request, store.trip_detail, trip_id)


@router.get("/plan/{year}/warnings")
def warnings(year: int, request: Request, _: Identity = Depends(planner)) -> dict:
    return _db(request, store.plan_warnings, year)
