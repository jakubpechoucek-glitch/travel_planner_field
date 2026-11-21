from datetime import date, timedelta

import psycopg
import pytest
from conftest import ADMIN_EMAIL, IDENTITY_KEY, TEST_DB, make_settings
from fastapi.testclient import TestClient
from orgfixture import build_workbook

from travel_planner import trip_edit
from travel_planner.identity import key_hash
from travel_planner.main import create_app

ADMIN = {"X-Forwarded-Email": ADMIN_EMAIL}


@pytest.fixture
def c():
    settings = make_settings(bootstrap_admin_hashes=key_hash(ADMIN_EMAIL, IDENTITY_KEY))
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def plan(c, tmp_path):
    path = tmp_path / "org.xlsx"
    build_workbook(path)
    with open(path, "rb") as fh:
        c.post("/api/admin/org-import", params={"effective_date": "2027-01-01", "commit": "true"}, headers=ADMIN,
               files={"file": ("org.xlsx", fh, "application/vnd.ms-excel")})
    assert c.post("/api/admin/plan/2027/generate?commit=true", headers=ADMIN).status_code == 200
    return c


def q(sql, *args):
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        cur = conn.execute(sql, args)
        return cur.fetchall() if cur.description else []


def trip_of(code, cluster, status="generated"):
    return q("SELECT t.id FROM travel.trip t JOIN travel.event_type e ON e.id = t.event_type_id "
             "JOIN travel.org_unit u ON u.id = t.visited_org_unit_id WHERE e.code = %s AND u.name = %s "
             "AND t.status = %s ORDER BY t.start_date, t.id LIMIT 1", code, cluster, status)[0][0]


def post(c, tid, action, headers=ADMIN, commit=False, **body):
    body.setdefault("reason", "Customer request")
    return c.post(f"/api/plan/trips/{tid}/{action}?commit={'true' if commit else 'false'}", headers=headers, json=body)


def user(email, role, scope_name=None):
    """A linked person with a role, optionally scoped to an org unit."""
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        pid = conn.execute("INSERT INTO travel.person(full_name, sso_key_hash) VALUES (%s, %s) RETURNING id",
                           (f"{role} {email}", key_hash(email, IDENTITY_KEY))).fetchone()[0]
        scope = None
        if scope_name:
            scope = conn.execute("SELECT id FROM travel.org_unit WHERE name = %s", (scope_name,)).fetchone()[0]
        conn.execute("INSERT INTO travel.user_role(person_id, role, scope_org_unit_id) VALUES (%s,%s,%s)",
                     (pid, role, scope))
    return {"X-Forwarded-Email": email}


def test_a_reason_is_mandatory(plan):
    tid = trip_of("AM-FSV-VISIT", "Alpha 1")
    assert post(plan, tid, "edit", commit=True, notes="x", reason="").status_code == 422
    assert post(plan, tid, "edit", commit=True, notes="x", reason="ok").status_code == 422        # too short
    body = {"notes": "Changed note"}
    r = plan.post(f"/api/plan/trips/{tid}/edit?commit=true", headers=ADMIN, json=body)
    assert r.status_code == 422 and r.json()["detail"].startswith("Please check the form")


def test_preview_saves_nothing(plan):
    tid = trip_of("AM-FSV-VISIT", "Alpha 1")
    before = q("SELECT start_date, updated_at FROM travel.trip WHERE id = %s", tid)[0]
    r = post(plan, tid, "edit", start_date=str(before[0] + timedelta(days=7)),
             end_date=str(before[0] + timedelta(days=8)))
    assert r.status_code == 200 and r.json()["committed"] is False
    assert q("SELECT start_date, updated_at FROM travel.trip WHERE id = %s", tid)[0] == before
    assert q("SELECT count(*) FROM travel.trip_change WHERE trip_id = %s AND change_type <> 'generated'", tid)[0][0] == 0


def test_move_keeps_history_and_generated_dates(plan):
    tid = trip_of("AM-FSV-VISIT", "Alpha 1")
    start, end = q("SELECT start_date, end_date FROM travel.trip WHERE id = %s", tid)[0]
    r = post(plan, tid, "edit", commit=True, acknowledge=True, category="business_request",
             start_date=str(start + timedelta(days=14)), end_date=str(end + timedelta(days=14)))
    assert r.status_code == 200, r.text
    trip = r.json()["trip"]
    assert trip["start_date"] == str(start + timedelta(days=14))
    assert trip["generated_start_date"] == str(start)               # the rule-based date is kept
    hist = plan.get(f"/api/plan/trips/{tid}/history", headers=ADMIN).json()
    assert hist[0]["change_type"] == "moved" and hist[0]["reason"] == "Customer request"
    assert hist[0]["category"] == "business_request" and hist[0]["before_data"]["start"] == str(start)
    # resizing is recorded as such
    r2 = post(plan, tid, "edit", commit=True, acknowledge=True, end_date=str(end + timedelta(days=15)),
              expected_updated_at=trip["updated_at"])
    assert r2.status_code == 200
    assert plan.get(f"/api/plan/trips/{tid}/history", headers=ADMIN).json()[0]["change_type"] == "resized"


