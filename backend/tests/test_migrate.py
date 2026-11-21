import psycopg
from conftest import MIGRATIONS, TEST_DB, make_settings

from travel_planner.db import create_pool
from travel_planner.migrate import apply_migrations


def test_migrations_apply_once_and_are_idempotent():
    pool = create_pool(make_settings())
    pool.open(wait=True)
    try:
        first = apply_migrations(pool, MIGRATIONS)
        assert first and first[0] == "0001_baseline"
        assert apply_migrations(pool, MIGRATIONS) == []
    finally:
        pool.close()
    with psycopg.connect(TEST_DB) as conn:
        n = conn.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='travel'"
        ).fetchone()[0]
    assert n >= 22


def test_trip_constraints():
    pool = create_pool(make_settings())
    pool.open(wait=True)
    apply_migrations(pool, MIGRATIONS)
    pool.close()
    import pytest

    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("INSERT INTO travel.plan_year(year) VALUES (2027) ON CONFLICT DO NOTHING")
        conn.execute("INSERT INTO travel.event_type(code, name) VALUES ('X', 'x')")
        event_id = conn.execute("SELECT id FROM travel.event_type WHERE code = 'X'").fetchone()[0]
        with pytest.raises(psycopg.errors.CheckViolation):  # end before start
            conn.execute(
                "INSERT INTO travel.trip(plan_year, event_type_id, title, start_date, end_date)"
                f" VALUES (2027, {event_id}, 't', '2027-03-02', '2027-03-01')"
            )
        with pytest.raises(psycopg.errors.CheckViolation):  # cancelled without a reason
            conn.execute(
                "INSERT INTO travel.trip(plan_year, event_type_id, title, start_date, end_date, status)"
                " VALUES (2027, 1, 't', '2027-03-02', '2027-03-03', 'cancelled')"
            )
