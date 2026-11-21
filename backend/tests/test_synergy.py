"""Synergy suggestions: two trips to the same place a few days apart."""

from datetime import date, timedelta

import psycopg
import pytest
from conftest import ADMIN_EMAIL, IDENTITY_KEY, TEST_DB, make_settings
from fastapi.testclient import TestClient
from orgfixture import build_workbook
from psycopg.rows import dict_row

from travel_planner import synergy
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


def db():
    return psycopg.connect(TEST_DB, options="-c search_path=travel,public", row_factory=dict_row)


def test_suggestions_are_found_ranked_and_dismissable(plan):
    # make a clean case: two trips of one place, 6 days apart, with a person who travels on both
    with db() as conn:
        a = conn.execute("SELECT t.id, t.location_id, t.end_date, t.start_date FROM trip t JOIN trip_participant p "
                         "ON p.trip_id = t.id AND p.travels WHERE t.status = 'generated' AND t.location_id IS NOT NULL "
                         "ORDER BY t.start_date, t.id LIMIT 1").fetchone()
        person = conn.execute("SELECT person_id FROM trip_participant WHERE trip_id = %s AND travels LIMIT 1",
                              (a["id"],)).fetchone()["person_id"]
        b = conn.execute(
            "SELECT t.id FROM trip t WHERE t.id <> %s AND t.status = 'generated' AND t.location_id = %s LIMIT 1",
            (a["id"], a["location_id"])).fetchone()
        assert b, "the fixture should have two trips to one place"
        conn.execute("UPDATE trip SET start_date = %s, end_date = %s WHERE id = %s",
                     (a["end_date"] + timedelta(days=6), a["end_date"] + timedelta(days=6), b["id"]))
        conn.execute("INSERT INTO trip_participant(trip_id, person_id, role, travels) VALUES (%s,%s,'traveler',true) "
                     "ON CONFLICT DO NOTHING", (b["id"], person))
        conn.commit()
    r = plan.get("/api/plan/2027/synergies?within_days=10", headers=ADMIN)
    assert r.status_code == 200, r.text
    data = r.json()
    mine = next(s for s in data["suggestions"] if {s["first"]["id"], s["second"]["id"]} == {a["id"], b["id"]})
    assert mine["gap_days"] == 6 and mine["shared"] and mine["first"]["id"] == a["id"]
    assert data["suggestions"][0]["shared"], "shared travelers come first"
    # a narrower window leaves it out
    narrow = plan.get("/api/plan/2027/synergies?within_days=3", headers=ADMIN).json()
    assert not any({s["first"]["id"], s["second"]["id"]} == {a["id"], b["id"]} for s in narrow["suggestions"])
    # dismiss it: it does not come back
    r = plan.post("/api/plan/2027/synergies/dismiss", headers=ADMIN,
                  json={"trip_a": b["id"], "trip_b": a["id"], "reason": "Different teams"})
    assert r.status_code == 200 and q("SELECT count(*) FROM travel.synergy_dismissal")[0][0] == 1
    again = plan.get("/api/plan/2027/synergies?within_days=10", headers=ADMIN).json()
    assert not any({s["first"]["id"], s["second"]["id"]} == {a["id"], b["id"]} for s in again["suggestions"])


def test_left_out_cases_and_permissions(plan):
    with db() as conn:
        assert synergy.suggestions(conn, 2027, None, 10, today=date(2028, 1, 1))["suggestions"] == []   # all in the past
        for s in synergy.suggestions(conn, 2027, None, 14, today=date(2027, 1, 1))["suggestions"]:
            assert s["gap_days"] > 0 and s["first"]["end_date"] < s["second"]["start_date"]              # never overlapping
    stranger = {"X-Forwarded-Email": "nobody@example.test"}
    assert plan.get("/api/plan/2027/synergies", headers=stranger).status_code == 403
    assert plan.post("/api/plan/2027/synergies/dismiss", headers=stranger, json={"trip_a": 1, "trip_b": 2}).status_code == 403
    assert plan.post("/api/plan/2027/synergies/dismiss", headers=ADMIN, json={"trip_a": 1, "trip_b": 1}).status_code == 422
    assert plan.post("/api/plan/2027/synergies/dismiss", headers=ADMIN, json={"trip_a": 1, "trip_b": 99999}).status_code == 404
    assert plan.get("/api/plan/2027/synergies?within_days=0", headers=ADMIN).status_code == 422
