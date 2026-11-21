"""Suggest a change: a person on a trip asks the planner to move it or to take them off."""

from datetime import timedelta

import psycopg
import pytest
from conftest import ADMIN_EMAIL, IDENTITY_KEY, TEST_DB, make_settings
from fastapi.testclient import TestClient
from orgfixture import build_workbook

from travel_planner.identity import key_hash
from travel_planner.main import create_app

ADMIN = {"X-Forwarded-Email": ADMIN_EMAIL}
SAM = {"X-Forwarded-Email": "sam@example.test"}


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
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("UPDATE travel.person SET sso_key_hash = %s WHERE full_name = 'Sam Stone'",
                     (key_hash("sam@example.test", IDENTITY_KEY),))
        conn.execute("INSERT INTO travel.user_role(person_id, role) SELECT id, 'viewer' FROM travel.person "
                     "WHERE full_name = 'Sam Stone'")
    assert c.post("/api/admin/plan/2027/status", headers=ADMIN, json={"status": "published"}).status_code == 200
    return c


def q(sql, *args):
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        cur = conn.execute(sql, args)
        return cur.fetchall() if cur.description else []


def sams_trip():
    return q("SELECT t.id, t.start_date, t.end_date FROM travel.trip t JOIN travel.trip_participant p ON p.trip_id = t.id "
             "JOIN travel.person x ON x.id = p.person_id WHERE x.full_name = 'Sam Stone' AND t.status = 'generated' "
             "ORDER BY t.start_date LIMIT 1")[0]


def test_suggest_see_and_withdraw(plan):
    tid, start, end = sams_trip()
    body = {"kind": "move", "message": "Exam week for my team", "proposed_start": str(start + timedelta(days=7))}
    r = plan.post(f"/api/my/trips/{tid}/requests", headers=SAM, json=body)
    assert r.status_code == 201, r.text
    mine = next(t for t in plan.get("/api/my/trips", headers=SAM).json()["trips"] if t["id"] == tid)
    req = mine["my_request"]
    assert req["status"] == "open" and req["proposed_start"] == str(start + timedelta(days=7))
    assert req["proposed_end"] == str(end + timedelta(days=7))                        # same length by default
    assert plan.post(f"/api/my/trips/{tid}/requests", headers=SAM, json=body).status_code == 409   # one open request
    assert plan.post(f"/api/my/requests/{req['id']}/withdraw", headers=SAM).status_code == 200
    assert plan.post(f"/api/my/requests/{req['id']}/withdraw", headers=SAM).status_code == 409
    assert plan.post(f"/api/my/trips/{tid}/requests", headers=SAM,
                     json={"kind": "cannot_attend", "message": "On leave"}).status_code == 201


def test_validation_and_privacy(plan):
    tid, start, _ = sams_trip()
    stranger = {"X-Forwarded-Email": "nobody@example.test"}
    assert plan.post(f"/api/my/trips/{tid}/requests", headers=stranger,
                     json={"kind": "other", "message": "hello"}).status_code == 403
    other = q("SELECT t.id FROM travel.trip t WHERE NOT EXISTS (SELECT 1 FROM travel.trip_participant p JOIN "
              "travel.person x ON x.id = p.person_id WHERE p.trip_id = t.id AND x.full_name = 'Sam Stone') LIMIT 1")[0][0]
    assert plan.post(f"/api/my/trips/{other}/requests", headers=SAM,
                     json={"kind": "other", "message": "hello"}).status_code == 404   # not on that trip
    assert plan.post(f"/api/my/trips/{tid}/requests", headers=SAM, json={"kind": "move", "message": "Please"}).status_code == 422
    assert plan.post(f"/api/my/trips/{tid}/requests", headers=SAM,
                     json={"kind": "move", "message": "Please", "proposed_start": "2030-01-05"}).status_code == 422
    assert plan.post(f"/api/my/trips/{tid}/requests", headers=SAM, json={"kind": "other", "message": "x"}).status_code == 422
    assert plan.post("/api/my/requests/99999/withdraw", headers=SAM).status_code == 404


def test_planner_decides(plan):
    tid, _, _ = sams_trip()
    plan.post(f"/api/my/trips/{tid}/requests", headers=SAM, json={"kind": "cannot_attend", "message": "On leave"})
    assert plan.get("/api/plan/2027/requests", headers=SAM).status_code == 403            # supervisors do not answer
    data = plan.get("/api/plan/2027/requests", headers=ADMIN).json()
    assert data["open"] == 1 and data["requests"][0]["requester"] == "Sam Stone" and data["requests"][0]["editable"]
    rid = data["requests"][0]["id"]
    assert plan.post(f"/api/plan/requests/{rid}/decide", headers=ADMIN, json={"decision": "declined"}).status_code == 422
    r = plan.post(f"/api/plan/requests/{rid}/decide", headers=ADMIN,
                  json={"decision": "declined", "note": "We need you there"})
    assert r.status_code == 200
    assert plan.post(f"/api/plan/requests/{rid}/decide", headers=ADMIN, json={"decision": "accepted"}).status_code == 409
    mine = next(t for t in plan.get("/api/my/trips", headers=SAM).json()["trips"] if t["id"] == tid)["my_request"]
    assert mine["status"] == "declined" and mine["decision_note"] == "We need you there"
    assert plan.get("/api/plan/2027/requests", headers=ADMIN).json()["open"] == 0
    done = plan.get("/api/plan/2027/requests?state=all", headers=ADMIN).json()
    assert done["requests"][0]["decided_by"] is None or isinstance(done["requests"][0]["decided_by"], str)
    # after a decision a new suggestion is possible
    assert plan.post(f"/api/my/trips/{tid}/requests", headers=SAM,
                     json={"kind": "other", "message": "Another idea"}).status_code == 201


def test_everyone_with_access_can_list_plan_years(plan):
    assert [y["year"] for y in plan.get("/api/plan-years", headers=SAM).json()] == [2027]
    assert plan.get("/api/plan-years", headers={"X-Forwarded-Email": "nobody@example.test"}).status_code == 403
