import psycopg
import pytest
from budgetfixture import build_budget
from conftest import ADMIN_EMAIL, IDENTITY_KEY, TEST_DB, make_settings
from fastapi.testclient import TestClient
from orgfixture import build_workbook

from travel_planner.identity import key_hash
from travel_planner.main import create_app

ADMIN = {"X-Forwarded-Email": ADMIN_EMAIL}
RITA = {"X-Forwarded-Email": "rita.rivera@example.test"}
AMY = {"X-Forwarded-Email": "amy.alvarez@example.test"}
SAM = {"X-Forwarded-Email": "sam.stone@example.test"}


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
        c.post("/api/admin/users/suggest-roles?commit=true", headers=ADMIN)
        for name, mail in (("Rita Rivera", "rita.rivera@example.test"), ("Amy Alvarez", "amy.alvarez@example.test"),
                           ("Sam Stone", "sam.stone@example.test")):
            c.post(f"/api/admin/users/{users[name]}/login", headers=ADMIN, json={"email": mail})
        c.post(f"/api/admin/users/{users['Sam Stone']}/roles", headers=ADMIN, json={"role": "viewer"})
        assert c.post("/api/admin/plan/2027/generate?commit=true", headers=ADMIN).status_code == 200
        yield c


def forecast(c, headers=ADMIN, **params):
    r = c.get("/api/cost/2027/forecast", headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def region_id(c, name):
    return next(r["id"] for r in c.get("/api/cost/config", headers=ADMIN).json()["regions"] if r["name"] == name)


def test_the_starting_rate_card_comes_from_the_budget(plan):
    cfg = plan.get("/api/cost/config", headers=ADMIN).json()
    rates = {(r["rate_kind"], r["position"]): r["amount"] for r in cfg["rates"]}
    assert rates[("airfare", None)] == 20000 and rates[("local_transport", None)] == 2500
    assert rates[("lodging_per_night", None)] == 3000 and rates[("lodging_per_night", "Head of Nationwide Field")] == 5000
    assert rates[("per_diem", None)] == 600
    assert {r["name"] for r in cfg["regions"]} == {"North", "South"} and cfg["modes"] == [] and cfg["tiers"] == []


def test_without_travel_modes_the_forecast_says_it_is_guessing(plan):
    f = forecast(plan)
    assert f["assumptions"]["modes_loaded"] is False
    assert f["assumptions"]["assumed_mode_person_trips"] > 0
    assert f["totals"]["cost"] > 0 and f["totals"]["person_trips"] > 0


def test_the_conference_follows_the_budget_formula(plan):
    north = region_id(plan, "North")
    assert plan.post("/api/admin/cost/modes/suggest", headers=ADMIN).json()["added"] == 4
    assert plan.put("/api/admin/cost/settings", headers=ADMIN,
                    json={"hq_region_id": north, "venue_region_id": north}).status_code == 200
    f = forecast(plan)
    conf = next(e for e in f["by_event"] if e["event"] == "Collection Conference")
    # 2 days, 1 night. Two AMs and one RM from the North, the Head based in the North: by land.
    #   AM / RM: 1 x 3,000 + 2,500 + 2 x 600 = 6,700;  Head: 1 x 5,000 + 2,500 + 2 x 600 = 8,700
    # The RM of the South flies: 20,000 + 3,000 + 2,500 + 1,200 = 26,700
    assert conf["person_trips"] == 5 and conf["cost"] == 3 * 6700 + 8700 + 26700
    assert f["by_mode"]["air"]["person_trips"] >= 1


def test_all_the_breakdowns_add_up(plan):
    plan.post("/api/admin/cost/modes/suggest", headers=ADMIN)
    f = forecast(plan)
    total = f["totals"]["cost"]
    assert round(sum(m["cost"] for m in f["by_month"]), 2) == total
    assert round(sum(e["cost"] for e in f["by_event"]), 2) == total
    assert round(sum(p["cost"] for p in f["by_place"]), 2) == total
    assert round(sum(p["cost"] for p in f["by_position"]), 2) == total
    assert sum(v["person_trips"] for v in f["by_mode"].values()) == f["totals"]["person_trips"]
    summary = plan.get("/api/plan/2027/summary", headers=ADMIN).json()
    assert f["totals"]["trips"] == summary["totals"]["trips"]
    travelers = q("SELECT count(*) FROM travel.trip_participant tp JOIN travel.trip t ON t.id = tp.trip_id "
                  "WHERE tp.travels AND t.status <> 'cancelled' AND t.merged_into_trip_id IS NULL")[0][0]
    assert f["totals"]["person_trips"] == travelers
    assert abs(f["totals"]["avg_per_person_trip"] - total / travelers) < 0.01


def test_early_booking_needs_tiers_from_the_business(plan):
    plan.post("/api/admin/cost/modes/suggest", headers=ADMIN)
    north = region_id(plan, "North")
    plan.put("/api/admin/cost/settings", headers=ADMIN, json={"hq_region_id": north, "venue_region_id": north})
    none = forecast(plan)["early_booking"]
    assert none["has_tiers"] is False and none["saving"] == 0 and none["fares_without_discount"] > 0
    tiers = [{"min_days_ahead": 30, "factor": 0.9}, {"min_days_ahead": 60, "factor": 0.8}]
    assert plan.put("/api/admin/cost/booking-tiers", headers=ADMIN, json={"tiers": tiers}).status_code == 200
    eb = forecast(plan, book_ahead_days=60)["early_booking"]
    assert eb["has_tiers"] and eb["target_days"] == 60 and eb["factor_at_target"] == 0.8
    assert eb["fares_if_booked_ahead"] == round(eb["fares_without_discount"] * 0.8, 2)
    assert eb["saving"] == round(eb["fares"] - eb["fares_if_booked_ahead"], 2) >= 0
    assert forecast(plan)["early_booking"]["target_days"] == 60                      # default: the longest tier
    bad = plan.put("/api/admin/cost/booking-tiers", headers=ADMIN,
                   json={"tiers": [{"min_days_ahead": 30, "factor": 0.8}, {"min_days_ahead": 60, "factor": 0.9}]})
    assert bad.status_code == 422 and "dearer" in bad.json()["detail"]
    assert plan.put("/api/admin/cost/booking-tiers", headers=ADMIN, json={"tiers": [
        {"min_days_ahead": 30, "factor": 0.9}, {"min_days_ahead": 30, "factor": 0.8}]}).status_code == 422
    assert plan.put("/api/admin/cost/booking-tiers", headers=ADMIN, json={"tiers": [
        {"min_days_ahead": 30, "factor": 1.5}]}).status_code == 422


def test_a_new_rate_closes_the_old_one_and_changes_the_forecast(plan):
    plan.post("/api/admin/cost/modes/suggest", headers=ADMIN)
    before = forecast(plan)["totals"]["cost"]
    new = {"rate_kind": "per_diem", "amount": 700, "valid_from": "2027-07-01", "note": "New policy"}
    assert plan.post("/api/admin/cost/rates", headers=ADMIN, json=new).status_code == 201
    rows = [r for r in plan.get("/api/cost/config", headers=ADMIN).json()["rates"] if r["rate_kind"] == "per_diem"]
    assert [(r["amount"], r["valid_to"]) for r in rows] == [(600.0, "2027-06-30"), (700.0, None)]
    assert forecast(plan)["totals"]["cost"] > before
    assert plan.post("/api/admin/cost/rates", headers=ADMIN, json={**new, "valid_from": "2027-03-01"}).status_code == 409
    assert plan.post("/api/admin/cost/rates", headers=ADMIN, json={**new, "amount": -5}).status_code == 422
    new_id = next(r["id"] for r in rows if r["amount"] == 700.0)
    assert plan.delete(f"/api/admin/cost/rates/{new_id}", headers=ADMIN).status_code == 204
    assert plan.delete(f"/api/admin/cost/rates/{new_id}", headers=ADMIN).status_code == 404


def test_a_missing_rate_is_reported(plan):
    q("DELETE FROM travel.cost_rate WHERE rate_kind = 'airfare'")
    plan.post("/api/admin/cost/modes/suggest", headers=ADMIN)
    f = forecast(plan)
    assert "airfare (air)" in f["assumptions"]["missing_rates"] or f["by_mode"].get("air", {}).get("person_trips", 0) == 0


def test_an_island_can_be_set_to_always_need_a_flight(plan):
    plan.post("/api/admin/cost/modes/suggest", headers=ADMIN)
    before = forecast(plan)
    cluster = q("SELECT id FROM travel.org_unit WHERE name = 'Alpha 1'")[0][0]
    r = plan.post("/api/admin/cost/overrides", headers=ADMIN, json={"to_unit_id": cluster, "mode": "air",
                                                                     "note": "By plane"})
    assert r.status_code == 201
    after = forecast(plan)
    assert after["totals"]["cost"] > before["totals"]["cost"]
    assert after["by_mode"]["air"]["person_trips"] > before["by_mode"].get("air", {"person_trips": 0})["person_trips"]
    assert plan.delete(f"/api/admin/cost/overrides/{r.json()['id']}", headers=ADMIN).status_code == 204
    assert forecast(plan)["totals"]["cost"] == before["totals"]["cost"]
    assert plan.post("/api/admin/cost/overrides", headers=ADMIN, json={"to_unit_id": 99999, "mode": "air"}).status_code == 422


def test_the_budget_is_imported_and_compared(plan, tmp_path):
    plan.post("/api/admin/cost/modes/suggest", headers=ADMIN)
    path = tmp_path / "budget.xlsx"
    build_budget(path)

    def upload(commit):
        with open(path, "rb") as fh:
            return plan.post(f"/api/admin/budget/import?year=2027&commit={commit}", headers=ADMIN,
                             files={"file": ("budget.xlsx", fh, "application/vnd.ms-excel")})

    preview = upload("false").json()
    expected = 4 * 4 * 30300 + 1 * 8 * 34300 + 10 * 4 * 10800 + 12 * 1 * 30300 + 120000
    assert preview["applied"] is False and preview["lines"] == 5 and preview["total"] == expected
    assert preview["unmatched_lines"] == 1 and preview["unmatched_total"] == 120000
    assert q("SELECT count(*) FROM travel.budget_line")[0][0] == 0                         # a preview saves nothing
    assert upload("true").json()["applied"] is True
    assert upload("true").json()["lines"] == 5 and q("SELECT count(*) FROM travel.budget_line")[0][0] == 5   # replaced
    lines = plan.get("/api/cost/2027/budget", headers=ADMIN).json()
    assert len(lines) == 5 and lines[0]["event"] == "Area Visit"
    cmp_ = forecast(plan)["budget"]
    assert cmp_["budget_total"] == expected and cmp_["unmatched"] == 120000
    by = {r["event"]: r for r in cmp_["rows"]}
    visit = by["Area Visit"]
    assert visit["budget_cost"] == 4 * 4 * 30300 and visit["budget_person_trips"] == 16
    assert visit["forecast_cost"] > 0 and visit["difference"] == round(visit["forecast_cost"] - visit["budget_cost"], 2)
    assert "Not matched to an event" in by
    assert round(sum(r["forecast_cost"] for r in cmp_["rows"]), 2) == cmp_["forecast_total"] == forecast(plan)["totals"]["cost"]
    # the unmatched line can be matched by hand
    unmatched = next(line for line in lines if line["event_type_id"] is None)
    meet = q("SELECT id FROM travel.event_type WHERE code = 'AM-FSV-MEET'")[0][0]
    assert plan.put(f"/api/admin/budget/lines/{unmatched['id']}", headers=ADMIN, json={"event_type_id": meet}).status_code == 200
    assert forecast(plan)["budget"]["unmatched"] == 0
    assert plan.put(f"/api/admin/budget/lines/{unmatched['id']}", headers=ADMIN, json={"event_type_id": 99999}).status_code == 422


def test_bad_budget_files_are_refused(plan, tmp_path):
    empty = tmp_path / "empty.xlsx"
    build_budget(empty, no_table=True)
    with open(empty, "rb") as fh:
        r = plan.post("/api/admin/budget/import?year=2027", headers=ADMIN,
                      files={"file": ("empty.xlsx", fh, "application/vnd.ms-excel")})
    assert r.status_code == 422 and "No budget table" in r.json()["detail"]
    assert plan.post("/api/admin/budget/import?year=2027", headers=ADMIN,
                     files={"file": ("notes.txt", b"hi", "text/plain")}).status_code == 400
    assert plan.post("/api/admin/budget/import?year=2027", headers=ADMIN,
                     files={"file": ("x.xlsx", b"not a zip", "application/octet-stream")}).status_code == 400


def test_a_regional_planner_sees_only_their_region_and_no_budget(plan, tmp_path):
    plan.post("/api/admin/cost/modes/suggest", headers=ADMIN)
    path = tmp_path / "budget.xlsx"
    build_budget(path)
    with open(path, "rb") as fh:
        plan.post("/api/admin/budget/import?year=2027&commit=true", headers=ADMIN,
                  files={"file": ("budget.xlsx", fh, "application/vnd.ms-excel")})
    whole, mine = forecast(plan), forecast(plan, headers=RITA)
    assert 0 < mine["totals"]["cost"] < whole["totals"]["cost"]
    assert mine["budget"] is None and whole["budget"] is not None
    assert not any("Beta 1" in p["place"] or p["place"].startswith("South") for p in mine["by_place"])
    assert plan.get("/api/cost/2027/budget", headers=RITA).status_code == 403
    assert plan.get("/api/cost/config", headers=RITA).status_code == 200
    assert plan.post("/api/admin/cost/rates", headers=RITA,
                     json={"rate_kind": "per_diem", "amount": 1, "valid_from": "2030-01-01"}).status_code == 403


def test_who_sees_costs(plan):
    assert plan.get("/api/cost/2027/forecast").status_code == 401
    for headers in (AMY, SAM, {"X-Forwarded-Email": "nobody@example.test"}):
        assert plan.get("/api/cost/2027/forecast", headers=headers).status_code == 403   # costs are for managers
        assert plan.get("/api/cost/config", headers=headers).status_code == 403
    assert plan.get("/api/cost/2030/forecast", headers=ADMIN).status_code == 404
    assert plan.get("/api/cost/2027/forecast?book_ahead_days=0", headers=ADMIN).status_code == 422


def test_changes_are_in_the_audit_log(plan):
    plan.post("/api/admin/cost/modes/suggest", headers=ADMIN)
    plan.put("/api/admin/cost/booking-tiers", headers=ADMIN, json={"tiers": [{"min_days_ahead": 30, "factor": 0.9}]})
    actions = {r[0] for r in q("SELECT action FROM travel.audit_log WHERE action LIKE 'cost.%%'")}
    assert {"cost.mode.suggest", "cost.tiers"} <= actions


def test_everything_is_in_philippine_pesos(plan):
    cfg = plan.get("/api/cost/config", headers=ADMIN).json()
    f = forecast(plan)
    assert cfg["currency"] == f["currency"] == "PHP" and cfg["currency_symbol"] == f["currency_symbol"] == "\u20b1"
    assert {r["currency"] for r in cfg["rates"]} == {"PHP"}
    # the database refuses any other currency ...
    with pytest.raises(psycopg.errors.CheckViolation):
        q("INSERT INTO travel.cost_rate(rate_kind, amount, currency, valid_from) VALUES ('per_diem', 1, 'USD', '2030-01-01')")
    # ... and so does the API: a currency field is refused, not silently ignored
    body = {"rate_kind": "per_diem", "amount": 700, "valid_from": "2030-01-01"}
    assert plan.post("/api/admin/cost/rates", headers=ADMIN, json={**body, "currency": "USD"}).status_code == 422
    assert plan.post("/api/admin/cost/rates", headers=ADMIN, json=body).status_code == 201
