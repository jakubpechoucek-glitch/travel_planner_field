"""Suggest a change: a person on a trip asks the planner to move it or to take them off it.

A request changes nothing in the plan. The planner of the trip (administrator, national planner, or the regional or
area planner of its place) reads it, carries out the change as a normal edit with a reason, or declines it with a note.
The requester sees the answer in My plan. A person has at most one open request per trip. Requests carry free text,
so the form tells people not to write contact details; nothing is sent by e-mail.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from psycopg import Connection
from pydantic import BaseModel, Field

from .access import can_edit, can_see
from .catalog import CatalogError, audit
from .identity import Identity

KINDS = ("move", "cannot_attend", "other")
KIND_LABEL = {"move": "Move the trip", "cannot_attend": "I cannot take part", "other": "Something else"}


class RequestIn(BaseModel):
    kind: Literal["move", "cannot_attend", "other"]
    message: str = Field(min_length=3, max_length=500)
    proposed_start: date | None = None
    proposed_end: date | None = None


class DecideIn(BaseModel):
    decision: Literal["accepted", "declined"]
    note: str | None = Field(default=None, max_length=500)


def _today() -> date:  # a function so tests can pin the date
    return date.today()


def create_request(conn: Connection, trip_id: int, body: RequestIn, person_id: int | None) -> dict[str, Any]:
    if person_id is None:
        raise CatalogError("Your sign-in is not linked to a person.", 403)
    t = conn.execute(
        "SELECT t.id, t.status, t.start_date, t.end_date, t.plan_year, py.status AS plan_status FROM trip t "
        "JOIN plan_year py ON py.year = t.plan_year WHERE t.id = %s", (trip_id,)).fetchone()
    on_trip = t and conn.execute("SELECT 1 FROM trip_participant WHERE trip_id = %s AND person_id = %s",
                                 (trip_id, person_id)).fetchone()
    if t is None or not on_trip:
        raise CatalogError("The trip does not exist.", 404)          # nobody learns about trips they are not on
    if t["status"] == "cancelled" or t["end_date"] < _today():
        raise CatalogError("You can only suggest a change to a trip that has not taken place yet.", 409)
    if t["plan_status"] not in ("review", "published"):
        raise CatalogError("This plan year is closed.", 409)
    start, end = body.proposed_start, body.proposed_end
    if body.kind == "move":
        if start is None:
            raise CatalogError("Enter the date you would prefer.")
        end = end or start + (t["end_date"] - t["start_date"])
        if end < start:
            raise CatalogError("The end date cannot be before the start date.")
        if start.year != t["plan_year"] or end.year != t["plan_year"]:
            raise CatalogError(f"The new dates must be inside {t['plan_year']}.")
    else:
        start = end = None
    if conn.execute("SELECT 1 FROM change_request WHERE trip_id = %s AND requested_by = %s AND status = 'open'",
                    (trip_id, person_id)).fetchone():
        raise CatalogError("You already have an open suggestion for this trip. Withdraw it first to send another.", 409)
    row = conn.execute(
        "INSERT INTO change_request(trip_id, requested_by, kind, message, proposed_start, proposed_end) "
        "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id", (trip_id, person_id, body.kind, body.message, start, end)).fetchone()
    audit(conn, person_id, "change_request.create", "trip", trip_id, {"request_id": row["id"], "kind": body.kind})
    return {"id": row["id"], "status": "open"}


def withdraw(conn: Connection, request_id: int, person_id: int | None) -> dict[str, Any]:
    r = conn.execute("SELECT id, requested_by, status, trip_id FROM change_request WHERE id = %s FOR UPDATE",
                     (request_id,)).fetchone()
    if r is None or r["requested_by"] != person_id:
        raise CatalogError("The suggestion does not exist.", 404)
    if r["status"] != "open":
        raise CatalogError("Only an open suggestion can be withdrawn.", 409)
    conn.execute("UPDATE change_request SET status = 'withdrawn', decided_at = now() WHERE id = %s", (request_id,))
    audit(conn, person_id, "change_request.withdraw", "trip", r["trip_id"], {"request_id": request_id})
    return {"status": "withdrawn"}


def my_requests(conn: Connection, person_id: int, trip_ids: list[int]) -> dict[int, dict[str, Any]]:
    """The latest suggestion of the person for each of the trips."""
    out: dict[int, dict[str, Any]] = {}
    if not trip_ids:
        return out
    for r in conn.execute(
            "SELECT DISTINCT ON (trip_id) id, trip_id, kind, message, status, proposed_start, proposed_end, "
            "decision_note, created_at FROM change_request WHERE requested_by = %s AND trip_id = ANY(%s) "
            "ORDER BY trip_id, created_at DESC, id DESC", (person_id, trip_ids)):
        out[r["trip_id"]] = {
            "id": r["id"], "kind": r["kind"], "message": r["message"], "status": r["status"],
            "proposed_start": str(r["proposed_start"]) if r["proposed_start"] else None,
            "proposed_end": str(r["proposed_end"]) if r["proposed_end"] else None,
            "decision_note": r["decision_note"], "created_at": r["created_at"].isoformat()}
    return out


def list_requests(conn: Connection, year: int, allowed: set[int] | None, state: str = "open") -> dict[str, Any]:
    clauses, args = ["t.plan_year = %s"], [year]
    if state != "all":
        clauses.append("r.status = %s")
        args.append(state)
    rows = conn.execute(
        "SELECT r.id, r.kind, r.message, r.status, r.proposed_start, r.proposed_end, r.decision_note, r.created_at, "
        "t.id AS trip_id, t.title, t.start_date, t.end_date, t.visited_org_unit_id, p.full_name AS requester, "
        "d.full_name AS decided_by FROM change_request r JOIN trip t ON t.id = r.trip_id "
        "JOIN person p ON p.id = r.requested_by LEFT JOIN person d ON d.id = r.decided_by "
        f"WHERE {' AND '.join(clauses)} ORDER BY r.created_at, r.id LIMIT 300", args).fetchall()  # noqa: S608
    out = []
    for r in rows:
        if not can_see(allowed, r["visited_org_unit_id"]):
            continue
        out.append({
            "id": r["id"], "kind": r["kind"], "kind_label": KIND_LABEL[r["kind"]], "message": r["message"],
            "status": r["status"], "requester": r["requester"], "decided_by": r["decided_by"],
            "decision_note": r["decision_note"], "created_at": r["created_at"].isoformat(),
            "proposed_start": str(r["proposed_start"]) if r["proposed_start"] else None,
            "proposed_end": str(r["proposed_end"]) if r["proposed_end"] else None,
            "trip": {"id": r["trip_id"], "title": r["title"], "start_date": str(r["start_date"]),
                     "end_date": str(r["end_date"])},
            "editable": can_edit(allowed, r["visited_org_unit_id"])})
    open_n = len(out) if state == "open" else len(list_requests(conn, year, allowed, "open")["requests"])
    return {"year": year, "open": open_n, "requests": out}


def decide(conn: Connection, request_id: int, body: DecideIn, who: Identity,
           allowed: set[int] | None) -> dict[str, Any]:
    r = conn.execute(
        "SELECT r.id, r.status, r.trip_id, t.visited_org_unit_id FROM change_request r JOIN trip t ON t.id = r.trip_id "
        "WHERE r.id = %s FOR UPDATE OF r", (request_id,)).fetchone()
    if r is None or not can_see(allowed, r["visited_org_unit_id"]):
        raise CatalogError("The suggestion does not exist.", 404)
    if not can_edit(allowed, r["visited_org_unit_id"]):
        raise CatalogError("You can only answer suggestions for trips in your own area.", 403)
    if r["status"] != "open":
        raise CatalogError("This suggestion has already been answered or withdrawn.", 409)
    note = (body.note or "").strip() or None
    if body.decision == "declined" and (note is None or len(note) < 3):
        raise CatalogError("Please say why the suggestion is declined.")
    conn.execute("UPDATE change_request SET status = %s, decided_by = %s, decided_at = now(), decision_note = %s "
                 "WHERE id = %s", (body.decision, who.person_id, note, request_id))
    audit(conn, who.person_id, f"change_request.{body.decision}", "trip", r["trip_id"], {"request_id": request_id})
    return {"status": body.decision}
