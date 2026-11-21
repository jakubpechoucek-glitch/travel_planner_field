"""Cost forecast endpoints. Costs are visible to administrators, national planners and regional planners (their own
region); the rate card, travel modes, early-booking tiers and the budget are changed by administrators."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile

from . import cost_store as cs
from .access import ALL_ACCESS, allowed_units
from .catalog import CatalogError
from .identity import Identity
from .routes_org import require_roles

router = APIRouter(prefix="/api")
cost_access = require_roles("administrator", "national_planner", "regional_planner")
admin = require_roles("administrator")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _run(request: Request, fn, *args, commit: bool = False, who: Identity | None = None, scoped: bool = False):
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


# ---------------------------------------------------------------------------------------- reading


@router.get("/cost/{year}/forecast")
def forecast(year: int, request: Request, book_ahead_days: int | None = Query(None, ge=1, le=730),
             who: Identity = Depends(cost_access)) -> dict:
    def run(conn, allowed):
        report = cs.forecast_report(conn, year, allowed, book_ahead_days)
        report.pop("trip_costs", None)
        return report

    return _run(request, run, who=who, scoped=True)


@router.get("/cost/config")
def config(request: Request, _: Identity = Depends(cost_access)) -> dict:
    return _run(request, cs.config)


@router.get("/cost/{year}/budget")
def budget(year: int, request: Request, who: Identity = Depends(cost_access)) -> list[dict]:
    if not set(who.roles) & ALL_ACCESS:
        raise HTTPException(status_code=403, detail="The budget is visible to administrators and national planners.")
    return _run(request, cs.budget_lines, year)


# ---------------------------------------------------------------------------------------- administration


@router.post("/admin/cost/rates", status_code=201)
def save_rate(body: cs.RateIn, request: Request, who: Identity = Depends(admin)) -> dict:
    return {"id": _run(request, cs.save_rate, body, who.person_id, commit=True)}


@router.delete("/admin/cost/rates/{rate_id}", status_code=204)
def end_rate(rate_id: int, request: Request, who: Identity = Depends(admin)) -> None:
    _run(request, cs.end_rate, rate_id, who.person_id, commit=True)


@router.put("/admin/cost/modes")
def set_mode(body: cs.ModeIn, request: Request, who: Identity = Depends(admin)) -> dict:
    _run(request, cs.set_mode, body, who.person_id, commit=True)
    return {"ok": True}


@router.post("/admin/cost/modes/suggest")
def suggest_modes(request: Request, who: Identity = Depends(admin)) -> dict:
    return _run(request, cs.suggest_modes, who.person_id, commit=True)


@router.post("/admin/cost/overrides", status_code=201)
def add_override(body: cs.OverrideIn, request: Request, who: Identity = Depends(admin)) -> dict:
    return {"id": _run(request, cs.add_override, body, who.person_id, commit=True)}


@router.delete("/admin/cost/overrides/{override_id}", status_code=204)
def delete_override(override_id: int, request: Request, who: Identity = Depends(admin)) -> None:
    _run(request, cs.delete_override, override_id, who.person_id, commit=True)


@router.put("/admin/cost/settings")
def save_settings(body: cs.SettingsIn, request: Request, who: Identity = Depends(admin)) -> dict:
    return _run(request, cs.save_settings, body, who.person_id, commit=True)


@router.put("/admin/cost/booking-tiers")
def save_tiers(body: cs.TiersIn, request: Request, who: Identity = Depends(admin)) -> list[dict]:
    return _run(request, cs.save_tiers, body, who.person_id, commit=True)


@router.post("/admin/budget/import")
async def import_budget(request: Request, file: UploadFile = File(...), year: int = Query(2027),
                        commit: bool = Query(False), who: Identity = Depends(admin)) -> dict:
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Please upload an Excel file (.xlsx).")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="The file is larger than 10 MB.")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "budget.xlsx"
        path.write_bytes(data)
        try:
            return _run(request, cs.import_budget, year, path, commit, who.person_id, commit=commit)
        except HTTPException:
            raise
        except Exception as exc:
            if "zip" in type(exc).__name__.lower() or "BadZip" in repr(exc) or "InvalidFile" in repr(exc):
                raise HTTPException(status_code=400, detail="The file could not be read as an Excel workbook.") from exc
            raise


@router.put("/admin/budget/lines/{line_id}")
def map_line(line_id: int, body: cs.MappingIn, request: Request, who: Identity = Depends(admin)) -> dict:
    _run(request, cs.map_budget_line, line_id, body, who.person_id, commit=True)
    return {"ok": True}
