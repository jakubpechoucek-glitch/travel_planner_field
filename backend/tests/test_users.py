import psycopg
import pytest
from conftest import ADMIN_EMAIL, IDENTITY_KEY, TEST_DB, make_settings
from fastapi.testclient import TestClient
from orgfixture import build_workbook

from travel_planner.identity import key_hash
from travel_planner.main import create_app

ADMIN = {"X-Forwarded-Email": ADMIN_EMAIL}
API = "/api/admin/users"


def q(sql, *args):
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        cur = conn.execute(sql, args)
        return cur.fetchall() if cur.description else []


@pytest.fixture
def c():
    settings = make_settings(bootstrap_admin_hashes=key_hash(ADMIN_EMAIL, IDENTITY_KEY))
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def org(c, tmp_path):
    path = tmp_path / "org.xlsx"
    build_workbook(path)
    with open(path, "rb") as fh:
        r = c.post("/api/admin/org-import", params={"effective_date": "2027-01-01", "commit": "true"},
                   headers=ADMIN, files={"file": ("org.xlsx", fh, "application/vnd.ms-excel")})
    assert r.json()["applied"]
    return c


def find(c, name, **params):
    users = c.get(API, params={"q": name, **params}, headers=ADMIN).json()["users"]
    return next(u for u in users if u["full_name"] == name)


def test_list_and_filters(org):
    data = org.get(API, headers=ADMIN).json()
    assert data["total"] == 10
    sam = find(org, "Sam Stone")
    assert sam["position"] == "Field Supervisor" and sam["cluster"] == "Alpha 1" and sam["manager"] == "Amy Alvarez"
    assert sam["has_login"] is False and sam["roles"] == []
    assert org.get(API, params={"q": "1003"}, headers=ADMIN).json()["total"] == 1          # by employee number
    assert org.get(API, params={"role": "none"}, headers=ADMIN).json()["total"] == 10
    assert org.get(API, params={"login": "linked"}, headers=ADMIN).json()["total"] == 0
    page = org.get(API, params={"limit": 3, "offset": 9}, headers=ADMIN).json()
    assert page["total"] == 10 and len(page["users"]) == 1


def test_meta(org):
    m = org.get(f"{API}/meta", headers=ADMIN).json()
    assert {"HEAD", "RM", "AM", "FSV"} <= {p["code"] for p in m["positions"]}
    assert {r["name"] for r in m["regions"]} == {"North", "South"} and len(m["clusters"]) == 3
    assert {r["role"]: r["scope_kind"] for r in m["roles"]}["regional_planner"] == "region"
    assert m["bootstrap_admin"] is True and m["administrators"] == 0


def test_create_and_edit_a_person(org):
    m = org.get(f"{API}/meta", headers=ADMIN).json()
    fsv = next(p["id"] for p in m["positions"] if p["code"] == "FSV")
    cluster = next(c["id"] for c in m["clusters"] if c["name"] == "Alpha 1")
    amy = find(org, "Amy Alvarez")["id"]
    body = {"full_name": "New Person", "employee_no": "9001",
            "assignment": {"position_id": fsv, "manager_id": amy, "cluster_id": cluster, "effective_date": "2027-01-01"}}
    r = org.post(API, headers=ADMIN, json=body)
    assert r.status_code == 201 and r.json()["manager"] == "Amy Alvarez" and r.json()["cluster"] == "Alpha 1"
    assert org.post(API, headers=ADMIN, json=body).status_code == 409                   # employee number used
    bad = {**body, "employee_no": "9002", "assignment": {**body["assignment"], "position_id": 99999}}
    assert org.post(API, headers=ADMIN, json=bad).status_code == 422
    pid = r.json()["id"]
    upd = org.put(f"{API}/{pid}", headers=ADMIN, json={"full_name": "Renamed Person", "employee_no": ""})
    assert upd.json()["full_name"] == "Renamed Person" and upd.json()["employee_no"] is None
    selfmgr = org.put(f"{API}/{pid}", headers=ADMIN, json={"assignment": {"position_id": fsv, "manager_id": pid}})
    assert selfmgr.status_code == 422


