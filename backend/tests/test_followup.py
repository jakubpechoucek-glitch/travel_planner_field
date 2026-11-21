"""Choosing the area of a trip later (Special Area visits) and the follow-up of actions."""

from datetime import date, timedelta

import psycopg
import pytest
from conftest import ADMIN_EMAIL, IDENTITY_KEY, TEST_DB, make_settings
from fastapi.testclient import TestClient
from orgfixture import build_workbook
from psycopg.rows import dict_row

from travel_planner import actions, plan_store
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


def special_trips():
    return q("SELECT t.id, u.name, t.start_date, t.area_decide_by, t.title FROM travel.trip t "
             "JOIN travel.event_type e ON e.id = t.event_type_id JOIN travel.org_unit u ON u.id = t.visited_org_unit_id "
             "WHERE e.code = 'SPECIAL-AREA' AND t.status <> 'cancelled' AND t.area_pending ORDER BY u.name")


def test_special_area_trips_hold_a_region_slot(plan):
    trips = special_trips()
    assert {t[1] for t in trips} == {"North", "South"}            # one per region
    for _id, _place, start, decide_by, _title in trips:
        assert decide_by == start - timedelta(days=60)


def test_choose_the_area_later(plan):
    tid, _, _, _, title = special_trips()[0]                      # North
    opts = plan.get(f"/api/plan/trips/{tid}/area-options", headers=ADMIN).json()
    assert {o["name"] for o in opts} == {"Alpha 1", "Alpha 2"}
    south = next(o for o in plan.get(f"/api/plan/trips/{special_trips()[1][0]}/area-options", headers=ADMIN).json())
    assert plan.post(f"/api/plan/trips/{tid}/choose-area", headers=ADMIN, json={"cluster_id": south["id"]}).status_code == 422
    r = plan.post(f"/api/plan/trips/{tid}/choose-area", headers=ADMIN,
                  json={"cluster_id": opts[0]["id"], "area_focus": "diagnostic"})
    assert r.status_code == 200, r.text
    trip = r.json()["trip"]
    assert trip["area_pending"] is False and trip["place"] == "Alpha 1" and trip["area_focus"] == "diagnostic"
    assert trip["title"].endswith(": Alpha 1") and title.rsplit(": ", 1)[0] in trip["title"]
    history = plan.get(f"/api/plan/trips/{tid}/history", headers=ADMIN).json()
    assert history[0]["reason"] == "Area chosen: Alpha 1 (diagnostic)."
    assert plan.post(f"/api/plan/trips/{tid}/choose-area", headers=ADMIN, json={"cluster_id": opts[0]["id"]}).status_code == 409
    assert plan.get(f"/api/plan/trips/{tid}/area-options", headers=ADMIN).json() == []


def test_area_warnings_overdue_and_mix(plan):
    (n_id, *_), (s_id, *_) = special_trips()
    with db() as conn:
        late = plan_store.area_warnings(conn, 2027, today=date(2027, 12, 31))
        assert {w.code for w in late} == {"area_overdue"} and len(late) == 2
        assert plan_store.area_warnings(conn, 2027, today=date(2026, 1, 1)) == []
    for tid in (n_id, s_id):
        cid = plan.get(f"/api/plan/trips/{tid}/area-options", headers=ADMIN).json()[0]["id"]
        plan.post(f"/api/plan/trips/{tid}/choose-area", headers=ADMIN, json={"cluster_id": cid, "area_focus": "benchmark"})
    warnings = plan.get("/api/plan/2027/warnings", headers=ADMIN).json()
    assert "area_mix" in warnings["counts"]                       # two benchmark areas, the rule allows one


def test_actions_and_follow_up(plan):
    tid = special_trips()[0][0]
    end = q("SELECT end_date FROM travel.trip WHERE id = %s", tid)[0][0]
    r = plan.post(f"/api/plan/trips/{tid}/actions", headers=ADMIN, json={"title": "Fix the daily report"})
    assert r.status_code == 201
    first = r.json()["actions"][0]
    assert first["status"] == "open" and first["due_date"] == str(end + timedelta(days=30))
    for title in ("Automate the hand-off", "Review supervisor load"):
        assert plan.post(f"/api/plan/trips/{tid}/actions", headers=ADMIN, json={"title": title}).status_code == 201
    r = plan.post(f"/api/plan/trips/{tid}/actions", headers=ADMIN, json={"title": "One too many"})
    assert r.status_code == 409 and "at most 3" in r.json()["detail"]
    # close one, drop one: a slot is free again
    r = plan.put(f"/api/plan/actions/{first['id']}", headers=ADMIN, json={"status": "done", "close_note": "Shipped"})
    done = next(a for a in r.json()["actions"] if a["id"] == first["id"])
    assert done["status"] == "done" and done["closed_at"] and done["close_note"] == "Shipped"
    assert len(plan.get(f"/api/plan/trips/{tid}", headers=ADMIN).json()["actions"]) == 3

    with db() as conn:
        before = actions.follow_ups(conn, 2027, None, today=end - timedelta(days=5))
        assert next(x for x in before["trips"] if x["id"] == tid)["state"] == "upcoming"
        mid = actions.follow_ups(conn, 2027, None, today=end + timedelta(days=10))
        row = next(x for x in mid["trips"] if x["id"] == tid)
        assert row["state"] == "open" and (row["open"], row["done"]) == (2, 1)
        late = actions.follow_ups(conn, 2027, None, today=end + timedelta(days=45))
        assert next(x for x in late["trips"] if x["id"] == tid)["state"] == "overdue"
        assert late["counts"]["overdue"] >= 1 and late["trips"][0]["state"] == "overdue"   # late ones come first
    for a in plan.get(f"/api/plan/trips/{tid}", headers=ADMIN).json()["actions"]:
        if a["status"] == "open":
            plan.put(f"/api/plan/actions/{a['id']}", headers=ADMIN, json={"status": "dropped"})
    with db() as conn:
        closed = actions.follow_ups(conn, 2027, None, today=end + timedelta(days=45))
        assert next(x for x in closed["trips"] if x["id"] == tid)["state"] == "closed"


def test_follow_up_permissions(plan):
    tid = special_trips()[0][0]
    stranger = {"X-Forwarded-Email": "nobody@example.test"}
    assert plan.post(f"/api/plan/trips/{tid}/actions", headers=stranger, json={"title": "Not allowed"}).status_code == 403
    assert plan.get("/api/plan/2027/follow-ups", headers=stranger).status_code == 403
    assert plan.put("/api/plan/actions/99999", headers=ADMIN, json={"status": "done"}).status_code == 404
    r = plan.get("/api/plan/2027/follow-ups", headers=ADMIN).json()
    assert r["trips"] and all(x["state"] in ("upcoming", "missing", "open", "overdue", "closed") for x in r["trips"])