def test_dates_must_make_sense(plan):
    tid = trip_of("AM-FSV-VISIT", "Alpha 1")
    assert post(plan, tid, "edit", start_date="2027-05-10", end_date="2027-05-09").status_code == 422
    assert post(plan, tid, "edit", start_date="2028-01-04", end_date="2028-01-04").status_code == 422
    assert post(plan, tid, "edit", reason="Nothing to change").status_code == 422


def test_warnings_need_acknowledgement(plan):
    tid = trip_of("AM-FSV-MEET", "Alpha 1")
    r = post(plan, tid, "edit", start_date="2027-04-13", end_date="2027-04-13")     # the conference month
    out = r.json()
    assert r.status_code == 200 and out["requires_acknowledgement"] and not out["blocked"]
    assert any(w["code"] == "blackout" for w in out["new_warnings"])
    refused = post(plan, tid, "edit", commit=True, start_date="2027-04-13", end_date="2027-04-13")
    assert refused.status_code == 409
    ok = post(plan, tid, "edit", commit=True, acknowledge=True, start_date="2027-04-13", end_date="2027-04-13")
    assert ok.status_code == 200
    acks = q("SELECT warning_code, reason FROM travel.warning_ack WHERE trip_id = %s", tid)
    assert ("blackout", "Customer request") in acks
    # the plan-wide check now lists it too
    w = plan.get("/api/plan/2027/warnings", headers=ADMIN).json()
    assert w["counts"].get("blackout", 0) >= 1


def test_block_severity_refuses_the_change(plan):
    q("UPDATE travel.blackout_period SET severity = 'block' WHERE name LIKE 'Collection Conference%%'")
    tid = trip_of("AM-FSV-MEET", "Alpha 1")
    r = post(plan, tid, "edit", commit=True, acknowledge=True, start_date="2027-04-13", end_date="2027-04-13")
    assert r.status_code == 422 and "not allowed" in r.json()["detail"]
    assert q("SELECT start_date FROM travel.trip WHERE id = %s", tid)[0][0] != date(2027, 4, 13)


def test_stale_token_is_refused(plan):
    tid = trip_of("AM-FSV-VISIT", "Alpha 1")
    token = plan.get(f"/api/plan/trips/{tid}", headers=ADMIN).json()["updated_at"]
    assert post(plan, tid, "edit", commit=True, acknowledge=True, notes="First", expected_updated_at=token).status_code == 200
    again = post(plan, tid, "edit", commit=True, acknowledge=True, notes="Second", expected_updated_at=token)
    assert again.status_code == 409 and "Someone else" in again.json()["detail"]


def test_cancelling_shows_the_effect_on_the_quota(plan):
    tid = trip_of("AM-FSV-MEET", "Alpha 2")
    r = post(plan, tid, "cancel", reason="Area closed for the week", category="capacity")
    assert any(w["code"] == "quota_short" and "Area Management Meeting, Alpha 2" in w["message"]
               for w in r.json()["new_warnings"])
    assert post(plan, tid, "cancel", commit=True, reason="Area closed for the week").status_code == 409  # not acknowledged
    done = post(plan, tid, "cancel", commit=True, acknowledge=True, reason="Area closed for the week", category="capacity")
    assert done.status_code == 200 and done.json()["trip"]["status"] == "cancelled"
    assert q("SELECT cancel_reason FROM travel.trip WHERE id = %s", tid)[0][0] == "Area closed for the week"
    assert q("SELECT change_type, category FROM travel.trip_change WHERE trip_id = %s AND change_type = 'cancelled'",
             tid) == [("cancelled", "capacity")]
    assert post(plan, tid, "edit", commit=True, acknowledge=True, notes="x").status_code == 409   # a cancelled trip is final


