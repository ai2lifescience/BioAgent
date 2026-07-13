"""Execution tracing for BioAgent."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class TraceEvent:
    """One structured event emitted during an agent run."""

    timestamp: str
    session_id: str
    event: str
    data: dict[str, Any] = field(default_factory=dict)


class InMemoryTraceStore:
    """In-process trace store keyed by session id."""

    def __init__(self) -> None:
        self._events: dict[str, list[TraceEvent]] = {}
        self._lock = RLock()

    def record(self, session_id: str, event: str, **data: Any) -> TraceEvent:
        trace_event = TraceEvent(
            timestamp=_now(),
            session_id=session_id,
            event=event,
            data=data,
        )
        with self._lock:
            self._events.setdefault(session_id, []).append(trace_event)
        return trace_event

    def list_events(self, session_id: str, start: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            events = list(self._events.get(session_id, []))[start:]
        return [
            {
                "timestamp": event.timestamp,
                "session_id": event.session_id,
                "event": event.event,
                "data": event.data,
            }
            for event in events
        ]
