from datetime import UTC, date, datetime, timedelta

import psycopg
import pytest
from conftest import ADMIN_EMAIL, IDENTITY_KEY, TEST_DB, make_settings
from fastapi.testclient import TestClient
from orgfixture import build_workbook

from travel_planner.identity import key_hash
from travel_planner.main import create_app
from travel_planner.my_plan import ics_for

ADMIN = {"X-Forwarded-Email": ADMIN_EMAIL}
SAM = {"X-Forwarded-Email": "sam.stone@example.test"}
AMY = {"X-Forwarded-Email": "amy.alvarez@example.test"}


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
        c.post(f"/api/admin/users/{users['Sam Stone']}/login", headers=ADMIN, json={"email": "sam.stone@example.test"})
        c.post(f"/api/admin/users/{users['Sam Stone']}/roles", headers=ADMIN, json={"role": "viewer"})
        c.post("/api/admin/users/suggest-roles?commit=true", headers=ADMIN)
        c.post(f"/api/admin/users/{users['Amy Alvarez']}/login", headers=ADMIN, json={"email": "amy.alvarez@example.test"})
        assert c.post("/api/admin/plan/2027/generate?commit=true", headers=ADMIN).status_code == 200
        yield c


def publish(c):
    r = c.post("/api/admin/plan/2027/status", headers=ADMIN, json={"status": "published"})
    assert r.status_code == 200, r.text


def test_publication_lifecycle_and_permissions(plan):
    assert plan.get("/api/plan/2027/summary", headers=ADMIN).json()["status"] == "review"
    assert plan.post("/api/admin/plan/2027/status", headers=AMY, json={"status": "published"}).status_code == 403
    assert plan.post("/api/admin/plan/2027/status", headers=ADMIN, json={"status": "closed"}).status_code == 409
    publish(plan)
    s = plan.get("/api/plan/2027/summary", headers=ADMIN).json()
    assert s["status"] == "published" and s["published_at"]
    assert plan.post("/api/admin/plan/2027/generate", headers=ADMIN).status_code == 409        # no regeneration any more
    assert plan.post("/api/admin/plan/2027/status", headers=ADMIN, json={"status": "review"}).status_code == 200
    publish(plan)
    assert plan.post("/api/admin/plan/2027/status", headers=ADMIN, json={"status": "closed"}).status_code == 200
    assert plan.post("/api/admin/plan/2027/status", headers=ADMIN, json={"status": "published"}).status_code == 409
    assert {r[0] for r in q("SELECT action FROM travel.audit_log WHERE action = 'plan.status'")} == {"plan.status"}
    assert plan.post("/api/admin/plan/2027/status", headers=ADMIN, json={"status": "bogus"}).status_code == 422


def test_an_empty_plan_cannot_be_published(tmp_path):
    with TestClient(create_app(make_settings(bootstrap_admin_hashes=key_hash(ADMIN_EMAIL, IDENTITY_KEY)))) as c:
        r = c.post("/api/admin/plan/2027/status", headers=ADMIN, json={"status": "published"})
        assert r.status_code == 409 and "Generate the plan first" in r.json()["detail"]


def test_supervisors_see_nothing_before_publication(plan):
    mine = plan.get("/api/my/trips", headers=SAM).json()
    assert mine["linked"] and mine["published"] is False and mine["trips"] == [] and mine["plan_status"] == "review"
    assert plan.get("/api/my/trips.ics", headers=SAM).status_code == 404
    # planners see their own trips while the plan is being reviewed
    amy = plan.get("/api/my/trips", headers=AMY).json()
    assert amy["published"] is True and amy["trips"]


def test_a_supervisor_sees_only_their_own_trips(plan):
    publish(plan)
    mine = plan.get("/api/my/trips", headers=SAM).json()
    trips = mine["trips"]
    assert mine["published"] and trips and mine["year"] == 2027
    # nothing from other clusters: his own cluster, local office or region (skip-level sessions), or nationwide events
    assert all("Alpha 1" in t["title"] or t["place"] in (None, "Alpha 1", "Port One", "North") for t in trips)
    assert all(any(p["name"] == "Sam Stone" for p in t["participants"]) for t in trips)
    roles = {t["event"]: t["my_role"] for t in trips}
    assert roles["Area Visit"] == "traveler" or roles["Area Visit"] == "host"
    visit = next(t for t in trips if t["event"] == "Area Visit")
    assert visit["my_travels"] is False                                                     # the visited team hosts
    meeting = next(t for t in trips if t["event"] == "Area Management Meeting")
    assert meeting["my_travels"] is True and meeting["organizer"] == "Amy Alvarez"
    assert not [t for t in trips if t["cancel_reason"] and t["cancel_reason"].startswith("Combined")]
    assert [t["start_date"] for t in trips] == sorted(t["start_date"] for t in trips)
    # someone else's trips are not visible to Sam, and the other cluster's people are not in his list
    names = {p["name"] for t in trips for p in t["participants"]}
    assert "Bob Beta" not in names and "Sue Smith" not in names


