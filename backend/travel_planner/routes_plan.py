"""Plan endpoints.

* Generate the plan and the plan-wide checks: administrators and national planners.
* Read the plan and change trips: administrators, national planners, and regional and area planners within their
  own scope (see ``access``).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel

from . import actions, plan_export
from . import plan_store as store
from . import trip_edit as edit
from .access import allowed_units, has_plan_access
from .catalog import CatalogError
from .identity import Identity, resolve_identity
from .routes_org import require_roles

router = APIRouter(prefix="/api")
planner = require_roles("administrator", "national_planner")


def plan_access(identity: Identity = Depends(resolve_identity)) -> Identity:
    if not has_plan_access(identity):
        raise HTTPException(status_code=403, detail="You do not have permission to do this.")
    return identity


def _db(request: Request, fn, *args, commit: bool = False, who: Identity | None = None, scoped: bool = False):
    """Run ``fn(conn, *args)`` in one transaction; with ``scoped`` the caller's allowed places are appended."""
    with request.app.state.pool.connection() as conn:
        try:
            extra = (allowed_units(conn, who),) if scoped and who else ()
            result = fn(conn, *args, *extra)
            conn.commit() if commit else conn.rollback()
            return result
        except CatalogError as exc:
            conn.rollback()
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
        except Exception:
            conn.rollback()
            raise


def _change(request: Request, who: Identity, fn, args: tuple, commit: bool):
    """A change with a preview: the preview rolls back, a commit saves."""
    with request.app.state.pool.connection() as conn:
        try:
            allowed = allowed_units(conn, who)
            result = fn(conn, *args, who, allowed, commit)
            conn.commit() if commit else conn.rollback()
            return result
        except CatalogError as exc:
            conn.rollback()
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
        except Exception:
            conn.rollback()
            raise


# ---------------------------------------------------------------------------------------- generate and checks


@router.post("/admin/plan/{year}/generate")
def generate(year: int, request: Request, commit: bool = Query(default=False),
             who: Identity = Depends(planner)) -> dict:
    """Preview (default) or save the generated plan. Untouched generated trips are replaced; edited ones stay."""
    return _db(request, store.generate_plan, year, commit, who.person_id, commit=commit)


class StatusBody(BaseModel):
    status: Literal["published", "review", "closed"]


@router.post("/admin/plan/{year}/status")
def plan_status(year: int, body: StatusBody, request: Request, who: Identity = Depends(planner)) -> dict:
    """Publish the plan (supervisors can then see their trips), withdraw it, or close the year."""
    return _db(request, store.set_plan_status, year, body.status, who.person_id, commit=True)


class YearBody(BaseModel):
    year: int


@router.get("/plan-years")
def plan_years(request: Request, _: Identity = Depends(plan_access)) -> list[dict]:
    return _db(request, store.list_plan_years)


@router.post("/admin/plan-years", status_code=201)
def new_plan_year(body: YearBody, request: Request, who: Identity = Depends(planner)) -> dict:
    """Open the next plan year as a draft."""
    return _db(request, store.create_plan_year, body.year, who.person_id, commit=True)


@router.get("/plan/{year}/warnings")
def warnings(year: int, request: Request, _: Identity = Depends(planner)) -> dict:
    return _db(request, store.plan_warnings, year)


# ---------------------------------------------------------------------------------------- reading


@router.get("/plan/{year}/summary")
def summary(year: int, request: Request, who: Identity = Depends(plan_access)) -> dict:
    return _db(request, store.plan_summary, year, who=who, scoped=True)


