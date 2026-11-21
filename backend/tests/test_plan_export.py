from datetime import date, datetime, timedelta
from io import BytesIO

import psycopg
import pytest
from conftest import ADMIN_EMAIL, IDENTITY_KEY, TEST_DB, make_settings
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from orgfixture import build_workbook

from travel_planner.identity import key_hash
from travel_planner.main import create_app

ADMIN = {"X-Forwarded-Email": ADMIN_EMAIL}
RITA = {"X-Forwarded-Email": "rita.rivera@example.test"}
SAM = {"X-Forwarded-Email": "sam.stone@example.test"}
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def q(sql, *args):
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        cur = conn.execute(sql, args)
        return cur.fetchall() if cur.description else []


@pytest.fixture
def plan(tmp_path):
    settings = make_settings(bootstrap_admin_hashes=key_hash(ADMIN_EMAIL, IDENTITY_KEY))
    with TestClient(create_app(settings)) as c:
        path = tmp_path / "org.xlsx"
        build_workbook(path)
        with open(path, "rb") as fh:
            c.post("/api/admin/org-import", params={"effective_date": "2027-01-01", "commit": "true"},
                   headers=ADMIN, files={"file": ("org.xlsx", fh, "application/vnd.ms-excel")})
        users = {u["full_name"]: u["id"] for u in c.get("/api/admin/users", headers=ADMIN).json()["users"]}
        c.post("/api/admin/users/suggest-roles?commit=true", headers=ADMIN)
        c.post(f"/api/admin/users/{users['Rita Rivera']}/login", headers=ADMIN, json={"email": "rita.rivera@example.test"})
        c.post(f"/api/admin/users/{users['Sam Stone']}/login", headers=ADMIN, json={"email": "sam.stone@example.test"})
        c.post(f"/api/admin/users/{users['Sam Stone']}/roles", headers=ADMIN, json={"role": "viewer"})
        assert c.post("/api/admin/plan/2027/generate?commit=true", headers=ADMIN).status_code == 200
        yield c


def export(c, headers=ADMIN, **params):
    r = c.get("/api/plan/2027/export.xlsx", headers=headers, params=params)
    assert r.status_code == 200, r.text
    return load_workbook(BytesIO(r.content)), r


def rows(wb, sheet, start=2):
    ws = wb[sheet]
    return [[c.value for c in row] for row in ws.iter_rows(min_row=start) if any(c.value is not None for c in row)]


def header(wb, sheet, row=1):
    return [c.value for c in wb[sheet][row]]


def all_text(wb):
    return [c.value for ws in wb for row in ws.iter_rows() for c in row if isinstance(c.value, str)]


def test_the_file_and_its_sheets(plan):
    wb, r = export(plan)
    assert r.headers["content-type"].startswith(XLSX)
    assert 'filename="travel-plan-2027.xlsx"' in r.headers["content-disposition"]
    assert wb.sheetnames == ["About", "Summary", "Trips", "People on trips", "Per person", "Changes", "Checks"]
    assert wb.properties.title == "Travel plan 2027"
    assert any("snapshot" in t for t in all_text(wb))


def test_trips_match_the_plan(plan):
    wb, _ = export(plan)
    summary = plan.get("/api/plan/2027/summary", headers=ADMIN).json()
    trips = rows(wb, "Trips")
    assert len(trips) == summary["totals"]["trips"]
    h = header(wb, "Trips")
    col = {name: i for i, name in enumerate(h)}
    assert {"Trip ID", "Event", "Region", "Cluster", "Start", "End", "Days", "Nights", "Status", "Organizer"} <= set(h)
    for t in trips:
        start, end = t[col["Start"]], t[col["End"]]
        assert isinstance(start, datetime | date) and isinstance(end, datetime | date)          # real Excel dates
        assert t[col["Days"]] == (end - start).days + 1 and t[col["Nights"]] == (end - start).days
        assert start.weekday() < 5
        assert t[col["Status"]] in ("Proposed", "Confirmed", "Done")
    assert {t[col["Cluster"]] for t in trips} >= {"Alpha 1", "Alpha 2", "Beta 1"}
    meeting = next(t for t in trips if t[col["Event"]] == "Area Management Meeting" and t[col["Cluster"]] == "Alpha 1")
    assert meeting[col["Organizer"]] == "Amy Alvarez" and meeting[col["Travelers"]] >= 2
    assert any(t[col["Also held at this trip"]] for t in trips)                                 # combined trips are noted