def test_changes_and_cancellations_show_with_their_reasons(plan):
    publish(plan)
    first = plan.get("/api/my/trips", headers=SAM).json()["trips"]
    meeting = next(t for t in first if t["event"] == "Area Management Meeting" and not t["combined"])
    start = date.fromisoformat(meeting["start_date"])
    ok = plan.post(f"/api/plan/trips/{meeting['id']}/edit?commit=true", headers=ADMIN, json={
        "start_date": str(start + timedelta(days=7)), "end_date": str(start + timedelta(days=7)),
        "reason": "Office closed on the original day", "category": "capacity", "acknowledge": True})
    assert ok.status_code == 200
    visit = next(t for t in first if t["event"] == "Area Visit")
    assert plan.post(f"/api/plan/trips/{visit['id']}/cancel?commit=true", headers=ADMIN, json={
        "reason": "Visit moved to next quarter", "acknowledge": True}).status_code == 200
    after = {t["id"]: t for t in plan.get("/api/my/trips", headers=SAM).json()["trips"]}
    moved = after[meeting["id"]]
    assert moved["last_change"]["reason"] == "Office closed on the original day"
    assert moved["generated_start_date"] == meeting["start_date"] != moved["start_date"]
    assert after[visit["id"]]["status"] == "cancelled" and after[visit["id"]]["cancel_reason"] == "Visit moved to next quarter"


def test_the_calendar_export(plan):
    publish(plan)
    r = plan.get("/api/my/trips.ics", headers=SAM)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    assert "my-travel-2027.ics" in r.headers["content-disposition"]
    body = r.text
    trips = plan.get("/api/my/trips", headers=SAM).json()["trips"]
    assert body.startswith("BEGIN:VCALENDAR\r\n") and body.endswith("END:VCALENDAR\r\n")
    assert body.count("BEGIN:VEVENT") == len([t for t in trips if t["status"] != "cancelled"])
    t = trips[0]
    end = date.fromisoformat(t["end_date"]) + timedelta(days=1)
    assert f"DTSTART;VALUE=DATE:{t['start_date'].replace('-', '')}" in body and f"DTEND;VALUE=DATE:{end:%Y%m%d}" in body
    assert all(len(line.encode()) <= 75 for line in body.split("\r\n"))
    assert "Bob Beta" not in body                      # nobody else's name or trips


def test_ics_escaping_and_folding():
    trip = {"id": 7, "title": "Meeting, with; special\\chars", "status": "planned", "event": "Area Meeting",
            "place": "Alpha 1, North", "start_date": "2027-03-02", "end_date": "2027-03-03", "my_role": "traveler",
            "notes": "Line one\nLine two " + "x" * 200}
    cancelled = {**trip, "id": 8, "status": "cancelled"}
    text = ics_for([trip, cancelled], 2027, now=datetime(2026, 11, 21, 12, 0, tzinfo=UTC))
    assert text.count("BEGIN:VEVENT") == 1
    assert r"SUMMARY:Meeting\, with\; special\\chars" in text.replace("\r\n ", "")
    assert "LOCATION:Alpha 1\\, North" in text and "DTSTAMP:20261121T120000Z" in text
    assert "DTEND;VALUE=DATE:20270304" in text and "\\n" in text.replace("\r\n ", "")
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    host = ics_for([{**trip, "my_role": "host"}], 2027)
    assert "TRANSP:TRANSPARENT" in host and "You host this visit." in host


def test_access_rules(plan):
    publish(plan)
    assert plan.get("/api/my/trips").status_code == 401
    assert plan.get("/api/my/trips", headers={"X-Forwarded-Email": "nobody@example.test"}).status_code == 403
    # an administrator without a person record has no trips of their own
    me = plan.get("/api/my/trips", headers=ADMIN).json()
    assert me["linked"] is False and me["trips"] == []
    other_year = plan.get("/api/my/trips?year=2030", headers=SAM).json()
    assert other_year["published"] is False and other_year["trips"] == []
    q("UPDATE travel.person SET active = false WHERE full_name = 'Sam Stone'")
    assert plan.get("/api/my/trips", headers=SAM).status_code == 403
