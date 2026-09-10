"""No-network smoke checks for model tool-calling fallback."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_core.memory import InMemoryStateStore
from agent_core.orchestrator import BioAgentOrchestrator
from agent_core.trace import InMemoryTraceStore
from interfaces.web import _runtime_info
from models.llm_client import LLMClient


class FakeMessage:
    def __init__(self, content: str | None = None, tool_calls: list[dict[str, Any]] | None = None) -> None:
        self.role = "assistant"
        self.content = content
        self.tool_calls = tool_calls or []


class FakeResponse:
    def __init__(self, message: FakeMessage) -> None:
        self.choices = [type("Choice", (), {"message": message})()]


class FakeClient:
    def __init__(
        self,
        tool_response: FakeResponse | Exception | None = None,
        plain_response: FakeResponse | Exception | None = None,
        supports_tool_calling: bool = True,
    ) -> None:
        self.model_label = "Fake model"
        self.supports_tool_calling = supports_tool_calling
        self.tool_response = tool_response or FakeResponse(FakeMessage("tool answer"))
        self.plain_response = plain_response or FakeResponse(FakeMessage("plain answer"))
        self.tool_requests: list[dict[str, Any]] = []
        self.plain_requests: list[dict[str, Any]] = []

    def complete(self, **kwargs: Any) -> FakeResponse:
        self.tool_requests.append(kwargs)
        if isinstance(self.tool_response, Exception):
            raise self.tool_response
        return self.tool_response

    def complete_without_tools(self, **kwargs: Any) -> FakeResponse:
        self.plain_requests.append(kwargs)
        if isinstance(self.plain_response, Exception):
            raise self.plain_response
        return self.plain_response


def _run_loop(client: FakeClient) -> tuple[dict[str, Any], InMemoryTraceStore, str]:
    memory = InMemoryStateStore()
    trace_store = InMemoryTraceStore()
    orchestrator = BioAgentOrchestrator(
        memory=memory,
        trace_store=trace_store,
        llm_client_factory=lambda **_kwargs: client,
    )
    session = memory.create_session(user_request="Handle an ambiguous biology request.", session_id="fallback-smoke")
    result = orchestrator._run_llm_skill_loop_step(
        session=session,
        model_key="fake",
        max_skill_steps=2,
        log_fn=None,
    )
    return result, trace_store, session.session_id


def _trace_event_names(trace_store: InMemoryTraceStore, session_id: str) -> list[str]:
    return [str(event.get("event")) for event in trace_store.list_events(session_id)]


def _check_llm_timeout() -> None:
    client = object.__new__(LLMClient)
    client.model_id = "fake-model"
    client.model_config = {}
    client.timeout_seconds = 17.0
    captured: dict[str, Any] = {}

    def fake_completion(**request: Any) -> FakeResponse:
        captured.clear()
        captured.update(request)
        return FakeResponse(FakeMessage("ok"))

    client._completion = fake_completion
    client.complete(messages=[{"role": "user", "content": "test"}])
    assert captured["timeout"] == 17.0

    client.complete_without_tools(messages=[{"role": "user", "content": "test"}])
    assert "tools" not in captured
    assert "tool_choice" not in captured


def main() -> int:
    _check_llm_timeout()

    timeout_client = FakeClient(
        tool_response=TimeoutError("tool request timed out"),
        plain_response=FakeResponse(FakeMessage("Fallback answer.")),
    )
    fallback_result, fallback_trace, fallback_session_id = _run_loop(timeout_client)
    assert fallback_result["answer"] == "Fallback answer."
    assert len(timeout_client.tool_requests) == 1
    assert len(timeout_client.plain_requests) == 1
    assert _trace_event_names(fallback_trace, fallback_session_id) == [
        "model_requested",
        "model_tool_fallback_started",
        "model_tool_fallback_completed",
        "model_responded",
    ]
    fallback_runtime = _runtime_info(
        {
            "trace": fallback_trace.list_events(fallback_session_id),
            "evidence": {},
            "run": {},
        },
        elapsed_seconds=1,
        logs=[],
    )
    assert fallback_runtime["model_tool_fallback"] == {
        "used": True,
        "status": "model_tool_fallback_completed",
        "reason": "TimeoutError: tool request timed out",
    }

    disabled_client = FakeClient(
        plain_response=FakeResponse(FakeMessage("Tool-free model answer.")),
        supports_tool_calling=False,
    )
    disabled_result, disabled_trace, disabled_session_id = _run_loop(disabled_client)
    assert disabled_result["answer"] == "Tool-free model answer."
    assert not disabled_client.tool_requests
    assert len(disabled_client.plain_requests) == 1
    assert "model_tool_fallback_completed" in _trace_event_names(disabled_trace, disabled_session_id)

    ask_user_call = {
        "id": "ask-user-smoke",
        "type": "function",
        "function": {
            "name": "ask_user",
            "arguments": json.dumps(
                {
                    "question": "Which database should I search?",
                    "options": ["UniProt", "NCBI"],
                }
            ),
        },
    }
    ask_user_client = FakeClient(tool_response=FakeResponse(FakeMessage(tool_calls=[ask_user_call])))
    ask_user_result, _ask_user_trace, _ask_user_session_id = _run_loop(ask_user_client)
    assert ask_user_result["answer"] == "Which database should I search?"

    failed_client = FakeClient(
        tool_response=TimeoutError("tool request timed out"),
        plain_response=TimeoutError("tool-free request timed out"),
    )
    try:
        _run_loop(failed_client)
    except RuntimeError as exc:
        assert "tool-free retry" in str(exc)
    else:
        raise AssertionError("Expected both model requests to fail.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
