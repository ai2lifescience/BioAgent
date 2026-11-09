"""CAS authentication using the same stable user ID as MSCAN."""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import time
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from .context import AuthError, Principal
from .store import AuthStore, database, password_hash

STATE_COOKIE = "bioagent_cas_state"
_USERNAME_KEYS = ("userName", "username", "cn", "name", "uid")


def _required_url(name: str, *, https: bool = False) -> str:
    value = os.getenv(name, "").strip()
    parsed = urlparse(value)
    if parsed.scheme not in ({"https"} if https else {"http", "https"}) or not parsed.netloc:
        raise ValueError(f"{name} must be a valid {'HTTPS' if https else 'HTTP(S)'} URL.")
    return value


def service_url() -> str:
    configured = os.getenv("AGENT_CAS_SERVICE_URL", "").strip()
    if configured:
        value = configured
    else:
        public = _required_url("AGENT_PUBLIC_ORIGIN")
        value = public.rstrip("/") + "/auth/cas/callback"
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.fragment:
        raise ValueError("AGENT_CAS_SERVICE_URL must be an HTTP(S) callback URL without a fragment.")
    return value


def _return_path(value: str | None) -> str:
    value = (value or "/").strip()
    if (not value.startswith("/") or value.startswith("//") or "\\" in value
            or "\r" in value or "\n" in value):
        return "/"
    return value


def _state_schema(db) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS cas_states "
        "(digest TEXT PRIMARY KEY, return_to TEXT NOT NULL, expires_at REAL NOT NULL)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS cas_logins "
        "(ticket_hash TEXT PRIMARY KEY, token_hash TEXT NOT NULL, user_id TEXT)"
    )
    columns = {row["name"] for row in db.execute("PRAGMA table_info(cas_logins)").fetchall()}
    if "user_id" not in columns:
        db.execute("ALTER TABLE cas_logins ADD COLUMN user_id TEXT")


def begin_login(return_to: str | None) -> tuple[str, str]:
    state = secrets.token_urlsafe(32)
    digest = hashlib.sha256(state.encode()).hexdigest()
    with database(AuthStore().path) as db:
        _state_schema(db)
        db.execute("DELETE FROM cas_states WHERE expires_at<?", (time.time(),))
        db.execute(
            "INSERT INTO cas_states VALUES (?,?,?)",
            (digest, _return_path(return_to), time.time() + 300),
        )
    callback = service_url() + ("&" if "?" in service_url() else "?") + urlencode({"state": state})
    login = _required_url("AGENT_CAS_LOGIN_URL", https=True)
    separator = "&" if "?" in login else "?"
    return login + separator + urlencode({"service": callback}), state


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _validate_ticket(ticket: str, callback: str) -> tuple[str, str]:
    if not re.fullmatch(r"[A-Za-z0-9._~-]{8,512}", ticket or ""):
        raise AuthError("Invalid CAS service ticket.")
    validate = _required_url("AGENT_CAS_VALIDATE_URL", https=True)
    url = validate + ("&" if "?" in validate else "?") + urlencode({"ticket": ticket, "service": callback})
    try:
        with urlopen(Request(url, headers={"Accept": "application/xml"}), timeout=10) as response:
            data = response.read(1024 * 1024 + 1)
    except Exception as exc:
        raise AuthError("CAS ticket validation is unavailable.") from exc
    if len(data) > 1024 * 1024:
        raise AuthError("CAS validation response is too large.")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise AuthError("CAS returned an invalid validation response.") from exc
    success = next((node for node in root.iter() if _local_name(node.tag) == "authenticationSuccess"), None)
    if success is None:
        raise AuthError("CAS rejected the service ticket.")
    principal = next((node.text.strip() for node in success.iter()
                      if _local_name(node.tag) == "user" and node.text and node.text.strip()), "")
    attributes: dict[str, str] = {}
    for node in success.iter():
        name = _local_name(node.tag)
        if name not in {"authenticationSuccess", "attributes", "user"} and node.text and node.text.strip():
            attributes.setdefault(name, node.text.strip())
    user_id = attributes.get("userId", "").strip()
    username = next((attributes.get(key, "").strip() for key in _USERNAME_KEYS
                     if attributes.get(key, "").strip()), principal or user_id)
    if not user_id or len(user_id) > 128 or not username or len(username) > 100:
        raise AuthError("CAS assertion does not contain a valid userId and username.")
    if any(ord(char) < 32 for char in user_id + username):
        raise AuthError("CAS assertion contains invalid identity characters.")
    return user_id, username


