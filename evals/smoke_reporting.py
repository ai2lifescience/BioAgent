"""Offline reporting concurrency, fallback, tracing, and embedding regressions."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx2
from openai import AsyncOpenAI, OpenAI

from harness.context import BioRunContext
from harness.sessions import SessionMetadata
from harness.tracing import LOCAL_TRACES
from models.config import DEFAULT_MODEL_KEYS, resolve_model_id
from rag.embeddings import embed_records, embed_texts
from tools.function_tools.species_report.reporting.opinions import collect_species_model_opinions
from tools.function_tools.species_report.reporting.synthesis import synthesize_species_markdown_report


def completion(content):
    return httpx2.Response(200, json={
        "id": "offline-report", "created": 1, "model": "offline-model",
        "object": "chat.completion", "choices": [{"index": 0, "finish_reason": "stop",
            "message": {"role": "assistant", "content": content}}],
    })


class ReportingTests(unittest.IsolatedAsyncioTestCase):
    def make_client(self, respond):
        client = AsyncOpenAI(
            api_key="offline-fixture", base_url="https://offline.invalid/v1", max_retries=0,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(respond), trust_env=False),
        )
        self.addAsyncCleanup(client.close)
        return client

    async def test_opinions_run_concurrently_and_preserve_partial_results(self):
        requests = []
        both_started = asyncio.Event()
        keys = ["gpt-oss", "deepseek-v4-flash"]

        async def respond(request):
            body = json.loads(request.content)
            requests.append(body)
            if len(requests) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=3)
            if body["model"] == resolve_model_id(keys[1]):
                return httpx2.Response(400, json={"error": {"message": "Fixture unavailable", "type": "invalid_request_error"}})
            return completion("A cautious opinion.")

        context = BioRunContext(session=SessionMetadata(session_id="report"), model_key=keys[0])
        client = self.make_client(respond)
        with patch("models.openrouter_provider.create_async_client", return_value=client) as factory:
            result = await asyncio.to_thread(
                collect_species_model_opinions, "Arabidopsis", "Summarize reference annotations.", keys, context,
            )
        self.assertEqual(result["model_answers"][keys[0]], "A cautious opinion.")
        self.assertIn("Fixture unavailable", result["model_answers"][keys[1]])
        self.assertEqual(result["model_keys"], keys)
        factory.assert_called_once()
        self.assertTrue(client.is_closed())
        self.assertTrue(all(request["temperature"] == 0.2 for request in requests))
        self.assertTrue(any(event["event"] == "sdk_span_finished" for event in context.events))
        self.assertNotIn(context, LOCAL_TRACES.contexts.values())

    async def test_synthesis_falls_back_after_empty_response(self):
        requests = []

        def respond(request):
            requests.append(json.loads(request.content))
            return completion("" if len(requests) == 1 else "# Report\nSupported finding [S1].")

        client = self.make_client(respond)
        with patch("models.openrouter_provider.create_async_client", return_value=client) as factory:
            result = await asyncio.to_thread(
                synthesize_species_markdown_report,
                species_name="Arabidopsis", question="Summarize reference annotations.",
                model_answers={"gpt-oss": "A cautious opinion."},
                sources=[{"id": "S1", "title": "Fixture source", "source": "fixture", "url": "https://offline.invalid/source"}],
                retrieval_context="Fixture evidence.", model_key="gpt-oss",
            )
        expected_fallback = next(key for key in DEFAULT_MODEL_KEYS if key != "gpt-oss")
        self.assertEqual(result["model_key"], expected_fallback)
        self.assertIn("[S1]", result["markdown"])
        self.assertEqual([request["model"] for request in requests], [resolve_model_id(key) for key in ("gpt-oss", expected_fallback)])
        self.assertIn("Fixture evidence.", str(requests[1]["messages"]))
        self.assertTrue(all(request["temperature"] == 0.15 for request in requests))
        factory.assert_called_once()
        self.assertTrue(client.is_closed())

    async def test_all_synthesis_failures_are_reported_and_client_closes(self):
        client = self.make_client(lambda _request: completion(""))
        with patch("models.openrouter_provider.create_async_client", return_value=client):
            with self.assertRaisesRegex(RuntimeError, "All report synthesis models failed") as failure:
                await asyncio.to_thread(
                    synthesize_species_markdown_report, "Arabidopsis", "Summarize annotations.", {}, [],
                )
        for key in DEFAULT_MODEL_KEYS:
            self.assertIn(key, str(failure.exception))
        self.assertTrue(client.is_closed())


class EmbeddingTests(unittest.TestCase):
    def test_empty_batch_needs_no_client(self):
        with patch("rag.embeddings.create_client") as factory:
            self.assertEqual(embed_texts(iter([])), [])
        factory.assert_not_called()

    def test_embeddings_are_matched_to_records_by_provider_index(self):
        requests = []

        def respond(request):
            requests.append(json.loads(request.content))
            return httpx2.Response(200, json={
                "object": "list", "model": "openrouter/fixture-embedding",
                "data": [{"object": "embedding", "index": index, "embedding": [float(index)]} for index in (1, 0)],
                "usage": {"prompt_tokens": 2, "total_tokens": 2},
            })

        client = OpenAI(
            api_key="offline-fixture", base_url="https://offline.invalid/v1",
            http_client=httpx2.Client(transport=httpx2.MockTransport(respond), trust_env=False),
        )
        self.addCleanup(client.close)
        records = [{"text": "First record"}, {"text": "Second record"}]
        with patch("rag.embeddings.create_client", return_value=client):
            result = embed_records(records, model="openrouter/fixture-embedding")
        self.assertEqual([record["embedding"] for record in result], [[0.0], [1.0]])
        self.assertEqual(requests[0]["input"], ["First record", "Second record"])
        self.assertEqual(requests[0]["model"], "openrouter/fixture-embedding")
        self.assertTrue(client.is_closed())


if __name__ == "__main__":
    unittest.main()