def test_confirm_and_finish(plan, monkeypatch):
    tid = trip_of("AM-FSV-VISIT", "Alpha 1")
    ok = plan.post(f"/api/plan/trips/{tid}/status", headers=ADMIN, json={"status": "planned"})
    assert ok.status_code == 200 and ok.json()["trip"]["status"] == "planned"
    assert q("SELECT reason FROM travel.trip_change WHERE trip_id = %s AND change_type = 'status'", tid) == [
        ("Confirmed by planner.",)]
    early = plan.post(f"/api/plan/trips/{tid}/status", headers=ADMIN, json={"status": "completed"})
    assert early.status_code == 409 and "started" in early.json()["detail"]
    monkeypatch.setattr(trip_edit, "_today", lambda: date(2027, 12, 31))
    done = plan.post(f"/api/plan/trips/{tid}/status", headers=ADMIN, json={"status": "completed", "note": "All good"})
    assert done.status_code == 200 and done.json()["trip"]["status"] == "completed"
    assert plan.post(f"/api/plan/trips/{tid}/status", headers=ADMIN, json={"status": "planned"}).status_code == 409
    assert post(plan, tid, "edit", commit=True, acknowledge=True, notes="x").status_code == 409


def test_regeneration_keeps_confirmed_and_edited_trips(plan):
    confirmed = trip_of("AM-FSV-VISIT", "Alpha 1")
    edited = trip_of("AM-FSV-VISIT", "Alpha 2")
    plan.post(f"/api/plan/trips/{confirmed}/status", headers=ADMIN, json={"status": "planned"})
    post(plan, edited, "edit", commit=True, acknowledge=True, notes="Bring the new forms")
    report = plan.post("/api/admin/plan/2027/generate?commit=true", headers=ADMIN).json()
    assert report["trips_kept"] >= 2
    assert q("SELECT count(*) FROM travel.trip WHERE id = ANY(%s)", [confirmed, edited])[0][0] == 2


def test_adding_a_trip_by_hand(plan):
    cluster = q("SELECT id FROM travel.org_unit WHERE name = 'Alpha 1'")[0][0]
    event = q("SELECT id FROM travel.event_type WHERE code = 'AM-FSV-MEET'")[0][0]
    body = {"event_type_id": event, "unit_id": cluster, "start_date": "2027-05-04", "end_date": "2027-05-04",
            "reason": "Extra meeting after the audit", "category": "business_request"}
    preview = plan.post("/api/plan/2027/trips?commit=false", headers=ADMIN, json=body).json()
    assert preview["requires_acknowledgement"]                                        # a seventh meeting: quota is 6
    assert any(w["code"] == "quota_over" for w in preview["new_warnings"])
    assert q("SELECT count(*) FROM travel.trip WHERE source = 'manual'")[0][0] == 0
    assert plan.post("/api/plan/2027/trips?commit=true", headers=ADMIN, json=body).status_code == 409
    r = plan.post("/api/plan/2027/trips?commit=true", headers=ADMIN, json={**body, "acknowledge": True})
    assert r.status_code == 200
    trip = r.json()["trip"]
    assert trip["source"] == "manual" and trip["status"] == "planned" and trip["participants"]
    assert any(p["role"] == "organizer" for p in trip["participants"])               # defaults came from the catalog
    assert q("SELECT change_type, reason FROM travel.trip_change WHERE trip_id = %s", trip["id"]) == [
        ("created", "Extra meeting after the audit")]
    assert plan.post("/api/plan/2027/trips?commit=true", headers=ADMIN,
                     json={**body, "reason": "", "acknowledge": True}).status_code == 422


def test_changing_participants(plan):
    tid = trip_of("AM-FSV-MEET", "Alpha 1")
    detail = plan.get(f"/api/plan/trips/{tid}", headers=ADMIN).json()
    fsv = next(p for p in detail["participants"] if p["position"] == "Field Supervisor")
    others = plan.get("/api/plan/people?q=Rita", headers=ADMIN).json()
    assert others and others[0]["name"] == "Rita Rivera"
    r = post(plan, tid, "edit", commit=True, acknowledge=True, reason="Supervisor on leave",
             remove_participants=[fsv["person_id"]], add_participants=[{"person_id": others[0]["person_id"]}])
    assert r.status_code == 200
    names = {p["name"] for p in r.json()["trip"]["participants"]}
    assert "Rita Rivera" in names and fsv["name"] not in names
    assert plan.get(f"/api/plan/trips/{tid}/history", headers=ADMIN).json()[0]["change_type"] == "reassigned"
    assert post(plan, tid, "edit", remove_participants=[999999]).status_code == 422


