"""Application settings, read from environment variables.

Local development and tests use DATABASE_URL. On Databricks (Lakebase) the
connection comes from PGHOST / PGDATABASE / PGUSER and a short-lived OAuth token.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["dev", "test", "demo", "prod"] = "dev"

    # Local / test database (full connection URL). Not used in prod.
    database_url: str | None = None

    # Lakebase (prod). Password is a short-lived OAuth token, fetched at connect time.
    pghost: str | None = None
    pgport: int = 5432
    pgdatabase: str | None = None
    pguser: str | None = None
    pgsslmode: str = "require"

    # Secret used to hash SSO e-mail addresses. E-mail addresses are never stored.
    identity_key: str = ""
    # Comma-separated key hashes of the first administrator(s).
    bootstrap_admin_hashes: str = ""
    # Header carrying the signed-in user's e-mail (set by the Databricks Apps proxy).
    identity_header: str = "X-Forwarded-Email"
    # Dev only: e-mail to use when no identity header is present.
    dev_user_email: str | None = None

    # demo mode (hosting outside Databricks): sign-in with an access passcode instead of SSO
    demo_passcode: str = ""
    session_hours: int = 12
    # Demo only: while no administrator exists, the first person to sign in becomes one.
    demo_first_login_admin: bool = False

    run_migrations: bool = True
    migrations_dir: Path = REPO_ROOT / "db" / "migrations"
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"

    @model_validator(mode="after")
    def _check(self) -> Settings:
        if self.app_env == "prod":
            if not self.identity_key:
                raise ValueError("IDENTITY_KEY must be set in prod")
            if self.dev_user_email:
                raise ValueError("DEV_USER_EMAIL must not be set in prod")
            if not (self.pghost and self.pgdatabase and self.pguser):
                raise ValueError("PGHOST, PGDATABASE and PGUSER must be set in prod")
        elif self.app_env == "demo":
            if not (self.identity_key and self.demo_passcode and self.database_url):
                raise ValueError("IDENTITY_KEY, DEMO_PASSCODE and DATABASE_URL must be set in demo")
            if self.dev_user_email:
                raise ValueError("DEV_USER_EMAIL must not be set in demo")
        elif not self.database_url:
            raise ValueError("DATABASE_URL must be set when APP_ENV is dev or test")
        return self

    @property
    def bootstrap_hashes(self) -> frozenset[str]:
        return frozenset(h.strip().lower() for h in self.bootstrap_admin_hashes.split(",") if h.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
