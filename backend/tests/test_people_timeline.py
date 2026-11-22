"""The people timeline: who is where, when."""

import psycopg
import pytest
from conftest import ADMIN_EMAIL, IDENTITY_KEY, TEST_DB, make_settings
from fastapi.testclient import TestClient
from orgfixture import build_workbook

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


def get(c, headers=ADMIN, **params):
    params = {"start": "2027-01-01", "end": "2027-05-05", **params}   # 125 days, the longest window
    return c.get("/api/plan/2027/people-timeline", params=params, headers=headers)


def test_rows_are_people_with_their_trips(plan):
    data = get(plan).json()
    assert data["total"] == len(data["people"]) > 0 and data["truncated"] is False
    amy = next(p for p in data["people"] if p["name"] == "Amy Alvarez")
    assert amy["position"] == "Area Manager" and amy["unit"] == "Alpha 1" and amy["trips"]
    assert all(t["travels"] for p in data["people"] for t in p["trips"])           # hosts are left out by default
    assert amy["days_away"] >= len(amy["trips"])
    withhosts = get(plan, hosts="true").json()
    assert any(not t["travels"] for p in withhosts["people"] for t in p["trips"])
    assert get(plan, q="amy").json()["people"][0]["name"] == "Amy Alvarez" and get(plan, q="amy").json()["total"] == 1
    unit = q("SELECT id FROM travel.org_unit WHERE name = 'Alpha 2'")[0][0]
    assert {p["unit"] for p in get(plan, unit_id=unit).json()["people"]} == {"Alpha 2"}


def test_window_days_away_and_clashes(plan):
    amy_trip = q("SELECT t.id, t.start_date, t.end_date FROM travel.trip t JOIN travel.trip_participant p ON p.trip_id = t.id "
                 "JOIN travel.person x ON x.id = p.person_id WHERE x.full_name = 'Amy Alvarez' AND p.travels "
                 "AND t.status = 'generated' ORDER BY t.start_date LIMIT 1")[0]
    tid, start, end = amy_trip
    window = get(plan, start=str(start), end=str(end)).json()
    amy = next(p for p in window["people"] if p["name"] == "Amy Alvarez")
    assert {t["id"] for t in amy["trips"]} >= {tid} and amy["days_away"] == (end - start).days + 1
    assert get(plan, start="2027-02-28", end="2027-02-28").status_code == 200
    # put Amy on a second trip at the same time: both bars are marked as a clash
    other = q("SELECT t.id FROM travel.trip t WHERE t.status = 'generated' AND t.id <> %s AND NOT EXISTS ("
              "SELECT 1 FROM travel.trip_participant p JOIN travel.person x ON x.id = p.person_id "
              "WHERE p.trip_id = t.id AND x.full_name = 'Amy Alvarez') LIMIT 1", tid)[0][0]
    q("UPDATE travel.trip SET start_date = %s, end_date = %s WHERE id = %s", start, end, other)
    q("INSERT INTO travel.trip_participant(trip_id, person_id, role, travels) SELECT %s, id, 'traveler', true "
      "FROM travel.person WHERE full_name = 'Amy Alvarez'", other)
    amy = next(p for p in get(plan, start=str(start), end=str(end)).json()["people"] if p["name"] == "Amy Alvarez")
    assert amy["clashes"] == 2 and all(t["clash"] for t in amy["trips"] if t["id"] in (tid, other))
    assert amy["days_away"] == (end - start).days + 1                                   # days are not counted twice


def test_blackouts_validation_and_permissions(plan):
    data = get(plan, start="2027-04-01", end="2027-04-30").json()
    assert any("Conference" in b["name"] for b in data["blackouts"])
    assert get(plan, start="2027-05-01", end="2027-04-01").status_code == 422
    assert get(plan, start="2027-01-01", end="2027-05-05").status_code == 200                # 125 days is the limit
    assert get(plan, start="2027-01-01", end="2027-05-06").status_code == 422                # 126 days is too long
    stranger = {"X-Forwarded-Email": "nobody@example.test"}
    assert get(plan, headers=stranger).status_code == 403
