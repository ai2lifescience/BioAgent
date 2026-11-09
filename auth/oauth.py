"""OAuth client flow for BioAgent's independent application session."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import urlencode, urlparse

import requests

from .context import AuthError, Principal
from .store import AuthStore, database, password_hash

STATE_COOKIE = "bioagent_oauth_state"


def _return_path(value: str | None) -> str:
    value = (value or "/").strip()
    if not value.startswith("/") or value.startswith("//") or "\\" in value or "\r" in value or "\n" in value:
        return "/"
    return value


def _settings() -> tuple[str, str, str, str]:
    base = os.getenv("AGENT_OAUTH_SERVER_URL", "").strip().rstrip("/")
    client_id = os.getenv("AGENT_OAUTH_CLIENT_ID", "bioagent").strip()
    secret = os.getenv("AGENT_OAUTH_CLIENT_SECRET", "").strip()
    redirect = os.getenv("AGENT_OAUTH_REDIRECT_URI", "").strip()
    parsed_base = urlparse(base)
    if (not base or parsed_base.scheme not in {"http", "https"} or not parsed_base.netloc
            or parsed_base.path or parsed_base.query or parsed_base.fragment or parsed_base.username):
        raise ValueError("AGENT_OAUTH_SERVER_URL must be an HTTP(S) origin.")
    if not client_id or len(secret) < 32:
        raise ValueError("Configure AGENT_OAUTH_CLIENT_ID and a 32-character AGENT_OAUTH_CLIENT_SECRET.")
    if not redirect:
        public = os.getenv("AGENT_PUBLIC_ORIGIN", "").strip().rstrip("/")
        if not public:
            raise ValueError("Configure AGENT_OAUTH_REDIRECT_URI or AGENT_PUBLIC_ORIGIN.")
        redirect = public + "/auth/oauth/callback"
    parsed = urlparse(redirect)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.fragment:
        raise ValueError("AGENT_OAUTH_REDIRECT_URI must be an HTTP(S) callback URL.")
    return base, client_id, secret, redirect


def _post_logout_redirect_uri() -> str:
    value = os.getenv("AGENT_OAUTH_POST_LOGOUT_REDIRECT_URI", "").strip()
    if not value:
        public = os.getenv("AGENT_PUBLIC_ORIGIN", "").strip().rstrip("/")
        value = public + "/" if public else ""
    parsed = urlparse(value)
    if (not value or parsed.scheme not in {"http", "https"} or not parsed.netloc
            or parsed.fragment or parsed.username):
        raise ValueError("AGENT_OAUTH_POST_LOGOUT_REDIRECT_URI must be an HTTP(S) URL.")
    return value


def _oauth_proxies():
    proxy = os.getenv("AGENT_OAUTH_PROXY", "").strip()
    return {"http": proxy, "https": proxy} if proxy else None


def validate_config() -> None:
    _settings()
    _post_logout_redirect_uri()


def begin_login(return_to: str | None, db_path=None) -> tuple[str, str]:
    base, client_id, _secret, redirect = _settings()
    store = AuthStore(db_path)
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    with database(store.path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS oauth_client_states "
                   "(digest TEXT PRIMARY KEY,verifier TEXT NOT NULL,return_to TEXT NOT NULL,expires_at REAL NOT NULL)")
        db.execute("DELETE FROM oauth_client_states WHERE expires_at<?", (time.time(),))
        db.execute("INSERT INTO oauth_client_states VALUES (?,?,?,?)",
                   (hashlib.sha256(state.encode()).hexdigest(), verifier, _return_path(return_to), time.time() + 600))
    query = urlencode({
        "response_type": "code", "client_id": client_id, "redirect_uri": redirect,
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
    })
    return f"{base}/authorize?{query}", state


def _exchange(code: str, verifier: str) -> dict:
    base, client_id, secret, redirect = _settings()
    proxies = _oauth_proxies()
    try:
        response = requests.post(
            base + "/oauth/token",
            data={"grant_type": "authorization_code", "client_id": client_id,
                  "client_secret": secret, "code": code, "redirect_uri": redirect,
                  "code_verifier": verifier},
            timeout=15, proxies=proxies, allow_redirects=False,
        )
        response.raise_for_status()
        access_token = response.json().get("access_token", "")
        if not isinstance(access_token, str) or not access_token:
            raise AuthError("OAuth service returned an invalid access token.")
        profile = requests.get(base + "/oauth/userinfo?client_id=" + client_id,
                              headers={"Authorization": "Bearer " + access_token},
                              timeout=15, proxies=proxies, allow_redirects=False)
        profile.raise_for_status()
        identity = profile.json()
    except AuthError:
        raise
    except Exception as exc:
        raise AuthError("BioAgent could not verify the OAuth login with the identity service.") from exc
    user_id = identity.get("user_id") or identity.get("sub")
    username = identity.get("username")
    sid = identity.get("sid")
    if (not isinstance(user_id, str) or not isinstance(username, str) or not isinstance(sid, str)
            or not user_id.strip() or not username.strip() or not sid.strip()):
        raise AuthError("OAuth identity response is missing a user ID or username.")
    email = identity.get("email", "")
    if not isinstance(email, str) or len(email) > 254:
        raise AuthError("OAuth identity response contains an invalid email.")
    return {"user_id": user_id.strip(), "username": username.strip(),
            "email": email.strip(), "sid": sid.strip()}


def begin_logout() -> str:
    base, client_id, secret, _redirect = _settings()
    try:
        response = requests.post(
            base + "/oauth/logout-request",
            data={"client_id": client_id, "client_secret": secret,
                  "post_logout_redirect_uri": _post_logout_redirect_uri()},
            timeout=15, proxies=_oauth_proxies(), allow_redirects=False,
        )
        response.raise_for_status()
        logout_url = response.json().get("logout_url", "")
    except Exception as exc:
        raise AuthError("BioAgent signed out locally, but the identity service logout is unavailable.") from exc
    if not isinstance(logout_url, str):
        raise AuthError("Identity service returned an invalid logout URL.")
    parsed_base = urlparse(base)
    parsed_logout = urlparse(logout_url)
    if (parsed_logout.scheme != parsed_base.scheme
            or parsed_logout.netloc != parsed_base.netloc or parsed_logout.path != "/logout"
            or not parsed_logout.query or parsed_logout.fragment or parsed_logout.username):
        raise AuthError("Identity service returned an invalid logout URL.")
    return logout_url


def _create_login(user_id: str, username: str, email: str, sid: str) -> tuple[str, Principal]:
    store = AuthStore()
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with database(store.path) as db:
        row = db.execute("SELECT username,email,disabled FROM users WHERE user_id=?", (user_id,)).fetchone()
        collision = db.execute("SELECT user_id FROM users WHERE username=?", (username,)).fetchone()
        if collision and collision["user_id"] != user_id:
            raise AuthError("The OAuth username is already assigned to another account.")
        if row and row["disabled"]:
            raise AuthError("This account is disabled.")
        if row:
            if row["username"] != username or row["email"] != email:
                db.execute("UPDATE users SET username=?,email=? WHERE user_id=?",
                           (username, email, user_id))
        else:
            db.execute("INSERT INTO users(user_id,username,password_hash,email) VALUES (?,?,?,?)",
                       (user_id, username, password_hash(secrets.token_urlsafe(48)), email))
        db.execute("DELETE FROM logins WHERE expires_at<?", (time.time(),))
        db.execute("INSERT INTO logins(token_hash,user_id,expires_at,sid) VALUES (?,?,?,?)",
                   (token_hash, user_id, time.time() + 8 * 3600, sid))
    return token, Principal(user_id, username, token_hash, sid)


def consume_backchannel_logout(body: bytes, signature: str) -> int:
    if not body or len(body) > 16384 or not signature.startswith("sha256="):
        raise AuthError("Invalid OAuth backchannel logout.")
    _base, _client_id, secret, _redirect = _settings()
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature[7:], expected):
        raise AuthError("Invalid OAuth backchannel logout signature.")
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthError("Invalid OAuth backchannel logout payload.") from exc
    sid = payload.get("sid") if isinstance(payload, dict) and payload.get("event") == "logout" else None
    if not isinstance(sid, str) or not sid or len(sid) > 256:
        raise AuthError("Invalid OAuth backchannel logout payload.")
    return AuthStore().revoke_sid(sid)


def complete_login(code: str, state: str, cookie_state: str, db_path=None) -> tuple[str, Principal, str]:
    if not state or not secrets.compare_digest(state, cookie_state or ""):
        raise AuthError("OAuth login state is missing or does not match.")
    digest = hashlib.sha256(state.encode()).hexdigest()
    store = AuthStore(db_path)
    with database(store.path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS oauth_client_states "
                   "(digest TEXT PRIMARY KEY,verifier TEXT NOT NULL,return_to TEXT NOT NULL,expires_at REAL NOT NULL)")
        row = db.execute("SELECT verifier,return_to,expires_at FROM oauth_client_states WHERE digest=?", (digest,)).fetchone()
        db.execute("DELETE FROM oauth_client_states WHERE digest=?", (digest,))
    if not row or row["expires_at"] < time.time():
        raise AuthError("OAuth login state expired.")
    if not code or len(code) > 256:
        raise AuthError("OAuth authorization code is invalid.")
    identity = _exchange(code, row["verifier"])
    token, principal = _create_login(
        identity["user_id"], identity["username"], identity["email"], identity["sid"]
    )
    return token, principal, _return_path(row["return_to"])
