"""Application session metadata alongside SDK SQLite conversation sessions."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from threading import Lock, RLock
from typing import Any
from uuid import uuid4


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SessionMetadata:
    """Application metadata only. Conversation messages live in SQLiteSession."""

    session_id: str
    user_request: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now)
    updated_at: str = field(default_factory=now)


class SessionMetadataStore:
    def __init__(self, root: str | Path = "runtime/session_metadata") -> None:
        self.root = Path(root)
        self._sessions: dict[str, SessionMetadata] = {}
        self._locks: dict[str, Lock] = {}
        self._lock = RLock()

    def _path(self, session_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
            raise ValueError("Invalid session_id; use letters, digits, underscores, or hyphens.")
        return self.root / f"{session_id}.json"

    def save(self, session: SessionMetadata) -> None:
        with self._lock:
            path = self._path(session.session_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(f".{uuid4().hex}.tmp")
            temporary.write_text(json.dumps(asdict(session), ensure_ascii=False, indent=2), encoding="utf-8")
            os.chmod(temporary, 0o600)
            temporary.replace(path)

    def create_session(self, user_request: str = "", session_id: str | None = None) -> SessionMetadata:
        with self._lock:
            identifier = str(session_id or uuid4()).strip()
            self._path(identifier)
            session = SessionMetadata(session_id=identifier, user_request=user_request)
            session.metadata["title"] = " ".join(user_request.split())[:64] or "New chat"
            self._sessions[identifier] = session
            self._locks.setdefault(identifier, Lock())
            self.save(session)
            return session

    def get_session(self, session_id: str) -> SessionMetadata | None:
        with self._lock:
            if session_id in self._sessions:
                return self._sessions[session_id]
            path = self._path(session_id)
            if not path.exists():
                return None
            session = SessionMetadata(**json.loads(path.read_text(encoding="utf-8")))
            self._sessions[session_id] = session
            self._locks.setdefault(session_id, Lock())
            return session

    def get_or_create_session(self, session_id: str | None, user_request: str = "") -> tuple[SessionMetadata, bool]:
        with self._lock:
            session = self.get_session(session_id) if session_id else None
            if session is not None:
                return session, False
            return self.create_session(user_request, session_id), True

    def _session_lock(self, session_id: str) -> Lock:
        with self._lock:
            return self._locks.setdefault(session_id, Lock())

    @contextmanager
    def locked_session(self, session_id: str | None, user_request: str = ""):
        session, created = self.get_or_create_session(session_id, user_request)
        with self._session_lock(session.session_id):
            try:
                yield session, created
            finally:
                self.save(session)

    @asynccontextmanager
    async def async_locked_session(self, session_id: str | None, user_request: str = ""):
        session, created = self.get_or_create_session(session_id, user_request)
        lock = self._session_lock(session.session_id)
        await asyncio.to_thread(lock.acquire)
        try:
            yield session, created
        finally:
            self.save(session)
            lock.release()

    @contextmanager
    def session_lock(self, session_id: str):
        with self._session_lock(session_id):
            try:
                yield
            finally:
                session = self.get_session(session_id)
                if session is not None:
                    self.save(session)

    def record_exchange(self, session: SessionMetadata, request: str, answer: str) -> None:
        if session.metadata.get("title") in {None, "", "New chat"}:
            session.metadata["title"] = " ".join(request.split())[:64]
        session.metadata["message_count"] = int(session.metadata.get("message_count", 0)) + 2
        session.metadata["last_message"] = answer
        session.user_request = request
        session.updated_at = now()
        self.save(session)

    def list_sessions(self) -> list[dict[str, Any]]:
        if self.root.exists():
            for path in self.root.glob("*.json"):
                self.get_session(path.stem)
        with self._lock:
            sessions = [
                {"session_id": s.session_id, "title": s.metadata.get("title", "New chat"),
                 "created_at": s.created_at, "updated_at": s.updated_at,
                 "message_count": s.metadata.get("message_count", 0),
                 "last_message": s.metadata.get("last_message", "")}
                for s in self._sessions.values()
            ]
        return sorted(sessions, key=lambda item: item["updated_at"], reverse=True)

    def delete_session(self, session_id: str) -> bool:
        lock = self._session_lock(session_id)
        if not lock.acquire(blocking=False):
            return False
        try:
            with self._lock:
                exists = self.get_session(session_id) is not None
                self._sessions.pop(session_id, None)
                self._path(session_id).unlink(missing_ok=True)
                return exists
        finally:
            lock.release()
