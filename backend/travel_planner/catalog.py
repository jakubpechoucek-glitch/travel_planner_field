"""Event catalog and travel rules: validation, plain-English descriptions, and database access."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any, Literal

from psycopg import Connection
from pydantic import BaseModel, Field

RULE_TYPES = (
    "cadence", "annual_quota", "participation_cap", "period_cap", "preferred_window", "rotation", "concurrency_cap",
)
SCOPES = ("person", "position", "local_office", "cluster", "region", "nationwide")
PERIODS = ("week", "month", "quarter", "half_year", "year")
Severity = Literal["block", "warn", "info"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
PERIOD_WORD = {"week": "week", "month": "month", "quarter": "quarter", "half_year": "half-year", "year": "year"}
SCOPE_WORD = {"local_office": "local office", "cluster": "cluster", "region": "region"}


# ------------------------------------------------------------------------------------------ input models


class RuleIn(BaseModel):
    event_type_id: int | None = None
    rule_type: Literal[RULE_TYPES]  # type: ignore[valid-type]
    scope_kind: Literal[SCOPES]  # type: ignore[valid-type]
    position_id: int | None = None
    period: Literal[PERIODS] | None = None  # type: ignore[valid-type]
    interval_n: int | None = Field(default=None, ge=1, le=60)
    min_count: int | None = Field(default=None, ge=0, le=1000)
    max_count: int | None = Field(default=None, ge=0, le=1000)
    params: dict[str, Any] = Field(default_factory=dict)
    severity: Severity = "warn"
    description: str | None = Field(default=None, max_length=500)


class ParticipationIn(BaseModel):
    position_id: int
    participation: Literal["organizer", "participant"] = "participant"
    yearly_limit: int | None = Field(default=None, ge=0, le=366)
    travels: bool = True


class MergeIn(BaseModel):
    merges_into_id: int
    condition_text: str | None = Field(default=None, max_length=300)
    severity: Severity = "info"


class EventTypeIn(BaseModel):
    code: str | None = Field(default=None, pattern=r"^[A-Z0-9][A-Z0-9-]{1,29}$")
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    organizer_position_id: int | None = None
    visited_kind: Literal["local_office", "cluster", "region", "nationwide", "external"] = "cluster"
    joint_visit: Literal["no", "partial", "yes"] = "no"
    is_company_event: bool = False
    typical_days: int | None = Field(default=None, ge=1, le=30)
    typical_mode: Literal["land", "air", "sea", "air_land", "air_sea", "mixed"] | None = None
    scheduling_notes: str | None = Field(default=None, max_length=1000)
    active: bool = True
    participation: list[ParticipationIn] = Field(default_factory=list)
    merges: list[MergeIn] = Field(default_factory=list)


class BlackoutIn(BaseModel):
    plan_year: int = Field(ge=2000, le=2100)
    name: str = Field(min_length=1, max_length=120)
    start_date: date
    end_date: date
    reason: str | None = Field(default=None, max_length=500)
    severity: Severity = "warn"
    event_type_ids: list[int] = Field(default_factory=list)
    caused_by_event_type_id: int | None = None


class CatalogError(Exception):
    """A request that is well-formed but not acceptable; the message is shown to the user."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------------------------------ rule logic