def test_summary_totals_agree_with_the_trips(plan):
    wb, _ = export(plan)
    ws = wb["Summary"]
    total_row = next(r for r in ws.iter_rows(values_only=True) if r[0] == "Total")
    trips = len(rows(wb, "Trips"))
    assert total_row[14] == trips and sum(total_row[2:14]) == trips
    rows_ = list(ws.iter_rows(values_only=True))
    start = next(i for i, r in enumerate(rows_) if r[0] == "Event") + 1
    by_event = {r[0]: r[2] for r in rows_[start:] if r[0]}
    assert set(by_event) == {t[1] for t in rows(wb, "Trips")}
    assert sum(by_event.values()) == trips


def test_people_and_per_person_sheets(plan):
    wb, _ = export(plan)
    people = rows(wb, "People on trips")
    h = {n: i for i, n in enumerate(header(wb, "People on trips"))}
    hosts = [p for p in people if p[h["Role"]] == "Host"]
    assert hosts and all(p[h["Travels"]] == "No" and p[h["Days away"]] == 0 for p in hosts)
    travelers = [p for p in people if p[h["Travels"]] == "Yes"]
    assert all(p[h["Days away"]] >= 1 for p in travelers)
    per = {r[0]: r for r in rows(wb, "Per person")}
    ph = {n: i for i, n in enumerate(header(wb, "Per person"))}
    amy = per["Amy Alvarez"]
    mine = [p for p in travelers if p[h["Person"]] == "Amy Alvarez"]
    assert amy[ph["Trips"]] == len(mine) and amy[ph["Days away"]] == sum(p[h["Days away"]] for p in mine)
    assert sum(amy[ph["Jan"]:ph["Dec"] + 1]) == amy[ph["Trips"]]
    assert amy[ph["Most trips in a month"]] == max(amy[ph["Jan"]:ph["Dec"] + 1])


def test_changes_and_reasons_are_in_the_file(plan):
    unit = q("SELECT id FROM travel.org_unit WHERE name = 'Alpha 1'")[0][0]
    trip = plan.get(f"/api/plan/2027/trips?unit_id={unit}", headers=ADMIN).json()[0]
    start = date.fromisoformat(trip["start_date"]) + timedelta(days=14)
    end = date.fromisoformat(trip["end_date"]) + timedelta(days=14)
    ok = plan.post(f"/api/plan/trips/{trip['id']}/edit?commit=true", headers=ADMIN, json={
        "start_date": str(start), "end_date": str(end), "reason": "Training clashes", "category": "capacity",
        "acknowledge": True})
    assert ok.status_code == 200
    wb, _ = export(plan)
    h = {n: i for i, n in enumerate(header(wb, "Trips"))}
    row = next(r for r in rows(wb, "Trips") if r[h["Trip ID"]] == trip["id"])
    assert row[h["Moved"]] == "Yes" and row[h["Changed by hand"]] == "Yes" and row[h["Last reason"]] == "Training clashes"
    assert row[h["Start by the rules"]].date() == date.fromisoformat(trip["start_date"])
    changes = rows(wb, "Changes")
    assert len(changes) == 1 and changes[0][0] == trip["id"]
    assert changes[0][3:] == ["Administrator", "Moved", "Capacity", "Training clashes"]


def test_cancelled_and_combined_trips_only_on_request(plan):
    trip = plan.get("/api/plan/2027/trips?month=1", headers=ADMIN).json()[0]
    plan.post(f"/api/plan/trips/{trip['id']}/cancel?commit=true", headers=ADMIN,
              json={"reason": "Not needed any more", "acknowledge": True})
    plain, _ = export(plan)
    full, _ = export(plan, include="cancelled")
    h = {n: i for i, n in enumerate(header(full, "Trips"))}
    statuses = [r[h["Status"]] for r in rows(full, "Trips")]
    assert len(rows(full, "Trips")) > len(rows(plain, "Trips"))
    assert "Cancelled" in statuses and "Combined into another trip" in statuses
    assert "Cancelled" not in [r[h["Status"]] for r in rows(plain, "Trips")]
    reason_col = h["Last reason"]
    assert any(r[reason_col] == "Not needed any more" for r in rows(full, "Trips"))
    assert not any("Cancelled trips and trips combined" in t for t in all_text(full))
    assert any("Cancelled trips and trips combined" in t for t in all_text(plain))


