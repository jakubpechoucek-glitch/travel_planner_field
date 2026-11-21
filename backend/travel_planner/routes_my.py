"""My plan: every signed-in person sees their own trips."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from . import my_plan
from .access import has_plan_access
from .identity import Identity, resolve_identity

router = APIRouter(prefix="/api/my")


def signed_in(identity: Identity = Depends(resolve_identity)) -> Identity:
    if not identity.has_access:
        raise HTTPException(status_code=403, detail="You do not have access yet.")
    return identity


def _load(request: Request, who: Identity, year: int | None) -> dict:
    with request.app.state.pool.connection() as conn:
        try:
            return my_plan.my_trips(conn, who.person_id, year, has_plan_access(who))
        finally:
            conn.rollback()


@router.get("/trips")
def trips(request: Request, year: int | None = Query(None, ge=2000, le=2100),
          who: Identity = Depends(signed_in)) -> dict:
    return _load(request, who, year)


@router.get("/trips.ics")
def trips_ics(request: Request, year: int | None = Query(None, ge=2000, le=2100),
              who: Identity = Depends(signed_in)) -> Response:
    data = _load(request, who, year)
    if not data.get("published") or data["year"] is None:
        raise HTTPException(status_code=404, detail="There is no published plan to export yet.")
    body = my_plan.ics_for(data["trips"], data["year"])
    return Response(body, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="my-travel-{data["year"]}.ics"'})