def validate_rule(r: RuleIn, *, positions: set[int], events: set[int]) -> list[str]:
    """Return plain-English problems; an empty list means the rule is acceptable."""
    errors: list[str] = []
    t = r.rule_type
    if r.event_type_id is not None and r.event_type_id not in events:
        errors.append("The event type does not exist.")
    if r.position_id is not None and r.position_id not in positions:
        errors.append("The position does not exist.")
    if r.min_count is not None and r.max_count is not None and r.max_count < r.min_count:
        errors.append("The maximum cannot be smaller than the minimum.")
    event_required = t in ("cadence", "annual_quota", "preferred_window", "rotation")
    if event_required and r.event_type_id is None:
        errors.append("This kind of rule must belong to an event type.")
    if t in ("cadence", "rotation", "participation_cap", "period_cap", "concurrency_cap") and r.period is None:
        errors.append("Choose a period (week, month, quarter, half-year or year).")
    if t == "cadence":
        if r.interval_n is None:
            errors.append("Enter how many periods apart the events should be (for example 2 months).")
        if r.scope_kind in ("person", "position"):
            errors.append("A cadence applies to a cluster, local office, region or nationwide.")
    if t == "annual_quota":
        if r.min_count is None and r.max_count is None:
            errors.append("Enter a minimum, a maximum, or both.")
        if r.scope_kind in ("person", "position"):
            errors.append("A yearly quota applies to a cluster, local office, region or nationwide.")
    if t == "participation_cap":
        if r.position_id is None:
            errors.append("Choose the position the limit applies to.")
        if r.max_count is None:
            errors.append("Enter the maximum.")
    if t == "period_cap":
        if r.scope_kind not in ("person", "position"):
            errors.append("A trip limit applies to each person or to a position.")
        if r.scope_kind == "position" and r.position_id is None:
            errors.append("Choose the position the limit applies to.")
        if r.min_count is None and r.max_count is None:
            errors.append("Enter a minimum, a maximum, or both.")
    if t == "preferred_window":
        months = r.params.get("months")
        if not (isinstance(months, list) and months and all(isinstance(m, int) and 1 <= m <= 12 for m in months)):
            errors.append("Choose at least one month.")
    if t == "rotation":
        if r.params.get("unit") not in ("cluster", "local_office"):
            errors.append("Choose what is rotated: clusters or local offices.")
        if r.min_count is None and r.max_count is None:
            errors.append("Enter how many units are covered per period.")
    if t == "concurrency_cap" and (r.max_count is None or r.max_count < 1):
        errors.append("Enter the maximum (at least 1).")
    return errors


def _count_phrase(mn: int | None, mx: int | None) -> str:
    if mn is not None and mx is not None:
        return str(mn) if mn == mx else f"{mn} to {mx}"
    return f"at most {mx}" if mx is not None else f"at least {mn}"


def describe_rule(rule: dict[str, Any], position_names: dict[int, str]) -> str:
    """One readable sentence for a rule (also shown in the app and used in help)."""
    t, mn, mx = rule["rule_type"], rule.get("min_count"), rule.get("max_count")
    period = PERIOD_WORD.get(rule.get("period") or "", "")
    scope = SCOPE_WORD.get(rule["scope_kind"], "")
    pos = position_names.get(rule.get("position_id") or 0, "")
    per_scope = f" for each {scope}" if scope else " nationwide"
    if t == "cadence":
        n = rule.get("interval_n") or 1
        return (f"Every {period}" if n == 1 else f"Every {n} {period}s") + per_scope + "."
    if t == "annual_quota":
        return f"{_count_phrase(mn, mx).capitalize()} per year" + per_scope + "."
    if t == "participation_cap":
        return f"{pos}: {_count_phrase(None, mx)} per {period}."
    if t == "period_cap":
        who = pos if rule["scope_kind"] == "position" else "Each person"
        unit = "trip" if (mx if mx is not None else mn) == 1 else "trips"
        return f"{who}: {_count_phrase(mn, mx)} {unit} per {period}."
    if t == "preferred_window":
        months = [MONTHS[m - 1] for m in rule["params"].get("months", []) if 1 <= m <= 12]
        return "Prefer " + ", ".join(months) + "."
    if t == "rotation":
        unit = rule["params"].get("unit", "cluster").replace("_", " ")
        return (f"Cover {_count_phrase(mn, mx)} {unit}s per {period}{per_scope}, "
                "without repeating until all are covered.")
    if t == "concurrency_cap":
        return f"At most {mx} at the same time{per_scope}, per {period}."
    return ""


# ------------------------------------------------------------------------------------------ database


