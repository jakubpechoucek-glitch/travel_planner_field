import psycopg
import pytest
from conftest import ADMIN_EMAIL, IDENTITY_KEY, TEST_DB, make_settings
from fastapi.testclient import TestClient

from travel_planner.catalog import RuleIn, describe_rule, validate_rule
from travel_planner.identity import key_hash
from travel_planner.main import create_app

ADMIN = {"X-Forwarded-Email": ADMIN_EMAIL}


@pytest.fixture
def c():
    settings = make_settings(bootstrap_admin_hashes=key_hash(ADMIN_EMAIL, IDENTITY_KEY))
    with TestClient(create_app(settings)) as client:
        yield client


def catalog(c):
    return c.get("/api/catalog", headers=ADMIN).json()


def event(cat, code):
    return next(e for e in cat["event_types"] if e["code"] == code)


def pos_id(cat, code):
    return next(p["id"] for p in cat["positions"] if p["code"] == code)


def test_seeded_catalog(c):
    cat = catalog(c)
    assert len(cat["event_types"]) == 15
    meet = event(cat, "AM-FSV-MEET")
    assert meet["joint_visit"] == "partial"
    summaries = {r["rule_key"]: r["summary"] for r in meet["rules"]}
    assert summaries["AMM-QUOTA"] == "6 per year for each cluster."
    assert summaries["AMM-CADENCE"] == "Every 2 months for each cluster."
    # the Head's yearly limits are kept as participation limits
    head = pos_id(cat, "HEAD")
    assert {p["position_id"]: p["yearly_limit"] for p in event(cat, "RM-AM-MEET")["participation"]}[head] == 3
    assert {r["rule_key"]: r["summary"] for r in cat["general_rules"]}["RM-TRIPS-MONTH"] == (
        "Regional Manager: at most 2 trips per month."
    )
    assert [m["merges_into_name"] for m in event(cat, "LAKBAY")["merges"]] == [
        "Area Management Meeting", "Region Management Meeting"] or len(event(cat, "LAKBAY")["merges"]) == 2
    assert len(cat["blackouts"]) == 2 and len(cat["blackouts"][0]["event_type_ids"]) == 2


def test_descriptions():
    base = {"rule_type": "annual_quota", "scope_kind": "cluster", "min_count": 6, "max_count": 12, "position_id": None,
            "period": "year", "interval_n": None, "params": {}}
    assert describe_rule(base, {}) == "6 to 12 per year for each cluster."
    assert describe_rule({**base, "scope_kind": "nationwide", "min_count": 1, "max_count": 1}, {}) == (
        "1 per year nationwide.")
    assert describe_rule({**base, "rule_type": "cadence", "period": "quarter", "interval_n": 1}, {}) == (
        "Every quarter for each cluster.")
    assert describe_rule({**base, "rule_type": "preferred_window", "params": {"months": [11, 12, 1]}}, {}) == (
        "Prefer Nov, Dec, Jan.")
    assert describe_rule({**base, "rule_type": "period_cap", "scope_kind": "position", "position_id": 7,
                          "period": "month", "min_count": None, "max_count": 1}, {7: "Head"}) == (
        "Head: at most 1 trip per month.")


def test_validation_rules():
    ok = RuleIn(rule_type="annual_quota", scope_kind="cluster", event_type_id=1, min_count=1)
    assert validate_rule(ok, positions={1}, events={1}) == []
    bad = RuleIn(rule_type="annual_quota", scope_kind="person", event_type_id=1)
    msgs = " ".join(validate_rule(bad, positions=set(), events={1}))
    assert "minimum" in msgs and "cluster" in msgs
    assert validate_rule(RuleIn(rule_type="cadence", scope_kind="cluster"), positions=set(), events=set())
    assert validate_rule(RuleIn(rule_type="preferred_window", scope_kind="nationwide", event_type_id=1,
                                params={"months": [13]}), positions=set(), events={1})


