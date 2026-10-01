"""Pipeline completion handoff regressions without remote jobs or paid calls."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from agents import Agent, RunContextWrapper, function_tool
from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call
from harness import runtime, sandbox
from harness.context import AgentRunContext
from harness.pipeline_completion import collect_started_pipelines
from harness.sessions import SessionMetadataStore
from interfaces.api import list_session_messages

JOB = 'a' * 32


def launched():
    return {'tool': 'pipeline_shell', 'arguments': {'command': f'agent-pipeline run --plan-id {JOB}'},
            'result': {'job_id': JOB, 'status': 'queued'}}


def state(status):
    return {'job_id': JOB, 'pipeline_name': 'template_wdl', 'status': status}


class CompletionTests(unittest.IsolatedAsyncioTestCase):
    def context(self):
        context = SimpleNamespace(run={'session_dir': '/tmp/fixture'}, tool_results=[launched()], events=[], public=lambda value: value)
        context.record = lambda event, **data: context.events.append({'event': event, 'data': data})
        return context

    async def test_queued_running_success_collects_once_without_resubmission(self):
        context, events = self.context(), []
        verified = {**state('succeeded'), 'files': [], 'bundle_path': 'runtime/agent_runs/fixture/results.zip'}
        with patch('harness.pipeline_completion.service.status', side_effect=[state(s) for s in ['queued', 'running', 'running', 'succeeded']]), patch(
            'harness.pipeline_completion.service.results', return_value=verified
        ) as results, patch('harness.pipeline_completion.service.start') as start:
            completed = await collect_started_pipelines(context, lambda name, data: events.append(data), poll_interval=0)
            self.assertEqual(completed, [verified])
            self.assertEqual([item['status'] for item in events], ['queued', 'running', 'succeeded'])
            self.assertEqual(await collect_started_pipelines(context, poll_interval=0), [])
            results.assert_called_once_with(Path('/tmp/fixture'), JOB)
            start.assert_not_called()

    async def test_all_unsuccessful_terminal_states_are_reported_once(self):
        for status in ['failed', 'cancelled', 'timed_out', 'interrupted']:
            with self.subTest(status=status):
                context = self.context()
                with patch('harness.pipeline_completion.service.status', return_value=state(status)), patch('harness.pipeline_completion.service.results') as results:
                    self.assertEqual((await collect_started_pipelines(context))[0]['status'], status)
                    self.assertEqual(await collect_started_pipelines(context), [])
                    results.assert_not_called()

    async def test_unverified_outputs_are_not_reported_as_success(self):
        context = self.context()
        with patch('harness.pipeline_completion.service.status', return_value=state('succeeded')), patch('harness.pipeline_completion.service.results', side_effect=ValueError('Output hash changed')):
            result = (await collect_started_pipelines(context))[0]
        self.assertEqual(result['status'], 'error')
        self.assertIn('Output hash changed', result['error'])
        self.assertEqual(result['files'], [])
        self.assertEqual(await collect_started_pipelines(context), [])

    async def test_unrelated_jobs_and_already_collected_outputs_are_not_monitored(self):
        for records in [[], [launched(), {'tool': 'pipeline_shell', 'arguments': {'command': f'agent-pipeline results --job-id {JOB}'}, 'result': state('succeeded')}]]:
            context = self.context(); context.tool_results = records
            with patch('harness.pipeline_completion.service.status') as status:
                self.assertEqual(await collect_started_pipelines(context), [])
                status.assert_not_called()


class RuntimeCompletionTests(unittest.TestCase):
    def check_runtime(self, max_turns=5, *, inspect_after_completion=False):
        @function_tool
        async def launch_test(ctx: RunContextWrapper[AgentRunContext]) -> str:
            ctx.context.tool_results.append(launched())
            return 'Pipeline is running.'

        @function_tool
        async def inspect_test() -> str:
            return 'Verified output details.'

        steps = [
            ModelStep(output=[function_call('launch_test', {}, call_id='launch')]),
            ModelStep(output=[assistant_message('The pipeline is still running.')]),
        ]
        if inspect_after_completion:
            steps.append(ModelStep(output=[function_call('inspect_test', {}, call_id='inspect')]))
        steps.append(ModelStep(output=[assistant_message('Pipeline completed with verified outputs.')]))
        model = ScriptedModel(steps)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(runtime, 'STATE_STORE', SessionMetadataStore(root/'metadata')), patch.object(runtime, 'SESSION_DB', root/'sessions.sqlite3'), patch.object(sandbox, 'WORKSPACES_DIR', root/'workspaces'), patch.object(
                runtime, 'create_agent', return_value=Agent(name='fixture', model=model, tools=[launch_test, inspect_test])
            ), patch('harness.pipeline_completion.service.status', side_effect=[state('running'), state('succeeded')]), patch(
                'harness.pipeline_completion.service.results', return_value={**state('succeeded'), 'files': [], 'bundle_path': 'outputs/results.zip'}
            ), patch('harness.pipeline_completion.asyncio.sleep', new=AsyncMock()):
                result = runtime.run_agent('Run the demonstration pipeline.', session_id='completion', model=model, max_turns=max_turns)
                history = list_session_messages('completion')['messages']
        self.assertEqual(result['status'], 'ok', result['answer'])
        self.assertTrue(any(event['event'] == 'pipeline_completion_collected' for event in result['trace']))
        self.assertEqual(len([message for message in history if message['role'] == 'user']), 1)
        self.assertEqual(history[-1]['text'], result['answer'])
        return result, model

    def test_runtime_resumes_with_completion_without_another_user_message(self):
        result, model = self.check_runtime()
        self.assertEqual(result['answer'], 'Pipeline completed with verified outputs.')
        self.assertEqual(len(model.calls), 3)

    def test_exhausted_turn_budget_still_returns_actual_completion(self):
        result, model = self.check_runtime(max_turns=2)
        self.assertIn('succeeded', result['answer'])
        self.assertIn('outputs/results.zip', result['answer'])
        self.assertEqual(len(model.calls), 2)

    def test_launch_on_last_tool_turn_still_collects_results(self):
        result, model = self.check_runtime(max_turns=1)
        self.assertIn('succeeded', result['answer'])
        self.assertIn('outputs/results.zip', result['answer'])
        self.assertEqual(len(model.calls), 1)

    def test_analysis_turn_limit_preserves_verified_completion(self):
        result, model = self.check_runtime(max_turns=3, inspect_after_completion=True)
        self.assertIn('succeeded', result['answer'])
        self.assertIn('outputs/results.zip', result['answer'])
        self.assertEqual(len(model.calls), 3)


if __name__ == '__main__':
    unittest.main()
