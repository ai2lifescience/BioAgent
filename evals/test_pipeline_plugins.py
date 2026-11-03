"""Agent-side plugin integration using temporary, non-biological workflows."""
import asyncio
import json
import os
from pathlib import Path
import shlex
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

import yaml

from auth import Principal, principal_scope, OwnershipStore, AccessDenied, ExecutionUnavailable
from isolation import WorkspaceAccess, supervisor
from tools.infrastructure.pipeline_engine import broker, contracts, service, isolated_worker
from tools.infrastructure.pipeline_engine.engine import cromwell, paths
from tools.infrastructure.pipeline_engine.store import JobStore


class PluginTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.plugins = self.base / 'plugins'; self.plugins.mkdir()
        self.env = patch.dict(os.environ, {'AGENT_AUTH_MODE': 'multiuser', 'AGENT_WORKER_BACKEND': 'docker',
                                          'CROMWELL_URL': 'http://fixture.invalid'})
        self.env.start(); self.addCleanup(self.env.stop)
        for module in (service, paths):
            change = patch.object(module, 'PIPELINES_ROOT', self.plugins)
            change.start(); self.addCleanup(change.stop)
        scope = principal_scope(Principal('plugin-owner')); scope.__enter__(); self.addCleanup(scope.__exit__, None, None, None)
        self.access = WorkspaceAccess(OwnershipStore(self.base / 'metadata'), self.base / 'sessions')
        self.access.ownership.claim('session')
        self.root = self.access.workspace('session'); self.root.mkdir(parents=True)
        (self.root / 'first.txt').write_text('first\n')
        (self.root / 'second;part.txt').write_text('second\n')

    def plugin(self, engine='shell'):
        name = 'fixture_' + uuid4().hex[:12]
        directory = self.plugins / name; directory.mkdir()
        manifest = {'name': name, 'engine': engine, 'timeout': 60,
                    'inputs': {'texts': {'config_key': 'input_path', 'required': True, 'multiple': True, 'accepts': ['.txt']}},
                    'outputs': {'report': {'config_key': 'report_path', 'default': 'report.txt', 'wdl_output': 'Fixture.report'},
                                'metrics': {'config_key': 'metrics_path', 'default': 'metrics.json', 'wdl_output': 'Fixture.metrics'}},
                    'param_overrides': {'heading': {'config_key': 'params.heading', 'default': 'Example', 'type': 'string'}}}
        if engine == 'wdl':
            manifest['workflow'] = 'steps/custom-entry.wdl'
            manifest['inputs']['texts']['config_key'] = 'Fixture.texts'
            manifest['param_overrides']['heading']['config_key'] = 'Fixture.heading'
            (directory / 'steps').mkdir()
            (directory / manifest['workflow']).write_text('version 1.0\nworkflow Fixture { input { Array[File] texts String heading } }\n')
        else:
            manifest['entrypoint'] = 'execute.sh'
            manifest['params'] = {'heading': 'Example'}
            (directory / 'execute.sh').write_text('exec python "$(dirname "$0")/workflow.py" "$1"\n')
            (directory / 'workflow.py').write_text('''import json, sys, yaml
from pathlib import Path
config = yaml.safe_load(Path(sys.argv[1]).read_text())
items = config['input_path']
assert isinstance(items, list), items
text = config['params']['heading'] + '\\n' + ''.join(Path(path).read_text() for path in items)
Path(config['report_path']).write_text(text)
Path(config['metrics_path']).write_text(json.dumps({'files': len(items)}))
''')
        (directory / 'runner.yaml').write_text(yaml.safe_dump(manifest))
        return name

    def plan(self, name):
        value = shlex.quote('texts=' + json.dumps(['first.txt', 'second;part.txt']))
        with patch.object(broker, '_configured'):
            return broker.dispatch(self.root, f'agent-pipeline plan --pipeline {name} --input {value} --param heading=Hello', access=self.access)

    def test_new_manifest_is_discovered_without_a_registry_entry(self):
        self.assertEqual(broker.catalog(), [])
        shell, wdl = self.plugin(), self.plugin('wdl')
        self.assertEqual({entry['name'] for entry in broker.catalog()}, {shell, wdl})
        self.assertEqual(contracts.backend(shell), 'docker')
        self.assertEqual(contracts.backend(wdl), 'cromwell')
        result = self.plan(shell)
        self.assertEqual(result['plan']['parameters']['heading'], 'Hello')
        self.assertEqual(len(result['plan']['inputs']['texts']), 2)
        with principal_scope(Principal('other')), self.assertRaises(AccessDenied):
            broker.get_plan(self.root, result['plan_id'], access=self.access)

    def test_policy_is_separate_from_adapter_selection(self):
        from isolation.pipeline_policy import RESTRICTED_WORKFLOWS
        with patch.object(service, 'definition') as definition:
            for name in RESTRICTED_WORKFLOWS:
                with self.assertRaises(ExecutionUnavailable): contracts.backend(name)
            definition.assert_not_called()

    def test_parameters_follow_manifest_and_reject_undeclared_capabilities(self):
        name = self.plugin()
        _, manifest, config = contracts.definition(name)
        contracts.validate_parameters({'heading': 'Hello'}, manifest, config)
        for values in ({'unknown': 1}, {'heading': True}, {'heading': '$(id)'}, {'heading': '/etc/passwd'}):
            with self.assertRaises(ValueError): contracts.validate_parameters(values, manifest, config)

    def test_wdl_submission_uses_entrypoint_and_all_declared_file_inputs(self):
        name = self.plugin('wdl'); plan = self.plan(name)
        uploaded, submitted = [], {}
        class Uploads:
            backend = 's3'
            base_uri = 's3://fixture'
            def upload(self, source, key):
                uploaded.append(source.read_text())
                return 's3://fixture/' + key
        def submit(base, method, suffix, **kwargs):
            self.assertEqual((method, suffix), ('POST', ''))
            files = kwargs['files']
            submitted['filename'] = files['workflowSource'][0]
            submitted['source'] = files['workflowSource'][1].read().decode()
            submitted['inputs'] = json.load(files['workflowInputs'][1])
            return {'id': str(uuid4())}
        with patch.object(broker, '_configured', return_value=('http://fixture.invalid', Uploads(), SimpleNamespace(mount_prefix='/outputs'))), patch.object(broker, '_http', side_effect=submit):
            result = broker.dispatch(self.root, plan['command'], access=self.access)
        self.assertEqual(result['status'], 'queued')
        self.assertEqual(submitted['filename'], 'custom-entry.wdl')
        self.assertIn('workflow Fixture', submitted['source'])
        self.assertEqual(uploaded, ['first\n', 'second\n'])
        self.assertEqual(len(submitted['inputs']['Fixture.texts']), 2)
        self.assertTrue(all(value.startswith('s3://fixture/') for value in submitted['inputs']['Fixture.texts']))
        self.assertEqual(submitted['inputs']['Fixture.heading'], 'Hello')

    def test_only_file_slots_can_upload_host_file_contents(self):
        from tools.infrastructure.pipeline_engine.engine.input_storage import upload_local_file_values
        secret = self.base / 'not-an-input.txt'; secret.write_text('must stay on host')
        payload = self.base / 'inputs.json'
        payload.write_text(json.dumps({'Fixture.texts': [str(self.root / 'first.txt')], 'Fixture.heading': str(secret)}))
        calls = []
        uploader = SimpleNamespace(upload=lambda source, key: calls.append(source) or 's3://fixture/' + key)
        upload_local_file_values(payload, uploader, pipeline_name='fixture', run_id='fixture', input_keys={'Fixture.texts'})
        self.assertEqual(calls, [self.root / 'first.txt'])
        self.assertEqual(json.loads(payload.read_text())['Fixture.heading'], str(secret))

    def test_ordinary_and_isolated_submissions_have_the_same_workflow_and_inputs(self):
        name = self.plugin('wdl')
        isolated_plan = self.plan(name)
        local_plan = service.plan(self.root, name,
            {'texts': ['first.txt', 'second;part.txt']}, {'heading': 'Hello'})
        captured = []
        uploader = SimpleNamespace(backend='fixture', base_uri='s3://fixture',
            upload=lambda source, key: 's3://fixture/' + service.digest(source))
        report, metrics = self.base / 'report.txt', self.base / 'metrics.json'
        report.write_text('fixture report'); metrics.write_text('{"files": 2}')
        def submission(files):
            captured.append({key: value[1].read() for key, value in files.items()})
            return {'id': str(uuid4()), 'status': 'Succeeded'}
        with patch.object(cromwell.S3InputUploader, 'from_environment', return_value=uploader), \
             patch.object(cromwell.S3OutputStorage, 'from_environment', return_value=None), \
             patch('requests.post', side_effect=lambda url, **kw: Mock(ok=True, json=lambda: submission(kw['files']))), \
             patch('requests.get', side_effect=[Mock(ok=True, json=lambda: {}),
                 Mock(ok=True, json=lambda: {'outputs': {'Fixture.report': str(report), 'Fixture.metrics': str(metrics)}})]):
            result = service.execute_engine(self.root, JobStore(self.root).get(local_plan['plan_id']))
        self.assertEqual(result['metrics']['files'], 2)
        with patch.object(broker, '_configured', return_value=('http://fixture.invalid', uploader, SimpleNamespace(mount_prefix='/outputs'))), \
             patch.object(broker, '_http', side_effect=lambda base, method, suffix, **kw: submission(kw['files'])):
            self.assertEqual(broker.dispatch(self.root, isolated_plan['command'], access=self.access)['status'], 'queued')
        self.assertEqual(captured[0]['workflowSource'], captured[1]['workflowSource'])
        self.assertEqual(json.loads(captured[0]['workflowInputs']), json.loads(captured[1]['workflowInputs']))
        isolated_options = json.loads(captured[1]['workflowOptions'])
        self.assertFalse(isolated_options['read_from_cache'])
        self.assertFalse(isolated_options['write_to_cache'])
        self.assertEqual(isolated_options['final_workflow_outputs_dir'], '/outputs')

    def test_submission_failure_never_replays_and_preparation_failure_is_distinct(self):
        name = self.plugin('wdl'); plan = self.plan(name)
        uploader = SimpleNamespace(backend='fixture', base_uri='s3://fixture',
                                  upload=lambda source, key: 's3://fixture/' + key)
        configured = ('http://fixture.invalid', uploader, SimpleNamespace(mount_prefix='/outputs'))
        with patch.object(broker, '_configured', return_value=configured), \
             patch.object(broker, '_http', side_effect=OSError('connection lost')) as request:
            result = broker.dispatch(self.root, plan['command'], access=self.access)
            self.assertEqual(result['status'], 'interrupted')
            self.assertTrue(broker.get_plan(self.root, plan['plan_id'], access=self.access)['submission_unknown'])
            broker.dispatch(self.root, plan['command'], access=self.access)
            request.assert_called_once()
        other = self.plan(name)
        with patch.object(broker, '_configured', return_value=configured), \
             patch.object(cromwell, 'prepare_workflow', side_effect=OSError('storage unavailable')), \
             patch.object(broker, '_http') as request:
            self.assertEqual(broker.dispatch(self.root, other['command'], access=self.access)['status'], 'failed')
            self.assertFalse(broker.get_plan(self.root, other['plan_id'], access=self.access)['submission_unknown'])
            request.assert_not_called()

    def test_manifest_api_version_is_retained_for_poll_and_cancel(self):
        name = self.plugin('wdl')
        manifest_path = self.plugins / name / 'runner.yaml'
        manifest = yaml.safe_load(manifest_path.read_text())
        manifest['cromwell_api_version'] = 'v2'
        manifest_path.write_text(yaml.safe_dump(manifest))
        plan = self.plan(name)
        uploader = SimpleNamespace(backend='fixture', base_uri='s3://fixture',
                                  upload=lambda source, key: 's3://fixture/' + key)
        remote_id = str(uuid4())
        with patch.object(broker, '_configured', return_value=('http://fixture.invalid', uploader, SimpleNamespace(mount_prefix='/outputs'))), \
             patch.object(broker, '_http', return_value={'id': remote_id, 'status': 'Running'}) as request:
            broker.dispatch(self.root, plan['command'], access=self.access)
            broker.dispatch(self.root, f"agent-pipeline cancel --job-id {plan['plan_id']}", access=self.access)
            self.assertEqual([call.args[2] for call in request.call_args_list],
                             ['', f'/{remote_id}/status', f'/{remote_id}/abort'])
            self.assertTrue(all(call.kwargs['api_version'] == 'v2' for call in request.call_args_list))
        with patch.object(broker, '_http', return_value={'status': 'Aborted'}) as request:
            self.assertEqual(broker.dispatch(self.root, f"agent-pipeline status --job-id {plan['plan_id']}", access=self.access)['status'], 'cancelled')
            self.assertEqual(request.call_args.kwargs['api_version'], 'v2')

    def test_array_inputs_survive_optional_local_staging(self):
        from tools.infrastructure.pipeline_engine.engine.runner import prepare_pipeline_context
        name = self.plugin()
        inputs = [str(self.root / 'first.txt'), str(self.root / 'second;part.txt')]
        context = prepare_pipeline_context(pipeline_name=name, input_overrides={'texts': inputs},
                                           stage_input=True, artifact_dir=str(self.base / 'artifacts'))
        self.assertEqual([path.read_text() for path in context.resolved_input_overrides['input_path']], ['first\n', 'second\n'])
        with patch('tools.infrastructure.pipeline_engine.engine.runner.stage_pipeline_input', return_value=None):
            context = prepare_pipeline_context(pipeline_name=name, input_overrides={'texts': inputs},
                                               stage_input=True, artifact_dir=str(self.base / 'artifacts'))
        self.assertEqual(context.resolved_input_overrides['input_path'], list(map(Path, inputs)))

    def test_remote_arrays_keep_all_files_and_absent_optional_output_is_allowed(self):
        name = self.plugin('wdl'); plan = self.plan(name)
        private = self.access.metadata_root / '.pipelines' / 'session'
        store = JobStore(private); identifier = plan['plan_id']; remote_id = str(uuid4())
        output = store.directory(identifier) / 'outputs' / 'report.txt'
        record = store.update(identifier, remote_id=remote_id, remote_base='http://fixture.invalid', output_records=[
            {'name': 'report', 'path': str(output), 'wdl_output': 'Fixture.report', 'required': True},
            {'name': 'optional', 'path': str(output.with_name('optional.txt')), 'wdl_output': 'Fixture.optional', 'required': False}])
        response = {'outputs': {'Fixture.report': [f's3://fixture/{remote_id}/a.txt', f's3://fixture/{remote_id}/b.txt'], 'Fixture.optional': None}}
        storage = SimpleNamespace(uri_for_path=lambda value: value,
                                  client=SimpleNamespace(head_object=lambda **kw: {'ContentLength': 3, 'ETag': 'fixture'}))
        with patch.object(broker, '_http', return_value=response), patch('tools.infrastructure.pipeline_engine.engine.input_storage.S3OutputStorage.from_environment', return_value=storage):
            result = broker._collect(private, record)
        files = result['result']['output_records']
        self.assertEqual(len(files), 2)
        self.assertEqual(len({item['path'] for item in files}), 2)
        self.assertEqual({item['remote']['key'].rsplit('/', 1)[-1] for item in files}, {'a.txt', 'b.txt'})

    @unittest.skipUnless(os.getenv('AGENT_TEST_DOCKER') == '1', 'Set AGENT_TEST_DOCKER=1')
    def test_new_plugin_executes_in_existing_image_and_publishes_owned_results(self):
        # The random plugin exists only on the host, never in the image build.
        name = self.plugin(); plan = self.plan(name)
        private = self.access.metadata_root / '.pipelines' / 'session'
        store = JobStore(private); record = store.get(plan['plan_id'])
        private_access = WorkspaceAccess(self.access.ownership, self.access.metadata_root / '.pipelines')
        metadata = {'session_id': 'session', 'owner_user_id': 'plugin-owner',
                    'session_dir': str(private), 'workspace_dir': str(private / 'outputs')}
        result = asyncio.run(supervisor.calculate(isolated_worker._operation, {'record': record}, metadata,
                             'pipeline_execute', access=private_access, quota_access=self.access))
        store.update(record['job_id'], status='succeeded', result=result, execution_backend='docker')
        published = broker.dispatch(self.root, f"agent-pipeline results --job-id {record['job_id']}", access=self.access)
        report = next(item for item in published['files'] if Path(item['path']).name == 'report.txt')
        self.assertEqual((self.root / report['path']).read_text(), 'Hello\nfirst\nsecond\n')
        self.assertEqual(result['metrics'], {'files': 2})


if __name__ == '__main__': unittest.main()
