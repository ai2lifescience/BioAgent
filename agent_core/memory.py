"""Session memory and state storage for BioAgent runs."""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock, RLock
from uuid import uuid4
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _title_from_request(user_request: str) -> str:
    title = " ".join(user_request.split()).strip()
    if not title:
        return "New chat"
    return title[:64].rstrip() or "New chat"


@dataclass
class AgentSession:
    """Mutable state for one chat session."""

    session_id: str
    user_request: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    skill_results: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)


class InMemoryStateStore:
    """Minimal in-process state store.

    This keeps the architecture explicit without introducing an external database.
    A persistent implementation can replace this class later.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, AgentSession] = {}
        self._session_locks: dict[str, Lock] = {}
        self._lock = RLock()

    def create_session(
        self,
        user_request: str = "",
        session_id: str | None = None,
    ) -> AgentSession:
        with self._lock:
            resolved_session_id = str(session_id or uuid4()).strip() or str(uuid4())
            session = AgentSession(
                session_id=resolved_session_id,
                user_request=user_request,
            )
            session.metadata["title"] = _title_from_request(user_request)
            self._sessions[session.session_id] = session
            self._session_locks.setdefault(session.session_id, Lock())
            return session

    def get_or_create_session(
        self,
        session_id: str | None,
        user_request: str = "",
    ) -> tuple[AgentSession, bool]:
        with self._lock:
            clean_session_id = str(session_id or "").strip()
            if clean_session_id and clean_session_id in self._sessions:
                session = self._sessions[clean_session_id]
                if not session.metadata.get("title"):
                    session.metadata["title"] = _title_from_request(user_request)
                return session, False
            return self.create_session(
                user_request=user_request,
                session_id=clean_session_id or None,
            ), True

    def get_session(self, session_id: str) -> AgentSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            lock = self._session_locks.get(session_id)
            if lock is None:
                return False
        if not lock.acquire(blocking=False):
            return False
        try:
            with self._lock:
                deleted = self._sessions.pop(session_id, None) is not None
                if deleted:
                    self._session_locks.pop(session_id, None)
                return deleted
        finally:
            lock.release()

    @contextmanager
    def locked_session(
        self,
        session_id: str | None,
        user_request: str = "",
    ) -> Iterator[tuple[AgentSession, bool]]:
        while True:
            session, created = self.get_or_create_session(
                session_id=session_id,
                user_request=user_request,
            )
            with self._lock:
                lock = self._session_locks.setdefault(session.session_id, Lock())

            lock.acquire()
            with self._lock:
                active_session = self._sessions.get(session.session_id)
                if active_session is session:
                    break
            lock.release()

        try:
            yield session, created
        finally:
            lock.release()

    @contextmanager
    def session_lock(self, session_id: str) -> Iterator[None]:
        with self._lock:
            lock = self._session_locks.setdefault(session_id, Lock())
        with lock:
            yield

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return
            session.messages.append(
                {
                    "role": role,
                    "content": content,
                    "metadata": metadata or {},
                    "created_at": _now(),
                }
            )
            if role == "user" and not session.metadata.get("title"):
                session.metadata["title"] = _title_from_request(content)
            session.updated_at = _now()

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            summaries = [self._session_summary(session) for session in self._sessions.values()]
        return sorted(summaries, key=lambda item: str(item["updated_at"]), reverse=True)

    def recent_messages(
        self,
        session: AgentSession,
        limit: int = 8,
    ) -> list[dict[str, str]]:
        """Return recent user/assistant messages in model-ready form."""
        with self._lock:
            messages = list(session.messages[-max(0, limit) :])
        return [
            {"role": str(message["role"]), "content": str(message["content"])}
            for message in messages
            if message.get("role") in {"user", "assistant"} and message.get("content")
        ]

    @staticmethod
    def _session_summary(session: AgentSession) -> dict[str, Any]:
        last_message = session.messages[-1] if session.messages else {}
        return {
            "session_id": session.session_id,
            "title": session.metadata.get("title") or _title_from_request(session.user_request),
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "message_count": len(session.messages),
            "last_message": str(last_message.get("content") or ""),
        }
