from datetime import date

import psycopg
import pytest
from conftest import ADMIN_EMAIL, IDENTITY_KEY, MIGRATIONS, TEST_DB, make_settings
from fastapi.testclient import TestClient
from orgfixture import build_workbook

from travel_planner.db import create_pool
from travel_planner.identity import key_hash
from travel_planner.main import create_app
from travel_planner.migrate import apply_migrations
from travel_planner.orgimport import parse_workbook, run_import

JAN = date(2027, 1, 1)


@pytest.fixture
def pool():
    p = create_pool(make_settings())
    p.open(wait=True)
    apply_migrations(p, MIGRATIONS)
    yield p
    p.close()


@pytest.fixture
def xlsx(tmp_path):
    path = tmp_path / "org.xlsx"
    build_workbook(path)
    return path


def q(sql, *args):
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        return conn.execute(sql, args).fetchall()


def codes(report, level=None):
    return [i["code"] for i in report["issues"] if level in (None, i["level"])]


def test_parse_structure(xlsx):
    org = parse_workbook(xlsx)
    assert not org.has_errors
    assert sorted(org.regions.values()) == ["North", "South"]
    assert len(org.clusters) == 3
    assert {p.position for p in org.people.values()} == {"HEAD", "RM", "AM", "FSV", "FSV2", "SFSV", "DM"}
    assert org.people["sue smith"].name == "Sue Smith"  # NBSP removed, ALL CAPS prettified
    # Beta 1 has no AM: the Regional Manager acts, and leads the cluster
    assert org.cluster_lead["beta 1"] == "ramon reyes"
    assert "acting_am" in [i.code for i in org.issues]
    # the cluster table wins over the employee list; the difference is reported
    assert org.people["sue smith"].manager_key == "alan abad"
    assert "manager_differs" in [i.code for i in org.issues]
    # a person only in the employee list gets cluster and manager from their office
    only = org.people["only list"]
    assert (only.cluster, only.manager_key, only.employee_no) == ("beta 1", "ramon reyes", "1004")
    assert org.people["ramon reyes"].manager_key == "hana head"


def test_preview_saves_nothing_and_commit_saves(pool, xlsx):
    preview = run_import(pool, xlsx, JAN, commit=False)
    assert not preview["applied"] and preview["summary"]["people_created"] == 10
    assert q("SELECT count(*) FROM travel.person")[0][0] == 0

    done = run_import(pool, xlsx, JAN, commit=True)
    assert done["applied"] and done["errors"] == 0
    assert q("SELECT count(*) FROM travel.person")[0][0] == 10
    assert q("SELECT count(*) FROM travel.audit_log WHERE action = 'org.import'")[0][0] == 1
    leads = dict(q("SELECT o.name, p.full_name FROM travel.org_unit o JOIN travel.person p ON p.id = o.lead_person_id"))
    assert leads["Alpha 2"] == "Alan Abad" and leads["Beta 1"] == "Ramon Reyes" and leads["North"] == "Rita Rivera"
    mgr = q("SELECT m.full_name FROM travel.person_assignment a JOIN travel.person p ON p.id = a.person_id "
            "JOIN travel.person m ON m.id = a.manager_id WHERE p.full_name = 'Sue Smith' AND a.valid_to IS NULL")
    assert mgr == [("Alan Abad",)]


def test_import_is_idempotent(pool, xlsx):
    run_import(pool, xlsx, JAN, commit=True)
    again = run_import(pool, xlsx, JAN, commit=True)["summary"]
    assert again["people_unchanged"] == 10 and again["assignments_unchanged"] == 10
    assert not any(k.endswith(("_created", "_updated", "_changed")) for k in again)
    assert q("SELECT count(*) FROM travel.person_assignment")[0][0] == 10


def test_change_with_later_effective_date_keeps_history(pool, tmp_path, xlsx):
    run_import(pool, xlsx, JAN, commit=True)
    moved = tmp_path / "moved.xlsx"
    build_workbook(moved, move_bob=True)
    report = run_import(pool, moved, date(2027, 7, 1), commit=True)
    # Bob moved; "Only List" shared his office and loses the cluster that was derived from it
    assert report["summary"]["assignments_changed"] == 2
    rows = q("SELECT valid_from, valid_to FROM travel.person_assignment a JOIN travel.person p ON p.id = a.person_id "
             "WHERE p.full_name = 'Bob Beta' ORDER BY valid_from")
    assert rows == [(date(2027, 1, 1), date(2027, 6, 30)), (date(2027, 7, 1), None)]


def test_errors_block_saving(pool, tmp_path):
    bad = tmp_path / "bad.xlsx"
    build_workbook(bad, bad_position=True)
    report = run_import(pool, bad, JAN, commit=True)
    assert not report["applied"] and "unknown_position" in codes(report, "error")
    assert "not_applied" in codes(report)
    assert q("SELECT count(*) FROM travel.person")[0][0] == 0


def test_missing_tables_reported(pool, tmp_path):
    empty = tmp_path / "empty.xlsx"
    build_workbook(empty, no_tables=True)
    report = run_import(pool, empty, JAN, commit=True)
    assert not report["applied"] and "missing_blocks" in codes(report, "error")


def test_no_contact_data_is_stored(pool, xlsx):
    run_import(pool, xlsx, JAN, commit=True)
    dump = str(q("SELECT * FROM travel.person")) + str(q("SELECT * FROM travel.audit_log"))
    assert "90870" not in dump and "@" not in dump and "sam.stone" not in dump


def _upload(client, path, headers, **params):
    with open(path, "rb") as fh:
        return client.post("/api/admin/org-import", params=params, headers=headers,
                           files={"file": ("org.xlsx", fh, "application/vnd.ms-excel")})


def test_api_import_and_tree(xlsx):
    admin = {"X-Forwarded-Email": ADMIN_EMAIL}
    settings = make_settings(bootstrap_admin_hashes=key_hash(ADMIN_EMAIL, IDENTITY_KEY))
    with TestClient(create_app(settings)) as c:
        r = _upload(c, xlsx, admin, effective_date="2027-01-01")
        assert r.status_code == 200 and r.json()["applied"] is False
        assert q("SELECT count(*) FROM travel.person")[0][0] == 0
        r = _upload(c, xlsx, admin, effective_date="2027-01-01", commit="true")
        assert r.json()["applied"] is True
        tree = c.get("/api/org/tree", headers=admin).json()
        north = next(x for x in tree["regions"] if x["name"] == "North")
        assert north["lead"] == "Rita Rivera"
        alpha2 = next(x for x in north["clusters"] if x["name"] == "Alpha 2")
        assert alpha2["lead"] == "Alan Abad" and alpha2["supervisors"] == 1 and alpha2["offices"] == ["Port Two"]


def test_api_permissions(xlsx):
    settings = make_settings(bootstrap_admin_hashes=key_hash(ADMIN_EMAIL, IDENTITY_KEY))
    with TestClient(create_app(settings)) as c:
        stranger = {"X-Forwarded-Email": "nobody@example.test"}
        assert _upload(c, xlsx, stranger).status_code == 403
        assert c.get("/api/org/tree", headers=stranger).status_code == 403
        assert c.get("/api/org/tree").status_code == 401
        bad = c.post("/api/admin/org-import", headers={"X-Forwarded-Email": ADMIN_EMAIL},
                     files={"file": ("notes.txt", b"hello", "text/plain")})
        assert bad.status_code == 400
        broken = c.post("/api/admin/org-import", headers={"X-Forwarded-Email": ADMIN_EMAIL},
                        files={"file": ("x.xlsx", b"not a zip", "application/octet-stream")})
        assert broken.status_code == 400
