"""Excel export of the plan: a workbook for planning meetings, budget work and approvals.

Sheets: About, Summary (trips per month by place, trips by event), Trips (one row per trip), People on trips
(one row per person per trip), Per person (trips and days away), Changes (every manual change with its reason),
and Checks (rule warnings, only for people who see the whole plan).

* The export follows the caller's scope: a regional or area planner gets the trips of their own area, plus the
  nationwide events everybody can see.
* Text is always written as text: a note that starts with "=" can never become a formula.
* It is a snapshot with values, not formulas, so it looks the same in every spreadsheet program.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from psycopg import Connection

from . import plan_store as store
from .catalog import CatalogError, audit

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
STATUS = {"generated": "Proposed", "planned": "Confirmed", "requested": "Requested", "approved": "Approved",
          "completed": "Done", "cancelled": "Cancelled"}
ROLE = {"organizer": "Organizer", "traveler": "Traveler", "host": "Host"}
CHANGE = {"created": "Added", "moved": "Moved", "resized": "Length changed", "reassigned": "People changed",
          "edited": "Edited", "status": "Status changed", "cancelled": "Cancelled", "merged": "Combined",
          "split": "Split"}
CATEGORY = {"business_request": "Business request", "company_event_conflict": "Conflict with a company event",
            "merged": "Combined with another trip", "capacity": "Capacity", "budget": "Budget", "other": "Other"}
WARNING_TITLE = {"period_cap": "Trip limit per person", "period_min": "Too few trips", "yearly_limit": "Yearly limit",
                 "quota_short": "Too few trips for a place", "quota_over": "Too many trips for a place",
                 "blackout": "Trip in a blackout period", "overlap": "Person in two trips at once"}

ACCENT = "0B6E99"
HEADER_FILL = PatternFill("solid", fgColor=ACCENT)
HEADER_FONT = Font(bold=True, color="FFFFFF")
BAND_FILL = PatternFill("solid", fgColor="EEF4F8")
DATE_FORMAT = "ddd d mmm yyyy"


# ------------------------------------------------------------------------------------------ writing helpers


def put(ws: Worksheet, row: int, values: list[Any], *, header: bool = False, bold: bool = False) -> None:
    """Write a row. Strings are forced to text so that user input can never be read as a formula."""
    for col, value in enumerate(values, 1):
        cell = ws.cell(row, col)
        cell.value = value
        if isinstance(value, str):
            cell.data_type = "s"
        elif isinstance(value, date | datetime):
            cell.number_format = DATE_FORMAT
        if header:
            cell.fill, cell.font = HEADER_FILL, HEADER_FONT
            cell.alignment = Alignment(wrap_text=True, vertical="center")
        elif bold:
            cell.font = Font(bold=True)


def table(ws: Worksheet, headers: list[str], rows: list[list[Any]], widths: list[int], start: int = 1,
          wrap: set[int] | None = None) -> int:
    """A header row, the data rows, filter and frozen header. Returns the next free row."""
    put(ws, start, headers, header=True)
    ws.row_dimensions[start].height = 32
    for i, values in enumerate(rows, start + 1):
        put(ws, i, values)
        if (i - start) % 2 == 0:
            for c in range(1, len(headers) + 1):
                ws.cell(i, c).fill = BAND_FILL
    for c, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(c)].width = w
    for c in wrap or set():
        for r in range(start + 1, start + len(rows) + 1):
            ws.cell(r, c).alignment = Alignment(wrap_text=True, vertical="top")
    if rows:
        ws.auto_filter.ref = f"A{start}:{get_column_letter(len(headers))}{start + len(rows)}"
    ws.freeze_panes = ws.cell(start + 1, 1)
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{start}:{start}"
    return start + len(rows) + 1


def nights(start: date, end: date) -> int:
    return (end - start).days


# ------------------------------------------------------------------------------------------ data


def _load(conn: Connection, year: int, allowed: set[int] | None, include_cancelled: bool) -> dict[str, Any]:
    scope, scope_args = store._scope_sql(allowed)
    status_clause = "TRUE" if include_cancelled else "t.status <> 'cancelled'"
    trips = conn.execute(
        "SELECT t.id, t.title, t.start_date, t.end_date, t.status, t.source, t.notes, t.cancel_reason, "
        "t.generated_start_date, t.generated_end_date, t.transport_mode, t.sap_request_no, "
        "t.merged_into_trip_id, e.name AS event, e.code, u.kind AS unit_kind, u.name AS unit, "
        "p.name AS parent, pp.name AS grandparent, "
        "(SELECT c.reason FROM trip_change c WHERE c.trip_id = t.id AND c.change_type NOT IN ('generated') "
        " ORDER BY c.changed_at DESC, c.id DESC LIMIT 1) AS last_reason, "
        "EXISTS (SELECT 1 FROM trip_change c WHERE c.trip_id = t.id AND c.change_type NOT IN ('generated', 'created')) "
        " AS changed "
        "FROM trip t JOIN event_type e ON e.id = t.event_type_id LEFT JOIN org_unit u ON u.id = t.visited_org_unit_id "
        "LEFT JOIN org_unit p ON p.id = u.parent_id LEFT JOIN org_unit pp ON pp.id = p.parent_id "
        f"WHERE t.plan_year = %s AND {status_clause} AND {scope} ORDER BY t.start_date, t.end_date, t.id",  # noqa: S608
        (year, *scope_args)).fetchall()
    ids = [t["id"] for t in trips]
    parts = conn.execute(
        "SELECT tp.trip_id, tp.role, tp.travels, p.id AS person_id, p.full_name AS name, pos.name AS position, "
        "c.name AS cluster, a.cluster_id, a.region_id, a.local_office_id "
        "FROM trip_participant tp JOIN person p ON p.id = tp.person_id "
        "LEFT JOIN person_assignment a ON a.person_id = p.id AND a.valid_to IS NULL "
        "LEFT JOIN position pos ON pos.id = a.position_id LEFT JOIN org_unit c ON c.id = a.cluster_id "
        "WHERE tp.trip_id = ANY(%s) ORDER BY (tp.role = 'organizer') DESC, tp.travels DESC, p.full_name",
        (ids,)).fetchall() if ids else []
    changes = conn.execute(
        "SELECT c.trip_id, c.changed_at, c.change_type, c.category, c.reason, per.full_name AS who "
        "FROM trip_change c LEFT JOIN person per ON per.id = c.changed_by WHERE c.trip_id = ANY(%s) "
        "AND c.change_type <> 'generated' ORDER BY c.changed_at, c.id", (ids,)).fetchall() if ids else []
    absorbed = conn.execute(
        "SELECT m.merged_into_trip_id AS trip_id, e.name FROM trip m JOIN event_type e ON e.id = m.event_type_id "
        "WHERE m.merged_into_trip_id = ANY(%s) ORDER BY e.name", (ids,)).fetchall() if ids else []
    py = conn.execute("SELECT status, published_at FROM plan_year WHERE year = %s", (year,)).fetchone()
    return {"trips": trips, "parts": parts, "changes": changes, "absorbed": absorbed, "plan": py}


def _place(t: dict[str, Any]) -> tuple[str, str, str]:
    """Region, cluster and local office of the visited place."""
    kind, name = t["unit_kind"], t["unit"]
    if kind is None:
        return "Nationwide", "", ""
    if kind == "region":
        return name, "", ""
    if kind == "cluster":
        return t["parent"] or "", name, ""
    return t["parent"] or "", "", name  # local office


# ------------------------------------------------------------------------------------------ the workbook


def build(conn: Connection, year: int, allowed: set[int] | None, *, include_cancelled: bool, with_checks: bool,
          costs: dict[int, float] | None = None, event_costs: dict[str, float] | None = None,
          now: datetime | None = None) -> tuple[bytes, dict[str, int]]:
    data = _load(conn, year, allowed, include_cancelled)
    if data["plan"] is None:
        raise CatalogError(f"The plan year {year} does not exist.", 404)
    now = now or datetime.now(UTC)
    trips, parts = data["trips"], data["parts"]
    parts_by: dict[int, list[dict]] = defaultdict(list)
    for p in parts:
        parts_by[p["trip_id"]].append(p)
    combined: dict[int, list[str]] = defaultdict(list)
    for r in data["absorbed"]:
        combined[r["trip_id"]].append(r["name"])
    live = [t for t in trips if t["status"] != "cancelled" and t["merged_into_trip_id"] is None]

    def listed(trip: dict[str, Any], p: dict[str, Any]) -> bool:
        """A scoped export names people outside the scope only on trips inside it, never on nationwide trips."""
        if allowed is None or trip["unit_kind"] is not None:
            return True
        return any(u is not None and u in allowed for u in (p["cluster_id"], p["region_id"], p["local_office_id"]))

    def in_scope(p: dict[str, Any]) -> bool:
        return allowed is None or any(u is not None and u in allowed
                                      for u in (p["cluster_id"], p["region_id"], p["local_office_id"]))

    wb = Workbook()
    wb.properties.title = f"Travel plan {year}"
    wb.properties.creator = "Travel Planner for Field Teams"

    # ----- Summary
    ws = wb.active
    ws.title = "Summary"
    put(ws, 1, [f"Travel plan {year}"])
    ws["A1"].font = Font(bold=True, size=16, color=ACCENT)
    scope_note = "" if allowed is None else " (your area and the nationwide events)"
    put(ws, 2, [f"Plan status: {data['plan']['status']}. {len(live)} trips{scope_note}."])
    cells: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0] * 12)
    for t in live:
        region, cluster, office = _place(t)
        label = cluster or (f"{region}: region and local offices" if region != "Nationwide" else "Nationwide")
        cells[(region, label)][t["start_date"].month - 1] += 1
    row = 4
    put(ws, row, ["Trips per month, by place"], bold=True)
    row += 1
    put(ws, row, ["Region", "Place", *MONTHS, "Total"], header=True)
    first_data = row + 1
    for (region, label), months in sorted(cells.items()):
        row += 1
        put(ws, row, [region, label, *months, sum(months)])
    if cells:
        ws.conditional_formatting.add(
            f"C{first_data}:N{row}",
            ColorScaleRule(start_type="min", start_color="FFFFFF", end_type="max", end_color="5AA9C7"))
        row += 1
        totals = [sum(m[i] for m in cells.values()) for i in range(12)]
        put(ws, row, ["Total", "", *totals, sum(totals)], bold=True)
    row += 2
    put(ws, row, ["Trips by event"], bold=True)
    row += 1
    put(ws, row, ["Event", "", "Trips", "Merged", "Days away", *(["Estimate (PHP)"] if costs is not None else [])],
        header=True)
    ws.row_dimensions[row].height = 32
    by_event: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for t in live:
        e = by_event[t["event"]]
        e[0] += 1
        e[1] += len(combined[t["id"]])
        days = (t["end_date"] - t["start_date"]).days + 1
        e[2] += days * sum(1 for p in parts_by[t["id"]] if p["travels"])  # days away, summed over travelers
    for name, (n, m, d) in sorted(by_event.items()):
        row += 1
        put(ws, row, [name, "", n, m, d, *([round((event_costs or {}).get(name, 0.0))] if costs is not None else [])])
        if costs is not None:
            ws.cell(row, 6).number_format = "#,##0"
    for c, w in enumerate([34, 32, *([11] * 12), 9], 1):
        ws.column_dimensions[get_column_letter(c)].width = w
    for r in range(first_data, first_data + len(cells) + 1):  # zeros stay blank so the busy months stand out
        for c in range(3, 15):
            ws.cell(r, c).number_format = "0;-0;;@"
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True

    # ----- Trips
    ws = wb.create_sheet("Trips")
    rows = []
    for t in trips:
        region, cluster, office = _place(t)
        ps = parts_by[t["id"]]
        organizer = next((p["name"] for p in ps if p["role"] == "organizer"), "")
        status = ("Combined into another trip" if t["merged_into_trip_id"] and t["status"] == "cancelled"
                  else STATUS.get(t["status"], t["status"]))
        moved = bool(t["generated_start_date"] and (t["generated_start_date"], t["generated_end_date"]) !=
                     (t["start_date"], t["end_date"]))
        rows.append([
            t["id"], t["event"], t["code"], region, cluster, office, t["start_date"], t["end_date"],
            (t["end_date"] - t["start_date"]).days + 1,
            nights(t["start_date"], t["end_date"]), status, "By hand" if t["source"] == "manual" else "Rules",
            organizer, sum(1 for p in ps if p["travels"]), sum(1 for p in ps if not p["travels"]),
            (t["transport_mode"] or "").replace("_", " ").title(),
            t["generated_start_date"], t["generated_end_date"], "Yes" if moved else "No",
            "Yes" if t["changed"] else "No", t["last_reason"] or t["cancel_reason"] or "",
            ", ".join(combined[t["id"]]), t["notes"] or "", t["sap_request_no"] or "",
            *([costs.get(t["id"])] if costs is not None else []),
        ])
    table(ws, ["Trip ID", "Event", "Code", "Region", "Cluster", "Local office", "Start", "End", "Days",
               "Nights", "Status", "Source", "Organizer", "Travelers", "Hosts", "Transport", "Start by the rules",
               "End by the rules", "Moved", "Changed by hand", "Last reason", "Also held at this trip", "Notes",
               "SAP request", *(["Estimated cost (PHP)"] if costs is not None else [])],
          rows, [9, 32, 15, 14, 16, 16, 16, 16, 7, 8, 14, 9, 22, 10, 7, 12, 16, 16, 8, 10, 36, 28, 36, 14, 16],
          wrap={22, 23, 24})
    if costs is not None:
        for r in range(2, len(rows) + 2):
            ws.cell(r, 25).number_format = "#,##0"

    # ----- People on trips
    ws = wb.create_sheet("People on trips")
    rows, per_person = [], {}
    for t in trips:
        if t["merged_into_trip_id"] is not None:
            continue
        region, cluster, office = _place(t)
        days = (t["end_date"] - t["start_date"]).days + 1
        for p in parts_by[t["id"]]:
            if not listed(t, p):
                continue
            rows.append([t["id"], t["event"], cluster or office or region, t["start_date"], t["end_date"], p["name"],
                         p["position"] or "", p["cluster"] or "", ROLE.get(p["role"], p["role"]),
                         "Yes" if p["travels"] else "No", days if p["travels"] else 0,
                         nights(t["start_date"], t["end_date"]) if p["travels"] else 0])
            if p["travels"] and t["status"] != "cancelled" and in_scope(p):
                agg = per_person.setdefault(p["person_id"], {"name": p["name"], "position": p["position"] or "",
                                                              "cluster": p["cluster"] or "", "months": [0] * 12,
                                                              "days": 0, "nights": 0, "trips": 0})
                agg["months"][t["start_date"].month - 1] += 1
                agg["days"] += days
                agg["nights"] += nights(t["start_date"], t["end_date"])
                agg["trips"] += 1
    table(ws, ["Trip ID", "Event", "Place", "Start", "End", "Person", "Position", "Person's cluster", "Role",
               "Travels", "Days away", "Nights"],
          rows, [9, 30, 18, 16, 16, 24, 24, 16, 11, 9, 10, 8])

    # ----- Per person
    ws = wb.create_sheet("Per person")
    rows = [[a["name"], a["position"], a["cluster"], a["trips"], a["days"], a["nights"], max(a["months"], default=0),
             *a["months"]] for a in sorted(per_person.values(), key=lambda a: (-a["trips"], a["name"]))]
    table(ws, ["Person", "Position", "Cluster", "Trips", "Days away", "Nights", "Most trips in a month", *MONTHS],
          rows, [24, 24, 16, 8, 10, 8, 12, *([6] * 12)])
    if rows:
        ws.conditional_formatting.add(
            f"H2:S{len(rows) + 1}", ColorScaleRule(start_type="min", start_color="FFFFFF", end_type="max",
                                                   end_color="5AA9C7"))

    # ----- Changes
    ws = wb.create_sheet("Changes")
    by_id = {t["id"]: t for t in trips}
    rows = [[c["trip_id"], by_id[c["trip_id"]]["title"], c["changed_at"].replace(tzinfo=None),
             c["who"] or "Administrator", CHANGE.get(c["change_type"], c["change_type"]),
             CATEGORY.get(c["category"] or "", ""), c["reason"] or ""] for c in data["changes"]]
    table(ws, ["Trip ID", "Trip", "When", "Who", "Change", "Type of reason", "Reason"], rows,
          [9, 40, 20, 22, 16, 26, 60], wrap={7})
    for r in range(2, len(rows) + 2):
        ws.cell(r, 3).number_format = "d mmm yyyy hh:mm"

    # ----- Checks
    if with_checks:
        ws = wb.create_sheet("Checks")
        warnings = store.plan_warnings(conn, year)
        rows = [[WARNING_TITLE.get(w["code"], w["code"]), {"block": "Not allowed", "warn": "Warning",
                                                          "info": "Note"}.get(w["level"], w["level"]), w["message"]]
                for w in warnings["warnings"]]
        note = "" if warnings["total"] <= len(rows) else f" (first {len(rows)} of {warnings['total']})"
        put(ws, 1, [f"Rule checks of the saved plan{note}"], bold=True)
        table(ws, ["Check", "Severity", "Message"], rows, [32, 14, 110], start=3)

    # ----- About
    ws = wb.create_sheet("About", 0)
    put(ws, 1, ["About this file"])
    ws["A1"].font = Font(bold=True, size=14, color=ACCENT)
    lines = [
        f"Plan year {year}, status: {data['plan']['status']}. Exported {now:%d %b %Y %H:%M} UTC. "
        "A snapshot: it does not update.",
        "Summary: trips per month by place, and trips by event.",
        "Trips: one row per trip. Trips combined into a bigger trip are listed in the bigger one "
        "(column \"Also held at this trip\").",
        "People on trips: one row per person per trip. Hosts are visited and do not travel, "
        "so they have no days away.",
        "Per person: trips, days away and nights of people who travel, and trips per month.",
        "Changes: every manual change with its reason. Checks: rule warnings (people who see the whole plan only).",
        "Days are calendar days from the start to the end date; nights are days minus one.",
        "The plan uses working days and does not know public holidays.",
    ]
    if allowed is not None:
        lines.insert(1, "This file contains the trips of your area and the nationwide events, not the whole plan. "
                        "People from outside your area are named only on trips in your area.")
    if not include_cancelled:
        lines.append("Cancelled trips and trips combined into another trip are not included as rows.")
    for i, line in enumerate(lines, 3):
        put(ws, i, [line])
    ws.column_dimensions["A"].width = 130

    out = BytesIO()
    wb.save(out)
    stats = {"trips": len(live), "rows": len(trips), "people": len(per_person), "changes": len(data["changes"])}
    return out.getvalue(), stats


def export(conn: Connection, year: int, allowed: set[int] | None, actor: int | None, *,
           include_cancelled: bool, with_checks: bool, with_costs: bool = False) -> bytes:
    costs = event_costs = None
    if with_costs:  # the cost estimate is only for the roles that may see costs
        from . import cost_store

        report = cost_store.forecast_report(conn, year, allowed)
        costs = report["trip_costs"]
        event_costs = {e["event"]: e["cost"] for e in report["by_event"]}
    content, stats = build(conn, year, allowed, include_cancelled=include_cancelled, with_checks=with_checks,
                           costs=costs, event_costs=event_costs)
    audit(conn, actor, "plan.export", "plan_year", year, {**stats, "whole_plan": allowed is None, "costs": with_costs})
    return content

