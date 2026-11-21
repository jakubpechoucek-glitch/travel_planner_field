"""Manual changes to trips: edit, cancel, confirm or finish, and add by hand.

Rules of the road
* Every change needs a reason (and a category). The database also refuses a history row without one.
* Before anything is saved the change is applied inside the transaction and the whole plan is checked again;
  the *new* rule warnings are returned. A preview rolls back.
* A warning of severity *warn* must be acknowledged; a *block* warning refuses the change.
* The trip carries an ``updated_at`` token: if someone else changed the trip meanwhile the change is refused.
* Planners change only trips in their own scope (see ``access``).
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Literal

from psycopg import Connection
from pydantic import BaseModel, Field

from . import plan_engine as pe
from . import plan_store as store
from .access import can_edit
from .catalog import CatalogError
from .identity import Identity

CATEGORIES = ("business_request", "company_event_conflict", "merged", "capacity", "budget", "other")
Category = Literal["business_request", "company_event_conflict", "merged", "capacity", "budget", "other"]


def _today() -> date:  # a function so tests can pin the date
    return date.today()


# ------------------------------------------------------------------------------------------ input models


class ParticipantIn(BaseModel):
    person_id: int
    role: Literal["organizer", "traveler", "host"] = "traveler"
    travels: bool = True


class _Change(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    category: Category = "other"
    acknowledge: bool = False
    expected_updated_at: datetime | None = None


class EditIn(_Change):
    start_date: date | None = None
    end_date: date | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=1000)
    add_participants: list[ParticipantIn] = Field(default_factory=list)
    remove_participants: list[int] = Field(default_factory=list)


class CancelIn(_Change):
    pass


class CreateIn(_Change):
    event_type_id: int
    unit_id: int | None = None  # None = nationwide
    start_date: date
    end_date: date
    title: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=1000)
    participants: list[ParticipantIn] = Field(default_factory=list)
    default_participants: bool = True


class StatusIn(BaseModel):
    status: Literal["planned", "completed"]
    note: str | None = Field(default=None, max_length=500)
    expected_updated_at: datetime | None = None


# ------------------------------------------------------------------------------------------ helpers


def _lock_trip(conn: Connection, trip_id: int, allowed: set[int] | None, token: datetime | None) -> dict[str, Any]:
    t = conn.execute(
        "SELECT t.*, py.status AS plan_status FROM trip t JOIN plan_year py ON py.year = t.plan_year "
        "WHERE t.id = %s FOR UPDATE OF t", (trip_id,)).fetchone()
    if t is None or (allowed is not None and t["visited_org_unit_id"] is not None
                     and t["visited_org_unit_id"] not in allowed):
        raise CatalogError("The trip does not exist.", 404)
    if not can_edit(allowed, t["visited_org_unit_id"]):
        raise CatalogError("You can only change trips in your own area.", 403)
    if t["status"] not in store.EDITABLE_STATUSES:
        raise CatalogError(f"A {t['status']} trip cannot be changed.", 409)
    if t["plan_status"] == "closed":
        raise CatalogError(f"The plan year {t['plan_year']} is closed.", 409)
    if token is not None and t["updated_at"] != token:
        raise CatalogError("Someone else changed this trip in the meantime. Please reload it and try again.", 409)
    return t


def _check_dates(start: date, end: date, year: int) -> None:
    if end < start:
        raise CatalogError("The end date cannot be before the start date.")
    if start.year != year or end.year != year:
        raise CatalogError(f"The trip must be inside {year}.")


def _impact(conn: Connection, year: int, apply) -> tuple[list[pe.Warn], list[pe.Warn]]:
    """Check the plan before and after a change; return the new and the resolved warnings."""
    inp = store.load_inputs(conn, year)
    before = pe.evaluate(store.load_trip_views(conn, year), inp)
    apply()
    after = pe.evaluate(store.load_trip_views(conn, year), inp)
    bk, ak = {(w.code, w.message) for w in before}, {(w.code, w.message) for w in after}
    return ([w for w in after if (w.code, w.message) not in bk], [w for w in before if (w.code, w.message) not in ak])


def _outcome(conn: Connection, commit: bool, ack: bool, new: list[pe.Warn], resolved: list[pe.Warn]) -> dict:
    blocked = [w for w in new if w.level == "block"]
    needs_ack = [w for w in new if w.level == "warn"]
    if commit and blocked:
        raise CatalogError("This change is not allowed: " + " ".join(w.message for w in blocked), 422)
    if commit and needs_ack and not ack:
        raise CatalogError("This change breaks rules. Confirm that you understand the warnings to save it.", 409)
    return {"committed": commit, "blocked": bool(blocked), "requires_acknowledgement": bool(needs_ack),
            "new_warnings": [w.__dict__ for w in new], "resolved_warnings": len(resolved)}


def _record(conn: Connection, trip_id: int, change_type: str, body: _Change, who: Identity, before: dict,
            after: dict, plan_status: str, new: list[pe.Warn]) -> None:
    if plan_status == "published":
        after = {**after, "after_publication": True}
    conn.execute(
        "INSERT INTO trip_change(trip_id, changed_by, change_type, category, reason, before_data, after_data) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (trip_id, who.person_id, change_type, body.category, body.reason,
         json.dumps(before, default=str), json.dumps(after, default=str)))
    for w in new:
        if w.level == "warn":
            conn.execute("INSERT INTO warning_ack(trip_id, warning_code, acknowledged_by, reason) VALUES (%s,%s,%s,%s)",
                         (trip_id, w.code, who.person_id, body.reason))


def _people_exist(conn: Connection, ids: list[int]) -> None:
    found = {r["id"] for r in conn.execute("SELECT id FROM person WHERE active AND id = ANY(%s)", (ids,))}
    if set(ids) - found:
        raise CatalogError("A person in the list does not exist.")


# ------------------------------------------------------------------------------------------ operations


def edit_trip(conn: Connection, trip_id: int, body: EditIn, who: Identity, allowed: set[int] | None,
              commit: bool) -> dict[str, Any]:
    t = _lock_trip(conn, trip_id, allowed, body.expected_updated_at)
    year = t["plan_year"]
    start, end = body.start_date or t["start_date"], body.end_date or t["end_date"]
    _check_dates(start, end, year)
    touching = [p.person_id for p in body.add_participants] + body.remove_participants
    if touching:
        _people_exist(conn, [p.person_id for p in body.add_participants])
    present = {r["person_id"] for r in
               conn.execute("SELECT person_id FROM trip_participant WHERE trip_id = %s", (trip_id,))}
    if set(body.remove_participants) - present:
        raise CatalogError("A person you want to remove is not on this trip.")

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    dates_changed = (start, end) != (t["start_date"], t["end_date"])
    if dates_changed:
        before.update(start=str(t["start_date"]), end=str(t["end_date"]))
        after.update(start=str(start), end=str(end))
    for field_, new in (("title", body.title), ("notes", body.notes)):
        if new is not None and new != t[field_]:
            before[field_], after[field_] = t[field_], new
    people_changed = bool(body.add_participants or body.remove_participants)
    if people_changed:
        after["added"] = [p.person_id for p in body.add_participants]
        after["removed"] = list(body.remove_participants)
    if not after:
        raise CatalogError("Nothing was changed.")
    if dates_changed and not (set(after) - {"start", "end"}):
        same_length = (end - start) == (t["end_date"] - t["start_date"])
        change_type = "moved" if same_length else "resized"
    elif people_changed and not (set(after) - {"added", "removed"}):
        change_type = "reassigned"
    else:
        change_type = "edited"

    def apply() -> None:
        conn.execute(
            "UPDATE trip SET start_date=%s, end_date=%s, title=COALESCE(%s, title), notes=COALESCE(%s, notes), "
            "updated_by=%s, updated_at=now() WHERE id=%s",
            (start, end, body.title, body.notes, who.person_id, trip_id))
        for pid in body.remove_participants:
            conn.execute("DELETE FROM trip_participant WHERE trip_id=%s AND person_id=%s", (trip_id, pid))
        for p in body.add_participants:
            conn.execute(
                "INSERT INTO trip_participant(trip_id, person_id, role, travels) VALUES (%s,%s,%s,%s) "
                "ON CONFLICT (trip_id, person_id) DO UPDATE SET role = EXCLUDED.role, travels = EXCLUDED.travels",
                (trip_id, p.person_id, p.role, p.travels))

    new, resolved = _impact(conn, year, apply)
    result = _outcome(conn, commit, body.acknowledge, new, resolved)
    if commit:
        _record(conn, trip_id, change_type, body, who, before, after, t["plan_status"], new)
        result["trip"] = store.trip_detail(conn, trip_id, allowed)
    return result


def cancel_trip(conn: Connection, trip_id: int, body: CancelIn, who: Identity, allowed: set[int] | None,
                commit: bool) -> dict[str, Any]:
    t = _lock_trip(conn, trip_id, allowed, body.expected_updated_at)

    def apply() -> None:
        conn.execute("UPDATE trip SET status='cancelled', cancel_reason=%s, updated_by=%s, updated_at=now() "
                     "WHERE id=%s", (body.reason, who.person_id, trip_id))

    new, resolved = _impact(conn, t["plan_year"], apply)
    result = _outcome(conn, commit, body.acknowledge, new, resolved)
    if commit:
        _record(conn, trip_id, "cancelled", body, who, {"status": t["status"]}, {"status": "cancelled"},
                t["plan_status"], new)
        result["trip"] = store.trip_detail(conn, trip_id, allowed)
    return result


def set_status(conn: Connection, trip_id: int, body: StatusIn, who: Identity, allowed: set[int] | None) -> dict:
    """Confirm a generated trip, or mark a trip as done. These are not deviations, so the reason is supplied."""
    t = _lock_trip(conn, trip_id, allowed, body.expected_updated_at)
    if body.status == "planned":
        if t["status"] != "generated":
            raise CatalogError("Only a generated trip can be confirmed.", 409)
        reason, completed = "Confirmed by planner.", False
    else:
        if t["status"] == "generated":
            raise CatalogError("Confirm the trip first.", 409)
        if t["start_date"] > _today():
            raise CatalogError("A trip can be marked as done once it has started.", 409)
        reason, completed = "Marked as done." + (f" {body.note}" if body.note else ""), True
    conn.execute(
        "UPDATE trip SET status=%s, completed_at=CASE WHEN %s THEN now() ELSE completed_at END, "
        "completion_note=CASE WHEN %s THEN %s ELSE completion_note END, updated_by=%s, updated_at=now() WHERE id=%s",
        (body.status, completed, completed, body.note, who.person_id, trip_id))
    conn.execute(
        "INSERT INTO trip_change(trip_id, changed_by, change_type, reason, before_data, after_data) "
        "VALUES (%s,%s,'status',%s,%s,%s)",
        (trip_id, who.person_id, reason, json.dumps({"status": t["status"]}), json.dumps({"status": body.status})))
    return {"committed": True, "trip": store.trip_detail(conn, trip_id, allowed)}


def create_trip(conn: Connection, year: int, body: CreateIn, who: Identity, allowed: set[int] | None,
                commit: bool) -> dict[str, Any]:
    py = conn.execute("SELECT status FROM plan_year WHERE year = %s", (year,)).fetchone()
    if py is None:
        raise CatalogError(f"The plan year {year} does not exist.", 404)
    if py["status"] == "closed":
        raise CatalogError(f"The plan year {year} is closed.", 409)
    _check_dates(body.start_date, body.end_date, year)
    event = conn.execute("SELECT id, name, typical_mode FROM event_type WHERE id = %s AND active",
                         (body.event_type_id,)).fetchone()
    if event is None:
        raise CatalogError("The event type does not exist or is not active.")
    unit = None
    if body.unit_id is not None:
        unit = conn.execute("SELECT id, kind, name FROM org_unit WHERE id = %s AND active", (body.unit_id,)).fetchone()
        if unit is None:
            raise CatalogError("The place does not exist.")
    if not can_edit(allowed, body.unit_id):
        raise CatalogError("You can only add trips in your own area.", 403)

    inp = store.load_inputs(conn, year)
    planner = pe.Planner(inp)
    scope = pe.UnitRef(unit["kind"], unit["id"]) if unit else pe.UnitRef("nationwide")
    parts: dict[int, tuple[str, bool]] = {}
    ev = next((e for e in inp.events if e.id == body.event_type_id), None)
    if body.default_participants and ev is not None:
        parts.update(planner.build_participants(ev, scope)[0])
    if body.participants:
        _people_exist(conn, [p.person_id for p in body.participants])
        parts.update({p.person_id: (p.role, p.travels) for p in body.participants})
    hub = planner.w.units[scope].hub_office_id
    location = conn.execute("SELECT id FROM location WHERE local_office_id = %s ORDER BY id LIMIT 1",
                            (hub,)).fetchone() if hub else None
    title = body.title or (f"{event['name']}: {unit['name']}" if unit else event["name"])
    created: dict[str, int] = {}

    def apply() -> None:
        row = conn.execute(
            "INSERT INTO trip(plan_year, event_type_id, title, visited_org_unit_id, location_id, start_date, end_date, "
            "status, source, transport_mode, notes, created_by, updated_by) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,'planned','manual',%s,%s,%s,%s) RETURNING id",
            (year, event["id"], title, body.unit_id, location["id"] if location else None, body.start_date,
             body.end_date, event["typical_mode"], body.notes, who.person_id, who.person_id)).fetchone()
        created["id"] = row["id"]
        for pid, (role, travels) in parts.items():
            conn.execute("INSERT INTO trip_participant(trip_id, person_id, role, travels) VALUES (%s,%s,%s,%s)",
                         (row["id"], pid, role, travels))

    new, resolved = _impact(conn, year, apply)
    result = _outcome(conn, commit, body.acknowledge, new, resolved)
    if commit:
        _record(conn, created["id"], "created", body, who, {}, {"start": str(body.start_date),
                                                               "end": str(body.end_date)}, py["status"], new)
        result["trip"] = store.trip_detail(conn, created["id"], allowed)
    return result


def places(conn: Connection, allowed: set[int] | None) -> list[dict[str, Any]]:
    """Places a planner may add trips for."""
    rows = conn.execute(
        "SELECT id, kind, name, parent_id FROM org_unit WHERE active AND (%s::int[] IS NULL OR id = ANY(%s)) "
        "ORDER BY kind, name", (sorted(allowed) if allowed is not None else None,
                                sorted(allowed) if allowed is not None else None)).fetchall()
    out = [dict(r) for r in rows]
    if allowed is None:
        out.insert(0, {"id": None, "kind": "nationwide", "name": "Nationwide", "parent_id": None})
    return out
