"""Authenticated identity and errors, independent of the application runtime."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import os

LOCAL_USER_ID = "local"
COOKIE_NAME = "bioagent_session"


class AuthError(Exception):
    status = 401


class AccessDenied(AuthError):
    status = 404


class ExecutionUnavailable(AuthError):
    status = 403


class RegistrationConflict(AuthError):
    status = 409


class RateLimited(AuthError):
    status = 429


@dataclass(frozen=True)
class Principal:
    user_id: str
    username: str = ""
    login_id: str | None = None


_principal: ContextVar[Principal | None] = ContextVar("bioagent_principal", default=None)


def registration_enabled() -> bool:
    return auth_mode() == "multiuser" and os.getenv("AGENT_REGISTRATION", "true").lower() == "true"


def auth_mode() -> str:
    mode = os.getenv("AGENT_AUTH_MODE", "local")
    if mode not in {"local", "multiuser", "cas"}:
        raise ValueError("AGENT_AUTH_MODE must be local, multiuser, or cas")
    return mode


@contextmanager
def principal_scope(principal: Principal):
    token = _principal.set(principal)
    try:
        yield principal
    finally:
        _principal.reset(token)


def current_principal() -> Principal:
    principal = _principal.get()
    if principal is None:
        if auth_mode() != "local":
            raise AuthError("Sign in to continue.")
        return Principal(LOCAL_USER_ID, "Local user")
    # Streams and long requests must stop serving data after logout/expiry.
    if principal.login_id:
        from .store import AuthStore
        AuthStore().validate_login(principal.login_id)
    return principal
