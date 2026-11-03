"""Authentication and resource ownership shared by all application entry points."""
from .context import (
    AccessDenied, AuthError, COOKIE_NAME, ExecutionUnavailable, LOCAL_USER_ID,
    Principal, RateLimited, RegistrationConflict, auth_mode, current_principal,
    principal_scope, registration_enabled,
)
from .ownership import OwnershipStore
from .store import AuthStore, database, password_hash

__all__ = [
    "AccessDenied", "AuthError", "AuthStore", "COOKIE_NAME", "ExecutionUnavailable",
    "LOCAL_USER_ID", "OwnershipStore", "Principal", "RateLimited", "RegistrationConflict",
    "auth_mode", "current_principal", "database", "password_hash", "principal_scope",
    "registration_enabled",
]