def test_text_is_never_turned_into_a_formula(plan):
    trip = plan.get("/api/plan/2027/trips?month=1", headers=ADMIN).json()[0]
    evil = '=HYPERLINK("http://example.invalid","click")'
    assert plan.post(f"/api/plan/trips/{trip['id']}/edit?commit=true", headers=ADMIN, json={
        "notes": evil, "reason": '=1+1 injected reason', "acknowledge": True}).status_code == 200
    wb, _ = export(plan)
    found = [c for ws in wb for row in ws.iter_rows() for c in row if c.value in (evil, "=1+1 injected reason")]
    assert len(found) >= 2 and all(c.data_type == "s" for c in found)
    assert not [c for ws in wb for row in ws.iter_rows() for c in row if c.data_type == "f"]


def test_a_regional_planner_gets_only_their_area(plan):
    wb, _ = export(plan, headers=RITA)
    assert "Checks" not in wb.sheetnames
    h = {n: i for i, n in enumerate(header(wb, "Trips"))}
    trips = rows(wb, "Trips")
    assert trips and {t[h["Cluster"]] for t in trips} <= {"Alpha 1", "Alpha 2", "", None}
    assert {t[h["Region"]] for t in trips} <= {"North", "Nationwide"}
    text = " ".join(all_text(wb))
    assert "Bob Beta" not in text and "Beta 1" not in text and "Ramon Reyes" not in text
    assert any("your area" in t for t in all_text(wb))
    people = {r[5] for r in rows(wb, "People on trips")}
    assert "Amy Alvarez" in people and "Ramon Reyes" not in people                        # a nationwide trip lists only your people
    assert {r[0] for r in rows(wb, "Per person")} <= {"Amy Alvarez", "Alan Abad", "Rita Rivera", "Sam Stone",
                                                      "Sue Smith", "Digi Mentor"}
    whole, _ = export(plan)
    assert len(rows(wb, "Trips")) < len(rows(whole, "Trips"))
    audit = q("SELECT details->>'whole_plan' FROM travel.audit_log WHERE action = 'plan.export' ORDER BY id")
    assert audit == [("false",), ("true",)]


def test_no_contact_data_in_the_file(plan):
    wb, _ = export(plan)
    assert not [t for t in all_text(wb) if "@" in t or "sso" in t.lower()]


def test_who_may_export(plan):
    assert plan.get("/api/plan/2027/export.xlsx").status_code == 401
    assert plan.get("/api/plan/2027/export.xlsx", headers=SAM).status_code == 403            # a viewer has no plan access
    assert plan.get("/api/plan/2027/export.xlsx", headers={"X-Forwarded-Email": "nobody@example.test"}).status_code == 403
    assert plan.get("/api/plan/2030/export.xlsx", headers=ADMIN).status_code == 404
    assert plan.get("/api/plan/2027/export.xlsx", headers=ADMIN, params={"include": "everything"}).status_code == 422


def test_the_cost_estimate_is_in_the_file_only_for_roles_that_may_see_costs(plan):
    from travel_planner.cost_store import forecast_report  # noqa: F401  (documents where the numbers come from)

    wb, _ = export(plan)
    h = {n: i for i, n in enumerate(header(wb, "Trips"))}
    assert "Estimated cost (PHP)" in h
    trips = rows(wb, "Trips")
    cost = sum(t[h["Estimated cost (PHP)"]] or 0 for t in trips)
    f = plan.get("/api/cost/2027/forecast", headers=ADMIN).json()["totals"]["cost"]
    assert abs(cost - f) < 1                                                    # the file agrees with the Costs page
    ws = wb["Summary"]
    start = next(i for i, r in enumerate(ws.iter_rows(values_only=True)) if r[0] == "Event") + 1
    events = [r for r in list(ws.iter_rows(values_only=True))[start:] if r[0]]
    assert abs(sum(r[5] for r in events) - f) < len(events)                     # rounded per event
    # a regional planner sees the costs of their own region
    wb_r, _ = export(plan, headers=RITA)
    assert "Estimated cost (PHP)" in header(wb_r, "Trips")
    # an area planner has plan access, but costs are not for them
    users = {u["full_name"]: u["id"] for u in plan.get("/api/admin/users", headers=ADMIN).json()["users"]}
    plan.post(f"/api/admin/users/{users['Amy Alvarez']}/login", headers=ADMIN, json={"email": "amy.alvarez@example.test"})
    amy = {"X-Forwarded-Email": "amy.alvarez@example.test"}
    wb_a, _ = export(plan, headers=amy)
    assert "Estimated cost (PHP)" not in header(wb_a, "Trips")
    assert not any("Estimate (PHP)" in str(c) for c in all_text(wb_a))
    assert q("SELECT bool_or((details->>'costs')::boolean) FROM travel.audit_log WHERE action = 'plan.export'")[0][0]