def test_permissions(c):
    assert c.get("/api/catalog").status_code == 401
    stranger = {"X-Forwarded-Email": "nobody@example.test"}
    assert c.get("/api/catalog", headers=stranger).status_code == 403
    assert c.post("/api/admin/rules", headers=stranger, json={}).status_code == 403
    # a linked user with a viewer role can read but not edit
    kh = key_hash("viewer@example.test", IDENTITY_KEY)
    c.get("/api/catalog", headers=ADMIN)  # make sure migrations ran
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("INSERT INTO travel.person(full_name, sso_key_hash) VALUES ('Vera Viewer', %s)", (kh,))
        conn.execute("INSERT INTO travel.user_role(person_id, role) SELECT id, 'viewer' FROM travel.person")
    viewer = {"X-Forwarded-Email": "viewer@example.test"}
    assert c.get("/api/catalog", headers=viewer).status_code == 200
    r = c.put("/api/admin/event-types/1", headers=viewer, json={"name": "x"})
    assert r.status_code == 403


def test_rule_versioning(c):
    cat = catalog(c)
    meet = event(cat, "AM-FSV-MEET")
    body = {"event_type_id": meet["id"], "rule_type": "annual_quota", "scope_kind": "cluster",
            "min_count": 4, "max_count": 8, "severity": "warn"}
    r = c.put("/api/admin/rules/AMM-QUOTA", headers=ADMIN, json=body)
    assert r.status_code == 200 and r.json()["version"] == 2
    rules = {x["rule_key"]: x for x in event(catalog(c), "AM-FSV-MEET")["rules"]}
    assert rules["AMM-QUOTA"]["summary"] == "4 to 8 per year for each cluster."
    with psycopg.connect(TEST_DB) as conn:  # history is kept
        rows = conn.execute("SELECT version, active FROM travel.rule WHERE rule_key = 'AMM-QUOTA' "
                            "ORDER BY version").fetchall()
        assert rows == [(1, False), (2, True)]
        assert conn.execute("SELECT count(*) FROM travel.audit_log WHERE action = 'catalog.rule.update'"
                            ).fetchone()[0] == 1
    assert c.put("/api/admin/rules/NOPE", headers=ADMIN, json=body).status_code == 404


def test_create_validate_and_deactivate_rule(c):
    cat = catalog(c)
    visit = event(cat, "AM-FSV-VISIT")
    bad = c.post("/api/admin/rules", headers=ADMIN,
                 json={"event_type_id": visit["id"], "rule_type": "annual_quota", "scope_kind": "cluster"})
    assert bad.status_code == 422 and "minimum" in bad.json()["detail"]
    junk = c.post("/api/admin/rules", headers=ADMIN, json={"rule_type": "magic", "scope_kind": "cluster"})
    assert junk.status_code == 422 and junk.json()["detail"].startswith("Please check the form")
    ok = c.post("/api/admin/rules", headers=ADMIN, json={
        "event_type_id": visit["id"], "rule_type": "preferred_window", "scope_kind": "nationwide",
        "params": {"months": [3, 4]}, "severity": "info"})
    assert ok.status_code == 201
    key = ok.json()["rule_key"]
    assert any(r["rule_key"] == key for r in event(catalog(c), "AM-FSV-VISIT")["rules"])
    assert c.delete(f"/api/admin/rules/{key}", headers=ADMIN).status_code == 204
    assert not any(r["rule_key"] == key for r in event(catalog(c), "AM-FSV-VISIT")["rules"])
    assert c.delete(f"/api/admin/rules/{key}", headers=ADMIN).status_code == 404


def test_event_type_create_and_update(c):
    cat = catalog(c)
    am, rm = pos_id(cat, "AM"), pos_id(cat, "RM")
    meet = event(cat, "AM-FSV-MEET")["id"]
    new = {"code": "WORKSHOP", "name": "Regional workshop", "visited_kind": "region", "joint_visit": "yes",
           "organizer_position_id": rm, "typical_days": 2,
           "participation": [{"position_id": rm, "participation": "organizer"},
                             {"position_id": am, "yearly_limit": 2}],
           "merges": [{"merges_into_id": meet, "condition_text": "Combine with the area meeting."}]}
    r = c.post("/api/admin/event-types", headers=ADMIN, json=new)
    assert r.status_code == 201
    eid = r.json()["id"]
    assert c.post("/api/admin/event-types", headers=ADMIN, json=new).status_code == 409  # duplicate code
    created = event(catalog(c), "WORKSHOP")
    assert len(created["participation"]) == 2 and created["merges"][0]["merges_into_id"] == meet

    upd = {**new, "name": "Regional workshop (updated)", "participation": [{"position_id": rm}], "merges": [],
           "active": False}
    assert c.put(f"/api/admin/event-types/{eid}", headers=ADMIN, json=upd).status_code == 200
    again = event(catalog(c), "WORKSHOP")
    assert again["name"].endswith("(updated)") and again["active"] is False
    assert len(again["participation"]) == 1 and again["merges"] == []
    # invalid inputs
    assert c.put(f"/api/admin/event-types/{eid}", headers=ADMIN,
                 json={**upd, "merges": [{"merges_into_id": eid}]}).status_code == 422
    assert c.put(f"/api/admin/event-types/{eid}", headers=ADMIN,
                 json={**upd, "participation": [{"position_id": 9999}]}).status_code == 422
    assert c.put("/api/admin/event-types/9999", headers=ADMIN, json=upd).status_code == 404
    assert c.post("/api/admin/event-types", headers=ADMIN, json={"name": "No code"}).status_code == 422


