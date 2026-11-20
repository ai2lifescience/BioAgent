"""Offline provider ownership, nested-agent, and approval-resume regressions."""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx2
from openai import AsyncOpenAI
from agents.testing import ModelStep, ScriptedModel, assistant_message

from harness import runtime, sandbox
from harness.sessions import SessionMetadataStore
from models.config import DEFAULT_AGENT_MODEL_KEY, resolve_model_id
from models.openrouter_provider import OpenRouterProvider


def completion(message, *, streaming=False):
    base = {"id": "offline-chat", "created": 1, "model": "offline-model"}
    finish = "tool_calls" if message.get("tool_calls") else "stop"
    if streaming:
        delta = dict(message)
        if message.get("tool_calls"):
            delta["tool_calls"] = [{"index": index, **call} for index, call in enumerate(message["tool_calls"])]
        chunks = [
            {**base, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
            {**base, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]},
        ]
        data = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n"
        return httpx2.Response(200, text=data, headers={"content-type": "text/event-stream"})
    return httpx2.Response(200, json={
        **base, "object": "chat.completion", "choices": [{
            "index": 0, "message": message,
            "finish_reason": finish,
        }],
    })


def tool_call(name, arguments, call_id):
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": call_id, "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }]}


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="agent-provider-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for module, name, value in (
            (runtime, "STATE_STORE", SessionMetadataStore(self.root / "metadata")),
            (runtime, "SESSION_DB", self.root / "conversation.sqlite3"),
            (sandbox, "WORKSPACES_DIR", self.root / "workspaces"),
        ):
            patcher = patch.object(module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.clients = []

    def make_client(self, respond):
        client = AsyncOpenAI(
            api_key="offline-fixture", base_url="https://offline.invalid/v1", max_retries=0,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(respond), trust_env=False),
        )
        self.clients.append(client)
        self.addAsyncCleanup(client.close)
        return client

    async def test_lazy_resolution_and_owned_client_cleanup(self):
        client = self.make_client(lambda _request: completion({"role": "assistant", "content": "OK"}))
        with patch("models.openrouter_provider.create_async_client", return_value=client) as factory:
            async with OpenRouterProvider() as provider:
                factory.assert_not_called()
                default = provider.get_model(None)
                self.assertIs(default, provider.get_model(DEFAULT_AGENT_MODEL_KEY))
                self.assertIs(default, provider.get_model(resolve_model_id(DEFAULT_AGENT_MODEL_KEY)))
                native = provider.get_model("openrouter/auto")
                self.assertEqual(native.model, "openrouter/auto")
                self.assertEqual(provider.get_model("openai/gpt-oss-120b").model, "openai/gpt-oss-120b")
                factory.assert_called_once()
                self.assertFalse(client.is_closed())
            self.assertTrue(client.is_closed())
            await provider.aclose()
            with self.assertRaisesRegex(RuntimeError, "closed"):
                provider.get_model(None)

    async def test_injected_client_remains_caller_owned(self):
        client = self.make_client(lambda _request: completion({"role": "assistant", "content": "OK"}))
        with patch("models.openrouter_provider.create_async_client") as factory:
            async with OpenRouterProvider(client=client) as provider:
                provider.get_model("gpt-oss")
            factory.assert_not_called()
        self.assertFalse(client.is_closed())

    async def test_injected_model_needs_no_provider_client(self):
        with patch("models.openrouter_provider.create_async_client", side_effect=AssertionError("Unexpected client")) as factory:
            result = await runtime.async_run_agent(
                "Hello", session_id="injected",
                model=ScriptedModel([ModelStep(output=[assistant_message("Hello back.")])]),
            )
        self.assertEqual(result["status"], "ok", result["answer"])
        factory.assert_not_called()

    async def test_missing_credentials_are_deferred_until_model_resolution(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}):
            async with OpenRouterProvider() as provider:
                with self.assertRaisesRegex(RuntimeError, "OPENROUTER_API_KEY"):
                    provider.get_model("gpt-oss")

    async def test_nested_approval_resume_uses_fresh_provider_and_executes_once(self):
        await self.check_nested_approval_resume()

    async def test_streamed_nested_approval_resumes_in_the_main_chat(self):
        await self.check_nested_approval_resume(streaming=True)

    async def check_nested_approval_resume(self, *, streaming=False):
        messages = [
            tool_call("pipeline_specialist", {"task": "Cancel the fixture job"}, "specialist"),
            tool_call("pipeline_shell", {
                "commands": ["agent-pipeline cancel --job-id " + "a" * 32],
                "timeout_ms": None, "max_output_length": None,
            }, "cancel"),
            {"role": "assistant", "content": "The fixture job was cancelled."},
            {"role": "assistant", "content": "Cancellation completed."},
        ]
        requests = []
        events = []
        event_fn = (lambda kind, data: events.append((kind, data))) if streaming else None

        def respond(request):
            request_body = json.loads(request.content)
            requests.append(request_body)
            return completion(messages[len(requests) - 1], streaming=request_body.get("stream", False))

        pipeline = importlib.import_module("tools.agent_tools.specialist.pipeline.pipeline_shell")
        with patch("models.openrouter_provider.create_async_client", side_effect=lambda: self.make_client(respond)) as factory:
            with patch.object(pipeline, "dispatch", return_value={"status": "ok"}) as dispatch:
                pending = await runtime.async_run_agent(
                    "Ask the pipeline specialist to cancel the fixture job", session_id="approval",
                    model_key="gpt-oss", event_fn=event_fn,
                )
                self.assertEqual(pending["status"], "pending_approval", pending["answer"])
                self.assertEqual(pending["approvals"][0]["agent"], "pipeline_specialist")
                dispatch.assert_not_called()
                factory.assert_called_once()
                self.assertTrue(self.clients[0].is_closed())
                runtime.STATE_STORE = SessionMetadataStore(self.root / "metadata")
                result = await runtime.async_resume_agent(
                    "approval", True, pending["approvals"][0]["approval_id"], event_fn=event_fn,
                )
                self.assertEqual(result["status"], "ok", result["answer"])
                self.assertEqual(result["answer"], "Cancellation completed.")
                self.assertEqual(factory.call_count, 2)
                dispatch.assert_called_once()
        self.assertTrue(all(client.is_closed() for client in self.clients))
        self.assertEqual(len(requests), 4)
        if streaming:
            self.assertTrue(requests[0]["stream"])
            self.assertTrue(any(data.get("agent") == "pipeline_specialist" for _, data in events))
        self.assertTrue(all(request["model"] == resolve_model_id("gpt-oss") for request in requests))
        for request, call_id in ((requests[2], "cancel"), (requests[3], "specialist")):
            self.assertTrue(any(item.get("tool_call_id") == call_id for item in request["messages"]))

    async def test_client_is_closed_after_failed_run(self):
        def respond(_request):
            return httpx2.Response(400, json={"error": {"message": "Offline model failure", "type": "invalid_request_error"}})

        client = self.make_client(respond)
        with patch("models.openrouter_provider.create_async_client", return_value=client):
            result = await runtime.async_run_agent("Hello", session_id="failure", model_key="gpt-oss")
        self.assertEqual(result["status"], "error")
        self.assertIn("Offline model failure", result["answer"])
        self.assertTrue(client.is_closed())


if __name__ == "__main__":
    unittest.main()
