"""Stream boundaries and nested-output regressions; no model/API calls."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from harness.jobs import execute_job
from harness.streaming import PublicEvents, STREAM_SINK, nested_stream


def raw(kind, **fields):
    return SimpleNamespace(type="raw_response_event", data=SimpleNamespace(type=kind, **fields))


class LiveProgressStreamTests(unittest.TestCase):
    def test_provider_without_text_done_flushes_each_scope_before_completion(self):
        events = []
        sink = PublicEvents(SimpleNamespace(public=lambda value: value), lambda name, data: events.append(data))
        sink(raw("response.output_text.delta", delta="Root tail", item_id="same"))
        sink(raw("response.output_text.delta", delta="Nested tail", item_id="same"), agent="research", parent_call_id="call")
        sink(raw("response.completed"))
        self.assertEqual(events[-2]["delta"], "tail")
        self.assertIsNone(events[-2]["parent_call_id"])
        self.assertEqual(events[-1]["data_type"], "response.completed")
        self.assertEqual(len(sink.pending), 1)
        sink(raw("response.completed"), agent="research", parent_call_id="call")
        self.assertEqual(events[-2]["delta"], "tail")
        self.assertEqual(events[-2]["parent_call_id"], "call")
        self.assertFalse(sink.pending)

    def test_nested_typed_output_is_labelled_and_private_deltas_are_omitted(self):
        events = []
        sink = PublicEvents(SimpleNamespace(public=lambda value: value), lambda name, data: events.append(data))
        token = STREAM_SINK.set(sink)
        try:
            nested_stream({
                "agent": SimpleNamespace(name="review", output_type=dict),
                "tool_call": SimpleNamespace(call_id="review-call"),
                "event": raw("response.output_text.delta", delta='{"assessment": "review"} ', item_id="review"),
            })
        finally:
            STREAM_SINK.reset(token)
        self.assertEqual(events[0]["content_kind"], "structured")
        self.assertEqual(events[0]["parent_call_id"], "review-call")
        for kind in ("response.function_call_arguments.delta", "response.reasoning_text.delta"):
            sink(raw(kind, delta="private text"))
            self.assertNotIn("delta", events[-1])

    def test_worker_preserves_metadata_when_nested_streams_interleave(self):
        queue = Mock()
        queue.get.return_value = {"status": "running", "request": "test", "session_id": "fixture", "model_key": "fixture", "max_turns": 5}

        def run_agent(*args, event_fn, **kwargs):
            base = {"sdk_type": "raw_response_event", "data_type": "response.output_text.delta", "item_id": "same", "content_index": 0}
            root = {**base, "agent": None, "parent_call_id": None, "content_kind": "narration"}
            nested = {**base, "agent": "review", "parent_call_id": "call", "content_kind": "structured"}
            for metadata, delta in [(root, "Root "), (nested, '{"assessment": '), (nested, '"ok"} '), (root, "continues.")]:
                event_fn("sdk_raw_response", {**metadata, "delta": delta})
            event_fn("sdk_raw_response", {**root, "data_type": "response.completed"})
            return {"status": "ok", "answer": "Done"}

        with patch("harness.runtime.run_agent", side_effect=run_agent):
            self.assertEqual(execute_job(queue, "fixture"), 0)
        payloads = [call.args[2] for call in queue.event.call_args_list if call.args[1] == "sdk_raw_response"]
        self.assertEqual([item.get("delta") for item in payloads], ["Root ", '{"assessment": "ok"} ', "continues.", None])
        self.assertEqual(payloads[1]["content_kind"], "structured")
        self.assertEqual(payloads[1]["parent_call_id"], "call")
        self.assertIsNone(payloads[2]["agent"])
        self.assertEqual(payloads[2]["item_id"], "same")
        queue.dispatch.assert_called_once()


if __name__ == "__main__":
    unittest.main()
