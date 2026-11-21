import psycopg
import pytest
from conftest import ADMIN_EMAIL, IDENTITY_KEY, TEST_DB, make_settings

from travel_planner.config import Settings
from travel_planner.identity import key_hash


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_me_requires_identity(client):
    assert client.get("/api/me").status_code == 401


def test_unknown_user_has_no_access(client):
    r = client.get("/api/me", headers={"X-Forwarded-Email": "nobody@example.test"})
    body = r.json()
    assert r.status_code == 200
    assert body["signed_in"] and not body["linked"] and not body["has_access"]


def test_bootstrap_admin(client):
    r = client.get("/api/me", headers={"X-Forwarded-Email": ADMIN_EMAIL.upper()})
    assert r.json()["roles"] == ["administrator"]


def test_linked_person_gets_roles_from_db(client):
    kh = key_hash("jane@example.test", IDENTITY_KEY)
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("INSERT INTO travel.person(full_name, sso_key_hash) VALUES ('Jane Test', %s)", (kh,))
        conn.execute(
            "INSERT INTO travel.user_role(person_id, role) SELECT id, 'regional_planner' FROM travel.person"
        )
    body = client.get("/api/me", headers={"X-Forwarded-Email": "Jane@Example.test"}).json()
    assert body["linked"] and body["has_access"]
    assert body["name"] == "Jane Test" and body["roles"] == ["regional_planner"]


def test_no_email_is_stored(client):
    client.get("/api/me", headers={"X-Forwarded-Email": "secret.person@example.test"})
    with psycopg.connect(TEST_DB) as conn:
        cols = conn.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'travel' AND column_name ILIKE '%mail%'"
        ).fetchall()
    assert cols == []


def test_prod_requires_secrets_and_forbids_dev_user():
    with pytest.raises(ValueError):
        Settings(app_env="prod", pghost="h", pgdatabase="d", pguser="u", _env_file=None)
    with pytest.raises(ValueError):
        Settings(app_env="prod", identity_key="k", pghost="h", pgdatabase="d", pguser="u",
                 dev_user_email="x@example.test", _env_file=None)


def test_dev_user_fallback_not_used_in_test_without_setting(client):
    assert client.get("/api/me").status_code == 401
    assert make_settings(dev_user_email="dev@example.test").dev_user_email


def _demo_client(**kw):
    from fastapi.testclient import TestClient

    from travel_planner.main import create_app

    settings = make_settings(
        app_env="demo", demo_passcode="letmein",
        bootstrap_admin_hashes=key_hash(ADMIN_EMAIL, IDENTITY_KEY), **kw,
    )
    return TestClient(create_app(settings), base_url="https://testserver")


def test_demo_login_flow():
    with _demo_client() as c:
        assert c.get("/api/auth/mode").json() == {"mode": "passcode"}
        assert c.get("/api/me").status_code == 401
        # the SSO header is ignored in demo mode
        assert c.get("/api/me", headers={"X-Forwarded-Email": ADMIN_EMAIL}).status_code == 401
        bad = c.post("/api/auth/login", json={"email": ADMIN_EMAIL, "passcode": "nope"})
        assert bad.status_code == 401
        ok = c.post("/api/auth/login", json={"email": ADMIN_EMAIL, "passcode": "letmein"})
        assert ok.status_code == 200
        assert ADMIN_EMAIL not in ok.headers.get("set-cookie", "")
        assert c.get("/api/me").json()["roles"] == ["administrator"]
        c.post("/api/auth/logout")
        assert c.get("/api/me").status_code == 401


def test_demo_rejects_forged_cookie():
    with _demo_client() as c:
        c.cookies.set("tp_session", f"{key_hash(ADMIN_EMAIL, IDENTITY_KEY)}.9999999999.deadbeef")
        assert c.get("/api/me").status_code == 401


def test_demo_requires_passcode_setting():
    with pytest.raises(ValueError):
        make_settings(app_env="demo")


def test_login_disabled_outside_demo(client):
    r = client.post("/api/auth/login", json={"email": "a@example.test", "passcode": "x"})
    assert r.status_code == 404


def test_demo_first_login_becomes_admin_only_once():
    with _demo_client(demo_first_login_admin=True) as c:
        c.post("/api/auth/login", json={"email": "first@example.test", "passcode": "letmein"})
        assert c.get("/api/me").json()["roles"] == ["administrator"]
        c.post("/api/auth/logout")
        c.post("/api/auth/login", json={"email": "second@example.test", "passcode": "letmein"})
        assert c.get("/api/me").json()["has_access"] is False