def audit(conn: Connection, actor_person_id: int | None, action: str, entity: str, entity_id: Any, details: dict):
    conn.execute(
        "INSERT INTO audit_log(actor_person_id, action, entity, entity_id, details) VALUES (%s, %s, %s, %s, %s)",
        (actor_person_id, action, entity, str(entity_id), json.dumps(details)),
    )


def _ids(conn: Connection, table: str) -> set[int]:
    return {r["id"] for r in conn.execute(f"SELECT id FROM {table}")}  # noqa: S608  (fixed table names)


def load_catalog(conn: Connection, plan_year: int | None = None) -> dict[str, Any]:
    positions = conn.execute(
        "SELECT id, code, name, level, function_area FROM position WHERE active ORDER BY level, name"
    ).fetchall()
    pos_name = {p["id"]: p["name"] for p in positions}
    events = conn.execute("SELECT * FROM event_type ORDER BY active DESC, name").fetchall()
    parts = conn.execute(
        "SELECT event_type_id, position_id, participation, yearly_limit, travels FROM event_type_position"
    ).fetchall()
    rules = conn.execute(
        "SELECT id, rule_key, version, event_type_id, rule_type, scope_kind, position_id, period, interval_n, "
        "min_count, max_count, params, severity, description, valid_from FROM rule WHERE active ORDER BY rule_key"
    ).fetchall()
    merges = conn.execute(
        "SELECT m.id, m.event_type_id, m.merges_into_id, e.name AS merges_into_name, m.condition_text, m.severity "
        "FROM merge_rule m JOIN event_type e ON e.id = m.merges_into_id WHERE m.active"
    ).fetchall()
    blackouts = conn.execute(
        "SELECT b.id, b.plan_year, b.name, b.start_date, b.end_date, b.reason, b.severity, b.caused_by_event_type_id, "
        "COALESCE(array_agg(be.event_type_id) FILTER (WHERE be.event_type_id IS NOT NULL), '{}') AS event_type_ids "
        "FROM blackout_period b LEFT JOIN blackout_event_type be ON be.blackout_id = b.id "
        "WHERE (%s::int IS NULL OR b.plan_year = %s) GROUP BY b.id ORDER BY b.start_date",
        (plan_year, plan_year),
    ).fetchall()
    for r in rules:
        r["summary"] = describe_rule(r, pos_name)
        r["valid_from"] = str(r["valid_from"])
    out_events = []
    for e in events:
        e = dict(e)
        e["participation"] = [
            {k: p[k] for k in ("position_id", "participation", "yearly_limit", "travels")}
            for p in parts if p["event_type_id"] == e["id"]
        ]
        e["rules"] = [r for r in rules if r["event_type_id"] == e["id"]]
        e["merges"] = [m for m in merges if m["event_type_id"] == e["id"]]
        out_events.append(e)
    for b in blackouts:
        b["start_date"], b["end_date"] = str(b["start_date"]), str(b["end_date"])
    return {
        "positions": positions,
        "event_types": out_events,
        "general_rules": [r for r in rules if r["event_type_id"] is None],
        "blackouts": blackouts,
    }


def _check_event(conn: Connection, data: EventTypeIn, event_id: int | None) -> None:
    positions = _ids(conn, "position")
    if data.organizer_position_id is not None and data.organizer_position_id not in positions:
        raise CatalogError("The organizer position does not exist.")
    seen: set[int] = set()
    for p in data.participation:
        if p.position_id not in positions:
            raise CatalogError("A position in the participation list does not exist.")
        if p.position_id in seen:
            raise CatalogError("A position appears twice in the participation list.")
        seen.add(p.position_id)
    events = _ids(conn, "event_type")
    for m in data.merges:
        if m.merges_into_id not in events or m.merges_into_id == event_id:
            raise CatalogError("A combined event is invalid.")
    if len({m.merges_into_id for m in data.merges}) != len(data.merges):
        raise CatalogError("The same combined event is listed twice.")


