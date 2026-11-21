"""Everybody's own view of the plan: the trips a person takes part in, and an iCalendar export of them.

A person sees only their own trips. Until a plan year is published, only planners see their own trips in it
(supervisors see a plan that is still being worked on only after it has been published).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from psycopg import Connection

VISIBLE_STATUSES = ("published", "closed")


def _year_info(conn: Connection, year: int | None) -> tuple[list[dict], dict | None]:
    years = conn.execute("SELECT year, status FROM plan_year ORDER BY year DESC").fetchall()
    chosen = next((y for y in years if y["year"] == year), years[0] if years and year is None else None)
    return years, chosen


def my_trips(conn: Connection, person_id: int | None, year: int | None, planner: bool) -> dict[str, Any]:
    if person_id is None:
        return {"linked": False, "year": None, "years": [], "published": False, "trips": []}
    years, chosen = _year_info(conn, year)
    if chosen is None:
        return {"linked": True, "year": year, "years": [y["year"] for y in years], "published": False, "trips": []}
    visible = planner or chosen["status"] in VISIBLE_STATUSES
    base = {"linked": True, "year": chosen["year"], "years": [y["year"] for y in years],
            "plan_status": chosen["status"], "published": visible, "trips": []}
    if not visible:
        return base
    trips = conn.execute(
        "SELECT t.id, t.title, t.start_date, t.end_date, t.status, t.source, t.notes, t.cancel_reason, "
        "t.generated_start_date, t.generated_end_date, t.area_pending, t.area_decide_by, e.name AS event, "
        "e.code AS event_code, u.name AS place, "
        "tp.role AS my_role, tp.travels AS my_travels, "
        "(SELECT p.full_name FROM trip_participant o JOIN person p ON p.id = o.person_id "
        " WHERE o.trip_id = t.id AND o.role = 'organizer' ORDER BY p.full_name LIMIT 1) AS organizer, "
        "(SELECT json_build_object('type', c.change_type, 'reason', c.reason, 'category', c.category, "
        "        'at', c.changed_at) FROM trip_change c WHERE c.trip_id = t.id AND c.change_type <> 'generated' "
        " ORDER BY c.changed_at DESC, c.id DESC LIMIT 1) AS last_change "
        "FROM trip t JOIN trip_participant tp ON tp.trip_id = t.id AND tp.person_id = %s "
        "JOIN event_type e ON e.id = t.event_type_id LEFT JOIN org_unit u ON u.id = t.visited_org_unit_id "
        "WHERE t.plan_year = %s AND t.merged_into_trip_id IS NULL ORDER BY t.start_date, t.id",
        (person_id, chosen["year"])).fetchall()
    ids = [t["id"] for t in trips]
    combined: dict[int, list[str]] = defaultdict(list)
    people: dict[int, list[dict]] = defaultdict(list)
    if ids:
        for r in conn.execute(
            "SELECT m.merged_into_trip_id AS trip_id, e.name FROM trip m JOIN event_type e ON e.id = m.event_type_id "
            "WHERE m.merged_into_trip_id = ANY(%s) ORDER BY e.name", (ids,)):
            combined[r["trip_id"]].append(r["name"])
        for r in conn.execute(
            "SELECT tp.trip_id, p.full_name AS name, tp.role, tp.travels, pos.name AS position "
            "FROM trip_participant tp JOIN person p ON p.id = tp.person_id "
            "LEFT JOIN person_assignment a ON a.person_id = p.id AND a.valid_to IS NULL "
            "LEFT JOIN position pos ON pos.id = a.position_id WHERE tp.trip_id = ANY(%s) "
            "ORDER BY (tp.role = 'organizer') DESC, tp.travels DESC, p.full_name", (ids,)):
            people[r["trip_id"]].append({k: r[k] for k in ("name", "role", "travels", "position")})
    for t in trips:
        for k in ("start_date", "end_date", "generated_start_date", "generated_end_date", "area_decide_by"):
            t[k] = str(t[k]) if t[k] else None
        t["combined"] = combined[t["id"]]
        t["participants"] = people[t["id"]][:60]
        t["participant_count"] = len(people[t["id"]])
        if t["last_change"]:
            t["last_change"]["at"] = str(t["last_change"]["at"])
    base["trips"] = trips
    return base


# ------------------------------------------------------------------------------------------ iCalendar


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")


def _fold(line: str) -> str:
    """Lines are at most 75 octets; longer lines continue on the next line after a space (RFC 5545)."""
    out, cur = [], ""
    for ch in line:
        if len((cur + ch).encode()) > (75 if not out else 74):
            out.append(cur)
            cur = ch
        else:
            cur += ch
    out.append(cur)
    return "\r\n ".join(out)


def ics_for(trips: list[dict[str, Any]], year: int, now: datetime | None = None) -> str:
    """An all-day event per trip (the end date of an all-day event is exclusive). Cancelled trips are left out."""
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Travel Planner for Field Teams//EN", "CALSCALE:GREGORIAN",
             f"X-WR-CALNAME:My travel plan {year}"]
    for t in trips:
        if t["status"] == "cancelled":
            continue
        start, end = date.fromisoformat(t["start_date"]), date.fromisoformat(t["end_date"])
        role = {"organizer": "You organize this trip.", "host": "You host this visit."}.get(
            t["my_role"], "You travel.")
        proposed = " This trip is not confirmed yet." if t["status"] == "generated" else ""
        desc = " ".join(x for x in (t["event"] + ".", role + proposed, t["notes"] or "") if x)
        lines += [
            "BEGIN:VEVENT", f"UID:trip-{t['id']}@travel-planner", f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{start:%Y%m%d}", f"DTEND;VALUE=DATE:{end + timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{_escape(t['title'])}", f"DESCRIPTION:{_escape(desc)}",
            *([f"LOCATION:{_escape(t['place'])}"] if t["place"] else []),
            "TRANSP:TRANSPARENT" if t["my_role"] == "host" else "TRANSP:OPAQUE",
            f"STATUS:{'TENTATIVE' if t['status'] == 'generated' else 'CONFIRMED'}", "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(x) for x in lines) + "\r\n"
