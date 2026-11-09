"""Standalone BioAgent login delegated to MSCAN's already verified identity."""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import time
from urllib.parse import urlencode, urlparse

from .context import AuthError, Principal
from .store import AuthStore, database

STATE_COOKIE = "bioagent_mscan_state"


def _return_path(value: str | None) -> str:
    value = (value or "/").strip()
    if (not value.startswith("/") or value.startswith("//") or "\\" in value
            or "\r" in value or "\n" in value):
        return "/"
    return value


def _required_origin(name: str) -> str:
    value = os.getenv(name, "").strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path:
        raise ValueError(f"{name} must be an HTTP(S) origin without a path.")
    return value


def enabled() -> bool:
    return bool(os.getenv("AGENT_MSCAN_LOGIN_URL", "").strip())


def begin_login(return_to: str | None) -> tuple[str, str]:
    target = os.getenv("AGENT_MSCAN_LOGIN_URL", "").strip()
    parsed = urlparse(target)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("AGENT_MSCAN_LOGIN_URL must be a valid HTTP(S) URL.")
    state = secrets.token_urlsafe(32)
    digest = hashlib.sha256(state.encode()).hexdigest()
    with database(AuthStore().path) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS mscan_login_states "
            "(digest TEXT PRIMARY KEY,return_to TEXT NOT NULL,expires_at REAL NOT NULL)"
        )
        db.execute("DELETE FROM mscan_login_states WHERE expires_at<?", (time.time(),))
        db.execute(
            "INSERT INTO mscan_login_states VALUES (?,?,?)",
            (digest, _return_path(return_to), time.time() + 300),
        )
    separator = "&" if parsed.query else "?"
    return target + separator + urlencode({"agent_sso_state": state}), state


def complete_login(code: str, state: str, cookie_state: str) -> tuple[str, Principal, str]:
    if not state or not secrets.compare_digest(state, cookie_state or ""):
        raise AuthError("MSCAN login state is missing or does not match.")
    if not re.fullmatch(r"[A-Za-z0-9._~-]{32,256}", code or ""):
        raise AuthError("Invalid MSCAN login grant.")
    digest = hashlib.sha256(state.encode()).hexdigest()
    with database(AuthStore().path) as db:
        row = db.execute(
            "SELECT return_to,expires_at FROM mscan_login_states WHERE digest=?",
            (digest,),
        ).fetchone()
        db.execute("DELETE FROM mscan_login_states WHERE digest=?", (digest,))
    if not row or row["expires_at"] < time.time():
        raise AuthError("MSCAN login state has expired.")

    from web_bridge.identity import Federation

    site = os.getenv("AGENT_MSCAN_SITE_ID", "mscan").strip()
    origin = _required_origin("AGENT_MSCAN_ORIGIN")
    token, _ = Federation().exchange(code, site, origin)
    principal = AuthStore().authenticate(token)
    return token, principal, _return_path(row["return_to"])
