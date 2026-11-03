"""Security and durability contracts for the multi-user network/job brokers."""
import asyncio
import base64
import importlib
import io
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from isolation import network as public_http, supervisor as isolated, WorkspaceAccess
from tools.infrastructure.pipeline_engine import broker
from auth import Principal, principal_scope, AccessDenied, OwnershipStore
from tools.infrastructure.pipeline_engine.store import JobStore


class PublicHTTPTests(unittest.TestCase):
    def test_pdb_download_is_limited_to_exact_rcsb_structure_urls(self):
        with patch.object(public_http, '_addresses', return_value=['93.184.216.34']), \
             patch.object(public_http, '_exchange', return_value={'status': 200}) as exchange:
            for suffix in ('cif', 'pdb', 'bcif'):
                self.assertEqual(public_http.fetch(f'https://files.rcsb.org/download/1A3N.{suffix}', 'pdb_download')['status'], 200)
            exchange.reset_mock()
            for url in ('http://files.rcsb.org/download/1A3N.cif',
                        'https://files.rcsb.org:80/download/1A3N.cif',
                        'https://example.org/download/1A3N.cif',
                        'https://files.rcsb.org/other/1A3N.cif',
                        'https://files.rcsb.org/download/1A3N.cif?redirect=elsewhere',
                        'https://files.rcsb.org/download/../1A3N.cif'):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    public_http.fetch(url, 'pdb_download')
            exchange.assert_not_called()

    def test_pdb_worker_provider_uses_pipe_and_preserves_structure_bytes(self):
        from isolation.network_client import install
        from tools.infrastructure.providers.pdb import client
        content = b'data_1A3N\n# fixture structure bytes\n'
        reply = {'status': 200, 'headers': {'Content-Type': 'application/octet-stream'}, 'body': base64.b64encode(content).decode()}
        reader, writer = io.BytesIO(json.dumps(reply).encode() + b'\n'), io.BytesIO()
        with tempfile.TemporaryDirectory() as directory, patch.object(client, 'request_http'), \
             patch('requests.request', side_effect=AssertionError('Worker must not use direct HTTP')):
            install(SimpleNamespace(), 'pdb_download', reader, writer)
            result = client.download_pdb_structure('1a3n', 'cif', directory)
            self.assertEqual(Path(result['structure_path']).read_bytes(), content)
            self.assertEqual(json.loads(writer.getvalue()), {'network_request': 'https://files.rcsb.org/download/1A3N.cif'})
        for status in (302, 404, 503):
            reply['status'] = status
            with patch.object(client, 'request_http'):
                install(SimpleNamespace(), 'pdb_download', io.BytesIO(json.dumps(reply).encode() + b'\n'), io.BytesIO())
                with self.assertRaisesRegex(ValueError, f'HTTP {status}'):
                    client.download_pdb_structure('1A3N')

    def test_blocks_private_special_ports_and_credentials(self):
        for url in ('http://127.0.0.1/', 'http://169.254.169.254/', 'http://192.168.164.46/',
                    'http://[::1]/', 'http://[::ffff:127.0.0.1]/', 'file:///etc/passwd',
                    'http://user:pass@example.org/', 'https://example.org:39000/'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                public_http.destination(url)

    def test_mixed_public_private_dns_is_rejected(self):
        addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443))
                     for ip in ('93.184.216.34', '127.0.0.1')]
        with patch.object(socket, 'getaddrinfo', return_value=addresses), self.assertRaises(ValueError):
            public_http.destination('https://example.org/')

    def test_connection_uses_validated_ip(self):
        addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 80))]
        with patch.dict(os.environ, {'AGENT_DISABLE_PROXY': 'true'}), \
             patch.object(socket, 'getaddrinfo', return_value=addresses), \
             patch.object(socket, 'create_connection', side_effect=OSError('test stop')) as connect:
            with self.assertRaises(OSError): public_http.fetch('http://example.org/', 'web_fetch')
            self.assertEqual(connect.call_args.args[0], ('93.184.216.34', 80))

    def test_code_tools_cannot_request_network(self):
        with self.assertRaises(ValueError): public_http.fetch('https://example.org/', 'code_test')

    def test_proxy_dns_is_pinned_and_private_answers_still_rejected(self):
        reply = {'status': 200, 'body': base64.b64encode(json.dumps({'Answer': [
            {'type': 1, 'data': '127.0.0.1'}]}).encode()).decode()}
        with patch.dict(os.environ, {'AGENT_PUBLIC_DNS': 'google'}), \
             patch.object(public_http, '_exchange', return_value=reply) as exchange, \
             self.assertRaises(ValueError):
            public_http.destination('https://example.org/')
        self.assertEqual(exchange.call_args.args[1:], ('dns.google', 443, '8.8.8.8'))

    def test_search_challenge_is_an_error_not_empty_evidence(self):
        from isolation.network_client import install
        reply = {'status': 202, 'headers': {}, 'body': base64.b64encode(b'challenge-form').decode()}
        module = SimpleNamespace()
        install(module, 'web_search', io.BytesIO(json.dumps(reply).encode() + b'\n'), io.BytesIO())
        with self.assertRaisesRegex(ValueError, 'browser verification'):
            asyncio.run(module.request('https://html.duckduckgo.com/html/', {'q': 'test'}))


class PipelineExampleQuotaTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        scope = principal_scope(Principal('alice')); scope.__enter__(); self.addCleanup(scope.__exit__, None, None, None)
        self.access = WorkspaceAccess(OwnershipStore(self.base / 'metadata'), self.base / 'sessions')
        self.access.ownership.claim('session')
        self.root = self.access.workspace('session'); self.root.mkdir(parents=True)
        self.definition = self.base / 'definition'
        source = self.definition / 'data/input'; source.mkdir(parents=True)
        (source / 'one.txt').write_bytes(b'12345')
        (source / 'two.txt').write_bytes(b'1234567')
        mock = patch.object(broker.service, 'definition', return_value=(self.definition, {'engine': 'shell'}, {}))
        mock.start(); self.addCleanup(mock.stop)

    def example(self):
        return broker.dispatch(self.root, 'agent-pipeline example --pipeline template_shell', access=self.access)

    def assert_no_copy(self):
        from isolation.storage import reservations
        self.assertFalse([path for path in self.root.rglob('*') if path.is_file()])
        self.assertFalse(list(self.root.rglob('.example-*')))
        self.assertFalse(reservations(self.access))

    def test_example_respects_session_account_and_file_limits(self):
        for setting, error in [('SESSION_STORAGE_BYTES', 'Session storage'), ('ACCOUNT_STORAGE_BYTES', 'Account storage'), ('MAX_FILE_BYTES', 'File')]:
            with self.subTest(setting=setting), patch.dict(os.environ, {'AGENT_' + setting: '1'}):
                with self.assertRaisesRegex(ValueError, error): self.example()
                self.assert_no_copy()

    def test_example_counts_pending_uploads(self):
        from interfaces.uploads import Uploads
        uploads = Uploads(self.access)
        with patch.dict(os.environ, {'AGENT_SESSION_STORAGE_BYTES': '20'}):
            upload = uploads.create('session', 'pending.txt', 10)
            try:
                with self.assertRaisesRegex(ValueError, 'Session storage'): self.example()
            finally: uploads.cancel(upload['upload_id'])
        self.assert_no_copy()

    def test_example_publishes_complete_files_and_repeat_hits_quota(self):
        from isolation.storage import reservations
        with patch.dict(os.environ, {'AGENT_SESSION_STORAGE_BYTES': '12'}):
            result = self.example()
            self.assertEqual(sorted(item['size'] for item in result['files']), [5, 7])
            for item in result['files']:
                path = self.root / item['workspace_path']
                self.assertEqual(path.read_bytes(), (self.definition / 'data/input' / path.name).read_bytes())
            before = sorted(str(path) for path in self.root.rglob('*'))
            with self.assertRaisesRegex(ValueError, 'Session storage'): self.example()
            self.assertEqual(sorted(str(path) for path in self.root.rglob('*')), before)
            self.assertFalse(reservations(self.access))

    def test_example_rejects_low_disk_before_copy(self):
        with patch('isolation.storage.shutil.disk_usage', return_value=SimpleNamespace(free=0)):
            with self.assertRaisesRegex(ValueError, 'disk space'): self.example()
        self.assert_no_copy()

    def test_concurrent_sessions_cannot_exceed_shared_account_quota(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from isolation.storage import reservations, usage
        self.access.ownership.claim('other')
        other = self.access.workspace('other'); other.mkdir()
        barrier = Barrier(2)
        def request(root):
            with principal_scope(Principal('alice')):
                barrier.wait(timeout=5)
                try:
                    broker.dispatch(root, 'agent-pipeline example --pipeline template_shell', access=self.access)
                    return 'published'
                except ValueError as exc:
                    self.assertIn('Account storage', str(exc))
                    return 'rejected'
        with patch.dict(os.environ, {'AGENT_ACCOUNT_STORAGE_BYTES': '12'}), ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(request, [self.root, other]))
        self.assertEqual(sorted(results), ['published', 'rejected'])
        self.assertEqual(usage(self.access, 'session') + usage(self.access, 'other'), 12)
        self.assertFalse(reservations(self.access))

    def test_copy_failure_leaves_no_partial_example_or_reservation(self):
        original = broker.copy_stream
        calls = []
        def fail_second(*args, **kwargs):
            calls.append(True)
            if len(calls) == 2: raise OSError('fixture disk write failure')
            return original(*args, **kwargs)
        with patch.object(broker, 'copy_stream', side_effect=fail_second):
            with self.assertRaisesRegex(OSError, 'fixture disk'): self.example()
        self.assertEqual(len(calls), 2)
        self.assert_no_copy()


class PipelineBrokerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        env = patch.dict(os.environ, {'AGENT_AUTH_MODE': 'multiuser', 'AGENT_WORKER_BACKEND': 'docker',
                                      'CROMWELL_URL': 'http://cromwell.invalid'})
        env.start(); self.addCleanup(env.stop)
        self.ownership = OwnershipStore(self.base / 'metadata')
        self.access = WorkspaceAccess(self.ownership, self.base / 'sessions')
        scope = principal_scope(Principal('alice')); scope.__enter__(); self.addCleanup(scope.__exit__, None, None, None)
        self.session = SimpleNamespace(session_id='alice-session')
        self.ownership.claim(self.session.session_id)
        self.root = self.access.workspace(self.session.session_id); self.root.mkdir(parents=True)
        (self.root / 'example.fa').write_text('>synthetic\nACGTACGT\n')

    def plan(self, extra=''):
        with patch.object(broker, '_configured'):
            return broker.dispatch(self.root, 'agent-pipeline plan --pipeline template_wdl --input sequence=example.fa ' + extra, access=self.access)

    def test_private_plan_snapshot_and_cross_account_checks(self):
        result = self.plan(); identifier = result['plan_id']
        self.assertEqual(result['plan']['inputs']['sequence'][0]['path'], 'example.fa')
        self.assertTrue(result['plan']['immutable_input_snapshot'])
        private = broker._owned(self.root, access=self.access)
        self.assertFalse(private.is_relative_to(self.root))
        (self.root / 'example.fa').write_text('changed')
        broker.service.verify(private, broker.get_plan(self.root, identifier, access=self.access)['plan'])
        fake = self.root / 'runtime/agent_runs/.pipeline/jobs.sqlite3'
        fake.parent.mkdir(parents=True); fake.write_text('model-controlled fake state')
        self.assertEqual(broker.get_plan(self.root, identifier, access=self.access)['status'], 'planned')
        with principal_scope(Principal('bob')):
            with self.assertRaises(AccessDenied): broker.get_plan(self.root, identifier, access=self.access)

    def test_rejects_parameter_injection_and_unapproved_workflows(self):
        for extra in ('--param label=bad\"quote', '--param min_length=-1', '--param uppercase=1'):
            with self.subTest(extra=extra), self.assertRaises(ValueError): self.plan(extra)
        with self.assertRaises(Exception):
            broker.dispatch(self.root, 'agent-pipeline plan --pipeline unregistered_workflow', access=self.access)

    def test_poll_and_cancel_use_persisted_remote_id_without_resubmission(self):
        identifier = self.plan()['plan_id']; private = broker._owned(self.root, access=self.access)
        remote_id = str(uuid4())
        JobStore(private).update(identifier, status='running', remote_id=remote_id,
                                deadline=10**12, remote_base='http://cromwell.invalid')
        with patch.object(broker, '_http', return_value={'status': 'Running'}) as request:
            value = broker.dispatch(self.root, f'agent-pipeline status --job-id {identifier}', access=self.access)
            self.assertEqual(value['status'], 'running')
            self.assertIn(remote_id, request.call_args.args[2])
            broker.dispatch(self.root, f'agent-pipeline cancel --job-id {identifier}', access=self.access)
            self.assertTrue(any(call.args[2].endswith('/abort') for call in request.call_args_list))
            self.assertFalse(any(call.args[2] == '' for call in request.call_args_list))
        with patch.object(broker, '_http', return_value={'status': 'Aborted'}):
            self.assertEqual(broker.dispatch(self.root, f'agent-pipeline status --job-id {identifier}', access=self.access)['status'], 'cancelled')

    def test_ambiguous_submission_is_never_retried(self):
        identifier = self.plan()['plan_id']; private = broker._owned(self.root, access=self.access)
        JobStore(private).update(identifier, status='submitting')
        with patch.object(broker, '_http') as request:
            self.assertEqual(broker.dispatch(self.root, f'agent-pipeline status --job-id {identifier}', access=self.access)['status'], 'interrupted')
            self.assertTrue(JobStore(private).get(identifier)['submission_unknown'])
            broker.dispatch(self.root, f'agent-pipeline run --plan-id {identifier}', access=self.access)
            request.assert_not_called()

    def test_output_scope_cannot_read_other_job_or_host_path(self):
        from tools.infrastructure.pipeline_engine.engine.input_storage import S3OutputStorage
        storage = S3OutputStorage('bucket', 'outputs', None, '/remote/outputs')
        remote_id = str(uuid4())
        for source in ('/etc/passwd', 's3://bucket/outputs/another-job/file',
                       f's3://bucket/outputs/{remote_id}/../another-job/file'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                broker._output_key(storage, source, remote_id)
        self.assertEqual(broker._output_key(storage, f'/remote/outputs/workflow/{remote_id}/file', remote_id)[0], 'bucket')

    def test_outputs_are_downloadable_public_paths_and_restore_after_edits(self):
        from tools.infrastructure.workspace.public import public_payload
        identifier = self.plan()['plan_id']; private = broker._owned(self.root, access=self.access)
        store = JobStore(private); artifact = store.directory(identifier) / 'outputs/report.md'
        artifact.parent.mkdir(); artifact.write_text('verified report')
        store.update(identifier, status='succeeded', result={'output_records': [{
            'name': 'report', 'path': str(artifact), 'workspace_path': artifact.relative_to(private).as_posix(),
            'exists': True, 'sha256': broker.service.digest(artifact), 'size': artifact.stat().st_size}]})
        result = broker.dispatch(self.root, f'agent-pipeline results --job-id {identifier}', access=self.access)
        self.assertNotIn('[internal path]', json.dumps(public_payload(result, self.root)))
        path = self.root / result['files'][0]['workspace_path']
        self.assertEqual(path.read_text(), 'verified report')
        path.write_text('edited by user')
        broker.dispatch(self.root, f'agent-pipeline results --job-id {identifier}', access=self.access)
        self.assertEqual(path.read_text(), 'verified report')

    def test_active_quota_and_repeat_run_cannot_submit(self):
        identifiers = [self.plan()['plan_id'] for _ in range(3)]
        private = broker._owned(self.root, access=self.access)
        for identifier in identifiers[:2]: JobStore(private).update(identifier, status='queued')
        with patch.object(broker, '_configured', return_value=('http://cromwell.invalid', None, None)), \
             patch.object(broker, '_http') as request:
            with self.assertRaisesRegex(ValueError, 'limit'):
                broker.dispatch(self.root, f'agent-pipeline run --plan-id {identifiers[2]}', access=self.access)
            broker.dispatch(self.root, f'agent-pipeline run --plan-id {identifiers[0]}', access=self.access)
            request.assert_not_called()

    def test_network_outage_preserves_active_job_and_deadline_requests_abort(self):
        identifier = self.plan()['plan_id']; private = broker._owned(self.root, access=self.access)
        JobStore(private).update(identifier, status='running', remote_id=str(uuid4()),
                                deadline=0, remote_base='http://cromwell.invalid')
        with patch.object(broker, '_http', side_effect=RuntimeError('offline')):
            value = broker.dispatch(self.root, f'agent-pipeline status --job-id {identifier}', access=self.access)
            self.assertEqual(value['status'], 'running'); self.assertIn('warning', value)
        with patch.object(broker, '_http', return_value={'status': 'Running'}) as request:
            value = broker.dispatch(self.root, f'agent-pipeline status --job-id {identifier}', access=self.access)
            self.assertEqual(value['status'], 'cancelling')
            self.assertTrue(request.call_args.args[2].endswith('/abort'))
        with patch.object(broker, '_http', return_value={'status': 'Aborted'}):
            self.assertEqual(broker.dispatch(self.root, f'agent-pipeline status --job-id {identifier}', access=self.access)['status'], 'timed_out')

    def test_small_remote_preview_uses_etag_for_unversioned_objects(self):
        from unittest.mock import Mock
        from tools.infrastructure.pipeline_engine.engine.input_storage import S3OutputStorage
        identifier = self.plan()['plan_id']; private = broker._owned(self.root, access=self.access)
        remote_id = str(uuid4()); data = b'{"count": 7}'
        store = JobStore(private)
        store.update(identifier, status='succeeded', remote_id=remote_id, result={'output_records': [{
            'path': str(store.directory(identifier) / 'outputs/metrics.json'), 'size': len(data),
            'remote': {'bucket': 'bucket', 'key': f'outputs/{remote_id}/metrics.json', 'etag': 'v1', 'version_id': 'null'},
        }]})
        client = Mock(); client.get_object.return_value = {'Body': io.BytesIO(data), 'ContentLength': len(data)}
        with patch.object(S3OutputStorage, 'from_environment', return_value=S3OutputStorage('bucket', 'outputs', client)):
            result = broker.dispatch(self.root, f'agent-pipeline results --job-id {identifier}', access=self.access)
        self.assertEqual(result['previews'][0]['text'], data.decode())
        self.assertEqual(client.get_object.call_args.kwargs['IfMatch'], 'v1')
        self.assertNotIn('VersionId', client.get_object.call_args.kwargs)

    def test_gateway_outputs_without_etag_use_timestamp_and_size(self):
        from datetime import datetime, timezone, timedelta
        from unittest.mock import Mock
        from tools.infrastructure.pipeline_engine.engine.input_storage import S3OutputStorage
        identifier = self.plan()['plan_id']; private = broker._owned(self.root, access=self.access)
        store = JobStore(private); remote_id = str(uuid4())
        stamp = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
        data = b'count\n7\n'
        record = store.update(identifier, status='running', remote_id=remote_id,
            remote_base='http://cromwell.invalid', deadline=10**12, output_records=[{
                'name': 'report', 'wdl_output': 'Fixture.report',
                'path': str(store.directory(identifier) / 'outputs/report.tsv')}])
        client = Mock()
        client.head_object.return_value = {'ContentLength': len(data), 'LastModified': stamp}
        storage = S3OutputStorage('bucket', 'outputs', client)
        with patch.object(S3OutputStorage, 'from_environment', return_value=storage), \
             patch.object(broker, '_http', return_value={'outputs': {'Fixture.report': f's3://bucket/outputs/{remote_id}/report.tsv'}}):
            completed = broker._collect(private, record)
            self.assertEqual(completed['status'], 'succeeded')
            artifact = broker._remote_file(completed, 0)
            self.assertEqual(completed['result']['output_records'][0]['remote']['last_modified'], stamp.isoformat())
            client.get_object.return_value = {'Body': io.BytesIO(data), 'ContentLength': len(data), 'LastModified': stamp}
            with broker.remote_stream(self.root, artifact['path'], access=self.access) as (response, _):
                self.assertEqual(response['Body'].read(), data)
            client.get_object.return_value = {'Body': io.BytesIO(data[1:4]), 'ContentLength': 3,
                'LastModified': stamp, 'ContentRange': f'bytes 1-3/{len(data)}'}
            with broker.remote_stream(self.root, artifact['path'], access=self.access, byte_range='bytes=1-3') as (response, _):
                self.assertEqual(response['Body'].read(), data[1:4])
            self.assertEqual(client.get_object.call_args.kwargs['Range'], 'bytes=1-3')
            body = io.BytesIO(data[1:4])
            client.get_object.return_value = {'Body': body, 'ContentLength': 3,
                'LastModified': stamp, 'ContentRange': f'bytes 0-2/{len(data)}'}
            with self.assertRaisesRegex(ValueError, 'invalid byte range'):
                with broker.remote_stream(self.root, artifact['path'], access=self.access, byte_range='bytes=1-3'): pass
            self.assertTrue(body.closed)
            for metadata in ({'LastModified': stamp + timedelta(seconds=1), 'ContentLength': len(data)},
                             {'LastModified': stamp, 'ContentLength': len(data) + 1},
                             {'ContentLength': len(data)}):
                with self.subTest(metadata=metadata):
                    body = io.BytesIO(data)
                    client.get_object.return_value = {'Body': body, **metadata}
                    with self.assertRaisesRegex(ValueError, 'changed'):
                        with broker.remote_stream(self.root, artifact['path'], access=self.access): pass
                    self.assertTrue(body.closed)
            with principal_scope(Principal('bob')), self.assertRaises(AccessDenied):
                with broker.remote_stream(self.root, artifact['path'], access=self.access): pass

            # Recovering a previously unavailable result must clear its old warning.
            store.update(identifier, artifact_status='unavailable', error='previous storage failure')
            client.get_object.return_value = {'Body': io.BytesIO(data), 'ContentLength': len(data), 'LastModified': stamp}
            result = broker.dispatch(self.root, f'agent-pipeline results --job-id {identifier}', access=self.access)
            self.assertEqual(result['artifact_status'], 'available')
            self.assertIsNone(result['error'])
            self.assertEqual(result['previews'][0]['text'], data.decode())

    def test_output_failure_does_not_leave_completed_workflow_running(self):
        identifier = self.plan()['plan_id']; private = broker._owned(self.root, access=self.access)
        store = JobStore(private)
        store.update(identifier, status='running', remote_id=str(uuid4()),
                     remote_base='http://cromwell.invalid', deadline=10**12)
        with patch.object(broker, '_http', return_value={'status': 'Succeeded'}) as request, \
             patch.object(broker, '_collect', side_effect=ValueError('storage metadata unavailable')):
            state = broker.dispatch(self.root, f'agent-pipeline status --job-id {identifier}', access=self.access)
            self.assertEqual(state['status'], 'succeeded')
            self.assertEqual(state['artifact_status'], 'unavailable')
            results = broker.dispatch(self.root, f'agent-pipeline results --job-id {identifier}', access=self.access)
            self.assertEqual(results['status'], 'succeeded')
            self.assertEqual(results['files'], [])
            self.assertIn('warning', results)
            request.assert_called_once()
            self.assertEqual(request.call_args.args[1], 'GET')
        recovered = store.update(identifier, artifact_status='available', error=None, result={'output_records': []})
        # Recollection is read-only relative to execution: it never starts a new job.
        store.update(identifier, artifact_status='unavailable')
        with patch.object(broker, '_collect', return_value=recovered) as collect, \
             patch.object(broker.service, 'results', return_value={'status': 'succeeded', 'files': [], 'tables': []}), \
             patch.object(broker, '_http') as request:
            result = broker.dispatch(self.root, f'agent-pipeline results --job-id {identifier}', access=self.access)
            self.assertEqual(result['status'], 'succeeded')
            collect.assert_called_once()
            request.assert_not_called()

    def test_large_remote_outputs_are_references_and_stream_on_import(self):
        from unittest.mock import Mock
        from tools.infrastructure.pipeline_engine.engine.input_storage import S3OutputStorage
        identifier = self.plan()['plan_id']; private = broker._owned(self.root, access=self.access)
        store = JobStore(private); remote_id = str(uuid4())
        size = 40 * 1024 * 1024
        path = store.directory(identifier) / 'outputs/result.bin'
        record = store.update(identifier, status='running', remote_id=remote_id, remote_base='http://cromwell.invalid',
                              deadline=10**12, output_records=[{'path': str(path), 'name': 'result'}])
        client = Mock(); client.head_object.return_value = {'ContentLength': size, 'ETag': 'version-marker'}
        storage = S3OutputStorage('bucket', 'outputs', client, '/remote/outputs')
        source = f's3://bucket/outputs/{remote_id}/result.bin'
        with patch.object(S3OutputStorage, 'from_environment', return_value=storage), \
             patch.object(broker, '_http', return_value={'outputs': {}}), \
             patch('tools.infrastructure.pipeline_engine.engine.wdl.output_value', return_value=source):
            result = broker._collect(private, record)
            self.assertEqual(result['status'], 'succeeded')
            client.get_object.assert_not_called()
            public = broker.dispatch(self.root, f'agent-pipeline results --job-id {identifier}', access=self.access)
            artifact = public['files'][0]
            self.assertTrue(artifact['remote']); self.assertEqual(artifact['size'], size)
            self.assertFalse(path.exists()); self.assertFalse((store.directory(identifier) / 'results.zip').exists())
            class Body:
                def __init__(self): self.left = size
                def read(self, amount):
                    if not 0 < amount <= 1024 * 1024: raise AssertionError('unbounded remote read')
                    count = min(amount, self.left); self.left -= count
                    return b'x' * count
                def close(self): pass
            client.get_object.side_effect = lambda **kwargs: {'Body': Body(), 'ContentLength': size}
            with principal_scope(Principal('bob')):
                with self.assertRaises(AccessDenied):
                    with broker.remote_stream(self.root, artifact['path'], access=self.access): pass
            imported = broker.materialize(self.root, artifact['path'], access=self.access)
            self.assertEqual((self.root / imported['path']).stat().st_size, size)
            self.assertEqual(client.get_object.call_args.kwargs['IfMatch'], 'version-marker')
            with broker.bundle_stream(self.root, identifier, access=self.access) as stream:
                import zipfile
                with zipfile.ZipFile(stream) as archive:
                    self.assertEqual(archive.infolist()[0].file_size, size)
            self.assertFalse((store.directory(identifier) / 'results.zip').exists())

    @unittest.skipUnless(os.getenv('AGENT_TEST_DOCKER') == '1', 'Set AGENT_TEST_DOCKER=1')
    def test_real_container_broker_redirect_revalidates_private_target(self):
        metadata = {'session_id': self.session.session_id, 'owner_user_id': 'alice', 'session_dir': str(self.root), 'workspace_dir': str(self.root / 'outputs')}
        handler = importlib.import_module('tools.function_tools.sources.web_fetch')._operation
        original = public_http.fetch
        def redirected(url, name):
            if url == 'https://example.org/':
                return {'status': 302, 'headers': {'Location': 'http://127.0.0.1/'}, 'body': ''}
            return original(url, name)
        with patch.object(public_http, 'fetch', side_effect=redirected), self.assertRaisesRegex(ValueError, 'Private'):
            asyncio.run(isolated.calculate(handler, {'url': 'https://example.org/', 'max_chars': 1000}, metadata, 'web_fetch', access=self.access))

    @unittest.skipUnless(os.getenv('AGENT_TEST_DOCKER') == '1', 'Set AGENT_TEST_DOCKER=1')
    def test_real_container_parses_broker_response_into_owned_evidence(self):
        metadata = {'session_id': self.session.session_id, 'owner_user_id': 'alice', 'session_dir': str(self.root), 'workspace_dir': str(self.root / 'outputs')}
        handler = importlib.import_module('tools.function_tools.sources.web_fetch')._operation
        reply = {'status': 200, 'headers': {'Content-Type': 'text/html'},
                 'body': base64.b64encode(b'<title>Example</title><p>Public evidence.</p>').decode()}
        with patch.object(public_http, 'fetch', return_value=reply):
            result = asyncio.run(isolated.calculate(handler, {'url': 'https://example.org/', 'max_chars': 1000}, metadata, 'web_fetch', access=self.access))
        self.assertEqual(result['data']['returned'], 1)
        self.assertTrue(list(self.root.rglob('evidence.json')))


if __name__ == '__main__': unittest.main()
