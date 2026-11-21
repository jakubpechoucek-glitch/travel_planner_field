"""Import the field organization (people, reporting lines, regions, clusters, local offices).

Source: the planning workbook ("Emp Tables" and, optionally, "EMP LIST FC upload").
The import is idempotent, header-driven, and reports problems instead of guessing.
It never reads or stores e-mail addresses or phone numbers.

    python -m travel_planner.orgimport workbook.xlsx                 # preview, nothing is saved
    python -m travel_planner.orgimport workbook.xlsx --apply         # save
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import openpyxl
from psycopg import Connection

# --------------------------------------------------------------------------- helpers


def norm(value: Any) -> str:
    """Normalized key: no NBSP, collapsed spaces, case-insensitive."""
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip().casefold()


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def pretty(value: str) -> str:
    """Display form: title case for ALL CAPS input (NCR stays upper case)."""
    value = clean(value)
    if not value.isupper():
        return value
    return " ".join("NCR" if w == "NCR" else w.title() for w in value.split(" "))


def slug(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", clean(value).upper()).strip("-")


# ordered: the first match wins ("am temp/regional manager" must be seen as an acting AM)
POSITION_RULES = [
    ("head of", "HEAD"),
    ("temp", "AM"),
    ("regional manager", "RM"),
    ("area manager", "AM"),
    ("senior field supervisor", "SFSV"),
    ("field supervisor ii", "FSV2"),
    ("field supervisor", "FSV"),
    ("digital mentor", "DM"),
    ("digital supervisor", "DSV"),
]
LEVEL = {"HEAD": 0, "RM": 1, "AM": 2, "SFSV": 3, "FSV2": 3, "FSV": 3, "DM": 3, "DSV": 3}


def position_code(text: Any) -> str | None:
    t = norm(text)
    return next((code for needle, code in POSITION_RULES if needle in t), None)


# --------------------------------------------------------------------------- model


@dataclass
class Issue:
    level: str  # error | warning | info
    code: str
    message: str


@dataclass
class PersonRec:
    key: str
    name: str
    position: str
    employee_no: str | None = None
    manager_key: str | None = None
    region: str | None = None  # normalized keys below
    cluster: str | None = None
    office: str | None = None
    acting_am: bool = False


@dataclass
class ParsedOrg:
    regions: dict[str, str] = field(default_factory=dict)  # key -> display
    clusters: dict[str, tuple[str, str | None]] = field(default_factory=dict)  # key -> (display, region key)
    offices: dict[str, tuple[str, str | None]] = field(default_factory=dict)  # key -> (display, region key)
    cluster_lead: dict[str, str] = field(default_factory=dict)  # cluster key -> person key
    region_lead: dict[str, str] = field(default_factory=dict)  # region key -> person key
    people: dict[str, PersonRec] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)

    def add(self, level: str, code: str, message: str) -> None:
        self.issues.append(Issue(level, code, message))

    @property
    def has_errors(self) -> bool:
        return any(i.level == "error" for i in self.issues)


# --------------------------------------------------------------------------- parsing


def _sheet(wb: openpyxl.Workbook, name: str):
    for ws in wb.worksheets:
        if norm(ws.title) == norm(name):
            return ws
    return None


def _blocks(ws) -> tuple[int, list[dict[str, int]]] | None:
    """Find the header row (several 'EMP NAME' cells) and the column map of each block."""
    for r in range(1, 16):
        cells = [norm(c.value) for c in ws[r]]
        starts = [i for i, v in enumerate(cells) if v == "emp name"]
        if len(starts) >= 3:
            blocks = []
            for n, s in enumerate(starts):
                end = starts[n + 1] if n + 1 < len(starts) else len(cells)
                cols: dict[str, int] = {}
                for i in range(s, end):
                    if cells[i] and cells[i] not in cols:
                        cols[cells[i]] = i
                blocks.append(cols)
            return r, blocks
    return None


def _rows(ws, header_row: int, cols: dict[str, int]):
    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        name = clean(row[cols["emp name"]]) if cols["emp name"] < len(row) else ""
        if not name or norm(name) == "emp name":
            continue

        def get(h: str, row=row) -> str:
            i = cols.get(h)
            return clean(row[i]) if i is not None and i < len(row) and row[i] is not None else ""

        yield name, get


def parse_workbook(path: str | Path) -> ParsedOrg:
    out = ParsedOrg()
    wb = openpyxl.load_workbook(path, read_only=False, data_only=True)
    tables = _sheet(wb, "Emp Tables")
    if tables is None:
        out.add("error", "missing_sheet", "The workbook has no sheet named 'Emp Tables'.")
        return out
    found = _blocks(tables)
    if found is None:
        out.add("error", "missing_blocks", "Could not find the RM, AM and FSV tables on 'Emp Tables'.")
        return out
    header_row, blocks = found
    if len(blocks) < 3:
        out.add("error", "missing_blocks", "Expected at least three tables (RM, AM, FSV) on 'Emp Tables'.")
        return out

    conflicts: Counter[str] = Counter()

    def region_key(text: str) -> str | None:
        k = norm(text)
        if k:
            out.regions.setdefault(k, pretty(text))
        return k or None

    def cluster_key(text: str, rkey: str | None) -> str | None:
        k = norm(text)
        if k:
            out.clusters.setdefault(k, (pretty(text), rkey))
        return k or None

    def office_key(text: str, rkey: str | None) -> str | None:
        k = norm(text)
        if not k:
            return None
        known = out.offices.get(k)
        if known is None or (known[1] is None and rkey):
            out.offices[k] = (known[0] if known else clean(text), rkey)
        elif rkey and known[1] != rkey:
            conflicts[k] += 1
        return k

    def put(rec: PersonRec) -> PersonRec:
        existing = out.people.get(rec.key)
        if existing is None:
            out.people[rec.key] = rec
            return rec
        if LEVEL[rec.position] < LEVEL[existing.position]:  # the higher role wins (RM over acting AM)
            rec.employee_no = rec.employee_no or existing.employee_no
            out.people[rec.key] = rec
            return rec
        return existing

    # 1. Regional managers
    for name, get in _rows(tables, header_row, blocks[0]):
        if position_code(get("position")) == "HEAD":
            put(PersonRec(norm(name), pretty(name), "HEAD"))
            continue
        if position_code(get("position")) != "RM":
            out.add("error", "rm_table_position", f"'{name}' in the RM table is not a Regional Manager.")
            continue
        rk = region_key(get("region"))
        ck = cluster_key(get("cluster"), rk)
        rec = put(PersonRec(norm(name), pretty(name), "RM", office=office_key(get("local office"), None)))
        if ck:
            out.cluster_lead.setdefault(ck, rec.key)  # provisional: replaced by the AM when there is one
        if rk and out.region_lead.setdefault(rk, rec.key) != rec.key:
            out.add("warning", "region_multiple_rm", f"Region '{get('region')}' has more than one RM.")
    rm_keys = {k for k, p in out.people.items() if p.position == "RM"}
    rm_cluster = dict(out.cluster_lead)

    # 2. Area managers (one per cluster; an acting AM that is an RM leaves the RM in charge)
    seen_am_cluster: dict[str, str] = {}
    for name, get in _rows(tables, header_row, blocks[1]):
        code = position_code(get("position"))
        rk = region_key(get("region"))
        ck = cluster_key(get("cluster"), rk)
        office = office_key(get("local office"), rk)
        key = norm(name)
        if code != "AM":
            out.add("error", "am_table_position", f"'{name}' in the AM table is not an Area Manager.")
            continue
        if key in rm_keys or "temp" in norm(get("position")):
            out.add("info", "acting_am", f"Cluster '{get('cluster')}' has no Area Manager; "
                    f"the Regional Manager acts as one.")
            continue
        rec = put(PersonRec(key, pretty(name), "AM", region=rk, cluster=ck, office=office,
                            manager_key=rm_cluster.get(ck) if ck else None))
        if ck:
            if seen_am_cluster.setdefault(ck, rec.key) != rec.key:
                out.add("warning", "cluster_multiple_am", f"Cluster '{get('cluster')}' has more than one AM.")
            else:
                out.cluster_lead[ck] = rec.key
        if rec.cluster not in (None, ck):
            out.add("warning", "am_multiple_clusters", f"'{name}' manages more than one cluster.")
    for ck, lead in out.cluster_lead.items():
        if ck not in seen_am_cluster and lead not in rm_keys:
            out.add("warning", "cluster_without_lead", f"Cluster '{out.clusters[ck][0]}' has no leader.")

    # 3. Head of Field (last table, optional): only the row with a "Head of ..." position
    if len(blocks) > 3 and "position" in blocks[3]:
        for name, get in _rows(tables, header_row, blocks[3]):
            if position_code(get("position")) == "HEAD":
                put(PersonRec(norm(name), pretty(name), "HEAD"))
    heads = [p for p in out.people.values() if p.position == "HEAD"]
    if not heads:
        out.add("warning", "no_head", "No Head of Field was found in the workbook.")
    for rm in rm_keys:
        if heads:
            out.people[rm].manager_key = heads[0].key
    if len(heads) > 1:
        out.add("warning", "multiple_heads", "More than one Head of Field was found.")

    # 4. Supervisors: the FSV table (cluster, office) merged with the employee list (number, manager)
    listing: dict[str, dict[str, str]] = {}
    emp_ws = _sheet(wb, "EMP LIST FC upload")
    if emp_ws is None:
        out.add("warning", "no_employee_list", "No 'EMP LIST FC upload' sheet: employee numbers and "
                "reporting lines are taken from the cluster leaders.")
    else:
        head = [norm(c.value) for c in next(emp_ws.iter_rows(min_row=1, max_row=1))]
        idx = {h: i for i, h in enumerate(head) if h}
        for row in emp_ws.iter_rows(min_row=2, values_only=True):
            def cell(h: str, row=row) -> str:
                i = idx.get(h)
                return clean(row[i]) if i is not None and i < len(row) and row[i] is not None else ""
            if cell("emp name"):
                listing[norm(cell("emp name"))] = {
                    "name": cell("emp name"), "no": cell("emp no"), "pos": cell("position"),
                    "manager": cell("am"), "region": cell("region"), "office": cell("area"),
                }

    fsv_seen: set[str] = set()
    for name, get in _rows(tables, header_row, blocks[2]):
        key = norm(name)
        code = position_code(get("position"))
        if code is None or LEVEL[code] != 3:
            out.add("error", "unknown_position", f"'{name}' has an unknown position '{get('position')}'.")
            continue
        rk = region_key(get("region"))
        extra = listing.get(key, {})
        fsv_seen.add(key)
        put(PersonRec(key, pretty(name), code, employee_no=extra.get("no") or None, region=rk,
                      cluster=cluster_key(get("cluster"), rk), office=office_key(get("local office"), rk),
                      manager_key=norm(extra["manager"]) if extra.get("manager") else None))
    for key, extra in listing.items():
        if key in fsv_seen or key in out.people:
            continue
        code = position_code(extra["pos"])
        if code is None or LEVEL[code] != 3:
            out.add("error", "unknown_position", f"'{extra['name']}' has an unknown position '{extra['pos']}'.")
            continue
        rk = region_key(extra["region"])
        rec = put(PersonRec(key, pretty(extra["name"]), code, employee_no=extra["no"] or None, region=rk,
                            office=office_key(extra["office"], rk),
                            manager_key=norm(extra["manager"]) if extra["manager"] else None))
        out.add("info", "only_in_employee_list", f"'{rec.name}' is in the employee list but not in the FSV table.")

    # 5. Resolve managers and clusters of supervisors
    leaders = {k for k, p in out.people.items() if p.position in ("HEAD", "RM", "AM")}
    differs: Counter[tuple[str, str, str]] = Counter()
    cluster_of_office: dict[str, set[str]] = {}
    for p in out.people.values():
        if p.cluster and p.office:
            cluster_of_office.setdefault(p.office, set()).add(p.cluster)
    for p in out.people.values():
        if LEVEL[p.position] != 3:
            continue
        if p.cluster is None and p.manager_key in out.people and out.people[p.manager_key].cluster:
            p.cluster = out.people[p.manager_key].cluster
        if p.cluster is None and p.office and len(cluster_of_office.get(p.office, ())) == 1:
            p.cluster = next(iter(cluster_of_office[p.office]))
        lead = out.cluster_lead.get(p.cluster) if p.cluster else None
        if p.manager_key and p.manager_key not in leaders:
            out.add("warning", "manager_not_found",
                    f"Manager of '{p.name}' is not an AM, RM or Head in the workbook; the cluster leader is used.")
            p.manager_key = None
        if lead and p.manager_key and p.manager_key != lead:
            differs[(p.manager_key, lead, p.cluster)] += 1
        if lead:  # the cluster tables are the authority for the current structure
            p.manager_key = lead
        elif p.manager_key is None:
            out.add("warning", "no_manager", f"'{p.name}' has no manager and no cluster leader.")
        if p.cluster is None:
            out.add("warning", "no_cluster", f"'{p.name}' has no cluster.")

    counts = Counter(p.position for p in out.people.values())
    for (listed, lead, ck), n in differs.most_common():
        out.add("warning", "manager_differs",
                f"{n} {'supervisor' if n == 1 else 'supervisors'} in cluster '{out.clusters[ck][0]}' "
                f"{'reports' if n == 1 else 'report'} to {out.people[listed].name} in the "
                f"employee list, but the cluster table names {out.people[lead].name}. The cluster table is used.")
    for k, n in conflicts.items():
        out.add("warning", "office_region_conflict",
                f"Local office '{out.offices[k][0]}' is listed under more than one region ({n} rows); "
                "the first one is used.")
    parts = [f"{n} {c}" for c, n in sorted(counts.items(), key=lambda x: LEVEL[x[0]])]
    out.add("info", "parsed", "Parsed " + ", ".join(parts) + ".")
    wb.close()
    return out


# --------------------------------------------------------------------------- applying


def apply_org(conn: Connection, org: ParsedOrg, effective: date) -> dict[str, int]:
    """Write the parsed organization. Runs inside the caller's transaction."""
    tally: Counter[str] = Counter()
    position_ids = {r["code"]: r["id"] for r in conn.execute("SELECT id, code FROM travel.position")}

    unit_ids: dict[tuple[str, str], int] = {}

    def upsert_unit(kind: str, key: str, name: str, parent_id: int | None) -> int:
        code = slug(name)
        row = conn.execute(
            "SELECT id, name, parent_id, active FROM travel.org_unit WHERE kind = %s AND code = %s", (kind, code)
        ).fetchone()
        if row is None:
            new = conn.execute(
                "INSERT INTO travel.org_unit(kind, code, name, parent_id) VALUES (%s, %s, %s, %s) RETURNING id",
                (kind, code, name, parent_id),
            ).fetchone()
            tally[f"{kind}s_created"] += 1
            unit_ids[(kind, key)] = new["id"]
            return new["id"]
        if (row["name"], row["parent_id"], row["active"]) != (name, parent_id, True):
            conn.execute("UPDATE travel.org_unit SET name=%s, parent_id=%s, active=true WHERE id=%s",
                         (name, parent_id, row["id"]))
            tally[f"{kind}s_updated"] += 1
        else:
            tally[f"{kind}s_unchanged"] += 1
        unit_ids[(kind, key)] = row["id"]
        return row["id"]

    for k, name in org.regions.items():
        upsert_unit("region", k, name, None)
    for k, (name, rk) in org.clusters.items():
        upsert_unit("cluster", k, name, unit_ids.get(("region", rk)) if rk else None)
    for k, (name, rk) in org.offices.items():
        oid = upsert_unit("local_office", k, name, unit_ids.get(("region", rk)) if rk else None)
        if conn.execute("SELECT 1 FROM travel.location WHERE local_office_id = %s AND name = %s",
                        (oid, name)).fetchone() is None:
            conn.execute("INSERT INTO travel.location(name, region_id, local_office_id) VALUES (%s, %s, %s)",
                         (name, unit_ids.get(("region", rk)) if rk else None, oid))
            tally["locations_created"] += 1

    # people
    person_ids: dict[str, int] = {}
    for p in org.people.values():
        row = None
        if p.employee_no:
            row = conn.execute("SELECT id, full_name, employee_no, active FROM travel.person WHERE employee_no = %s",
                               (p.employee_no,)).fetchone()
        if row is None:
            rows = conn.execute(
                "SELECT id, full_name, employee_no, active FROM travel.person WHERE name_key = %s "
                "AND (employee_no IS NULL OR employee_no = %s)", (p.key, p.employee_no)).fetchall()
            if len(rows) > 1:
                org.add("error", "ambiguous_person", f"More than one person named '{p.name}' exists; skipped.")
                continue
            row = rows[0] if rows else None
        if row is None:
            new = conn.execute(
                "INSERT INTO travel.person(employee_no, full_name, name_key) VALUES (%s, %s, %s) RETURNING id",
                (p.employee_no, p.name, p.key)).fetchone()
            person_ids[p.key] = new["id"]
            tally["people_created"] += 1
        else:
            person_ids[p.key] = row["id"]
            want = (p.name, p.employee_no or row["employee_no"], True)
            if (row["full_name"], row["employee_no"], row["active"]) != want:
                conn.execute("UPDATE travel.person SET full_name=%s, employee_no=%s, active=true, name_key=%s, "
                             "end_date=NULL, updated_at=now() WHERE id=%s", (*want[:2], p.key, row["id"]))
                tally["people_updated"] += 1
            else:
                conn.execute("UPDATE travel.person SET name_key=%s WHERE id=%s AND name_key IS DISTINCT FROM %s",
                             (p.key, row["id"], p.key))
                tally["people_unchanged"] += 1

    # assignments (effective dated)
    def uid(kind: str, key: str | None) -> int | None:
        return unit_ids.get((kind, key)) if key else None

    for p in org.people.values():
        pid = person_ids.get(p.key)
        if pid is None:
            continue
        region = p.region
        if p.position == "RM":
            regions = {r for r, lead in org.region_lead.items() if lead == p.key}
            region = next(iter(regions)) if len(regions) == 1 else None
        want = (
            position_ids[p.position],
            person_ids.get(p.manager_key) if p.manager_key else None,
            uid("region", region), uid("cluster", p.cluster), uid("local_office", p.office),
        )
        cur = conn.execute(
            "SELECT id, position_id, manager_id, region_id, cluster_id, local_office_id, valid_from "
            "FROM travel.person_assignment WHERE person_id=%s AND valid_to IS NULL "
            "ORDER BY valid_from DESC LIMIT 1", (pid,)).fetchone()
        have = (cur["position_id"], cur["manager_id"], cur["region_id"], cur["cluster_id"],
                cur["local_office_id"]) if cur else None
        if have == want:
            tally["assignments_unchanged"] += 1
        elif cur and cur["valid_from"] == effective:
            conn.execute("UPDATE travel.person_assignment SET position_id=%s, manager_id=%s, region_id=%s, "
                         "cluster_id=%s, local_office_id=%s WHERE id=%s", (*want, cur["id"]))
            tally["assignments_updated"] += 1
        elif cur and cur["valid_from"] > effective:
            org.add("error", "effective_date_too_early",
                    f"'{p.name}' already has an assignment starting {cur['valid_from']}; skipped.")
        else:
            if cur:
                conn.execute("UPDATE travel.person_assignment SET valid_to=%s WHERE id=%s",
                             (effective - timedelta(days=1), cur["id"]))
                tally["assignments_changed"] += 1
            else:
                tally["assignments_created"] += 1
            conn.execute("INSERT INTO travel.person_assignment(person_id, position_id, manager_id, region_id, "
                         "cluster_id, local_office_id, valid_from) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                         (pid, *want, effective))

    # leaders of regions and clusters
    for kind, leads in (("region", org.region_lead), ("cluster", org.cluster_lead)):
        for k, lead in leads.items():
            conn.execute(
                "UPDATE travel.org_unit SET lead_person_id=%s WHERE id=%s",
                (person_ids.get(lead), unit_ids[(kind, k)]),
            )

    missing = conn.execute(
        "SELECT count(*) AS n FROM travel.person p WHERE p.active AND NOT (p.name_key = ANY(%s)) "
        "AND EXISTS (SELECT 1 FROM travel.person_assignment a WHERE a.person_id = p.id AND a.valid_to IS NULL)",
        (list(org.people),)).fetchone()["n"]
    if missing:
        org.add("info", "missing_in_file", f"{missing} active people in the database are not in this file "
                "(they were left unchanged).")
    return dict(tally)


def run_import(pool, path: str | Path, effective: date, commit: bool, actor_person_id: int | None = None) -> dict:
    """Parse and apply inside a transaction; commit only when asked and when there are no errors.

    A preview (commit=False) runs the full write and rolls it back, so its counts are exact.
    """
    org = parse_workbook(path)
    summary: dict[str, int] = {}
    applied = False
    if not any(i.code in {"missing_sheet", "missing_blocks"} for i in org.issues):
        with pool.connection() as conn:
            try:
                summary = apply_org(conn, org, effective)
                if commit and not org.has_errors:
                    conn.execute(
                        "INSERT INTO travel.audit_log(actor_person_id, action, entity, details) "
                        "VALUES (%s, 'org.import', 'organization', %s)",
                        (actor_person_id, json.dumps({"effective": str(effective), **summary})),
                    )
                    conn.commit()
                    applied = True
                else:
                    conn.rollback()
            except Exception:
                conn.rollback()
                raise
    if commit and not applied:
        org.add("error", "not_applied", "Nothing was saved because the file has errors. Fix them and try again.")
    return {
        "applied": applied,
        "effective_date": str(effective),
        "summary": summary,
        "issues": [i.__dict__ for i in org.issues],
        "errors": sum(i.level == "error" for i in org.issues),
        "warnings": sum(i.level == "warning" for i in org.issues),
    }


# --------------------------------------------------------------------------- command line


def main() -> None:
    from .config import get_settings
    from .db import create_pool
    from .migrate import apply_migrations

    ap = argparse.ArgumentParser(description="Import the field organization from the planning workbook.")
    ap.add_argument("workbook")
    ap.add_argument("--effective", default="2027-01-01", help="date the structure is valid from (YYYY-MM-DD)")
    ap.add_argument("--apply", action="store_true", help="save the changes (default: preview only)")
    args = ap.parse_args()
    settings = get_settings()
    pool = create_pool(settings)
    pool.open(wait=True)
    apply_migrations(pool, settings.migrations_dir)
    report = run_import(pool, args.workbook, date.fromisoformat(args.effective), commit=args.apply)
    print("APPLIED" if report["applied"] else "PREVIEW ONLY (nothing saved)")
    for k, v in sorted(report["summary"].items()):
        print(f"  {k}: {v}")
    for i in report["issues"]:
        print(f"[{i['level']}] {i['code']}: {i['message']}")
    pool.close()


if __name__ == "__main__":
    main()
