"""Synergy suggestions: two trips to the same place a few days apart.

Trips that go to the same place close in time are chances to travel once instead of twice, and to book earlier and
cheaper. The suggestion names the two trips, the days between them and the people who travel on both. It is a hint
for the planner, who changes a trip (with a reason) or dismisses the suggestion; nothing changes by itself.
Trips that are already combined, cancelled or finished are left out, and so are pairs that overlap in time
(the plan checks report those as a person being in two trips at once).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from psycopg import Connection
from pydantic import BaseModel, Field

from .access import can_edit, can_see
from .catalog import CatalogError, audit
from .identity import Identity

DEFAULT_DAYS = 14
LIMIT = 100


class DismissIn(BaseModel):
    trip_a: int
    trip_b: int
    reason: str | None = Field(default=None, max_length=300)


def _today() -> date:  # a function so tests can pin the date
    return date.today()


def _brief(t: dict[str, Any], allowed: set[int] | None) -> dict[str, Any]:
    return {"id": t["id"], "title": t["title"], "event": t["event"], "start_date": str(t["start_date"]),
            "end_date": str(t["end_date"]), "editable": can_edit(allowed, t["visited_org_unit_id"])}


def suggestions(conn: Connection, year: int, allowed: set[int] | None, within_days: int = DEFAULT_DAYS,
                today: date | None = None) -> dict[str, Any]:
    today = today or _today()
    trips = conn.execute(
        "SELECT t.id, t.title, t.start_date, t.end_date, t.visited_org_unit_id, e.name AS event, "
        "COALESCE('l' || t.location_id::text, 'u' || t.visited_org_unit_id::text) AS dest, "
        "COALESCE(l.name, u.name) AS place "
        "FROM trip t JOIN event_type e ON e.id = t.event_type_id LEFT JOIN location l ON l.id = t.location_id "
        "LEFT JOIN org_unit u ON u.id = t.visited_org_unit_id "
        "WHERE t.plan_year = %s AND t.status IN ('generated', 'planned', 'requested', 'approved') "
        "AND t.merged_into_trip_id IS NULL AND t.end_date >= %s "
        "AND COALESCE(t.location_id::text, t.visited_org_unit_id::text) IS NOT NULL "
        "ORDER BY t.start_date, t.id", (year, today)).fetchall()
    trips = [t for t in trips if can_see(allowed, t["visited_org_unit_id"])]
    people: dict[int, dict[int, str]] = {t["id"]: {} for t in trips}
    if people:
        for r in conn.execute(
                "SELECT tp.trip_id, p.id AS pid, p.full_name FROM trip_participant tp "
                "JOIN person p ON p.id = tp.person_id WHERE tp.travels AND tp.trip_id = ANY(%s)", (list(people),)):
            people[r["trip_id"]][r["pid"]] = r["full_name"]
    dismissed = {(r["trip_a_id"], r["trip_b_id"])
                 for r in conn.execute("SELECT trip_a_id, trip_b_id FROM synergy_dismissal")}
    by_dest: dict[str, list[dict[str, Any]]] = {}
    for t in trips:
        by_dest.setdefault(t["dest"], []).append(t)
    out: list[dict[str, Any]] = []
    for group in by_dest.values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if b["start_date"] > a["end_date"] and (b["start_date"] - a["end_date"]).days > within_days:
                    break                                   # later trips are even further away
                if b["start_date"] <= a["end_date"]:
                    continue                                # overlapping trips are a different check
                if (min(a["id"], b["id"]), max(a["id"], b["id"])) in dismissed:
                    continue
                gap = (b["start_date"] - a["end_date"]).days
                shared = sorted(set(people[a["id"]].values()) & set(people[b["id"]].values()))
                both = len(set(people[a["id"]]) | set(people[b["id"]]))
                out.append({
                    "place": a["place"], "gap_days": gap, "shared": shared, "people": both,
                    "first": _brief(a, allowed),
                    "second": _brief(b, allowed),
                })
    # the most useful first: people who would travel twice, then the shortest gap
    out.sort(key=lambda s: (-len(s["shared"]), s["gap_days"], s["first"]["id"]))
    return {"year": year, "within_days": within_days, "total": len(out), "suggestions": out[:LIMIT]}


def dismiss(conn: Connection, year: int, body: DismissIn, who: Identity, allowed: set[int] | None) -> dict[str, Any]:
    if body.trip_a == body.trip_b:
        raise CatalogError("Choose two different trips.")
    rows = conn.execute("SELECT id, visited_org_unit_id, plan_year FROM trip WHERE id = ANY(%s)",
                        ([body.trip_a, body.trip_b],)).fetchall()
    if len(rows) != 2 or any(r["plan_year"] != year or not can_see(allowed, r["visited_org_unit_id"]) for r in rows):
        raise CatalogError("The trip does not exist.", 404)
    if not any(can_edit(allowed, r["visited_org_unit_id"]) for r in rows):
        raise CatalogError("You can only dismiss suggestions for trips in your own area.", 403)
    a, b = sorted((body.trip_a, body.trip_b))
    conn.execute(
        "INSERT INTO synergy_dismissal(trip_a_id, trip_b_id, reason, dismissed_by) VALUES (%s,%s,%s,%s) "
        "ON CONFLICT (trip_a_id, trip_b_id) DO NOTHING", (a, b, body.reason, who.person_id))
    audit(conn, who.person_id, "synergy.dismiss", "trip", a, {"other": b})
    return {"dismissed": True}