def test_assignment_changes_keep_history(org):
    sam = find(org, "Sam Stone")
    alan = find(org, "Alan Abad")
    m = org.get(f"{API}/meta", headers=ADMIN).json()
    alpha2 = next(c["id"] for c in m["clusters"] if c["name"] == "Alpha 2")
    r = org.put(f"{API}/{sam['id']}", headers=ADMIN, json={"assignment": {
        "position_id": sam["position_id"], "manager_id": alan["id"], "cluster_id": alpha2,
        "effective_date": "2027-07-01"}})
    assert r.status_code == 200 and r.json()["cluster"] == "Alpha 2"
    rows = q("SELECT valid_from, valid_to FROM travel.person_assignment WHERE person_id = %s ORDER BY valid_from",
             sam["id"])
    assert len(rows) == 2 and str(rows[0][1]) == "2027-06-30" and rows[1][1] is None
    early = org.put(f"{API}/{sam['id']}", headers=ADMIN, json={"assignment": {
        "position_id": sam["position_id"], "manager_id": alan["id"], "cluster_id": None, "effective_date": "2027-03-01"}})
    assert early.status_code == 422                                                         # earlier than the current one


def test_the_email_is_hashed_and_never_stored(org):
    sam = find(org, "Sam Stone")
    marker = "uniquemarker.person@example.test"
    r = org.post(f"{API}/{sam['id']}/login", headers=ADMIN, json={"email": marker})
    assert r.status_code == 200 and r.json()["has_login"] is True and marker not in r.text
    assert q("SELECT sso_key_hash FROM travel.person WHERE id = %s", sam["id"])[0][0] == key_hash(marker, IDENTITY_KEY)
    # the address is nowhere in the database
    dump = ""
    for table in ("person", "person_assignment", "audit_log", "user_role"):
        dump += str(q(f"SELECT * FROM travel.{table}"))  # noqa: S608
    assert "uniquemarker" not in dump and "@" not in dump
    # and signing in with it now finds the person
    me = org.get("/api/me", headers={"X-Forwarded-Email": marker.upper()}).json()
    assert me["linked"] is True and me["name"] == "Sam Stone"
    # the same address cannot be linked to someone else
    sue = find(org, "Sue Smith")
    dup = org.post(f"{API}/{sue['id']}/login", headers=ADMIN, json={"email": marker})
    assert dup.status_code == 409 and "Sam Stone" in dup.json()["detail"] and marker not in dup.text
    assert org.post(f"{API}/{sue['id']}/login", headers=ADMIN, json={"email": "not-an-email"}).status_code == 422
    # replacing and unlinking
    assert org.post(f"{API}/{sam['id']}/login", headers=ADMIN, json={"email": "other.one@example.test"}).status_code == 200
    assert org.get("/api/me", headers={"X-Forwarded-Email": marker}).json()["linked"] is False
    assert org.delete(f"{API}/{sam['id']}/login", headers=ADMIN).json()["has_login"] is False
    actions = {r[0] for r in q("SELECT action FROM travel.audit_log")}
    assert {"user.login.link", "user.login.replace", "user.login.unlink"} <= actions