@router.get("/plan/{year}/trips")
def trips(year: int, request: Request, unit_id: int | None = None, month: int | None = Query(None, ge=1, le=12),
          event_type_id: int | None = None, nationwide: bool = False,
          who: Identity = Depends(plan_access)) -> list[dict]:
    return _db(request, store.plan_trips, year, unit_id, month, event_type_id, nationwide, 500, who=who, scoped=True)


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/plan/{year}/export.xlsx")
def export_xlsx(year: int, request: Request, include: Literal["", "cancelled"] = "",
                who: Identity = Depends(plan_access)) -> Response:
    """The plan as an Excel workbook, limited to the caller's scope. Exports are written to the audit log."""
    with request.app.state.pool.connection() as conn:
        try:
            allowed = allowed_units(conn, who)
            content = plan_export.export(
                conn, year, allowed, who.person_id, include_cancelled=include == "cancelled",
                with_checks=allowed is None,
                with_costs=bool(set(who.roles) & {"administrator", "national_planner", "regional_planner"}))
            conn.commit()
        except CatalogError as exc:
            conn.rollback()
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
        except Exception:
            conn.rollback()
            raise
    return Response(content, media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="travel-plan-{year}.xlsx"'})


@router.get("/plan/places")
def places(request: Request, who: Identity = Depends(plan_access)) -> list[dict]:
    return _db(request, edit.places, who=who, scoped=True)


@router.get("/plan/people")
def people(request: Request, q: str | None = Query(None, max_length=60),
           who: Identity = Depends(plan_access)) -> list[dict]:
    return _db(request, lambda conn, allowed: store.plan_people(conn, allowed, q), who=who, scoped=True)


@router.get("/plan/trips/{trip_id}")
def trip(trip_id: int, request: Request, who: Identity = Depends(plan_access)) -> dict:
    return _db(request, store.trip_detail, trip_id, who=who, scoped=True)


@router.get("/plan/trips/{trip_id}/history")
def history(trip_id: int, request: Request, who: Identity = Depends(plan_access)) -> list[dict]:
    return _db(request, store.trip_history, trip_id, who=who, scoped=True)


# ---------------------------------------------------------------------------------------- changing trips


@router.post("/plan/trips/{trip_id}/edit")
def edit_trip(trip_id: int, body: edit.EditIn, request: Request, commit: bool = Query(default=False),
              who: Identity = Depends(plan_access)) -> dict:
    return _change(request, who, edit.edit_trip, (trip_id, body), commit)


@router.post("/plan/trips/{trip_id}/cancel")
def cancel_trip(trip_id: int, body: edit.CancelIn, request: Request, commit: bool = Query(default=False),
                who: Identity = Depends(plan_access)) -> dict:
    return _change(request, who, edit.cancel_trip, (trip_id, body), commit)


@router.post("/plan/trips/{trip_id}/status")
def set_status(trip_id: int, body: edit.StatusIn, request: Request, who: Identity = Depends(plan_access)) -> dict:
    return _db(request, lambda conn, allowed: edit.set_status(conn, trip_id, body, who, allowed),
               commit=True, who=who, scoped=True)


@router.get("/plan/trips/{trip_id}/area-options")
def area_options(trip_id: int, request: Request, who: Identity = Depends(plan_access)) -> list[dict]:
    return _db(request, edit.area_options, trip_id, who=who, scoped=True)


@router.post("/plan/trips/{trip_id}/choose-area")
def choose_area(trip_id: int, body: edit.ChooseAreaIn, request: Request, who: Identity = Depends(plan_access)) -> dict:
    return _db(request, lambda conn, allowed: edit.choose_area(conn, trip_id, body, who, allowed),
               commit=True, who=who, scoped=True)


@router.get("/plan/trips/{trip_id}/actions")
def trip_actions(trip_id: int, request: Request, who: Identity = Depends(plan_access)) -> list[dict]:
    return _db(request, actions.list_actions, trip_id, who=who, scoped=True)


@router.post("/plan/trips/{trip_id}/actions", status_code=201)
def add_action(trip_id: int, body: actions.ActionIn, request: Request, who: Identity = Depends(plan_access)) -> dict:
    return _db(request, lambda conn, allowed: actions.add_action(conn, trip_id, body, who, allowed),
               commit=True, who=who, scoped=True)


@router.put("/plan/actions/{action_id}")
def update_action(action_id: int, body: actions.ActionUpdate, request: Request,
                  who: Identity = Depends(plan_access)) -> dict:
    return _db(request, lambda conn, allowed: actions.update_action(conn, action_id, body, who, allowed),
               commit=True, who=who, scoped=True)


@router.get("/plan/{year}/follow-ups")
def follow_ups(year: int, request: Request, who: Identity = Depends(plan_access)) -> dict:
    return _db(request, lambda conn, allowed: actions.follow_ups(conn, year, allowed), who=who, scoped=True)


@router.post("/plan/{year}/trips", status_code=200)
def create_trip(year: int, body: edit.CreateIn, request: Request, commit: bool = Query(default=False),
                who: Identity = Depends(plan_access)) -> dict:
    return _change(request, who, edit.create_trip, (year, body), commit)
