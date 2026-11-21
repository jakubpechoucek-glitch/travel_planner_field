import os
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from travel_planner.config import Settings
from travel_planner.main import create_app

TEST_DB = os.environ.get("TEST_DATABASE_URL", "postgresql://tp:tp@localhost:5432/tp_test")
MIGRATIONS = Path(__file__).resolve().parents[2] / "db" / "migrations"
IDENTITY_KEY = "test-secret"
ADMIN_EMAIL = "admin@example.test"


def make_settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        database_url=TEST_DB,
        identity_key=IDENTITY_KEY,
        migrations_dir=MIGRATIONS,
        frontend_dist=Path("/nonexistent"),
        _env_file=None,
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture(autouse=True)
def clean_db():
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS travel CASCADE")
    yield


@pytest.fixture
def client():
    from travel_planner.identity import key_hash

    settings = make_settings(bootstrap_admin_hashes=key_hash(ADMIN_EMAIL, IDENTITY_KEY))
    with TestClient(create_app(settings)) as c:
        yield c