def _create_login(user_id: str, username: str, ticket: str) -> tuple[str, Principal]:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with database(AuthStore().path) as db:
        _state_schema(db)
        row = db.execute("SELECT user_id,username,disabled FROM users WHERE user_id=?", (user_id,)).fetchone()
        collision = db.execute("SELECT user_id FROM users WHERE username=?", (username,)).fetchone()
        if collision and collision["user_id"] != user_id:
            raise AuthError("The CAS username is already assigned to another account.")
        if row and row["disabled"]:
            raise AuthError("This account is disabled.")
        if row:
            if row["username"] != username:
                db.execute("UPDATE users SET username=? WHERE user_id=?", (username, user_id))
        else:
            db.execute(
                "INSERT INTO users(user_id,username,password_hash) VALUES (?,?,?)",
                (user_id, username, password_hash(secrets.token_urlsafe(48))),
            )
        db.execute("DELETE FROM logins WHERE expires_at<?", (time.time(),))
        db.execute("INSERT INTO logins VALUES (?,?,?)", (token_hash, user_id, time.time() + 8 * 3600))
        db.execute(
            "INSERT INTO cas_logins(ticket_hash,token_hash,user_id) VALUES (?,?,?) "
            "ON CONFLICT(ticket_hash) DO UPDATE SET "
            "token_hash=excluded.token_hash,user_id=excluded.user_id",
            (hashlib.sha256(ticket.encode()).hexdigest(), token_hash, user_id),
        )
    return token, Principal(user_id, username, token_hash)


def complete_login(ticket: str, state: str, cookie_state: str) -> tuple[str, Principal, str]:
    if not state or not secrets.compare_digest(state, cookie_state or ""):
        raise AuthError("CAS login state is missing or does not match.")
    digest = hashlib.sha256(state.encode()).hexdigest()
    with database(AuthStore().path) as db:
        _state_schema(db)
        row = db.execute("SELECT return_to,expires_at FROM cas_states WHERE digest=?", (digest,)).fetchone()
        db.execute("DELETE FROM cas_states WHERE digest=?", (digest,))
    if not row or row["expires_at"] < time.time():
        raise AuthError("CAS login state has expired.")
    callback = service_url() + ("&" if "?" in service_url() else "?") + urlencode({"state": state})
    user_id, username = _validate_ticket(ticket, callback)
    token, principal = _create_login(user_id, username, ticket)
    return token, principal, _return_path(row["return_to"])


def consume_single_logout(body: bytes, content_type: str) -> str:
    if len(body) > 64 * 1024:
        raise AuthError("CAS logout request is too large.")
    text = body.decode("utf-8", "strict")
    if "application/x-www-form-urlencoded" in content_type:
        text = (parse_qs(text).get("logoutRequest") or [""])[0]
    match = re.search(r"<(?:\w+:)?SessionIndex>\s*([^<\s]{8,512})\s*</(?:\w+:)?SessionIndex>", text)
    if not match:
        raise AuthError("Invalid CAS single logout request.")
    ticket_hash = hashlib.sha256(match.group(1).encode()).hexdigest()
    with database(AuthStore().path) as db:
        _state_schema(db)
        row = db.execute("SELECT token_hash,user_id FROM cas_logins WHERE ticket_hash=?", (ticket_hash,)).fetchone()
        if row:
            db.execute("DELETE FROM logins WHERE token_hash=?", (row["token_hash"],))
            db.execute("DELETE FROM cas_logins WHERE ticket_hash=?", (ticket_hash,))
    return row["user_id"] if row and row["user_id"] else ""


def logout_url() -> str:
    target = _required_url("AGENT_CAS_LOGOUT_URL", https=True)
    return_to = os.getenv("AGENT_CAS_LOGOUT_RETURN_URL", "").strip() or _required_url("AGENT_PUBLIC_ORIGIN")
    separator = "&" if "?" in target else "?"
    return target + separator + urlencode({"service": return_to})