def save_event_type(conn: Connection, event_id: int | None, data: EventTypeIn, actor: int | None) -> int:
    _check_event(conn, data, event_id)
    fields = (data.name, data.description, data.organizer_position_id, data.visited_kind, data.joint_visit,
              data.is_company_event, data.typical_days, data.typical_mode, data.scheduling_notes, data.active)
    if event_id is None:
        if not data.code:
            raise CatalogError("Enter a short code, for example AM-FSV-VISIT.")
        if conn.execute("SELECT 1 FROM event_type WHERE code = %s", (data.code,)).fetchone():
            raise CatalogError(f"The code {data.code} is already used.", 409)
        event_id = conn.execute(
            "INSERT INTO event_type(name, description, organizer_position_id, visited_kind, joint_visit, "
            "is_company_event, typical_days, typical_mode, scheduling_notes, active, code) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id", (*fields, data.code)).fetchone()["id"]
        action = "catalog.event_type.create"
    else:
        found = conn.execute(
            "UPDATE event_type SET name=%s, description=%s, organizer_position_id=%s, visited_kind=%s, "
            "joint_visit=%s, is_company_event=%s, typical_days=%s, typical_mode=%s, scheduling_notes=%s, active=%s "
            "WHERE id=%s RETURNING id", (*fields, event_id)).fetchone()
        if not found:
            raise CatalogError("The event type does not exist.", 404)
        action = "catalog.event_type.update"
    conn.execute("DELETE FROM event_type_position WHERE event_type_id = %s", (event_id,))
    for p in data.participation:
        conn.execute(
            "INSERT INTO event_type_position(event_type_id, position_id, participation, yearly_limit, travels) "
            "VALUES (%s,%s,%s,%s,%s)", (event_id, p.position_id, p.participation, p.yearly_limit, p.travels))
    conn.execute("DELETE FROM merge_rule WHERE event_type_id = %s", (event_id,))
    for m in data.merges:
        conn.execute(
            "INSERT INTO merge_rule(event_type_id, merges_into_id, condition_text, severity) VALUES (%s,%s,%s,%s)",
            (event_id, m.merges_into_id, m.condition_text, m.severity))
    audit(conn, actor, action, "event_type", event_id,
          {"positions": len(data.participation), "merges": len(data.merges)})
    return event_id


def _validated(conn: Connection, rule: RuleIn) -> RuleIn:
    errors = validate_rule(rule, positions=_ids(conn, "position"), events=_ids(conn, "event_type"))
    if errors:
        raise CatalogError(" ".join(errors))
    if rule.rule_type == "annual_quota":
        rule.period = "year"
    return rule


_RULE_COLS = ("event_type_id", "rule_type", "scope_kind", "position_id", "period", "interval_n", "min_count",
              "max_count", "params", "severity", "description")


def _rule_values(r: RuleIn) -> tuple:
    return (r.event_type_id, r.rule_type, r.scope_kind, r.position_id, r.period, r.interval_n, r.min_count,
            r.max_count, json.dumps(r.params), r.severity, r.description)


def create_rule(conn: Connection, rule: RuleIn, actor: int | None) -> str:
    rule = _validated(conn, rule)
    key = "R-" + conn.execute("SELECT substr(md5(random()::text), 1, 8) AS k").fetchone()["k"].upper()
    conn.execute(
        f"INSERT INTO rule(rule_key, version, valid_from, {', '.join(_RULE_COLS)}) "  # noqa: S608
        f"VALUES (%s, 1, CURRENT_DATE, {', '.join(['%s'] * len(_RULE_COLS))})", (key, *_rule_values(rule)))
    audit(conn, actor, "catalog.rule.create", "rule", key, {"type": rule.rule_type})
    return key


