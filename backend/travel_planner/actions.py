"""Follow-up of a trip: up to three actions with a due date, closed after the visit.

Calendars track trips, not outcomes. After a visit (for example a Special Area visit) the top actions are recorded on
the trip and closed within the follow-up period of the event type (``event_type.follow_up_days``, 30 days for the
Head of Field's visits). Planners record and close actions for trips in their own scope; the history of the
trip shows the actions, and the Plan page lists the follow-ups that are open or late.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal

from psycopg import Connection
from pydantic import BaseModel, Field

from . import plan_store as store
from .access import can_edit, can_see
from .catalog import CatalogError, audit
from .identity import Identity

MAX_ACTIONS = 3
DEFAULT_DAYS = 30


class ActionIn(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    due_date: date | None = None


class ActionUpdate(BaseModel):
    status: Literal["open", "done", "dropped"] | None = None
    title: str | None = Field(default=None, min_length=3, max_length=300)
    due_date: date | None = None
    close_note: str | None = Field(default=None, max_length=500)


def _today() -> date:  # a function so tests can pin the date
    return date.today()


def _trip(conn: Connection, trip_id: int, allowed: set[int] | None, write: bool) -> dict[str, Any]:
    t = conn.execute(
        "SELECT t.id, t.end_date, t.status, t.visited_org_unit_id, e.follow_up_days, py.status AS plan_status "
        "FROM trip t JOIN event_type e ON e.id = t.event_type_id JOIN plan_year py ON py.year = t.plan_year "
        "WHERE t.id = %s FOR UPDATE OF t" if write else
        "SELECT t.id, t.end_date, t.status, t.visited_org_unit_id, e.follow_up_days, py.status AS plan_status "
        "FROM trip t JOIN event_type e ON e.id = t.event_type_id JOIN plan_year py ON py.year = t.plan_year "
        "WHERE t.id = %s", (trip_id,)).fetchone()
    if t is None or not can_see(allowed, t["visited_org_unit_id"]):
        raise CatalogError("The trip does not exist.", 404)
    if write and not can_edit(allowed, t["visited_org_unit_id"]):
        raise CatalogError("You can only change trips in your own area.", 403)
    return t


def list_actions(conn: Connection, trip_id: int, allowed: set[int] | None) -> list[dict[str, Any]]:
    _trip(conn, trip_id, allowed, write=False)
    return store.actions_of(conn, trip_id)


def add_action(conn: Connection, trip_id: int, body: ActionIn, who: Identity, allowed: set[int] | None) -> dict:
    t = _trip(conn, trip_id, allowed, write=True)
    if t["status"] == "cancelled":
        raise CatalogError("A cancelled trip has no follow-up.", 409)
    if t["plan_status"] == "closed":
        raise CatalogError("The plan year is closed.", 409)
    n = conn.execute("SELECT count(*) AS n FROM trip_action WHERE trip_id = %s AND status <> 'dropped'",
                     (trip_id,)).fetchone()["n"]
    if n >= MAX_ACTIONS:
        raise CatalogError(f"A trip has at most {MAX_ACTIONS} actions. Drop one to add another.", 409)
    due = body.due_date or t["end_date"] + timedelta(days=t["follow_up_days"] or DEFAULT_DAYS)
    row = conn.execute(
        "INSERT INTO trip_action(trip_id, title, due_date, created_by) VALUES (%s,%s,%s,%s) RETURNING id",
        (trip_id, body.title, due, who.person_id)).fetchone()
    audit(conn, who.person_id, "trip.action.add", "trip", trip_id, {"action_id": row["id"]})
    return {"actions": store.actions_of(conn, trip_id)}


def update_action(conn: Connection, action_id: int, body: ActionUpdate, who: Identity,
                  allowed: set[int] | None) -> dict:
    a = conn.execute("SELECT id, trip_id, status FROM trip_action WHERE id = %s FOR UPDATE", (action_id,)).fetchone()
    if a is None:
        raise CatalogError("The action does not exist.", 404)
    _trip(conn, a["trip_id"], allowed, write=True)
    status = body.status or a["status"]
    closing = status in ("done", "dropped") and a["status"] == "open"
    reopening = status == "open" and a["status"] != "open"
    if reopening:
        n = conn.execute(
            "SELECT count(*) AS n FROM trip_action WHERE trip_id = %s AND status <> 'dropped' AND id <> %s",
            (a["trip_id"], action_id)).fetchone()["n"]
        if n >= MAX_ACTIONS:
            raise CatalogError(f"A trip has at most {MAX_ACTIONS} actions.", 409)
    conn.execute(
        "UPDATE trip_action SET status = %s, title = COALESCE(%s, title), due_date = COALESCE(%s, due_date), "
        "close_note = CASE WHEN %s THEN %s WHEN %s THEN NULL ELSE close_note END, "
        "closed_by = CASE WHEN %s THEN %s WHEN %s THEN NULL ELSE closed_by END, "
        "closed_at = CASE WHEN %s THEN now() WHEN %s THEN NULL ELSE closed_at END WHERE id = %s",
        (status, body.title, body.due_date, closing, body.close_note, reopening, closing, who.person_id, reopening,
         closing, reopening, action_id))
    audit(conn, who.person_id, "trip.action.update", "trip", a["trip_id"], {"action_id": action_id, "status": status})
    return {"actions": store.actions_of(conn, a["trip_id"])}


def follow_ups(conn: Connection, year: int, allowed: set[int] | None, today: date | None = None) -> dict[str, Any]:
    """Trips of the year whose event has a follow-up (or that have actions), with the state of the follow-up."""
    today = today or _today()
    rows = conn.execute(
        "SELECT t.id, t.title, t.start_date, t.end_date, t.visited_org_unit_id, e.name AS event, e.follow_up_days, "
        "u.name AS place, "
        "count(a.id) FILTER (WHERE a.status = 'open') AS open_n, "
        "count(a.id) FILTER (WHERE a.status = 'done') AS done_n "
        "FROM trip t JOIN event_type e ON e.id = t.event_type_id LEFT JOIN org_unit u ON u.id = t.visited_org_unit_id "
        "LEFT JOIN trip_action a ON a.trip_id = t.id "
        "WHERE t.plan_year = %s AND t.status <> 'cancelled' AND t.merged_into_trip_id IS NULL "
        "GROUP BY t.id, e.id, u.id HAVING e.follow_up_days IS NOT NULL OR count(a.id) > 0 "
        "ORDER BY t.end_date, t.id", (year,)).fetchall()
    out = []
    for r in rows:
        if not can_see(allowed, r["visited_org_unit_id"]):
            continue
        due = r["end_date"] + timedelta(days=r["follow_up_days"] or DEFAULT_DAYS)
        if r["end_date"] >= today:
            state = "upcoming"
        elif r["open_n"]:
            state = "overdue" if today > due else "open"
        elif r["done_n"]:
            state = "closed"
        else:
            state = "overdue" if today > due else "missing"
        out.append({"id": r["id"], "title": r["title"], "event": r["event"], "place": r["place"],
                    "end_date": str(r["end_date"]), "due_date": str(due), "state": state,
                    "open": r["open_n"], "done": r["done_n"], "editable": can_edit(allowed, r["visited_org_unit_id"])})
    order = {"overdue": 0, "missing": 1, "open": 2, "upcoming": 3, "closed": 4}
    out.sort(key=lambda x: (order[x["state"]], x["due_date"], x["id"]))
    counts: dict[str, int] = {}
    for x in out:
        counts[x["state"]] = counts.get(x["state"], 0) + 1
    return {"year": year, "counts": counts, "trips": out}
