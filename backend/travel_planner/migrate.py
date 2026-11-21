"""Apply numbered SQL migrations from db/migrations in order, exactly once each."""

from __future__ import annotations

import logging
from pathlib import Path

from psycopg_pool import ConnectionPool

log = logging.getLogger(__name__)

ADVISORY_LOCK_KEY = 726_001  # arbitrary constant: serializes concurrent app starts


def apply_migrations(pool: ConnectionPool, migrations_dir: Path) -> list[str]:
    """Apply pending migrations; return the versions applied in this call."""
    files = sorted(migrations_dir.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    applied_now: list[str] = []
    with pool.connection() as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (ADVISORY_LOCK_KEY,))
        try:
            conn.execute("CREATE SCHEMA IF NOT EXISTS travel")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS travel.schema_migration ("
                " version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
            )
            conn.commit()
            done = {r["version"] for r in conn.execute("SELECT version FROM travel.schema_migration")}
            conn.commit()
            for f in files:
                if f.stem in done:
                    continue
                log.info("Applying migration %s", f.name)
                try:
                    conn.execute(f.read_text(encoding="utf-8"))
                    conn.execute("INSERT INTO travel.schema_migration(version) VALUES (%s)", (f.stem,))
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                applied_now.append(f.stem)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (ADVISORY_LOCK_KEY,))
            conn.commit()
    return applied_now
