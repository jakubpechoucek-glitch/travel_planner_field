import psycopg
import pytest
from conftest import ADMIN_EMAIL, IDENTITY_KEY, TEST_DB, make_settings
from fastapi.testclient import TestClient
from orgfixture import build_workbook

from travel_planner.identity import key_hash
from travel_planner.main import create_app

ADMIN = {"X-Forwarded-Email": ADMIN_EMAIL}


@pytest.fixture
def c(tmp_path):
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
    assert r.json()["applied"] is True
    return c


def q(sql, *args):
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        return conn.execute(sql, args).fetchall()


def gen(c, commit=False):
    r = c.post(f"/api/admin/plan/2027/generate?commit={'true' if commit else 'false'}", headers=ADMIN)
    assert r.status_code == 200, r.text
    return r.json()


def test_preview_saves_nothing(org):
    report = gen(org)
    assert report["applied"] is False and report["trips_created"] > 0
    assert q("SELECT count(*) FROM travel.trip")[0][0] == 0
    assert q("SELECT status FROM travel.plan_year WHERE year = 2027")[0][0] == "draft"
    assert any(e["event"] == "Area Management Meeting" for e in report["by_event"])
    assert report["skipped"]  # events without a schedule rule are listed, not silently dropped


def test_commit_saves_a_consistent_plan(org):
    report = gen(org, commit=True)
    rows = q("SELECT status, source, merged_into_trip_id, cancel_reason FROM travel.trip")
    live = [r for r in rows if r[0] == "generated"]
    merged = [r for r in rows if r[0] == "cancelled"]
    assert len(live) == report["trips_created"] and len(merged) == report["trips_merged"]
    assert all(r[1] == "generated" for r in rows)
    assert all(r[2] is not None and r[3] and "Combined with" in r[3] for r in merged)
    assert q("SELECT status FROM travel.plan_year WHERE year = 2027")[0][0] == "review"
    assert q("SELECT count(*) FROM travel.trip_change WHERE change_type = 'generated'")[0][0] == len(rows)
    assert q("SELECT count(*) FROM travel.audit_log WHERE action = 'plan.generate'")[0][0] == 1
    # every trip is inside the year and on weekdays
    assert q("SELECT count(*) FROM travel.trip WHERE start_date < '2027-01-01' OR end_date > '2027-12-31' "
             "OR extract(isodow FROM start_date) > 5")[0][0] == 0


def test_summary_matches_the_trips(org):
    gen(org, commit=True)
    s = org.get("/api/plan/2027/summary", headers=ADMIN).json()
    assert s["status"] == "review"
    grid = sum(sum(r["months"]) for reg in s["regions"] for r in reg["rows"]) + sum(s["nationwide"]["months"])
    assert grid == s["totals"]["trips"] > 0
    labels = [r["label"] for reg in s["regions"] for r in reg["rows"]]
    assert "Alpha 1" in labels and "Beta 1" in labels
    cluster = next(r for reg in s["regions"] for r in reg["rows"] if r["label"] == "Alpha 1")
    month = next(i + 1 for i, n in enumerate(cluster["months"]) if n)
    trips = org.get(f"/api/plan/2027/trips?unit_id={cluster['unit_id']}&month={month}", headers=ADMIN).json()
    assert len(trips) == cluster["months"][month - 1]
    detail = org.get(f"/api/plan/trips/{trips[0]['id']}", headers=ADMIN).json()
    assert detail["participants"] and {"name", "role", "travels", "position"} <= set(detail["participants"][0])


