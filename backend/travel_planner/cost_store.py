"""Cost forecast on the database: load the plan, run the engine, aggregate, compare with the budget, and manage
the rate card, travel modes, settings, early-booking tiers and budget lines."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

from psycopg import Connection
from pydantic import BaseModel, ConfigDict, Field

from . import cost_engine as ce
from .budget_import import parse_budget
from .catalog import CatalogError, audit
from .currency import CURRENCY, SYMBOL
from .plan_store import _scope_sql

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
Mode = Literal["land", "air", "sea"]
RATE_KINDS = ("airfare", "sea_fare", "land_transport", "lodging_per_night", "per_diem", "local_transport", "other")
RateKind = Literal["airfare", "sea_fare", "land_transport", "lodging_per_night", "per_diem", "local_transport", "other"]
LUZON = ("NCR", "NORTH-LUZON", "SOUTH-LUZON")


# ------------------------------------------------------------------------------------------ input models


class RateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # a rate is always in pesos: a "currency" field is refused, not ignored

    rate_kind: RateKind
    mode: Mode | None = None
    position_id: int | None = None
    amount: float = Field(ge=0, le=10_000_000)
    valid_from: date
    note: str | None = Field(default=None, max_length=200)


class ModeIn(BaseModel):
    from_region_id: int
    to_region_id: int
    mode: Mode


class OverrideIn(BaseModel):
    from_region_id: int | None = None
    to_unit_id: int
    mode: Mode
    note: str | None = Field(default=None, max_length=200)


class SettingsIn(BaseModel):
    hq_region_id: int | None = None
    venue_region_id: int | None = None


class TierIn(BaseModel):
    min_days_ahead: int = Field(ge=1, le=730)
    factor: float = Field(gt=0, le=1)
    note: str | None = Field(default=None, max_length=200)


class TiersIn(BaseModel):
    tiers: list[TierIn] = Field(max_length=10)


class MappingIn(BaseModel):
    event_type_id: int | None = None


# ------------------------------------------------------------------------------------------ configuration


def _settings(conn: Connection) -> dict[str, int | None]:
    rows = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM app_setting")}
    return {k: (int(rows[k]) if rows.get(k) else None) for k in ("hq_region_id", "venue_region_id")}


def _default_regions(conn: Connection) -> dict[str, int | None]:
    """The settings, falling back to NCR (where the Head and the head office are) when it exists."""
    s = _settings(conn)
    ncr = conn.execute("SELECT id FROM org_unit WHERE kind = 'region' AND code = 'NCR'").fetchone()
    return {k: v if v is not None else (ncr["id"] if ncr else None) for k, v in s.items()}


def config(conn: Connection) -> dict[str, Any]:
    rates = conn.execute(
        "SELECT r.id, r.rate_kind, r.mode, r.position_id, p.name AS position, r.amount, r.currency, r.valid_from, "
        "r.valid_to, r.note FROM cost_rate r LEFT JOIN position p ON p.id = r.position_id "
        "ORDER BY r.rate_kind, r.mode NULLS FIRST, p.name NULLS FIRST, r.valid_from").fetchall()
    for r in rates:
        r["amount"] = float(r["amount"])
        r["valid_from"] = str(r["valid_from"])
        r["valid_to"] = str(r["valid_to"]) if r["valid_to"] else None
    regions = conn.execute(
        "SELECT id, name, code FROM org_unit WHERE kind = 'region' AND active ORDER BY name").fetchall()
    return {
        "currency": CURRENCY, "currency_symbol": SYMBOL,
        "rates": rates, "regions": regions,
        "modes": conn.execute("SELECT from_region_id, to_region_id, mode FROM travel_mode").fetchall(),
        "overrides": conn.execute(
            "SELECT o.id, o.from_region_id, f.name AS from_region, o.to_unit_id, u.name AS to_unit, u.kind AS to_kind, "
            "o.mode, o.note FROM travel_mode_override o JOIN org_unit u ON u.id = o.to_unit_id "
            "LEFT JOIN org_unit f ON f.id = o.from_region_id ORDER BY u.name").fetchall(),
        "settings": _settings(conn), "effective_settings": _default_regions(conn),
        "tiers": [{"min_days_ahead": t["min_days_ahead"], "factor": float(t["factor"]), "note": t["note"]}
                  for t in conn.execute("SELECT min_days_ahead, factor, note FROM booking_discount "
                                        "ORDER BY min_days_ahead")],
        "positions": conn.execute("SELECT id, name FROM position WHERE active ORDER BY level, name").fetchall(),
    }


def save_rate(conn: Connection, body: RateIn, actor: int | None) -> int:
    """A new rate from a date closes the open one it replaces, so the history of prices stays."""
    if body.position_id is not None and not conn.execute("SELECT 1 FROM position WHERE id = %s",
                                                         (body.position_id,)).fetchone():
        raise CatalogError("The position does not exist.")
    same = ("rate_kind = %s AND mode IS NOT DISTINCT FROM %s AND position_id IS NOT DISTINCT FROM %s")
    key = (body.rate_kind, body.mode, body.position_id)
    if conn.execute(f"SELECT 1 FROM cost_rate WHERE {same} AND valid_from >= %s",  # noqa: S608
                    (*key, body.valid_from)).fetchone():
        raise CatalogError("A rate that starts on or after this date already exists. Choose a later date.", 409)
    conn.execute(f"UPDATE cost_rate SET valid_to = %s WHERE {same} AND valid_to IS NULL",  # noqa: S608
                 (body.valid_from - timedelta(days=1), *key))
    rid = conn.execute(
        "INSERT INTO cost_rate(rate_kind, mode, position_id, amount, valid_from, note) VALUES (%s,%s,%s,%s,%s,%s) "
        "RETURNING id", (*key, body.amount, body.valid_from, body.note)).fetchone()["id"]
    audit(conn, actor, "cost.rate.save", "cost_rate", rid, {"kind": body.rate_kind, "amount": body.amount})
    return rid


def end_rate(conn: Connection, rate_id: int, actor: int | None) -> None:
    row = conn.execute("UPDATE cost_rate SET valid_to = GREATEST(valid_from, CURRENT_DATE - 1) "
                       "WHERE id = %s AND valid_to IS NULL RETURNING id", (rate_id,)).fetchone()
    if row is None:
        raise CatalogError("The rate does not exist or has ended already.", 404)
    audit(conn, actor, "cost.rate.end", "cost_rate", rate_id, {})


def set_mode(conn: Connection, body: ModeIn, actor: int | None) -> None:
    ids = {r["id"] for r in conn.execute("SELECT id FROM org_unit WHERE kind = 'region'")}
    if body.from_region_id not in ids or body.to_region_id not in ids:
        raise CatalogError("The region does not exist.")
    conn.execute(
        "INSERT INTO travel_mode(from_region_id, to_region_id, mode) VALUES (%s,%s,%s) "
        "ON CONFLICT (from_region_id, to_region_id) DO UPDATE SET mode = EXCLUDED.mode",
        (body.from_region_id, body.to_region_id, body.mode))
    audit(conn, actor, "cost.mode.set", "travel_mode", f"{body.from_region_id}-{body.to_region_id}",
          {"mode": body.mode})


def suggest_modes(conn: Connection, actor: int | None) -> dict[str, int]:
    """Suggested defaults for the regions that exist: land inside a region and between the Luzon regions
    (NCR, North Luzon, South Luzon), air everywhere else. Existing choices are kept. The business must confirm."""
    regions = conn.execute("SELECT id, code FROM org_unit WHERE kind = 'region' AND active").fetchall()
    added = 0
    for a in regions:
        for b in regions:
            mode = "land" if a["id"] == b["id"] or (a["code"] in LUZON and b["code"] in LUZON) else "air"
            added += conn.execute(
                "INSERT INTO travel_mode(from_region_id, to_region_id, mode) VALUES (%s,%s,%s) "
                "ON CONFLICT DO NOTHING RETURNING id", (a["id"], b["id"], mode)).rowcount
    audit(conn, actor, "cost.mode.suggest", "travel_mode", "all", {"added": added})
    return {"added": added, "regions": len(regions)}


def add_override(conn: Connection, body: OverrideIn, actor: int | None) -> int:
    if not conn.execute("SELECT 1 FROM org_unit WHERE id = %s", (body.to_unit_id,)).fetchone():
        raise CatalogError("The place does not exist.")
    if body.from_region_id is not None and not conn.execute(
            "SELECT 1 FROM org_unit WHERE id = %s AND kind = 'region'", (body.from_region_id,)).fetchone():
        raise CatalogError("The region does not exist.")
    row = conn.execute(
        "INSERT INTO travel_mode_override(from_region_id, to_unit_id, mode, note) VALUES (%s,%s,%s,%s) "
        "ON CONFLICT (COALESCE(from_region_id, 0), to_unit_id) DO UPDATE SET mode = EXCLUDED.mode, "
        "note = EXCLUDED.note RETURNING id", (body.from_region_id, body.to_unit_id, body.mode, body.note)).fetchone()
    audit(conn, actor, "cost.override.save", "travel_mode_override", row["id"], {"mode": body.mode})
    return row["id"]


def delete_override(conn: Connection, override_id: int, actor: int | None) -> None:
    if not conn.execute("DELETE FROM travel_mode_override WHERE id = %s RETURNING id", (override_id,)).fetchone():
        raise CatalogError("The override does not exist.", 404)
    audit(conn, actor, "cost.override.delete", "travel_mode_override", override_id, {})


def save_settings(conn: Connection, body: SettingsIn, actor: int | None) -> dict:
    for key, value in body.model_dump().items():
        if value is not None and not conn.execute("SELECT 1 FROM org_unit WHERE id = %s AND kind = 'region'",
                                                  (value,)).fetchone():
            raise CatalogError("The region does not exist.")
        conn.execute("INSERT INTO app_setting(key, value) VALUES (%s,%s) ON CONFLICT (key) DO UPDATE "
                     "SET value = EXCLUDED.value", (key, str(value) if value is not None else None))
    audit(conn, actor, "cost.settings", "app_setting", "cost", {})
    return _settings(conn)


def save_tiers(conn: Connection, body: TiersIn, actor: int | None) -> list[dict]:
    if len({t.min_days_ahead for t in body.tiers}) != len(body.tiers):
        raise CatalogError("Two tiers have the same number of days.")
    tiers = sorted(body.tiers, key=lambda t: t.min_days_ahead)
    if any(a.factor < b.factor for a, b in zip(tiers, tiers[1:], strict=False)):
        raise CatalogError("Booking earlier cannot be dearer: the factor must not rise with the number of days.")
    conn.execute("DELETE FROM booking_discount")
    for t in tiers:
        conn.execute("INSERT INTO booking_discount(min_days_ahead, factor, note) VALUES (%s,%s,%s)",
                     (t.min_days_ahead, t.factor, t.note))
    audit(conn, actor, "cost.tiers", "booking_discount", "all", {"tiers": len(tiers)})
    return [t.model_dump() for t in tiers]


# ------------------------------------------------------------------------------------------ the forecast


def _load(conn: Connection, year: int, allowed: set[int] | None):
    scope, args = _scope_sql(allowed)
    positions = {r["id"]: r["code"] for r in conn.execute("SELECT id, code FROM position")}
    settings = _default_regions(conn)
    rows = conn.execute(
        "SELECT t.id, t.event_type_id, t.start_date, t.end_date, t.visited_org_unit_id AS unit_id, u.kind, "
        "CASE u.kind WHEN 'region' THEN u.id ELSE u.parent_id END AS dest_region "
        "FROM trip t LEFT JOIN org_unit u ON u.id = t.visited_org_unit_id "
        f"WHERE t.plan_year = %s AND t.status <> 'cancelled' AND t.merged_into_trip_id IS NULL AND {scope} "  # noqa: S608
        "ORDER BY t.start_date, t.id", (year, *args)).fetchall()
    ids = [r["id"] for r in rows]
    people = {}
    if ids:
        for r in conn.execute(
            "SELECT DISTINCT p.id, pos.code, COALESCE(a.region_id, o.parent_id, c.parent_id) AS home "
            "FROM trip_participant tp JOIN person p ON p.id = tp.person_id "
            "JOIN person_assignment a ON a.person_id = p.id AND a.valid_to IS NULL "
            "JOIN position pos ON pos.id = a.position_id LEFT JOIN org_unit o ON o.id = a.local_office_id "
            "LEFT JOIN org_unit c ON c.id = a.cluster_id WHERE tp.trip_id = ANY(%s) AND tp.travels", (ids,)):
            home = r["home"] if r["home"] is not None else (settings["hq_region_id"] if r["code"] == "HEAD" else None)
            people[r["id"]] = ce.CostPerson(r["id"], r["code"], home)
    travelers: dict[int, list[ce.CostPerson]] = defaultdict(list)
    if ids:
        for r in conn.execute("SELECT trip_id, person_id FROM trip_participant WHERE trip_id = ANY(%s) AND travels "
                              "ORDER BY person_id", (ids,)):
            if r["person_id"] in people:
                travelers[r["trip_id"]].append(people[r["person_id"]])
    trips = [ce.CostTrip(r["id"], r["event_type_id"], r["start_date"], r["end_date"],
                         r["dest_region"] if r["kind"] else settings["venue_region_id"], r["unit_id"],
                         travelers[r["id"]]) for r in rows]
    rates = [ce.Rate(r["rate_kind"], float(r["amount"]), r["mode"], positions.get(r["position_id"]),
                     r["valid_from"], r["valid_to"]) for r in conn.execute("SELECT * FROM cost_rate")]
    modes = ce.ModeTable(
        {(r["from_region_id"], r["to_region_id"]): r["mode"] for r in conn.execute("SELECT * FROM travel_mode")},
        [(r["from_region_id"], r["to_unit_id"], r["mode"]) for r in conn.execute("SELECT * FROM travel_mode_override")])
    tiers = [(t["min_days_ahead"], float(t["factor"])) for t in
             conn.execute("SELECT min_days_ahead, factor FROM booking_discount ORDER BY min_days_ahead")]
    return rows, trips, rates, modes, tiers, settings


def forecast_report(conn: Connection, year: int, allowed: set[int] | None, book_ahead_days: int | None = None,
                    today: date | None = None) -> dict[str, Any]:
    if conn.execute("SELECT 1 FROM plan_year WHERE year = %s", (year,)).fetchone() is None:
        raise CatalogError(f"The plan year {year} does not exist.", 404)
    today = today or date.today()
    rows, trips, rates, modes, tiers, settings = _load(conn, year, allowed)
    res = ce.forecast(trips, rates, modes, tiers, today)
    lines = res.lines
    total = sum(ln.total for ln in lines)
    events = {r["id"]: (r["name"], r["code"]) for r in conn.execute("SELECT id, name, code FROM event_type")}
    units = {u["id"]: u for u in conn.execute("SELECT id, kind, name, parent_id FROM org_unit")}
    trip_unit = {r["id"]: r["unit_id"] for r in rows}
    cost_of = defaultdict(float)
    for ln in lines:
        cost_of[ln.trip_id] += ln.total

    def place(trip_id: int) -> str:
        u = units.get(trip_unit.get(trip_id))
        if u is None:
            return "Nationwide events"
        region = units.get(u["parent_id"]) if u["kind"] != "region" else u
        return u["name"] if u["kind"] == "cluster" else f"{region['name'] if region else ''}: region and local offices"

    by_month = ce.totals_by(lines, lambda ln: ln.month)
    by_place = ce.totals_by(lines, lambda ln: place(ln.trip_id))
    by_event = ce.totals_by(lines, lambda ln: ln.event_id)
    by_position = ce.totals_by(lines, lambda ln: ln.position)
    by_mode = ce.totals_by(lines, lambda ln: ln.mode)

    budget = _budget_comparison(conn, year, by_event, events) if allowed is None else None
    air = sum(by_mode[m]["person_trips"] for m in ("air", "sea") if m in by_mode)
    out: dict[str, Any] = {
        "year": year, "today": str(today), "currency": CURRENCY, "currency_symbol": SYMBOL,
        "totals": {"cost": round(total, 2), "trips": len(trips), "person_trips": len(lines),
                   "avg_per_person_trip": round(total / len(lines), 2) if lines else 0.0,
                   "air_or_sea_person_trips": air},
        "by_month": [{"month": MONTHS[m - 1], "cost": round(by_month[m]["cost"], 2) if m in by_month else 0.0,
                      "trips": len(by_month[m]["trips"]) if m in by_month else 0} for m in range(1, 13)],
        "by_place": sorted(({"place": k, "cost": round(v["cost"], 2), "trips": len(v["trips"]),
                             "person_trips": v["person_trips"]} for k, v in by_place.items()),
                           key=lambda x: -x["cost"]),
        "by_event": sorted(({"event_id": k, "event": events.get(k, ("?", ""))[0], "cost": round(v["cost"], 2),
                             "trips": len(v["trips"]), "person_trips": v["person_trips"]}
                            for k, v in by_event.items()), key=lambda x: -x["cost"]),
        "by_position": sorted(({"position": k, "cost": round(v["cost"], 2), "person_trips": v["person_trips"]}
                               for k, v in by_position.items()), key=lambda x: -x["cost"]),
        "by_mode": {k: {"person_trips": v["person_trips"], "cost": round(v["cost"], 2)} for k, v in by_mode.items()},
        "budget": budget, "early_booking": _early_booking(trips, rates, modes, tiers, today, book_ahead_days, lines),
        "assumptions": {
            "missing_rates": sorted(res.missing_rates),
            "assumed_mode_person_trips": sum(1 for ln in lines if ln.assumed_mode),
            "modes_loaded": bool(modes.matrix), "settings": settings, "tiers": [{"min_days_ahead": a, "factor": f}
                                                                                for a, f in tiers],
        },
        "trip_costs": {k: round(v, 2) for k, v in cost_of.items()},
    }
    return out


def _early_booking(trips, rates, modes, tiers, today, book_ahead_days, lines) -> dict[str, Any]:
    """What early booking is worth: the fares as they stand, and if every fare were booked N days ahead."""
    fares = sum(ln.fare for ln in lines)
    full = sum(ln.fare_full for ln in lines)
    if not tiers:
        return {"has_tiers": False, "fares": round(fares, 2), "fares_without_discount": round(full, 2),
                "target_days": None, "saving": 0.0}
    target = book_ahead_days if book_ahead_days is not None else max(t[0] for t in tiers)
    ahead = ce.forecast(trips, rates, modes, tiers, today, book_ahead_days=target)
    ahead_fares = sum(ln.fare for ln in ahead.lines)
    return {"has_tiers": True, "fares": round(fares, 2), "fares_without_discount": round(full, 2),
            "target_days": target, "fares_if_booked_ahead": round(ahead_fares, 2),
            "saving": round(fares - ahead_fares, 2),
            "factor_at_target": ce.booking_factor(tiers, target)}


def _budget_comparison(conn: Connection, year: int, by_event: dict, events: dict) -> dict[str, Any] | None:
    lines = conn.execute(
        "SELECT event_type_id, SUM(annual_cost) AS cost, SUM(COALESCE(persons, 0) * COALESCE(frequency, 0)) AS pt "
        "FROM budget_line WHERE plan_year = %s GROUP BY event_type_id", (year,)).fetchall()
    if not lines:
        return None
    budget = {r["event_type_id"]: (float(r["cost"]), float(r["pt"])) for r in lines}
    rows = []
    for eid in sorted(set(budget) | set(by_event), key=lambda e: (e is None, -(budget.get(e, (0, 0))[0]))):
        b_cost, b_pt = budget.get(eid, (0.0, 0.0))
        f = by_event.get(eid, {"cost": 0.0, "person_trips": 0})
        rows.append({
            "event_id": eid, "event": events[eid][0] if eid in events else "Not matched to an event",
            "budget_cost": round(b_cost, 2), "budget_person_trips": round(b_pt, 1),
            "forecast_cost": round(f["cost"], 2), "forecast_person_trips": f["person_trips"],
            "difference": round(f["cost"] - b_cost, 2),
        })
    total_b = sum(r["budget_cost"] for r in rows)
    total_f = sum(r["forecast_cost"] for r in rows)
    return {"rows": rows, "budget_total": round(total_b, 2), "forecast_total": round(total_f, 2),
            "difference": round(total_f - total_b, 2),
            "unmatched": round(budget.get(None, (0.0, 0.0))[0], 2)}


# ------------------------------------------------------------------------------------------ budget lines


def budget_lines(conn: Connection, year: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT b.id, b.event_name, b.position_name, b.remarks, b.persons, b.frequency, b.unit_price, b.annual_cost, "
        "b.cost_item, b.event_type_id, e.name AS event FROM budget_line b "
        "LEFT JOIN event_type e ON e.id = b.event_type_id "
        "WHERE b.plan_year = %s ORDER BY b.source_row, b.id", (year,)).fetchall()
    for r in rows:
        for k in ("persons", "frequency", "unit_price", "annual_cost"):
            r[k] = float(r[k]) if r[k] is not None else None
    return rows


def import_budget(conn: Connection, year: int, path: Path, commit: bool, actor: int | None) -> dict[str, Any]:
    """Replace the budget lines of a plan year with those of the workbook. A preview rolls back."""
    if conn.execute("SELECT 1 FROM plan_year WHERE year = %s", (year,)).fetchone() is None:
        raise CatalogError(f"The plan year {year} does not exist.", 404)
    rows, problems = parse_budget(path)
    if not rows:
        raise CatalogError(" ".join(problems), 422)
    codes = {r["code"]: r["id"] for r in conn.execute("SELECT id, code FROM event_type")}
    conn.execute("DELETE FROM budget_line WHERE plan_year = %s", (year,))
    for r in rows:
        conn.execute(
            "INSERT INTO budget_line(plan_year, cost_center, cost_item, event_name, position_name, remarks, persons, "
            "frequency, unit_price, annual_cost, event_type_id, justification, source_row) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (year, r.cost_center, r.cost_item, r.event, r.position, r.remarks, r.persons, r.frequency, r.unit_price,
             r.annual_cost, codes.get(r.event_code or ""), r.justification, r.row))
    unmatched = [r for r in rows if r.event_code is None or r.event_code not in codes]
    if commit:
        audit(conn, actor, "budget.import", "plan_year", year, {"lines": len(rows)})
    return {"applied": commit, "lines": len(rows), "total": round(sum(r.annual_cost for r in rows), 2),
            "unmatched_lines": len(unmatched), "unmatched_total": round(sum(r.annual_cost for r in unmatched), 2),
            "problems": problems}


def map_budget_line(conn: Connection, line_id: int, body: MappingIn, actor: int | None) -> None:
    if body.event_type_id is not None and not conn.execute("SELECT 1 FROM event_type WHERE id = %s",
                                                           (body.event_type_id,)).fetchone():
        raise CatalogError("The event type does not exist.")
    if not conn.execute("UPDATE budget_line SET event_type_id = %s WHERE id = %s RETURNING id",
                        (body.event_type_id, line_id)).fetchone():
        raise CatalogError("The budget line does not exist.", 404)
    audit(conn, actor, "budget.map", "budget_line", line_id, {"event_type_id": body.event_type_id})
