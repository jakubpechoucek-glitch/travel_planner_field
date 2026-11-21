"""Who is calling? E-mail addresses are used in memory only and never stored or logged.

The user is matched through HMAC-SHA256(lower(email)) against person.sso_key_hash.
"""

from __future__ import annotations

import hashlib
import hmac
import time
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
    scopes: tuple[tuple[str, int | None], ...] = field(default_factory=tuple)  # (role, org unit the role covers)

    @property
    def has_access(self) -> bool:
        return bool(self.roles)


SESSION_COOKIE = "tp_session"


def _sign(settings: Settings, kh: str, expires: int) -> str:
    msg = f"session|{kh}|{expires}".encode()
    return hmac.new(settings.identity_key.encode(), msg, hashlib.sha256).hexdigest()


def make_session(settings: Settings, kh: str) -> str:
    """Signed session value: key hash, expiry and signature. Contains no e-mail address."""
    expires = int(time.time()) + settings.session_hours * 3600
    return f"{kh}.{expires}.{_sign(settings, kh, expires)}"


def read_session(settings: Settings, value: str | None) -> str | None:
    try:
        kh, expires, sig = (value or "").split(".")
        if int(expires) < time.time() or not hmac.compare_digest(sig, _sign(settings, kh, int(expires))):
            return None
        return kh
    except ValueError:
        return None


def resolve_identity(request: Request) -> Identity:
    settings: Settings = request.app.state.settings
    pool: ConnectionPool = request.app.state.pool

    kh: str | None = None
    if settings.app_env == "demo":
        kh = read_session(settings, request.cookies.get(SESSION_COOKIE))
    else:
        email = request.headers.get(settings.identity_header)
        if not email and settings.app_env != "prod":
            email = settings.dev_user_email  # dev/test convenience only
        if email:
            kh = key_hash(email, settings.identity_key)
    if not kh:
        raise HTTPException(status_code=401, detail="Not signed in")

    person_id: int | None = None
    full_name: str | None = None
    roles: set[str] = set()
    scopes: tuple[tuple[str, int | None], ...] = ()
    with pool.connection() as conn:
        person = conn.execute(
            "SELECT id, full_name FROM person WHERE sso_key_hash = %s AND active", (kh,)
        ).fetchone()
        if person:
            person_id, full_name = person["id"], person["full_name"]
            rows = conn.execute(
                "SELECT role, scope_org_unit_id FROM user_role WHERE person_id = %s", (person_id,)).fetchall()
            roles.update(r["role"] for r in rows)
            scopes = tuple((r["role"], r["scope_org_unit_id"]) for r in rows)
    if kh in settings.bootstrap_hashes:
        roles.add("administrator")
    return Identity(kh, person_id, full_name, tuple(sorted(roles)), scopes)
