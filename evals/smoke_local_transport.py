"""Exercise the real Chat Completions converter and native local executors offline."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx2
from openai import AsyncOpenAI
from agents import Runner, RunConfig
from agents.sandbox import SandboxRunConfig

from harness import sandbox
from harness.agent import create_agent
from harness.context import BioRunContext
from harness.sessions import SessionMetadata
from models.config import resolve_model_id
from models.openrouter_provider import OpenRouterProvider


class LocalTransportTests(unittest.IsolatedAsyncioTestCase):
    async def check_runtime(self, streaming):
        requests = []
        calls = [
            {"id": "shell-1", "type": "function", "function": {
                "name": "pipeline_shell", "arguments": json.dumps({
                    "commands": ["bioagent-pipeline catalog"],
                    "timeout_ms": None, "max_output_length": None})}},
            {"id": "patch-1", "type": "function", "function": {
                "name": "apply_patch", "arguments": json.dumps({
                    "input": "*** Begin Patch\n*** Add File: note.txt\n+transport works\n*** End Patch"})}},
            {"id": "function-1", "type": "function", "function": {
                "name": "sequence_analysis", "arguments": json.dumps({"sequence": "ACGT"})}},
        ]

        def respond(request):
            body = json.loads(request.content)
            requests.append(body)
            first = len(requests) == 1
            base = {"id": "chat-test", "created": 1, "model": "offline-model"}
            if not body.get("stream"):
                message = {"role": "assistant", "content": None, "tool_calls": calls} if first else {
                    "role": "assistant", "content": "Completed."}
                return httpx2.Response(200, json={**base, "object": "chat.completion", "choices": [{
                    "index": 0, "message": message, "finish_reason": "tool_calls" if first else "stop"}]})
            deltas = []
            if first:
                for index, call in enumerate(calls):
                    deltas.append({"tool_calls": [{**call, "index": index, "function": {
                        "name": call["function"]["name"], "arguments": ""}}]})
                    deltas.append({"tool_calls": [{"index": index, "function": {
                        "arguments": call["function"]["arguments"]}}]})
            else:
                deltas.append({"role": "assistant", "content": "Completed."})
            chunks = [{**base, "object": "chat.completion.chunk", "choices": [{
                "index": 0, "delta": delta, "finish_reason": None}]} for delta in deltas]
            chunks.append({**base, "object": "chat.completion.chunk", "choices": [{
                "index": 0, "delta": {}, "finish_reason": "tool_calls" if first else "stop"}]})
            data = "".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks) + "data: [DONE]\n\n"
            return httpx2.Response(200, text=data, headers={"content-type": "text/event-stream"})

        with TemporaryDirectory(prefix="bioagent-transport-") as directory:
            with patch.object(sandbox, "WORKSPACES_DIR", Path(directory)):
                async with AsyncOpenAI(api_key="offline-fixture", base_url="https://offline.invalid/v1",
                        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(respond), trust_env=False)) as client:
                    provider = OpenRouterProvider(client=client)
                    self.addAsyncCleanup(provider.aclose)
                    session = SessionMetadata(session_id="transport")
                    sandbox.prepare_run(session)
                    context = BioRunContext(session=session, model_key="gpt-oss")
                    async with sandbox.open_workspace(session.session_id) as workspace:
                        context.sandbox_session = workspace
                        agent = create_agent("gpt-oss", sandbox_root=str(sandbox.session_root(session.session_id)))
                        config = RunConfig(model_provider=provider, sandbox=SandboxRunConfig(session=workspace, cwd="."))
                        arguments = dict(context=context, run_config=config, max_turns=3)
                        if streaming:
                            result = Runner.run_streamed(agent, "List local pipelines, write a note, and analyze ACGT.", **arguments)
                            events = [event async for event in result.stream_events()]
                            raw_events = [event.data for event in events if event.type == "raw_response_event"]
                            self.assertTrue(any(event.type == "response.function_call_arguments.delta" for event in raw_events))
                        else:
                            result = await Runner.run(agent, "List local pipelines, write a note, and analyze ACGT.", **arguments)
                        self.assertEqual(result.final_output, "Completed.")
                        self.assertEqual(await sandbox.read_file(workspace, "note.txt"), b"transport works")
                    types = {item["type"] for item in result.to_input_list() if "type" in item}
                    self.assertTrue({"shell_call", "shell_call_output", "custom_tool_call", "custom_tool_call_output"} <= types)

        self.assertEqual(len(requests), 2)
        self.assertTrue(all(request["model"] == resolve_model_id("gpt-oss") for request in requests))
        tools = {item["function"]["name"]: item["function"] for item in requests[0]["tools"]}
        self.assertIn("pipeline_shell", tools)
        self.assertIn("input", tools["apply_patch"]["parameters"]["properties"])
        outputs = {item["tool_call_id"]: item["content"] for item in requests[1]["messages"] if item["role"] == "tool"}
        self.assertEqual(set(outputs), {"shell-1", "patch-1", "function-1"})
        self.assertIn("example_sequence_qc", outputs["shell-1"])
        self.assertIn("note.txt", outputs["patch-1"])

    async def test_native_execution_and_history(self):
        await self.check_runtime(streaming=False)

    async def test_streamed_native_execution_and_history(self):
        await self.check_runtime(streaming=True)


if __name__ == "__main__":
    unittest.main()
