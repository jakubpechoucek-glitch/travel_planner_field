"""User administration: people, their assignment, roles with scope, and the link to a sign-in.

E-mail addresses are never stored. An administrator types an address, the server turns it into a keyed hash
(`identity.key_hash`), stores only the hash and forgets the address. Nothing here logs or returns an address.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Literal

from psycopg import Connection
from pydantic import BaseModel, Field

from .catalog import CatalogError, audit
from .identity import key_hash
from .orgimport import norm

# role -> the kind of org unit it is scoped to (None = the role has no scope)
ROLE_SCOPE: dict[str, str | None] = {
    "administrator": None, "national_planner": None, "regional_planner": "region", "area_planner": "cluster",
    "function_planner": None, "coordinator": None, "viewer": None,
}
Role = Literal["administrator", "national_planner", "regional_planner", "area_planner", "function_planner",
               "coordinator", "viewer"]
EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")
MAX_BULK_LINES = 2000


# ------------------------------------------------------------------------------------------ input models


class AssignmentIn(BaseModel):
    position_id: int
    manager_id: int | None = None
    region_id: int | None = None
    cluster_id: int | None = None
    local_office_id: int | None = None
    effective_date: date | None = None


class PersonIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    employee_no: str | None = Field(default=None, max_length=30)
    assignment: AssignmentIn


class PersonUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    employee_no: str | None = Field(default=None, max_length=30)
    active: bool | None = None
    assignment: AssignmentIn | None = None


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class RoleIn(BaseModel):
    role: Role
    scope_org_unit_id: int | None = None


class BulkIn(BaseModel):
    text: str = Field(max_length=300_000)


# ------------------------------------------------------------------------------------------ lookups


def meta(conn: Connection, bootstrap: bool = False) -> dict[str, Any]:
    units = conn.execute("SELECT id, kind, name, parent_id FROM org_unit WHERE active ORDER BY name").fetchall()
    return {
        "positions": conn.execute(
            "SELECT id, code, name, level FROM position WHERE active ORDER BY level, name").fetchall(),
        "regions": [u for u in units if u["kind"] == "region"],
        "clusters": [u for u in units if u["kind"] == "cluster"],
        "local_offices": [u for u in units if u["kind"] == "local_office"],
        "roles": [{"role": r, "scope_kind": k} for r, k in ROLE_SCOPE.items()],
        "administrators": _admin_count(conn),
        "bootstrap_admin": bootstrap,  # an administrator set in the configuration who needs no person record
    }


def _admin_count(conn: Connection, excluding: int | None = None) -> int:
    """Active administrators who can actually sign in."""
    return conn.execute(
        "SELECT count(*) AS n FROM person p WHERE p.active AND p.sso_key_hash IS NOT NULL "
        "AND p.id IS DISTINCT FROM %s AND EXISTS (SELECT 1 FROM user_role r WHERE r.person_id = p.id "
        "AND r.role = 'administrator')", (excluding,)).fetchone()["n"]


def _guard_last_admin(conn: Connection, person_id: int, bootstrap: bool, action: str) -> None:
    """Never remove the last administrator who can sign in (unless a bootstrap administrator is configured)."""
    is_admin = conn.execute(
        "SELECT 1 FROM person p JOIN user_role r ON r.person_id = p.id AND r.role = 'administrator' "
        "WHERE p.id = %s AND p.active AND p.sso_key_hash IS NOT NULL", (person_id,)).fetchone()
    if is_admin and not bootstrap and _admin_count(conn, excluding=person_id) == 0:
        raise CatalogError(f"This would leave the application without an administrator who can sign in. "
                           f"Make someone else an administrator before you {action}.", 409)


_LIST_SQL = """
SELECT p.id, p.full_name, p.employee_no, p.active, (p.sso_key_hash IS NOT NULL) AS has_login,
       pos.id AS position_id, pos.name AS position, pos.code AS position_code,
       a.manager_id, m.full_name AS manager, a.region_id, r.name AS region, a.cluster_id, c.name AS cluster,
       a.local_office_id, o.name AS office,
       COALESCE((SELECT json_agg(json_build_object('id', ur.id, 'role', ur.role, 'scope_id', ur.scope_org_unit_id,
                                                   'scope', su.name) ORDER BY ur.role, su.name)
                 FROM user_role ur LEFT JOIN org_unit su ON su.id = ur.scope_org_unit_id
                 WHERE ur.person_id = p.id), '[]'::json) AS roles
