"""Forward public SDK events from root and Agent.as_tool runs."""
from __future__ import annotations

from contextvars import ContextVar
from typing import Any

STREAM_SINK: ContextVar[Any] = ContextVar("pipeline2agent_stream_sink", default=None)


def nested_stream(payload) -> None:
    sink = STREAM_SINK.get()
    if sink:
        call = payload.get("tool_call")
        sink(payload["event"], agent=payload["agent"].name,
             parent_call_id=getattr(call, "call_id", None))


class PublicEvents:
    def __init__(self, context, emit):
        self.context, self.emit = context, emit
        self.pending: dict[tuple, tuple[str, dict]] = {}

    def __call__(self, event, *, agent=None, parent_call_id=None):
        kind = str(getattr(event, "type", "sdk_event"))
        payload = {"sdk_type": kind, "agent": agent, "parent_call_id": parent_call_id}
        if kind == "raw_response_event":
            data = event.data
            subtype = str(getattr(data, "type", "raw_response"))
            payload["data_type"] = subtype
            payload["item_id"] = getattr(data, "item_id", None)
            if subtype == "response.output_text.delta":
                key = (agent, parent_call_id, payload["item_id"], getattr(data, "content_index", None))
                text = self.pending.get(key, ("", payload))[0] + str(getattr(data, "delta", ""))
                # Buffer unfinished words so a host path split across model
                # tokens is never published before boundary sanitization.
                boundary = max((index + 1 for index, char in enumerate(text) if char.isspace()), default=0)
                self.pending[key] = (text[boundary:], payload)
                if boundary:
                    self.emit("sdk_raw_response", self.context.public({**payload, "delta": text[:boundary]}))
                return
            if subtype == "response.output_text.done":
                self.flush(agent=agent, parent_call_id=parent_call_id)
                self.emit("sdk_raw_response", self.context.public(payload))
                return
            # Preserve native SDK event lifecycle metadata, but never forward
            # function-call argument deltas: those are JSON fragments and can
            # contain an internal path split across tokens.
            self.emit("sdk_raw_response", self.context.public(payload))
            return
        if kind == "run_item_stream_event":
            payload["name"] = str(event.name)
            item = event.item
            payload["item_type"] = str(getattr(item, "type", ""))
            raw = getattr(item, "raw_item", None)
            raw = raw.model_dump() if hasattr(raw, "model_dump") else raw
            if isinstance(raw, dict):
                payload.update(call_id=raw.get("call_id"), tool_name=raw.get("name"), item_id=raw.get("id"))
            self.emit("sdk_run_item", self.context.public(payload))
        elif kind == "agent_updated_stream_event":
            payload["agent"] = event.new_agent.name
            self.emit("sdk_agent_updated", self.context.public(payload))

    def flush(self, **scope):
        for key, (text, payload) in list(self.pending.items()):
            if any(payload.get(k) != v for k, v in scope.items()):
                continue
            if text:
                self.emit("sdk_raw_response", self.context.public({**payload, "delta": text}))
            self.pending.pop(key)