def new_rule_version(conn: Connection, key: str, rule: RuleIn, actor: int | None) -> int:
    """Editing a rule never rewrites history: it adds a new version and retires the previous one."""
    old = conn.execute(
        "SELECT id, version, valid_from FROM rule WHERE rule_key = %s AND active ORDER BY version DESC LIMIT 1", (key,)
    ).fetchone()
    if not old:
        raise CatalogError("The rule does not exist.", 404)
    rule = _validated(conn, rule)
    today = date.today()
    conn.execute("UPDATE rule SET active = false, valid_to = %s WHERE id = %s",
                 (max(old["valid_from"], today - timedelta(days=1)), old["id"]))
    version = old["version"] + 1
    conn.execute(
        f"INSERT INTO rule(rule_key, version, valid_from, {', '.join(_RULE_COLS)}) "  # noqa: S608
        f"VALUES (%s, %s, %s, {', '.join(['%s'] * len(_RULE_COLS))})", (key, version, today, *_rule_values(rule)))
    audit(conn, actor, "catalog.rule.update", "rule", key, {"version": version})
    return version


def deactivate_rule(conn: Connection, key: str, actor: int | None) -> None:
    done = conn.execute(
        "UPDATE rule SET active = false, valid_to = GREATEST(valid_from, CURRENT_DATE - 1) "
        "WHERE rule_key = %s AND active RETURNING id", (key,)).fetchall()
    if not done:
        raise CatalogError("The rule does not exist.", 404)
    audit(conn, actor, "catalog.rule.deactivate", "rule", key, {})


def _check_blackout(conn: Connection, b: BlackoutIn) -> None:
    if b.end_date < b.start_date:
        raise CatalogError("The end date cannot be before the start date.")
    if not (date(b.plan_year, 1, 1) <= b.start_date and b.end_date <= date(b.plan_year, 12, 31)):
        raise CatalogError(f"The dates must be inside {b.plan_year}.")
    known = _ids(conn, "event_type")
    if set(b.event_type_ids) - known:
        raise CatalogError("An affected event type does not exist.")
    if b.caused_by_event_type_id is not None and b.caused_by_event_type_id not in known:
        raise CatalogError("The event that causes the blackout does not exist.")
    status = conn.execute("SELECT status FROM plan_year WHERE year = %s", (b.plan_year,)).fetchone()
    if status and status["status"] == "closed":
        raise CatalogError(f"The plan year {b.plan_year} is closed.", 409)


def save_blackout(conn: Connection, blackout_id: int | None, b: BlackoutIn, actor: int | None) -> int:
    _check_blackout(conn, b)
    conn.execute("INSERT INTO plan_year(year) VALUES (%s) ON CONFLICT DO NOTHING", (b.plan_year,))
    vals = (b.plan_year, b.name, b.start_date, b.end_date, b.reason, b.severity, b.caused_by_event_type_id)
    if blackout_id is None:
        blackout_id = conn.execute(
            "INSERT INTO blackout_period(plan_year, name, start_date, end_date, reason, severity, "
            "caused_by_event_type_id) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id", vals).fetchone()["id"]
        action = "catalog.blackout.create"
    else:
        if not conn.execute(
            "UPDATE blackout_period SET plan_year=%s, name=%s, start_date=%s, end_date=%s, reason=%s, severity=%s, "
            "caused_by_event_type_id=%s WHERE id=%s RETURNING id", (*vals, blackout_id)).fetchone():
            raise CatalogError("The blackout period does not exist.", 404)
        action = "catalog.blackout.update"
    conn.execute("DELETE FROM blackout_event_type WHERE blackout_id = %s", (blackout_id,))
    for eid in dict.fromkeys(b.event_type_ids):
        conn.execute("INSERT INTO blackout_event_type(blackout_id, event_type_id) VALUES (%s,%s)", (blackout_id, eid))
    audit(conn, actor, action, "blackout_period", blackout_id, {"plan_year": b.plan_year})
    return blackout_id


def delete_blackout(conn: Connection, blackout_id: int, actor: int | None) -> None:
    if not conn.execute("DELETE FROM blackout_period WHERE id = %s RETURNING id", (blackout_id,)).fetchone():
        raise CatalogError("The blackout period does not exist.", 404)
    audit(conn, actor, "catalog.blackout.delete", "blackout_period", blackout_id, {})

