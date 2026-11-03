"""SQLite accounts, password verification, login tokens and registration limits."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from uuid import uuid4

from .context import AuthError, ExecutionUnavailable, Principal, RateLimited, RegistrationConflict, registration_enabled

@contextmanager
def database(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    os.chmod(path, 0o600)
    try:
        db.execute("BEGIN IMMEDIATE")
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000).hex()
    return f"pbkdf2_sha256${salt}${digest}"


class AuthStore:
    def __init__(self, path: Path | None = None):
        self.path = path or Path(os.getenv("AGENT_AUTH_DB", "runtime/auth.sqlite3")).expanduser().resolve()
        with database(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, disabled INTEGER NOT NULL DEFAULT 0)")
            db.execute("CREATE TABLE IF NOT EXISTS logins (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires_at REAL NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS login_attempts (bucket TEXT PRIMARY KEY, count INTEGER NOT NULL, expires_at REAL NOT NULL)")

    def add_user(self, username: str, password: str) -> str:
        if username == "local" or not re.fullmatch(r"[A-Za-z0-9_.@-]{1,100}", username):
            raise ValueError("Use 1–100 letters, digits, or _.@- in the username.")
        if not 12 <= len(password) <= 1024:
            raise ValueError("Use a password between 12 and 1024 characters.")
        user_id = uuid4().hex
        digest = password_hash(password)
        with database(self.path) as db:
            db.execute("INSERT INTO users(user_id,username,password_hash) VALUES (?,?,?)", (user_id, username, digest))
        return user_id

    def login(self, username: str, password: str, client: str) -> tuple[str, Principal]:
        # Bound both per-account guessing and distributed-username attempts from
        # one client. Do not hold the DB transaction during password derivation.
        with database(self.path) as db:
            db.execute("DELETE FROM login_attempts WHERE expires_at < ?", (time.time(),))
            for bucket, limit in (("user:" + username, 10), ("client:" + client, 60)):
                row = db.execute("SELECT count FROM login_attempts WHERE bucket=?", (bucket,)).fetchone()
                if row and row["count"] >= limit:
                    raise AuthError("Too many sign-in attempts. Try again in 15 minutes.")
            for bucket in ("user:" + username, "client:" + client):
                db.execute("INSERT INTO login_attempts VALUES (?,1,?) ON CONFLICT(bucket) DO UPDATE SET count=count+1", (bucket, time.time() + 900))
            user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        stored = user["password_hash"] if user else f"pbkdf2_sha256${'00' * 16}${'00' * 32}"
        _, salt, _ = stored.split("$")
        valid = hmac.compare_digest(password_hash(password[:1025], salt), stored)
        if not user or user["disabled"] or not valid or len(password) > 1024:
            raise AuthError("Invalid username or password.")
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with database(self.path) as db:
            db.execute("DELETE FROM logins WHERE expires_at < ?", (time.time(),))
            db.execute("DELETE FROM login_attempts WHERE bucket=?", ("user:" + username,))
            db.execute("INSERT INTO logins VALUES (?,?,?)", (token_hash, user["user_id"], time.time() + 8 * 3600))
        return token, Principal(user["user_id"], username, token_hash)

    def register(self, username: str, password: str, client: str) -> tuple[str, Principal]:
        if not registration_enabled():
            raise ExecutionUnavailable("Registration is disabled.")
        # Persist throttling before validation/hashing, including failed attempts.
        bucket = "register:" + client
        with database(self.path) as db:
            db.execute("DELETE FROM login_attempts WHERE expires_at < ?", (time.time(),))
            row = db.execute("SELECT count FROM login_attempts WHERE bucket=?", (bucket,)).fetchone()
            if row and row["count"] >= 5:
                raise RateLimited("Too many registration attempts. Try again in one hour.")
            db.execute("INSERT INTO login_attempts VALUES (?,1,?) ON CONFLICT(bucket) DO UPDATE SET count=count+1", (bucket, time.time() + 3600))
        try:
            self.add_user(username, password)
        except sqlite3.IntegrityError:
            raise RegistrationConflict("That username is already registered.") from None
        return self.login(username, password, client)

    def validate_login(self, token_hash: str) -> Principal:
        with database(self.path) as db:
            row = db.execute("SELECT u.user_id,u.username FROM logins l JOIN users u ON u.user_id=l.user_id WHERE l.token_hash=? AND l.expires_at>? AND u.disabled=0", (token_hash, time.time())).fetchone()
        if not row:
            raise AuthError("Your session has expired. Sign in again.")
        return Principal(row["user_id"], row["username"], token_hash)

    def authenticate(self, token: str) -> Principal:
        if not token or len(token) > 256:
            raise AuthError("Sign in to continue.")
        return self.validate_login(hashlib.sha256(token.encode()).hexdigest())

    def logout(self, principal: Principal) -> None:
        with database(self.path) as db:
            db.execute("DELETE FROM logins WHERE token_hash=?", (principal.login_id,))

    def user(self, username: str) -> Principal:
        with database(self.path) as db:
            row = db.execute("SELECT * FROM users WHERE username=? AND disabled=0", (username,)).fetchone()
        if not row:
            raise ValueError("No such active user.")
        return Principal(row["user_id"], row["username"])

    def set_password(self, username: str, password: str) -> None:
        user = self.user(username)
        if not 12 <= len(password) <= 1024:
            raise ValueError("Use a password between 12 and 1024 characters.")
        digest = password_hash(password)
        with database(self.path) as db:
            db.execute("UPDATE users SET password_hash=? WHERE user_id=?", (digest, user.user_id))
            db.execute("DELETE FROM logins WHERE user_id=?", (user.user_id,))
