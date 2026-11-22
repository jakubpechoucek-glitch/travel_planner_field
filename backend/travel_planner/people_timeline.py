"""The people timeline: one row per person, one bar per trip, for a window of days.

It answers "who is where, when": the trips a person travels on (or hosts), the number of days away in the window, and
clashes where a person is on two trips at once. Blackout periods of the plan year are returned so the screen can shade
them. Planners see the people on the trips of their own scope.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from psycopg import Connection

from .access import can_see
from .catalog import CatalogError

MAX_DAYS = 125
MAX_PEOPLE = 250


def people_timeline(conn: Connection, year: int, allowed: set[int] | None, start: date, end: date,
                    unit_id: int | None = None, q: str | None = None, hosts: bool = False) -> dict[str, Any]:
    if end < start:
        raise CatalogError("The end of the window cannot be before its start.")
    if (end - start).days + 1 > MAX_DAYS:
        raise CatalogError(f"Choose a window of at most {MAX_DAYS} days.")
    clauses = ["t.plan_year = %s", "t.status <> 'cancelled'", "t.merged_into_trip_id IS NULL",
               "t.start_date <= %s", "t.end_date >= %s"]
    args: list[Any] = [year, end, start]
    if not hosts:
        clauses.append("tp.travels")
    if unit_id is not None:
        clauses.append("(a.region_id = %s OR a.cluster_id = %s OR a.local_office_id = %s)")
        args += [unit_id] * 3
    if q:
        clauses.append("p.full_name ILIKE %s")
        args.append(f"%{q.strip()}%")
    rows = conn.execute(
        "SELECT p.id AS person_id, p.full_name AS name, pos.name AS position, pos.level, "
        "COALESCE(cl.name, rg.name) AS unit, t.id AS trip_id, t.title, t.start_date, t.end_date, t.status, "
        "t.visited_org_unit_id, e.code AS event_code, e.name AS event, tp.role, tp.travels "
        "FROM trip_participant tp JOIN trip t ON t.id = tp.trip_id JOIN person p ON p.id = tp.person_id AND p.active "
        "JOIN event_type e ON e.id = t.event_type_id "
        "LEFT JOIN person_assignment a ON a.person_id = p.id AND a.valid_to IS NULL "
        "LEFT JOIN position pos ON pos.id = a.position_id "
        "LEFT JOIN org_unit cl ON cl.id = a.cluster_id LEFT JOIN org_unit rg ON rg.id = a.region_id "
        f"WHERE {' AND '.join(clauses)} ORDER BY p.full_name, p.id, t.start_date, t.id", args).fetchall()  # noqa: S608
    by_person: dict[int, dict[str, Any]] = {}
    for r in rows:
        if not can_see(allowed, r["visited_org_unit_id"]):
            continue
        person = by_person.setdefault(r["person_id"], {
            "person_id": r["person_id"], "name": r["name"], "position": r["position"], "unit": r["unit"], "trips": []})
        person["trips"].append({
            "id": r["trip_id"], "title": r["title"], "event": r["event"], "event_code": r["event_code"],
            "start_date": str(r["start_date"]), "end_date": str(r["end_date"]), "status": r["status"],
            "role": r["role"], "travels": r["travels"]})
    people = list(by_person.values())
    for p in people:
        trips = p["trips"]
        away: set[date] = set()
        for t in trips:
            t["clash"] = False
        for i, a in enumerate(trips):
            if not a["travels"]:
                continue
            s, e = date.fromisoformat(a["start_date"]), date.fromisoformat(a["end_date"])
            cur = max(s, start)
            while cur <= min(e, end):
                away.add(cur)
                cur = date.fromordinal(cur.toordinal() + 1)
            for b in trips[i + 1:]:
                if b["travels"] and a["start_date"] <= b["end_date"] and b["start_date"] <= a["end_date"]:
                    a["clash"] = b["clash"] = True
        p["days_away"] = len(away)
        p["clashes"] = sum(1 for t in trips if t["clash"])
    truncated = len(people) > MAX_PEOPLE
    blackouts = [
        {"id": b["id"], "name": b["name"], "start_date": str(b["start_date"]), "end_date": str(b["end_date"]),
         "severity": b["severity"]}
        for b in conn.execute(
            "SELECT id, name, start_date, end_date, severity FROM blackout_period WHERE plan_year = %s "
            "AND start_date <= %s AND end_date >= %s ORDER BY start_date", (year, end, start))]
    return {"year": year, "start": str(start), "end": str(end), "total": len(people), "truncated": truncated,
            "people": people[:MAX_PEOPLE], "blackouts": blackouts}
