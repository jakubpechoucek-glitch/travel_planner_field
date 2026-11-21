"""Organization endpoints: import (administrator) and read-only structure (administrator, national planner)."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile

from .identity import Identity, resolve_identity
from .orgimport import run_import

router = APIRouter(prefix="/api")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
VIEW_ROLES = {"administrator", "national_planner"}


def require_roles(*allowed: str):
    def dependency(identity: Identity = Depends(resolve_identity)) -> Identity:
        if not set(identity.roles) & set(allowed):
            raise HTTPException(status_code=403, detail="You do not have permission to do this.")
        return identity

    return dependency


@router.post("/admin/org-import")
async def org_import(
    request: Request,
    file: UploadFile = File(...),
    effective_date: date = Query(default=date(2027, 1, 1)),
    commit: bool = Query(default=False, description="false = preview only; nothing is saved"),
    identity: Identity = Depends(require_roles("administrator")),
) -> dict:
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Please upload an Excel file (.xlsx).")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="The file is larger than 10 MB.")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "upload.xlsx"
        path.write_bytes(data)
        try:
            return run_import(request.app.state.pool, path, effective_date, commit, identity.person_id)
        except Exception as exc:  # unreadable workbook: tell the user, keep details out of the response
            if "zip" in type(exc).__name__.lower() or "BadZip" in repr(exc) or "InvalidFile" in repr(exc):
                raise HTTPException(status_code=400, detail="The file could not be read as an Excel workbook.") from exc
            raise


@router.get("/org/tree")
def org_tree(request: Request, _: Identity = Depends(require_roles(*VIEW_ROLES))) -> dict:
    with request.app.state.pool.connection() as conn:
        units = conn.execute(
            "SELECT u.id, u.parent_id, u.kind, u.name, u.lead_person_id, p.full_name AS lead_name "
            "FROM org_unit u LEFT JOIN person p ON p.id = u.lead_person_id WHERE u.active ORDER BY u.name"
        ).fetchall()
        people = conn.execute(
            "SELECT a.cluster_id, a.local_office_id, pos.code AS position_code "
            "FROM person_assignment a JOIN person p ON p.id = a.person_id AND p.active "
            "JOIN position pos ON pos.id = a.position_id "
            "WHERE a.valid_to IS NULL AND a.cluster_id IS NOT NULL"  # the newest (open-ended) structure
        ).fetchall()
    names = {u["id"]: u["name"] for u in units}
    clusters: dict[int, dict] = {}
    for u in (u for u in units if u["kind"] == "cluster"):
        clusters[u["id"]] = {
            "id": u["id"], "name": u["name"], "lead": u["lead_name"], "supervisors": 0, "offices": set(),
            "region_id": u["parent_id"],
        }
    for p in people:
        c = clusters.get(p["cluster_id"])
        if c and p["position_code"] not in ("HEAD", "RM", "AM"):
            c["supervisors"] += 1
        if c and p["local_office_id"]:
            c["offices"].add(names.get(p["local_office_id"], ""))
    regions = []
    for r in (u for u in units if u["kind"] == "region"):
        regions.append({
            "id": r["id"], "name": r["name"], "lead": r["lead_name"],
            "clusters": [
                {**{k: v for k, v in c.items() if k not in ("offices", "region_id")},
                 "offices": sorted(o for o in c["offices"] if o)}
                for c in clusters.values() if c["region_id"] == r["id"]
            ],
        })
    return {"regions": regions, "local_offices": [u["name"] for u in units if u["kind"] == "local_office"]}