def test_regeneration_is_stable_and_keeps_edited_trips(org):
    first = gen(org, commit=True)
    total = q("SELECT count(*) FROM travel.trip")[0][0]
    # a planner moves one generated trip and gives a reason, another trip is added by hand
    trip_id, event_id, unit_id = q("SELECT id, event_type_id, visited_org_unit_id FROM travel.trip "
                                   "WHERE status = 'generated' AND visited_org_unit_id IS NOT NULL ORDER BY id LIMIT 1")[0]
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("UPDATE travel.trip SET start_date = start_date + 1, end_date = end_date + 1 WHERE id = %s", (trip_id,))
        conn.execute("INSERT INTO travel.trip_change(trip_id, change_type, reason) VALUES (%s, 'moved', 'Customer request')",
                     (trip_id,))
        conn.execute("INSERT INTO travel.trip(plan_year, event_type_id, title, start_date, end_date, status, source) "
                     "VALUES (2027, %s, 'Added by hand', '2027-02-02', '2027-02-02', 'planned', 'manual')", (event_id,))
    second = gen(org, commit=True)
    assert second["trips_kept"] == 2 and second["trips_replaced"] == first["trips_created"] + first["trips_merged"] - 1
    assert q("SELECT count(*) FROM travel.trip WHERE id = %s", trip_id)[0][0] == 1       # the edited trip survived
    assert q("SELECT count(*) FROM travel.trip WHERE title = 'Added by hand'")[0][0] == 1
    # quotas are respected: the two kept trips replace generated ones for the same event and unit
    assert q("SELECT count(*) FROM travel.trip WHERE status <> 'cancelled' AND event_type_id = %s "
             "AND visited_org_unit_id = %s", event_id, unit_id)[0][0] <= 6
    after_second = q("SELECT count(*) FROM travel.trip")[0][0]
    third = gen(org, commit=True)
    assert third["trips_created"] == second["trips_created"]                              # stable
    assert q("SELECT count(*) FROM travel.trip")[0][0] == after_second
    assert total > 0


def test_every_cluster_gets_its_six_area_meetings(org):
    gen(org, commit=True)
    # trips combined into a bigger event still count: they stay in the plan as "merged"
    rows = q("SELECT u.name, count(*) FROM travel.trip t JOIN travel.org_unit u ON u.id = t.visited_org_unit_id "
             "JOIN travel.event_type e ON e.id = t.event_type_id WHERE e.code = 'AM-FSV-MEET' GROUP BY u.name")
    assert dict(rows) == {"Alpha 1": 6, "Alpha 2": 6, "Beta 1": 6}


def test_checks_on_the_saved_plan_match_the_generation_report(org):
    report = gen(org, commit=True)
    w = org.get("/api/plan/2027/warnings", headers=ADMIN).json()
    assert w["total"] == report["warning_total"] and w["counts"] == report["warning_counts"]


def test_warnings_endpoint(org):
    gen(org, commit=True)
    w = org.get("/api/plan/2027/warnings", headers=ADMIN).json()
    assert {"total", "counts", "warnings"} <= set(w) and w["total"] == sum(w["counts"].values())
    # the seeded Lakbay rule needs 3 different clusters, the fixture has 1 or 2 per region
    assert any("Lakbay" in x["message"] for x in w["warnings"]) or "quota_short" in w["counts"]


def test_published_year_cannot_be_regenerated(org):
    gen(org, commit=True)
    q_exec = psycopg.connect(TEST_DB, autocommit=True)
    q_exec.execute("UPDATE travel.plan_year SET status = 'published' WHERE year = 2027")
    q_exec.close()
    r = org.post("/api/admin/plan/2027/generate?commit=true", headers=ADMIN)
    assert r.status_code == 409 and "published" in r.json()["detail"]


def test_errors_and_permissions(c):
    assert c.post("/api/admin/plan/2027/generate", headers=ADMIN).status_code == 409   # no organization yet
    assert c.post("/api/admin/plan/1999/generate", headers=ADMIN).status_code == 404
    stranger = {"X-Forwarded-Email": "nobody@example.test"}
    assert c.post("/api/admin/plan/2027/generate", headers=stranger).status_code == 403
    assert c.get("/api/plan/2027/summary", headers=stranger).status_code == 403
    assert c.get("/api/plan/2027/summary").status_code == 401
    assert c.get("/api/plan/trips/999999", headers=ADMIN).status_code == 404