def test_closed_year_is_read_only(plan):
    tid = trip_of("AM-FSV-VISIT", "Alpha 1")
    q("UPDATE travel.plan_year SET status = 'closed' WHERE year = 2027")
    assert post(plan, tid, "edit", commit=True, acknowledge=True, notes="x").status_code == 409
    assert post(plan, tid, "cancel", commit=True, acknowledge=True).status_code == 409


def test_a_change_after_publication_is_marked(plan):
    q("UPDATE travel.plan_year SET status = 'published' WHERE year = 2027")
    tid = trip_of("AM-FSV-VISIT", "Alpha 1")
    assert post(plan, tid, "edit", commit=True, acknowledge=True, notes="Late change").status_code == 200
    hist = plan.get(f"/api/plan/trips/{tid}/history", headers=ADMIN).json()
    assert hist[0]["after_data"]["after_publication"] is True


def test_regional_planner_sees_and_changes_only_the_region(plan):
    regional = user("rita@example.test", "regional_planner", "North")
    summary = plan.get("/api/plan/2027/summary", headers=regional).json()
    labels = {r["label"] for reg in summary["regions"] for r in reg["rows"]}
    assert labels == {"Alpha 1", "Alpha 2", "Region and local offices"}
    mine, theirs = trip_of("AM-FSV-VISIT", "Alpha 1"), trip_of("AM-FSV-VISIT", "Beta 1")
    assert plan.get(f"/api/plan/trips/{mine}", headers=regional).json()["editable"] is True
    assert plan.get(f"/api/plan/trips/{theirs}", headers=regional).status_code == 404
    assert post(plan, theirs, "edit", headers=regional, commit=True, acknowledge=True, notes="x").status_code == 404
    assert post(plan, mine, "edit", headers=regional, commit=True, acknowledge=True, notes="Mine").status_code == 200
    # adding a trip in another region is refused
    beta = q("SELECT id FROM travel.org_unit WHERE name = 'Beta 1'")[0][0]
    event = q("SELECT id FROM travel.event_type WHERE code = 'AM-FSV-VISIT'")[0][0]
    r = plan.post("/api/plan/2027/trips?commit=true", headers=regional, json={
        "event_type_id": event, "unit_id": beta, "start_date": "2027-05-04", "end_date": "2027-05-04",
        "reason": "Not my region", "acknowledge": True})
    assert r.status_code == 403
    # nationwide trips are visible but not editable by a regional planner
    conf = q("SELECT t.id FROM travel.trip t JOIN travel.event_type e ON e.id = t.event_type_id WHERE e.code = 'CONF'")[0][0]
    assert plan.get(f"/api/plan/trips/{conf}", headers=regional).json()["editable"] is False
    assert post(plan, conf, "edit", headers=regional, commit=True, acknowledge=True, notes="x").status_code == 403
    # plan-wide actions stay with administrators and national planners
    assert plan.post("/api/admin/plan/2027/generate", headers=regional).status_code == 403
    assert plan.get("/api/plan/2027/warnings", headers=regional).status_code == 403
    places = {p["name"] for p in plan.get("/api/plan/places", headers=regional).json()}
    assert "Beta 1" not in places and "Alpha 1" in places and "Nationwide" not in places
    assert {p["name"] for p in plan.get("/api/plan/people", headers=regional).json()} <= {
        "Rita Rivera", "Amy Alvarez", "Alan Abad", "Sam Stone", "Sue Smith", "Digi Mentor"}


def test_area_planner_is_limited_to_the_cluster(plan):
    area = user("amy@example.test", "area_planner", "Alpha 2")
    labels = {r["label"] for reg in plan.get("/api/plan/2027/summary", headers=area).json()["regions"]
              for r in reg["rows"]}
    assert labels == {"Alpha 2"}
    assert plan.get(f"/api/plan/trips/{trip_of('AM-FSV-VISIT', 'Alpha 1')}", headers=area).status_code == 404
    assert post(plan, trip_of("AM-FSV-VISIT", "Alpha 2"), "edit", headers=area, commit=True, acknowledge=True,
                notes="ok").status_code == 200


def test_people_without_a_planning_role_cannot_use_the_plan(plan):
    viewer = user("vera@example.test", "viewer")
    tid = trip_of("AM-FSV-VISIT", "Alpha 1")
    assert plan.get("/api/plan/2027/summary", headers=viewer).status_code == 403
    assert post(plan, tid, "edit", headers=viewer, commit=True, notes="x").status_code == 403
    assert plan.get(f"/api/plan/trips/{tid}/history", headers=viewer).status_code == 403
    assert post(plan, tid, "edit", headers={"X-Forwarded-Email": "nobody@example.test"}, notes="x").status_code == 403