FROM person p
LEFT JOIN person_assignment a ON a.person_id = p.id AND a.valid_to IS NULL
LEFT JOIN position pos ON pos.id = a.position_id
LEFT JOIN person m ON m.id = a.manager_id
LEFT JOIN org_unit r ON r.id = a.region_id
LEFT JOIN org_unit c ON c.id = a.cluster_id
LEFT JOIN org_unit o ON o.id = a.local_office_id
"""


def list_users(conn: Connection, q: str | None, role: str | None, login: str | None, active: bool | None,
               limit: int, offset: int) -> dict[str, Any]:
    where, args = ["TRUE"], []
    if q:
        where.append("(p.full_name ILIKE %s OR p.employee_no ILIKE %s)")
        args += [f"%{q}%", f"%{q}%"]
    if role == "none":
        where.append("NOT EXISTS (SELECT 1 FROM user_role x WHERE x.person_id = p.id)")
    elif role:
        where.append("EXISTS (SELECT 1 FROM user_role x WHERE x.person_id = p.id AND x.role = %s)")
        args.append(role)
    if login == "linked":
        where.append("p.sso_key_hash IS NOT NULL")
    elif login == "unlinked":
        where.append("p.sso_key_hash IS NULL")
    if active is not None:
        where.append("p.active = %s")
        args.append(active)
    cond = " AND ".join(where)
    total = conn.execute(f"SELECT count(*) AS n FROM person p WHERE {cond}", args).fetchone()["n"]  # noqa: S608
    rows = conn.execute(
        f"{_LIST_SQL} WHERE {cond} ORDER BY p.active DESC, p.full_name, p.id LIMIT %s OFFSET %s",  # noqa: S608
        (*args, limit, offset)).fetchall()
    return {"total": total, "users": rows}


def get_user(conn: Connection, person_id: int) -> dict[str, Any]:
    row = conn.execute(f"{_LIST_SQL} WHERE p.id = %s", (person_id,)).fetchone()  # noqa: S608
    if row is None:
        raise CatalogError("The person does not exist.", 404)
    return row


# ------------------------------------------------------------------------------------------ people


def _check_assignment(conn: Connection, person_id: int | None, a: AssignmentIn) -> None:
    if not conn.execute("SELECT 1 FROM position WHERE id = %s AND active", (a.position_id,)).fetchone():
        raise CatalogError("The position does not exist.")
    if a.manager_id is not None:
        if a.manager_id == person_id:
            raise CatalogError("A person cannot be their own manager.")
        if not conn.execute("SELECT 1 FROM person WHERE id = %s AND active", (a.manager_id,)).fetchone():
            raise CatalogError("The manager does not exist or is not active.")
    for unit_id, kind in ((a.region_id, "region"), (a.cluster_id, "cluster"), (a.local_office_id, "local_office")):
        if unit_id is not None and not conn.execute(
                "SELECT 1 FROM org_unit WHERE id = %s AND kind = %s AND active", (unit_id, kind)).fetchone():
            raise CatalogError(f"The {kind.replace('_', ' ')} does not exist.")


def _set_assignment(conn: Connection, person_id: int, a: AssignmentIn) -> bool:
    """Effective-dated, like the organization import: the old assignment is closed, the new one opened."""
    _check_assignment(conn, person_id, a)
    effective = a.effective_date or date.today()
    want = (a.position_id, a.manager_id, a.region_id, a.cluster_id, a.local_office_id)
    cur = conn.execute(
        "SELECT id, position_id, manager_id, region_id, cluster_id, local_office_id, valid_from "
        "FROM person_assignment WHERE person_id = %s AND valid_to IS NULL ORDER BY valid_from DESC LIMIT 1",
        (person_id,)).fetchone()
    if cur and (cur["position_id"], cur["manager_id"], cur["region_id"], cur["cluster_id"],
                cur["local_office_id"]) == want:
        return False
    if cur and cur["valid_from"] == effective:
        conn.execute("UPDATE person_assignment SET position_id=%s, manager_id=%s, region_id=%s, cluster_id=%s, "
                     "local_office_id=%s WHERE id=%s", (*want, cur["id"]))
    elif cur and cur["valid_from"] > effective:
        raise CatalogError(f"This person already has an assignment starting {cur['valid_from']}; "
                           "choose a later date.")
    else:
        if cur:
            conn.execute("UPDATE person_assignment SET valid_to = %s WHERE id = %s",
                         (effective - timedelta(days=1), cur["id"]))
        conn.execute("INSERT INTO person_assignment(person_id, position_id, manager_id, region_id, cluster_id, "
                     "local_office_id, valid_from) VALUES (%s,%s,%s,%s,%s,%s,%s)", (person_id, *want, effective))
    return True


def _employee_no(conn: Connection, value: str | None, person_id: int | None) -> str | None:
    value = (value or "").strip() or None
    if value and conn.execute("SELECT 1 FROM person WHERE employee_no = %s AND id IS DISTINCT FROM %s",
                              (value, person_id)).fetchone():
        raise CatalogError(f"The employee number {value} is already used.", 409)
    return value


def create_user(conn: Connection, body: PersonIn, actor: int | None) -> dict[str, Any]:
    name = body.full_name.strip()
    emp = _employee_no(conn, body.employee_no, None)
    pid = conn.execute(
        "INSERT INTO person(full_name, name_key, employee_no, start_date) VALUES (%s,%s,%s,%s) RETURNING id",
        (name, norm(name), emp, body.assignment.effective_date or date.today())).fetchone()["id"]
    _set_assignment(conn, pid, body.assignment)
    audit(conn, actor, "user.create", "person", pid, {})
    return get_user(conn, pid)


def update_user(conn: Connection, person_id: int, body: PersonUpdate, actor: int | None, bootstrap: bool) -> dict:
    cur = conn.execute("SELECT id, full_name, employee_no, active FROM person WHERE id = %s FOR UPDATE",
                       (person_id,)).fetchone()
    if cur is None:
        raise CatalogError("The person does not exist.", 404)
    if body.active is False and cur["active"]:
        if person_id == actor:
            raise CatalogError("You cannot deactivate yourself.", 409)
        _guard_last_admin(conn, person_id, bootstrap, "deactivate this person")
    if body.full_name is not None:
        name = body.full_name.strip()
        conn.execute("UPDATE person SET full_name=%s, name_key=%s WHERE id=%s", (name, norm(name), person_id))
    if "employee_no" in body.model_fields_set:
        conn.execute("UPDATE person SET employee_no=%s WHERE id=%s",
                     (_employee_no(conn, body.employee_no, person_id), person_id))
    if body.active is not None and body.active != cur["active"]:
        conn.execute("UPDATE person SET active=%s, end_date=CASE WHEN %s THEN NULL ELSE CURRENT_DATE END "
                     "WHERE id=%s", (body.active, body.active, person_id))
        audit(conn, actor, "user.activate" if body.active else "user.deactivate", "person", person_id, {})
    if body.assignment is not None and _set_assignment(conn, person_id, body.assignment):
        audit(conn, actor, "user.assignment", "person", person_id,
              {"position_id": body.assignment.position_id, "effective": str(body.assignment.effective_date)})
    conn.execute("UPDATE person SET updated_at = now() WHERE id = %s", (person_id,))
    audit(conn, actor, "user.update", "person", person_id, {})
    return get_user(conn, person_id)


# ------------------------------------------------------------------------------------------ sign-in link


def _hash_email(email: str, secret: str) -> str:
    email = email.strip()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise CatalogError("Enter a valid e-mail address, for example first.last@company.example.")
    return key_hash(email, secret)


def link_login(conn: Connection, person_id: int, body: LoginIn, secret: str, actor: int | None) -> dict:
    kh = _hash_email(body.email, secret)  # the address is not used again after this line
    cur = conn.execute("SELECT id, sso_key_hash FROM person WHERE id = %s AND active FOR UPDATE",
                       (person_id,)).fetchone()
    if cur is None:
        raise CatalogError("The person does not exist or is not active.", 404)
    other = conn.execute("SELECT full_name FROM person WHERE sso_key_hash = %s AND id <> %s",
                         (kh, person_id)).fetchone()
    if other:
        raise CatalogError(f"This sign-in is already linked to {other['full_name']}.", 409)
    if cur["sso_key_hash"] == kh:
        return get_user(conn, person_id)
    conn.execute("UPDATE person SET sso_key_hash = %s, updated_at = now() WHERE id = %s", (kh, person_id))
    audit(conn, actor, "user.login.replace" if cur["sso_key_hash"] else "user.login.link", "person", person_id, {})
    return get_user(conn, person_id)


def unlink_login(conn: Connection, person_id: int, actor: int | None, bootstrap: bool) -> dict:
    _guard_last_admin(conn, person_id, bootstrap, "unlink this sign-in")
    if not conn.execute("UPDATE person SET sso_key_hash = NULL, updated_at = now() WHERE id = %s RETURNING id",
                        (person_id,)).fetchone():
        raise CatalogError("The person does not exist.", 404)
    audit(conn, actor, "user.login.unlink", "person", person_id, {})
    return get_user(conn, person_id)


def parse_bulk(text: str) -> list[tuple[int, str, str]]:
    """Lines of 'e-mail, employee number or name' (either order; comma, semicolon or tab). Header lines are skipped."""
    out: list[tuple[int, str, str]] = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        parts = [p.strip() for p in re.split(r"[;,\t]", line) if p.strip()]
        emails = [p for p in parts if "@" in p]
        if not emails:
            if n == 1:
                continue  # a header such as "email, employee number"
            out.append((n, "", ""))  # reported as a problem
            continue
        rest = " ".join(p for p in parts if "@" not in p)
        out.append((n, emails[0], rest))
    return out


def bulk_login(conn: Connection, body: BulkIn, secret: str, commit: bool, actor: int | None) -> dict[str, Any]:
    """Link many sign-ins at once. A preview (commit=False) changes nothing. Addresses are never echoed back."""
    rows = parse_bulk(body.text)
    if not rows:
        raise CatalogError("Paste one person per line: the e-mail address and the employee number or the full name.")
    if len(rows) > MAX_BULK_LINES:
        raise CatalogError(f"At most {MAX_BULK_LINES} lines at once.")
    issues: list[dict[str, Any]] = []
    counts = {"linked": 0, "unchanged": 0, "problems": 0}
    seen_people: dict[int, int] = {}
    seen_hashes: dict[str, int] = {}

    def problem(line: int, code: str, message: str) -> None:
        counts["problems"] += 1
        issues.append({"line": line, "code": code, "message": f"Line {line}: {message}"})

    for line, email, key in rows:
        if not email or not key:
            problem(line, "format", "needs an e-mail address and an employee number or a name.")
            continue
        try:
            kh = _hash_email(email, secret)
        except CatalogError:
            problem(line, "invalid_email", f"the e-mail address for '{key}' is not valid.")
            continue
        found = conn.execute("SELECT id, full_name, sso_key_hash FROM person WHERE active AND employee_no = %s",
                             (key,)).fetchall()
        if not found:
            found = conn.execute("SELECT id, full_name, sso_key_hash FROM person WHERE active AND name_key = %s",
                                 (norm(key),)).fetchall()
        if not found:
            problem(line, "unknown_person", f"'{key}' does not match an active person.")
            continue
        if len(found) > 1:
            problem(line, "ambiguous_person", f"'{key}' matches more than one person; use the employee number.")
            continue
        person = found[0]
        if person["id"] in seen_people:
            first = seen_people[person["id"]]
            problem(line, "duplicate_person", f"{person['full_name']} already appears on line {first}.")
            continue
        if kh in seen_hashes:
            problem(line, "duplicate_email", f"this e-mail address already appears on line {seen_hashes[kh]}.")
            continue
        other = conn.execute("SELECT full_name FROM person WHERE sso_key_hash = %s AND id <> %s",
                             (kh, person["id"])).fetchone()
        if other:
            problem(line, "email_in_use", f"the e-mail address for {person['full_name']} is already linked to "
                    f"{other['full_name']}.")
            continue
        seen_people[person["id"]], seen_hashes[kh] = line, line
        if person["sso_key_hash"] == kh:
            counts["unchanged"] += 1
            continue
        if person["sso_key_hash"]:
            problem(line, "already_linked", f"{person['full_name']} already has a different sign-in; unlink it first.")
            continue
        conn.execute("UPDATE person SET sso_key_hash = %s, updated_at = now() WHERE id = %s", (kh, person["id"]))
        counts["linked"] += 1

    applied = commit and counts["problems"] == 0
    if commit and not applied:
        raise CatalogError("Nothing was saved because some lines have problems. Fix them and try again.", 422)
    if applied:
        audit(conn, actor, "user.logins.bulk", "person", "bulk", counts)
    return {"applied": applied, "lines": len(rows), **counts, "issues": issues[:100]}


# ------------------------------------------------------------------------------------------ roles


def _has_role(conn: Connection, person_id: int, role: str, scope: int | None) -> bool:
    return conn.execute("SELECT 1 FROM user_role WHERE person_id = %s AND role = %s AND "
                        "scope_org_unit_id IS NOT DISTINCT FROM %s", (person_id, role, scope)).fetchone() is not None


def add_role(conn: Connection, person_id: int, body: RoleIn, actor: int | None) -> dict:
    if not conn.execute("SELECT 1 FROM person WHERE id = %s AND active", (person_id,)).fetchone():
        raise CatalogError("The person does not exist or is not active.", 404)
    kind = ROLE_SCOPE[body.role]
    if kind is None and body.scope_org_unit_id is not None:
        raise CatalogError("This role does not have a scope.")
    if kind is not None:
        if body.scope_org_unit_id is None:
            raise CatalogError(f"Choose the {kind} this role covers.")
        if not conn.execute("SELECT 1 FROM org_unit WHERE id = %s AND kind = %s AND active",
                            (body.scope_org_unit_id, kind)).fetchone():
            raise CatalogError(f"The {kind} does not exist.")
    if _has_role(conn, person_id, body.role, body.scope_org_unit_id):
        raise CatalogError("This person already has this role.", 409)
    conn.execute("INSERT INTO user_role(person_id, role, scope_org_unit_id) VALUES (%s,%s,%s)",
                 (person_id, body.role, body.scope_org_unit_id))
    audit(conn, actor, "user.role.add", "person", person_id,
          {"role": body.role, "scope": body.scope_org_unit_id})
    return get_user(conn, person_id)


def remove_role(conn: Connection, person_id: int, role_id: int, actor: int | None, bootstrap: bool) -> dict:
    row = conn.execute("SELECT id, role, scope_org_unit_id FROM user_role WHERE id = %s AND person_id = %s",
                       (role_id, person_id)).fetchone()
    if row is None:
        raise CatalogError("The role does not exist.", 404)
    if row["role"] == "administrator":
        _guard_last_admin(conn, person_id, bootstrap, "remove this role")
    conn.execute("DELETE FROM user_role WHERE id = %s", (role_id,))
    audit(conn, actor, "user.role.remove", "person", person_id,
          {"role": row["role"], "scope": row["scope_org_unit_id"]})
    return get_user(conn, person_id)


def suggest_roles(conn: Connection, commit: bool, actor: int | None) -> dict[str, Any]:
    """Planning roles that follow from the organization: the Head, regional managers and area managers."""
    wanted: list[tuple[int, str, int | None, str]] = []  # person, role, scope, label
    for r in conn.execute(
        "SELECT p.id, p.full_name, pos.code, u.id AS unit_id, u.kind, u.name AS unit FROM org_unit u "
        "JOIN person p ON p.id = u.lead_person_id AND p.active "
        "JOIN person_assignment a ON a.person_id = p.id AND a.valid_to IS NULL "
        "JOIN position pos ON pos.id = a.position_id WHERE u.active"):
        if r["kind"] == "region":
            wanted.append((r["id"], "regional_planner", r["unit_id"],
                           f"{r['full_name']}: regional planner of {r['unit']}"))
        elif r["kind"] == "cluster" and r["code"] == "AM":
            wanted.append((r["id"], "area_planner", r["unit_id"], f"{r['full_name']}: area planner of {r['unit']}"))
    for r in conn.execute(
        "SELECT p.id, p.full_name FROM person p JOIN person_assignment a ON a.person_id = p.id AND a.valid_to IS NULL "
        "JOIN position pos ON pos.id = a.position_id WHERE p.active AND pos.code = 'HEAD'"):
        wanted.append((r["id"], "national_planner", None, f"{r['full_name']}: national planner"))
    new, existing = [], 0
    for pid, role, scope, label in wanted:
        if _has_role(conn, pid, role, scope):
            existing += 1
            continue
        new.append(label)
        if commit:
            conn.execute("INSERT INTO user_role(person_id, role, scope_org_unit_id) VALUES (%s,%s,%s)",
                         (pid, role, scope))
    if commit and new:
        audit(conn, actor, "user.roles.suggest", "person", "bulk", {"added": len(new)})
    return {"applied": commit, "to_add": len(new), "already_there": existing, "roles": sorted(new)}

