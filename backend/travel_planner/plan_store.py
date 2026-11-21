"""Plan generation on the database: load inputs, run the engine, save, and read the plan back."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any

from psycopg import Connection

from . import plan_engine as pe
from .access import can_edit, can_see
from .catalog import CatalogError, audit

EDITABLE_STATUSES = ('generated', 'planned', 'requested', 'approved')

REPLACEABLE_SQL = """
SELECT t.id, t.merged_into_trip_id
FROM trip t
WHERE t.plan_year = %s AND t.source = 'generated'
  AND (t.status = 'generated' OR (t.status = 'cancelled' AND t.merged_into_trip_id IS NOT NULL))
  AND NOT EXISTS (SELECT 1 FROM trip_change c WHERE c.trip_id = t.id AND c.change_type NOT IN ('generated', 'created'))
"""


def _unit_ref(kind: str | None, uid: int | None) -> pe.UnitRef:
    return pe.UnitRef(kind or "nationwide", uid)


def replaceable_ids(conn: Connection, year: int) -> set[int]:
    """Untouched generated trips. A merged trip is replaced only together with the trip that absorbed it."""
    rows = conn.execute(REPLACEABLE_SQL, (year,)).fetchall()
    ids = {r["id"] for r in rows}
    return {r["id"] for r in rows if r["merged_into_trip_id"] is None or r["merged_into_trip_id"] in ids}


def load_trip_views(conn: Connection, year: int, exclude: set[int] | None = None) -> list[pe.TripView]:
    exclude = exclude or set()
    trips = conn.execute(
        "SELECT t.id, t.event_type_id, t.status, t.start_date, t.end_date, t.merged_into_trip_id, "
        "u.kind AS unit_kind, u.id AS unit_id FROM trip t LEFT JOIN org_unit u ON u.id = t.visited_org_unit_id "
        "WHERE t.plan_year = %s ORDER BY t.id", (year,)).fetchall()
    parts: dict[int, dict[int, tuple[str, bool]]] = defaultdict(dict)
    for r in conn.execute(
        "SELECT tp.trip_id, tp.person_id, tp.role, tp.travels FROM trip_participant tp "
        "JOIN trip t ON t.id = tp.trip_id WHERE t.plan_year = %s", (year,)):
        parts[r["trip_id"]][r["person_id"]] = (r["role"], r["travels"])
    return [
        pe.TripView(t["id"], t["event_type_id"], _unit_ref(t["unit_kind"], t["unit_id"]), t["start_date"],
                    t["end_date"], parts[t["id"]], absorbed=t["merged_into_trip_id"] is not None, status=t["status"],
                    survivor_key=t["merged_into_trip_id"])
        for t in trips if t["id"] not in exclude
    ]


def load_inputs(conn: Connection, year: int, replace: set[int] | None = None) -> pe.Inputs:
    """Everything the engine needs. Trips in ``replace`` are left out (they are about to be regenerated)."""
    units = conn.execute(
        "SELECT id, kind, name, parent_id, lead_person_id FROM org_unit WHERE active ORDER BY name").fetchall()
    people_rows = conn.execute(
        "SELECT p.id, p.full_name, pos.code, pos.level, pos.function_area, a.region_id, a.cluster_id, "
        "a.local_office_id FROM person p JOIN person_assignment a ON a.person_id = p.id AND a.valid_to IS NULL "
        "JOIN position pos ON pos.id = a.position_id WHERE p.active ORDER BY p.id").fetchall()
    office_of = {r["id"]: r["local_office_id"] for r in people_rows}
    regions, clusters, offices = [], [], []
    for u in units:
        lead = u["lead_person_id"]
        hub = office_of.get(lead) if lead else None
        if u["kind"] == "region":
            regions.append(pe.UnitIn("region", u["id"], u["name"], u["id"], lead, hub))
        elif u["kind"] == "cluster":
            clusters.append(pe.UnitIn("cluster", u["id"], u["name"], u["parent_id"], lead, hub))
        else:
            offices.append(pe.UnitIn("local_office", u["id"], u["name"], u["parent_id"], None, u["id"]))
    people = [pe.PersonIn(r["id"], r["full_name"], r["code"], r["level"], r["function_area"], r["region_id"],
                          r["cluster_id"], r["local_office_id"]) for r in people_rows]
    positions = {r["code"]: (r["level"], r["function_area"]) for r in
                 conn.execute("SELECT code, level, function_area FROM position")}

    pos_code = {r["id"]: r["code"] for r in conn.execute("SELECT id, code FROM position")}
    rules_by_event: dict[int | None, list[pe.ERule]] = defaultdict(list)
    not_held: dict[int, str] = {}
    for r in conn.execute("SELECT * FROM rule WHERE active ORDER BY rule_key"):
        if r["rule_type"] in ("annual_quota", "cadence") and not pe.held_in(r["params"] or {}, year):
            not_held[r["event_type_id"]] = pe.schedule_phrase(r["params"])   # held in other years only
            continue
        rules_by_event[r["event_type_id"]].append(pe.ERule(
            r["id"], r["rule_key"], r["rule_type"], r["scope_kind"], pos_code.get(r["position_id"]), r["period"],
            r["interval_n"], r["min_count"], r["max_count"], r["params"] or {}, r["severity"]))
    parts: dict[int, list[pe.EventPos]] = defaultdict(list)
    for r in conn.execute("SELECT * FROM event_type_position ORDER BY position_id"):
        parts[r["event_type_id"]].append(pe.EventPos(
            pos_code[r["position_id"]], r["participation"], r["yearly_limit"], r["travels"]))
    events = [
        pe.EventIn(e["id"], e["code"], e["name"], e["is_company_event"], e["visited_kind"], e["typical_days"],
                   e["typical_mode"], pos_code.get(e["organizer_position_id"]), parts[e["id"]],
                   rules_by_event[e["id"]])
        for e in conn.execute("SELECT * FROM event_type WHERE active ORDER BY id")
    ]
    active = {e.id for e in events}
    merges = {frozenset({r["event_type_id"], r["merges_into_id"]})
              for r in conn.execute("SELECT event_type_id, merges_into_id FROM merge_rule WHERE active")
              if r["event_type_id"] in active and r["merges_into_id"] in active}
    blackouts = []
    for b in conn.execute(
        "SELECT b.*, COALESCE(array_agg(be.event_type_id) FILTER (WHERE be.event_type_id IS NOT NULL), '{}') AS ids "
        "FROM blackout_period b LEFT JOIN blackout_event_type be ON be.blackout_id = b.id "
        "WHERE b.plan_year = %s GROUP BY b.id ORDER BY b.start_date", (year,)):
        blackouts.append(pe.BlackoutIn(b["id"], b["name"], b["start_date"], b["end_date"], b["severity"],
                                       frozenset(b["ids"]), b["caused_by_event_type_id"]))
    kept = [v for v in load_trip_views(conn, year, exclude=replace or set())
            if v.status != "cancelled" and not v.absorbed]
    # an event that has a quota or cadence in force this year is held; one with only out-of-year rules is not
    for e in events:
        if any(r.rule_type in ("annual_quota", "cadence") for r in e.rules):
            not_held.pop(e.id, None)
    return pe.Inputs(year, regions, clusters, offices, people, events, rules_by_event[None], merges, blackouts,
                     positions, kept, not_held)


def _save(conn: Connection, year: int, result: pe.Result, replace: set[int], actor: int | None) -> None:
    if replace:
        conn.execute("DELETE FROM trip WHERE id = ANY(%s)", (list(replace),))
    location = {r["local_office_id"]: r["id"] for r in
                conn.execute("SELECT id, local_office_id FROM location WHERE local_office_id IS NOT NULL ORDER BY id")}
    events = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM event_type")}
    ids: dict[int, int] = {}
    by_key = {t.key: t for t in result.trips}
    ordered = sorted(result.trips, key=lambda t: (t.absorbed_into is not None, t.key))
    for t in ordered:
        survivor = ids.get(t.absorbed_into) if t.absorbed_into else None
        row = conn.execute(
            "INSERT INTO trip(plan_year, event_type_id, title, visited_org_unit_id, location_id, start_date, "
            "end_date, status, source, rule_id, generated_start_date, generated_end_date, merged_into_trip_id, "
            "transport_mode, notes, cancel_reason, created_by) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'generated',%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (year, t.event_id, t.title, t.visited.id if t.visited.kind != "nationwide" else None,
             location.get(t.hub_office_id), t.start, t.end,
             "cancelled" if survivor else "generated", t.rule_id, t.start, t.end, survivor, t.transport_mode,
             " ".join(t.notes) or None,
             f"Combined with {events[by_key[t.absorbed_into].event_id]} in the same place and week."
             if survivor else None, actor),
        ).fetchone()
        ids[t.key] = row["id"]
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO trip_participant(trip_id, person_id, role, travels) VALUES (%s,%s,%s,%s)",
            [(ids[t.key], pid, role, travels) for t in result.trips for pid, (role, travels) in t.participants.items()])
        cur.executemany(
            "INSERT INTO trip_change(trip_id, changed_by, change_type, after_data) VALUES (%s,%s,'generated',%s)",
            [(ids[t.key], actor, json.dumps({"start": str(t.start), "end": str(t.end)})) for t in result.trips])
    conn.execute("UPDATE plan_year SET status = 'review' WHERE year = %s AND status = 'draft'", (year,))


def generate_plan(conn: Connection, year: int, commit: bool, actor: int | None) -> dict[str, Any]:
    """Generate (or regenerate) the plan of a year. A preview runs everything and rolls back."""
    py = conn.execute("SELECT status FROM plan_year WHERE year = %s", (year,)).fetchone()
    if py is None:
        raise CatalogError(f"The plan year {year} does not exist.", 404)
    if py["status"] in ("published", "closed"):
        raise CatalogError(f"The plan year {year} is {py['status']}; it can no longer be regenerated.", 409)
    replace = replaceable_ids(conn, year)
    inp = load_inputs(conn, year, replace)
    if not inp.clusters:
        raise CatalogError("There is no organization yet. Import it first (Organization page).", 409)
    result = pe.generate(inp)
    _save(conn, year, result, replace, actor)
    event_names = {e.id: e.name for e in inp.events}
    survivors = [t for t in result.trips if t.absorbed_into is None]
    by_event = Counter(event_names[t.event_id] for t in survivors)
    merged = Counter(event_names[t.event_id] for t in result.trips if t.absorbed_into is not None)
    warn_counts = Counter(w.code for w in result.warnings)
    report = {
        "year": year,
        "applied": commit,
        "trips_created": len(survivors),
        "trips_merged": sum(merged.values()),
        "trips_replaced": len(replace),
        "trips_kept": len(inp.kept),
        "by_event": [{"event": n, "trips": c, "merged": merged.get(n, 0)} for n, c in sorted(by_event.items())],
        "unplaced": result.unplaced,
        "skipped": result.skipped,
        "warning_counts": dict(warn_counts),
        "warnings": [w.__dict__ for w in result.warnings[:60]],
        "warning_total": len(result.warnings),
    }
    if commit:
        audit(conn, actor, "plan.generate", "plan_year", year,
              {"created": len(survivors), "merged": sum(merged.values()), "replaced": len(replace),
               "kept": len(inp.kept), "warnings": len(result.warnings)})
    return report


# ----------------------------------------------------------------------------------------- reading the plan


def _scope_sql(allowed: set[int] | None, column: str = "t.visited_org_unit_id") -> tuple[str, list]:
    """SQL condition limiting trips to the places a person may see (nationwide trips are visible to every planner)."""
    if allowed is None:
        return "TRUE", []
    return f"({column} IS NULL OR {column} = ANY(%s))", [sorted(allowed)]


def plan_summary(conn: Connection, year: int, allowed: set[int] | None = None) -> dict[str, Any]:
    py = conn.execute("SELECT year, status, published_at FROM plan_year WHERE year = %s", (year,)).fetchone()
    if py is None:
        raise CatalogError(f"The plan year {year} does not exist.", 404)
    units = {u["id"]: u for u in conn.execute("SELECT id, kind, name, parent_id FROM org_unit WHERE active")}
    scope, scope_args = _scope_sql(allowed)
    rows = conn.execute(
        "SELECT t.visited_org_unit_id AS uid, EXTRACT(month FROM t.start_date)::int AS m, count(*) AS n "
        f"FROM trip t WHERE t.plan_year = %s AND t.status <> 'cancelled' AND {scope} GROUP BY 1, 2",  # noqa: S608
        (year, *scope_args)).fetchall()
    cells: dict[tuple[str, int | None], list[int]] = defaultdict(lambda: [0] * 12)
    for r in rows:
        u = units.get(r["uid"])
        if r["uid"] is None:
            key = ("nationwide", None)
        elif u["kind"] == "cluster":
            key = ("cluster", u["id"])
        else:  # region events and local office trips are shown on the region's own row
            rid = u["id"] if u["kind"] == "region" else u["parent_id"]
            key = ("region", rid)
        cells[key][r["m"] - 1] += r["n"]
    out_regions = []
    for region in sorted((u for u in units.values() if u["kind"] == "region"), key=lambda u: u["name"]):
        region_clusters = sorted(
            (u for u in units.values() if u["kind"] == "cluster" and u["parent_id"] == region["id"]),
            key=lambda u: u["name"])
        rows_ = [{"unit_id": c["id"], "label": c["name"], "months": cells.get(("cluster", c["id"]), [0] * 12)}
                 for c in region_clusters if allowed is None or c["id"] in allowed]
        if allowed is None or region["id"] in allowed:
            rows_.append({"unit_id": region["id"], "label": "Region and local offices",
                          "months": cells.get(("region", region["id"]), [0] * 12)})
        if rows_:
            out_regions.append({"id": region["id"], "name": region["name"], "rows": rows_})
    nationwide = cells.get(("nationwide", None), [0] * 12)
    totals = conn.execute(
        "SELECT count(*) FILTER (WHERE t.status <> 'cancelled') AS trips, "
        "count(*) FILTER (WHERE t.status = 'cancelled' AND t.merged_into_trip_id IS NOT NULL) AS merged, "
        "count(*) FILTER (WHERE t.source = 'manual' AND t.status <> 'cancelled') AS manual "
        f"FROM trip t WHERE t.plan_year = %s AND {scope}", (year, *scope_args)).fetchone()  # noqa: S608
    return {"year": year, "status": py["status"],
            "published_at": py["published_at"].isoformat() if py["published_at"] else None, "regions": out_regions,
            "nationwide": {"unit_id": None, "label": "Nationwide events", "months": nationwide},
            "totals": dict(totals), "can_edit_all": allowed is None}


def plan_trips(conn: Connection, year: int, unit_id: int | None, month: int | None, event_type_id: int | None,
               nationwide: bool, limit: int = 500, allowed: set[int] | None = None) -> list[dict[str, Any]]:
    scope, scope_args = _scope_sql(allowed)
    clauses, args = ["t.plan_year = %s", "t.status <> 'cancelled'", scope], [year, *scope_args]
    if nationwide:
        clauses.append("t.visited_org_unit_id IS NULL")
    elif unit_id is not None:
        # a region row also covers its local offices
        clauses.append("(t.visited_org_unit_id = %s OR u.parent_id = %s AND u.kind = 'local_office')")
        args += [unit_id, unit_id]
    if month:
        clauses.append("EXTRACT(month FROM t.start_date) = %s")
        args.append(month)
    if event_type_id:
        clauses.append("t.event_type_id = %s")
        args.append(event_type_id)
    rows = conn.execute(
        "SELECT t.id, t.title, t.start_date, t.end_date, t.status, t.source, t.notes, e.name AS event, "
        "e.code AS event_code, "
        "t.visited_org_unit_id, CASE u.kind WHEN 'local_office' THEN u.parent_id ELSE u.id END AS row_unit_id, "
        "u.name AS place, "
        "(SELECT count(*) FROM trip_participant p WHERE p.trip_id = t.id AND p.travels) AS travelers, "
        "(SELECT count(*) FROM trip m WHERE m.merged_into_trip_id = t.id) AS merged_count, "
        "EXISTS (SELECT 1 FROM trip_change c WHERE c.trip_id = t.id AND c.change_type NOT IN ('generated', 'created')) "
        "AS changed "
        "FROM trip t JOIN event_type e ON e.id = t.event_type_id LEFT JOIN org_unit u ON u.id = t.visited_org_unit_id "
        f"WHERE {' AND '.join(clauses)} ORDER BY t.start_date, t.id LIMIT %s", (*args, limit)).fetchall()  # noqa: S608
    for r in rows:
        r["start_date"], r["end_date"] = str(r["start_date"]), str(r["end_date"])
        r["editable"] = can_edit(allowed, r.pop("visited_org_unit_id"))
    return rows


def trip_detail(conn: Connection, trip_id: int, allowed: set[int] | None = None) -> dict[str, Any]:
    t = conn.execute(
        "SELECT t.*, e.name AS event, py.status AS plan_status, u.name AS place FROM trip t "
        "JOIN event_type e ON e.id = t.event_type_id JOIN plan_year py ON py.year = t.plan_year "
        "LEFT JOIN org_unit u ON u.id = t.visited_org_unit_id WHERE t.id = %s", (trip_id,)).fetchone()
    if t is None or not can_see(allowed, t["visited_org_unit_id"]):
        raise CatalogError("The trip does not exist.", 404)
    people = conn.execute(
        "SELECT p.id AS person_id, p.full_name AS name, tp.role, tp.travels, pos.name AS position "
        "FROM trip_participant tp JOIN person p ON p.id = tp.person_id "
        "JOIN person_assignment a ON a.person_id = p.id AND a.valid_to IS NULL "
        "JOIN position pos ON pos.id = a.position_id WHERE tp.trip_id = %s "
        "ORDER BY (tp.role = 'organizer') DESC, tp.travels DESC, p.full_name", (trip_id,)).fetchall()
    merged = conn.execute(
        "SELECT t.id, e.name AS event FROM trip t JOIN event_type e ON e.id = t.event_type_id "
        "WHERE t.merged_into_trip_id = %s", (trip_id,)).fetchall()
    editable = (can_edit(allowed, t["visited_org_unit_id"]) and t["status"] in EDITABLE_STATUSES
                and t["plan_status"] != "closed")
    return {"id": t["id"], "title": t["title"], "event": t["event"], "place": t["place"], "status": t["status"],
            "source": t["source"], "start_date": str(t["start_date"]), "end_date": str(t["end_date"]),
            "generated_start_date": str(t["generated_start_date"]) if t["generated_start_date"] else None,
            "generated_end_date": str(t["generated_end_date"]) if t["generated_end_date"] else None,
            "notes": t["notes"], "cancel_reason": t["cancel_reason"], "transport_mode": t["transport_mode"],
            "plan_year": t["plan_year"], "plan_status": t["plan_status"], "updated_at": t["updated_at"].isoformat(),
            "editable": editable, "participants": people, "combined": merged}


def trip_history(conn: Connection, trip_id: int, allowed: set[int] | None = None) -> list[dict[str, Any]]:
    t = conn.execute("SELECT visited_org_unit_id FROM trip WHERE id = %s", (trip_id,)).fetchone()
    if t is None or not can_see(allowed, t["visited_org_unit_id"]):
        raise CatalogError("The trip does not exist.", 404)
    rows = conn.execute(
        "SELECT c.id, c.changed_at, c.change_type, c.category, c.reason, c.before_data, c.after_data, "
        "p.full_name AS changed_by FROM trip_change c LEFT JOIN person p ON p.id = c.changed_by "
        "WHERE c.trip_id = %s ORDER BY c.changed_at DESC, c.id DESC", (trip_id,)).fetchall()
    for r in rows:
        r["changed_at"] = r["changed_at"].isoformat()
        r["changed_by"] = r["changed_by"] or ("System" if r["change_type"] == "generated" else "Administrator")
    return rows


def plan_people(conn: Connection, allowed: set[int] | None, q: str | None, limit: int = 40) -> list[dict[str, Any]]:
    clauses, args = ["p.active"], []
    if allowed is not None:
        clauses.append("(a.cluster_id = ANY(%s) OR a.region_id = ANY(%s) OR a.local_office_id = ANY(%s))")
        args += [sorted(allowed)] * 3
    if q:
        clauses.append("p.full_name ILIKE %s")
        args.append(f"%{q}%")
    return conn.execute(
        "SELECT p.id AS person_id, p.full_name AS name, pos.name AS position FROM person p "
        "JOIN person_assignment a ON a.person_id = p.id AND a.valid_to IS NULL "
        "JOIN position pos ON pos.id = a.position_id "
        f"WHERE {' AND '.join(clauses)} ORDER BY pos.level, p.full_name LIMIT %s", (*args, limit)).fetchall()  # noqa: S608


_TRANSITIONS = {("review", "published"), ("published", "review"), ("published", "closed")}


def set_plan_status(conn: Connection, year: int, to: str, actor: int | None) -> dict[str, Any]:
    """Publish a reviewed plan, withdraw it, or close the year. Supervisors see a plan once it is published."""
    row = conn.execute("SELECT status FROM plan_year WHERE year = %s FOR UPDATE", (year,)).fetchone()
    if row is None:
        raise CatalogError(f"The plan year {year} does not exist.", 404)
    if row["status"] == "draft" and to == "published":
        raise CatalogError("Generate the plan first.", 409)
    if (row["status"], to) not in _TRANSITIONS:
        raise CatalogError(f"A plan that is {row['status']} cannot become {to}.", 409)
    if to == "published" and not conn.execute(
            "SELECT 1 FROM trip WHERE plan_year = %s AND status <> 'cancelled' LIMIT 1", (year,)).fetchone():
        raise CatalogError("The plan has no trips yet.", 409)
    conn.execute(
        "UPDATE plan_year SET status = %s, published_at = CASE WHEN %s = 'published' THEN now() ELSE published_at END, "
        "published_by = CASE WHEN %s = 'published' THEN %s ELSE published_by END WHERE year = %s",
        (to, to, to, actor, year))
    audit(conn, actor, "plan.status", "plan_year", year, {"from": row["status"], "to": to})
    return {"year": year, "status": to}


def list_plan_years(conn: Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT y.year, y.status, (SELECT count(*) FROM trip t WHERE t.plan_year = y.year AND t.status <> 'cancelled') "
        "AS trips FROM plan_year y ORDER BY y.year").fetchall()
    return [dict(r) for r in rows]


def create_plan_year(conn: Connection, year: int, actor: int | None) -> dict[str, Any]:
    """Open a new plan year as a draft (for example 2028). Events held every second year need the following years."""
    last = conn.execute("SELECT max(year) AS y FROM plan_year").fetchone()["y"]
    if conn.execute("SELECT 1 FROM plan_year WHERE year = %s", (year,)).fetchone():
        raise CatalogError(f"The plan year {year} already exists.", 409)
    if last is not None and year != last + 1:
        raise CatalogError(f"The next plan year is {last + 1}.", 409)
    conn.execute("INSERT INTO plan_year(year) VALUES (%s)", (year,))
    audit(conn, actor, "plan.year.create", "plan_year", year, {})
    return {"year": year, "status": "draft", "trips": 0}


def plan_warnings(conn: Connection, year: int) -> dict[str, Any]:
    inp = load_inputs(conn, year)
    views = load_trip_views(conn, year)
    warns = pe.evaluate(views, inp)
    counts = Counter(w.code for w in warns)
    return {"year": year, "total": len(warns), "counts": dict(counts), "warnings": [w.__dict__ for w in warns[:200]]}


__all__ = ["generate_plan", "plan_summary", "plan_trips", "trip_detail", "trip_history", "plan_people",
           "plan_warnings", "set_plan_status"]