def test_roles_need_the_right_scope(org):
    rita = find(org, "Rita Rivera")["id"]
    m = org.get(f"{API}/meta", headers=ADMIN).json()
    north = next(r["id"] for r in m["regions"] if r["name"] == "North")
    cluster = m["clusters"][0]["id"]
    assert org.post(f"{API}/{rita}/roles", headers=ADMIN, json={"role": "regional_planner"}).status_code == 422
    assert org.post(f"{API}/{rita}/roles", headers=ADMIN,
                    json={"role": "regional_planner", "scope_org_unit_id": cluster}).status_code == 422   # a cluster
    assert org.post(f"{API}/{rita}/roles", headers=ADMIN,
                    json={"role": "national_planner", "scope_org_unit_id": north}).status_code == 422
    ok = org.post(f"{API}/{rita}/roles", headers=ADMIN, json={"role": "regional_planner", "scope_org_unit_id": north})
    assert ok.status_code == 201 and ok.json()["roles"][0]["scope"] == "North"
    assert org.post(f"{API}/{rita}/roles", headers=ADMIN,
                    json={"role": "regional_planner", "scope_org_unit_id": north}).status_code == 409
    glob = {"role": "national_planner"}
    assert org.post(f"{API}/{rita}/roles", headers=ADMIN, json=glob).status_code == 201
    assert org.post(f"{API}/{rita}/roles", headers=ADMIN, json=glob).status_code == 409   # global roles only once
    role_id = ok.json()["roles"][0]["id"]
    assert len(org.delete(f"{API}/{rita}/roles/{role_id}", headers=ADMIN).json()["roles"]) == 1
    assert org.delete(f"{API}/{rita}/roles/{role_id}", headers=ADMIN).status_code == 404


def test_a_role_and_a_login_give_access_to_the_scope(org):
    org.post("/api/admin/plan/2027/generate?commit=true", headers=ADMIN)
    rita = find(org, "Rita Rivera")["id"]
    north = next(r["id"] for r in org.get(f"{API}/meta", headers=ADMIN).json()["regions"] if r["name"] == "North")
    org.post(f"{API}/{rita}/roles", headers=ADMIN, json={"role": "regional_planner", "scope_org_unit_id": north})
    mail = {"X-Forwarded-Email": "rita.rivera@example.test"}
    org.post(f"{API}/{rita}/login", headers=ADMIN, json={"email": "rita.rivera@example.test"})
    summary = org.get("/api/plan/2027/summary", headers=mail).json()
    assert {r["label"] for reg in summary["regions"] for r in reg["rows"]} == {
        "Alpha 1", "Alpha 2", "Region and local offices"}
    # deactivating the person ends the access at once
    assert org.put(f"{API}/{rita}", headers=ADMIN, json={"active": False}).json()["active"] is False
    assert org.get("/api/plan/2027/summary", headers=mail).status_code == 403


def test_the_last_administrator_cannot_be_removed():
    admin_mail = "boss@example.test"
    settings = make_settings()                                  # no bootstrap administrator
    with TestClient(create_app(settings)) as c:
        c.get("/api/health")
        with psycopg.connect(TEST_DB, autocommit=True) as conn:
            pid = conn.execute("INSERT INTO travel.person(full_name, sso_key_hash) VALUES ('Boss', %s) RETURNING id",
                               (key_hash(admin_mail, IDENTITY_KEY),)).fetchone()[0]
            role_id = conn.execute("INSERT INTO travel.user_role(person_id, role) VALUES (%s, 'administrator') "
                                   "RETURNING id", (pid,)).fetchone()[0]
        h = {"X-Forwarded-Email": admin_mail}
        assert c.get(f"{API}/meta", headers=h).json()["administrators"] == 1
        assert c.delete(f"{API}/{pid}/roles/{role_id}", headers=h).status_code == 409
        assert c.delete(f"{API}/{pid}/login", headers=h).status_code == 409
        r = c.put(f"{API}/{pid}", headers=h, json={"active": False})
        assert r.status_code == 409 and "yourself" in r.json()["detail"]
        # a second administrator who can sign in makes the change possible
        with psycopg.connect(TEST_DB, autocommit=True) as conn:
            two = conn.execute("INSERT INTO travel.person(full_name, sso_key_hash) VALUES ('Second', %s) RETURNING id",
                               (key_hash("second@example.test", IDENTITY_KEY),)).fetchone()[0]
            conn.execute("INSERT INTO travel.user_role(person_id, role) VALUES (%s, 'administrator')", (two,))
        assert c.delete(f"{API}/{pid}/roles/{role_id}", headers=h).status_code == 200
        # now the second one is the last
        h2 = {"X-Forwarded-Email": "second@example.test"}
        second_role = c.get(f"{API}/{two}", headers=h2).json()["roles"][0]["id"]
        assert c.delete(f"{API}/{two}/roles/{second_role}", headers=h2).status_code == 409


