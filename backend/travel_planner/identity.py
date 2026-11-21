"""Who is calling? E-mail addresses are used in memory only and never stored or logged.

The user is matched through HMAC-SHA256(lower(email)) against person.sso_key_hash.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field

from fastapi import HTTPException, Request
from psycopg_pool import ConnectionPool

from .config import Settings


def key_hash(email: str, secret: str) -> str:
    """Keyed hash used to match a login to a person without storing the address."""
    return hmac.new(secret.encode(), email.strip().lower().encode(), hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class Identity:
    key_hash: str
    person_id: int | None = None
    full_name: str | None = None
    roles: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_access(self) -> bool:
        return bool(self.roles)


def resolve_identity(request: Request) -> Identity:
    settings: Settings = request.app.state.settings
    pool: ConnectionPool = request.app.state.pool

    email = request.headers.get(settings.identity_header)
    if not email and settings.app_env != "prod":
        email = settings.dev_user_email  # dev/test convenience only
    if not email:
        raise HTTPException(status_code=401, detail="Not signed in")

    kh = key_hash(email, settings.identity_key)
    person_id: int | None = None
    full_name: str | None = None
    roles: set[str] = set()
    with pool.connection() as conn:
        person = conn.execute(
            "SELECT id, full_name FROM person WHERE sso_key_hash = %s AND active", (kh,)
        ).fetchone()
        if person:
            person_id, full_name = person["id"], person["full_name"]
            rows = conn.execute("SELECT role FROM user_role WHERE person_id = %s", (person_id,)).fetchall()
            roles.update(r["role"] for r in rows)
    if kh in settings.bootstrap_hashes:
        roles.add("administrator")
    return Identity(kh, person_id, full_name, tuple(sorted(roles)))
