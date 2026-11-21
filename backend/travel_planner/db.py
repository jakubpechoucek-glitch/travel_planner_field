"""PostgreSQL connection pool (plain PostgreSQL locally, Lakebase on Databricks)."""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import Settings

SEARCH_PATH_OPTIONS = "-c search_path=travel,public"


def _lakebase_token() -> str:
    """Return a short-lived OAuth token for the app's service principal.

    VERIFY against the current Databricks Lakebase documentation: the supported way to
    obtain the database credential may differ (for example a dedicated credential API).
    """
    from databricks.sdk import WorkspaceClient  # imported lazily: only needed in prod

    return WorkspaceClient().config.oauth_token().access_token


class LakebaseConnection(psycopg.Connection):
    """Connection that fetches a fresh token each time the pool opens a connection."""

    @classmethod
    def connect(cls, conninfo: str = "", **kwargs: Any):  # type: ignore[override]
        kwargs["password"] = _lakebase_token()
        return super().connect(conninfo, **kwargs)


def create_pool(settings: Settings) -> ConnectionPool:
    common: dict[str, Any] = {"row_factory": dict_row, "options": SEARCH_PATH_OPTIONS}
    if settings.app_env == "prod":
        conninfo = (
            f"host={settings.pghost} port={settings.pgport} dbname={settings.pgdatabase} "
            f"user={settings.pguser} sslmode={settings.pgsslmode}"
        )
        return ConnectionPool(
            conninfo,
            connection_class=LakebaseConnection,
            kwargs=common,
            min_size=1,
            max_size=10,
            max_lifetime=1800,  # recycle before the OAuth token expires
            open=False,
        )
    return ConnectionPool(
        settings.database_url or "", kwargs=common, min_size=1, max_size=5, open=False
    )