def test_bulk_linking(org):
    text = "\n".join([
        "email, employee number",
        "sam.stone@example.test, 1001",
        "1002; sue.smith@example.test",                # either order
        "bob.beta@example.test\tBob Beta",             # by name
        "amy.alvarez@example.test, Amy Alvarez",
    ])
    r = org.post(f"{API}/bulk-login", headers=ADMIN, json={"text": text})
    out = r.json()
    assert r.status_code == 200 and out["applied"] is False and out["linked"] == 4 and out["problems"] == 0
    assert "@" not in r.text                                                               # nothing is echoed back
    assert org.get(API, params={"login": "linked"}, headers=ADMIN).json()["total"] == 0     # a preview saves nothing
    done = org.post(f"{API}/bulk-login?commit=true", headers=ADMIN, json={"text": text}).json()
    assert done["applied"] is True and done["linked"] == 4
    assert org.get(API, params={"login": "linked"}, headers=ADMIN).json()["total"] == 4
    again = org.post(f"{API}/bulk-login?commit=true", headers=ADMIN, json={"text": text}).json()
    assert again["unchanged"] == 4 and again["linked"] == 0
    assert org.get("/api/me", headers={"X-Forwarded-Email": "SAM.STONE@example.test"}).json()["name"] == "Sam Stone"


def test_bulk_linking_reports_problems_and_saves_nothing(org):
    text = "\n".join([
        "good@example.test, 1001",
        "nobody@example.test, 4242",                   # unknown
        "broken@address, 1002",                        # invalid e-mail
        "good@example.test, 1003",                     # the same address twice
        "just-a-line-without-an-address",
        "sue@example.test, Sue Smith",
        "other@example.test, 1002",                    # Sue again
    ])
    r = org.post(f"{API}/bulk-login", headers=ADMIN, json={"text": text}).json()
    codes = {i["code"] for i in r["issues"]}
    assert {"unknown_person", "invalid_email", "duplicate_email", "format", "duplicate_person"} <= codes
    assert all(i["message"].startswith("Line ") and "@" not in i["message"] for i in r["issues"])
    refused = org.post(f"{API}/bulk-login?commit=true", headers=ADMIN, json={"text": text})
    assert refused.status_code == 422
    assert org.get(API, params={"login": "linked"}, headers=ADMIN).json()["total"] == 0
    assert org.post(f"{API}/bulk-login", headers=ADMIN, json={"text": "   \n"}).status_code == 422


def test_suggested_roles_follow_the_organization(org):
    preview = org.post(f"{API}/suggest-roles", headers=ADMIN).json()
    assert preview["applied"] is False and preview["to_add"] == 5
    assert "Rita Rivera: regional planner of North" in preview["roles"]
    assert "Amy Alvarez: area planner of Alpha 1" in preview["roles"]
    assert "Hana Head: national planner" in preview["roles"]
    assert org.get(API, params={"role": "none"}, headers=ADMIN).json()["total"] == 10
    done = org.post(f"{API}/suggest-roles?commit=true", headers=ADMIN).json()
    assert done["applied"] and done["to_add"] == 5
    again = org.post(f"{API}/suggest-roles?commit=true", headers=ADMIN).json()
    assert again["to_add"] == 0 and again["already_there"] == 5
    assert find(org, "Hana Head")["roles"][0]["role"] == "national_planner"


def test_only_administrators_manage_users(org):
    org.post(f"{API}/suggest-roles?commit=true", headers=ADMIN)
    rita = find(org, "Rita Rivera")["id"]
    org.post(f"{API}/{rita}/login", headers=ADMIN, json={"email": "rita@example.test"})
    regional = {"X-Forwarded-Email": "rita@example.test"}
    assert org.get(API, headers=regional).status_code == 403
    assert org.post(f"{API}/{rita}/roles", headers=regional, json={"role": "administrator"}).status_code == 403
    assert org.get(API).status_code == 401
    assert org.get(API, headers={"X-Forwarded-Email": "nobody@example.test"}).status_code == 403
