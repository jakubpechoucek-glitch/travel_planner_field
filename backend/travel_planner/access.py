"""Who may see and change which part of the plan.

Administrators and national planners cover everything. A regional planner covers the units under the region(s)
they are assigned to, an area planner the cluster(s) and local offices of theirs. Nationwide events are visible
to every planner but changed only by administrators and national planners.
"""

from __future__ import annotations

from psycopg import Connection

from .identity import Identity

PLAN_ROLES = ("administrator", "national_planner", "regional_planner", "area_planner")
ALL_ACCESS = {"administrator", "national_planner"}


def has_plan_access(identity: Identity) -> bool:
    return bool(set(identity.roles) & set(PLAN_ROLES))


def allowed_units(conn: Connection, identity: Identity) -> set[int] | None:
    """Org unit ids the identity may see and edit; None means everything."""
    if set(identity.roles) & ALL_ACCESS:
        return None
    allowed: set[int] = set()
    for role, unit_id in identity.scopes:
        if unit_id is None:
            continue
        if role == "regional_planner":
            allowed.add(unit_id)
            allowed.update(r["id"] for r in conn.execute("SELECT id FROM org_unit WHERE parent_id = %s", (unit_id,)))
        elif role == "area_planner":
            allowed.add(unit_id)
            allowed.update(r["local_office_id"] for r in conn.execute(
                "SELECT DISTINCT local_office_id FROM person_assignment WHERE cluster_id = %s AND valid_to IS NULL "
                "AND local_office_id IS NOT NULL", (unit_id,)))
    return allowed


def can_edit(allowed: set[int] | None, visited_unit_id: int | None) -> bool:
    if allowed is None:
        return True
    return visited_unit_id is not None and visited_unit_id in allowed


def can_see(allowed: set[int] | None, visited_unit_id: int | None) -> bool:
    return allowed is None or visited_unit_id is None or visited_unit_id in allowed