def test_blackouts(c):
    cat = catalog(c)
    ev = event(cat, "AM-FSV-VISIT")["id"]
    body = {"plan_year": 2028, "name": "Conference", "start_date": "2028-04-01", "end_date": "2028-04-30",
            "severity": "warn", "event_type_ids": [ev]}
    r = c.post("/api/admin/blackouts", headers=ADMIN, json=body)  # creates the plan year 2028 on the way
    assert r.status_code == 201
    bid = r.json()["id"]
    in_year = c.get("/api/catalog?plan_year=2028", headers=ADMIN).json()["blackouts"]
    assert [b["name"] for b in in_year] == ["Conference"] and in_year[0]["event_type_ids"] == [ev]
    assert c.put(f"/api/admin/blackouts/{bid}", headers=ADMIN,
                 json={**body, "name": "Conference moved", "event_type_ids": []}).status_code == 200
    assert c.post("/api/admin/blackouts", headers=ADMIN,
                  json={**body, "end_date": "2028-03-01"}).status_code == 422
    assert c.post("/api/admin/blackouts", headers=ADMIN,
                  json={**body, "start_date": "2029-01-01", "end_date": "2029-01-05"}).status_code == 422
    assert c.delete(f"/api/admin/blackouts/{bid}", headers=ADMIN).status_code == 204
    assert c.delete(f"/api/admin/blackouts/{bid}", headers=ADMIN).status_code == 404


def test_generator_settings_in_the_catalog(c):
    cat = catalog(c)
    visit = event(cat, "AM-FSV-VISIT")
    fsv = pos_id(cat, "FSV")
    assert {p["position_id"]: p["travels"] for p in visit["participation"]}[fsv] is False   # visited, not travelling
    assert fsv in {p["position_id"] for p in event(cat, "YEAR-END")["participation"]}
    conf_id = event(cat, "CONF")["id"]
    assert {b["caused_by_event_type_id"] for b in cat["blackouts"]} == {conf_id, event(cat, "YEAR-END")["id"]}
    body = {"plan_year": 2027, "name": "Test", "start_date": "2027-02-01", "end_date": "2027-02-05",
            "caused_by_event_type_id": 9999}
    assert c.post("/api/admin/blackouts", headers=ADMIN, json=body).status_code == 422
    ok = c.post("/api/admin/blackouts", headers=ADMIN, json={**body, "caused_by_event_type_id": conf_id})
    assert ok.status_code == 201
    rfm = {r["rule_key"] for r in event(cat, "REGIONAL-FIELD-MEET")["rules"]}
    assert rfm == {"RFM-QUOTA"}                      # the quarterly rule was replaced by a yearly quota per region


def test_rule_held_every_n_years():
    base = dict(rule_type="annual_quota", scope_kind="nationwide", event_type_id=1, min_count=1)
    ok = RuleIn(**base, params={"every_n_years": 2, "first_year": 2027})
    assert validate_rule(ok, positions=set(), events={1}) == []
    assert any("first year" in m for m in validate_rule(RuleIn(**base, params={"every_n_years": 2}),
                                                         positions=set(), events={1}))
    assert any("years" in m for m in validate_rule(RuleIn(**base, params={"every_n_years": 1, "first_year": 2027}),
                                                    positions=set(), events={1}))
    text = describe_rule({**base, "params": ok.params, "position_id": None, "max_count": None}, {})
    assert text == "At least 1 per year nationwide. Held every 2 years, starting in 2027."
