"""Trusted website bridge used by website FunctionTools and the HTTP adapter.

The database is deliberately independent from the Agents SDK conversation
store: browser requests may outlive an SSE connection and are consumed by the
same durable job worker that is awaiting a FunctionTool result.
"""
from __future__ import annotations

import asyncio
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from uuid import uuid4


PROTOCOL = 1
REQUEST_TIMEOUT = 45
MAX_CONTEXT_BYTES = 64 * 1024
MAX_RESULT_BYTES = 512 * 1024


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_ticket(secret: str, *, site_id: str, origin: str, subject: str, ttl: int = 300) -> str:
    payload = {"site_id": site_id, "origin": origin, "sub": subject, "exp": int(time.time()) + min(max(1, ttl), 300), "jti": uuid4().hex}
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    return body + "." + _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())


def verify_ticket(token: str, secret: str, *, site_id: str, origin: str) -> dict:
    try:
        body, signature = str(token).split(".", 1)
        expected = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid ticket signature")
        payload = json.loads(_unb64(body))
    except (ValueError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("invalid website ticket") from exc
    if payload.get("site_id") != site_id or payload.get("origin") != origin or int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("expired or mismatched website ticket")
    return payload


def allowed_sites() -> dict[str, list[str]]:
    try:
        raw = json.loads(os.getenv("AGENT_WEBSITE_SITES", "{}"))
        return {str(site): [str(origin) for origin in origins] for site, origins in raw.items() if isinstance(origins, list)}
    except json.JSONDecodeError as exc:
        raise ValueError("AGENT_WEBSITE_SITES must be a JSON object") from exc


def check_site(site_id: str, origin: str) -> None:
    if origin not in allowed_sites().get(site_id, []):
        raise ValueError("website origin is not trusted for this site_id")


class WebsiteBridge:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or os.getenv("AGENT_WEBSITE_DB", "runtime/website_bridge.sqlite3")).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def db(self, write: bool = False):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _init(self) -> None:
        with self.db(True) as db:
            db.execute("CREATE TABLE IF NOT EXISTS bindings (binding_id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, site_id TEXT NOT NULL, origin TEXT NOT NULL, subject TEXT NOT NULL, session_id TEXT NOT NULL, instance_id TEXT NOT NULL, revision TEXT, context TEXT NOT NULL, capabilities TEXT NOT NULL, expires_at REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0)")
            db.execute("CREATE TABLE IF NOT EXISTS calls (call_id TEXT PRIMARY KEY, binding_id TEXT NOT NULL, run_id TEXT, method TEXT NOT NULL, arguments TEXT NOT NULL, revision TEXT, deadline REAL NOT NULL, status TEXT NOT NULL, result TEXT, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS ticket_nonces (jti TEXT PRIMARY KEY, expires_at REAL NOT NULL)")
            db.execute("CREATE INDEX IF NOT EXISTS calls_pending ON calls(binding_id,status)")

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def connect(self, *, ticket: str, site_id: str, origin: str, instance_id: str, session_id: str, context: dict, capabilities: list[str]) -> dict:
        secret = os.getenv("AGENT_WEBSITE_SECRET", "")
        if len(secret) < 32:
            raise ValueError("AGENT_WEBSITE_SECRET must be configured with at least 32 characters")
        check_site(site_id, origin)
        payload = verify_ticket(ticket, secret, site_id=site_id, origin=origin)
        if not isinstance(context, dict) or len(json.dumps(context).encode()) > MAX_CONTEXT_BYTES:
            raise ValueError("website context is invalid or too large")
        binding_id, token = uuid4().hex, secrets.token_urlsafe(32)
        with self.db(True) as db:
            try:
                db.execute("INSERT INTO ticket_nonces VALUES (?, ?)", (str(payload["jti"]), float(payload["exp"])))
            except sqlite3.IntegrityError as exc:
                raise ValueError("website ticket has already been used") from exc
            db.execute("INSERT INTO bindings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)", (binding_id, self._hash(token), site_id, origin, str(payload.get("sub", "")), session_id, instance_id, str(context.get("revision", "")), json.dumps(context), json.dumps(capabilities), time.time() + 8 * 3600))
        return {"binding_id": binding_id, "token": token, "protocol": PROTOCOL, "session_id": session_id}

    def _binding(self, binding_id: str, token: str) -> sqlite3.Row:
        with self.db() as db:
            row = db.execute("SELECT * FROM bindings WHERE binding_id=? AND token_hash=? AND revoked=0 AND expires_at>?", (binding_id, self._hash(token), time.time())).fetchone()
        if row is None:
            raise ValueError("website binding is missing, expired, or revoked")
        return row

    def context(self, binding_id: str, token: str, value: dict) -> dict:
        row = self._binding(binding_id, token)
        if not isinstance(value, dict) or len(json.dumps(value).encode()) > MAX_CONTEXT_BYTES:
            raise ValueError("website context is invalid or too large")
        with self.db(True) as db:
            db.execute("UPDATE bindings SET context=?,revision=? WHERE binding_id=?", (json.dumps(value), str(value.get("revision", "")), row["binding_id"]))
        return {"binding_id": binding_id, "revision": value.get("revision")}

    def disconnect(self, binding_id: str, token: str) -> None:
        row = self._binding(binding_id, token)
        with self.db(True) as db:
            db.execute("UPDATE bindings SET revoked=1 WHERE binding_id=?", (row["binding_id"],))

    def binding_for_run(self, binding_id: str, token: str, session_id: str) -> dict:
        row = self._binding(binding_id, token)
        if row["session_id"] != session_id:
            raise ValueError("website binding does not belong to this session")
        return {"binding_id": row["binding_id"], "token": token, "site_id": row["site_id"], "origin": row["origin"], "revision": row["revision"]}

    async def request(self, binding: dict, *, run_id: str, method: str, arguments: dict) -> dict:
        row = self._binding(binding["binding_id"], binding["token"])
        with self.db(True) as db:
            current = json.loads(row["context"])
            requested_revision = str(arguments.pop("_revision", "") or row["revision"])
            if requested_revision and requested_revision != str(current.get("revision", "")):
                raise ValueError("website page changed; refresh context before reading it")
            call_id = uuid4().hex
            db.execute("INSERT INTO calls VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', NULL, NULL, ?, ?)", (call_id, row["binding_id"], run_id, method, json.dumps(arguments), requested_revision, time.time() + REQUEST_TIMEOUT, _now(), _now()))
        deadline = time.monotonic() + REQUEST_TIMEOUT
        while time.monotonic() < deadline:
            with self.db() as db:
                call = db.execute("SELECT * FROM calls WHERE call_id=?", (call_id,)).fetchone()
            if call and call["status"] == "done":
                return json.loads(call["result"])
            if call and call["status"] == "error":
                raise ValueError(json.loads(call["error"])["message"])
            await asyncio.sleep(0.25)
        with self.db(True) as db:
            db.execute("UPDATE calls SET status='error',error=?,updated_at=? WHERE call_id=? AND status='pending'", (json.dumps({"code": "timeout", "message": "website callback timed out"}), _now(), call_id))
        raise TimeoutError("website callback timed out")

    def pending(self, binding_id: str, token: str) -> list[dict]:
        row = self._binding(binding_id, token)
        with self.db() as db:
            calls = db.execute("SELECT * FROM calls WHERE binding_id=? AND status='pending' ORDER BY created_at", (row["binding_id"],)).fetchall()
        return [{"call_id": c["call_id"], "run_id": c["run_id"], "method": c["method"], "arguments": json.loads(c["arguments"]), "revision": c["revision"], "deadline": c["deadline"]} for c in calls if c["deadline"] > time.time()]

    def respond(self, binding_id: str, token: str, call_id: str, *, result=None, error=None, revision: str = "") -> dict:
        row = self._binding(binding_id, token)
        if len(json.dumps(result if result is not None else error).encode()) > MAX_RESULT_BYTES:
            raise ValueError("website callback result is too large")
        with self.db(True) as db:
            call = db.execute("SELECT * FROM calls WHERE call_id=? AND binding_id=?", (call_id, row["binding_id"])).fetchone()
            if call is None:
                raise ValueError("unknown website call")
            if call["status"] in {"done", "error"}:
                previous = json.loads(call["result"] if call["status"] == "done" else call["error"] or "null")
                incoming = result if error is None else error
                if previous != incoming:
                    raise ValueError("conflicting duplicate website response")
                return {"call_id": call_id, "status": "done"}
            if call["status"] != "pending" or call["deadline"] < time.time():
                raise ValueError("website call is stale")
            status, value = ("error", error) if error is not None else ("done", result)
            db.execute("UPDATE calls SET status=?,result=?,error=?,updated_at=? WHERE call_id=?", (status, json.dumps(value) if result is not None else None, json.dumps(value) if error is not None else None, _now(), call_id))
        return {"call_id": call_id, "status": status, "revision": revision}

    def get_binding(self, binding_id: str, token: str) -> dict:
        row = self._binding(binding_id, token)
        return {"binding_id": row["binding_id"], "session_id": row["session_id"], "site_id": row["site_id"], "origin": row["origin"], "context": json.loads(row["context"]), "capabilities": json.loads(row["capabilities"])}


_bridge: WebsiteBridge | None = None


def get_bridge() -> WebsiteBridge:
    global _bridge
    if _bridge is None:
        _bridge = WebsiteBridge()
    return _bridge
