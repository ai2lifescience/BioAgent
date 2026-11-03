"""Container isolation checks. Set AGENT_TEST_DOCKER=1 for real Docker probes."""
from __future__ import annotations

import asyncio
import base64
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from uuid import uuid4
from unittest.mock import patch

from harness import runtime, sandbox
from isolation import supervisor as isolated
from isolation import WorkspaceAccess, require_execution_policy
from auth import Principal, principal_scope, ExecutionUnavailable
from harness.sessions import SessionMetadataStore
from isolation.protocol import relative_path
from isolation.files import inventory, import_staged, fingerprint


class WorkerProtocolTests(unittest.TestCase):
    def test_packages_import_without_the_application_runtime(self):
        probe = '''
import sys
import auth
assert 'isolation' not in sys.modules
assert 'harness' not in sys.modules
import isolation
assert 'harness' not in sys.modules
assert 'tools' not in sys.modules
'''
        completed = subprocess.run([sys.executable, '-B', '-c', probe],
                                   capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_explicit_access_rejects_wrong_owner_and_workspace_before_docker(self):
        from auth import OwnershipStore
        with tempfile.TemporaryDirectory() as temporary, \
             patch.dict(os.environ, {'AGENT_AUTH_MODE': 'multiuser'}), principal_scope(Principal('alice')):
            root = Path(temporary)
            ownership = OwnershipStore(root / 'metadata')
            ownership.claim('alice-session')
            access = WorkspaceAccess(ownership, root / 'workspaces')
            metadata = {'session_id': 'alice-session', 'owner_user_id': 'alice',
                        'session_dir': str(root / 'workspaces' / 'alice-session')}
            for changed in ({'owner_user_id': 'bob'}, {'session_dir': str(root / 'elsewhere')}):
                with self.subTest(changed=changed), patch.object(isolated, 'ensure_available') as docker:
                    with self.assertRaises(ExecutionUnavailable):
                        asyncio.run(isolated.calculate(None, {}, {**metadata, **changed}, 'code_test', access=access))
                    docker.assert_not_called()

    def test_rejects_untrusted_paths_and_file_directory_conflicts(self):
        for name in ['../secret', '/etc/passwd', 'a/../../b', 'a//b', 'a/./b', 'a\\b', '']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                relative_path(name)

    def test_rejects_symlinks_and_nonregular_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'link').symlink_to('/etc/passwd')
            with self.assertRaises(ValueError): inventory(root)
            (root / 'link').unlink()
            os.mkfifo(root / 'pipe')
            with self.assertRaises(ValueError): inventory(root)

    def test_import_checks_all_conflicts_before_writing_and_preserves_new_uploads(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = root / 'stage'; stage.mkdir()
            (root / 'edited').write_bytes(b'old')
            before = {'edited': fingerprint(root, 'edited')}
            (root / 'edited').write_bytes(b'concurrent change')
            (stage / 'new').write_bytes(b'new'); (stage / 'edited').write_bytes(b'worker')
            with self.assertRaises(ValueError):
                import_staged(root, before, stage)
            self.assertFalse((root / 'new').exists())
            (stage / 'edited').unlink()
            import_staged(root, {}, stage)
            self.assertEqual((root / 'edited').read_bytes(), b'concurrent change')
            self.assertEqual((root / 'new').read_bytes(), b'new')

    def test_missing_container_runtime_has_no_host_fallback(self):
        with patch.dict(os.environ, {'AGENT_AUTH_MODE': 'multiuser', 'AGENT_WORKER_BACKEND': 'docker', 'AGENT_ALLOW_SHARED_EXECUTION': 'true'}), \
             patch.object(isolated, '_available', None), patch.object(isolated.shutil, 'which', return_value=None):
            with self.assertRaises(ExecutionUnavailable): require_execution_policy()

    def test_profile_excludes_execution_bypasses(self):
        from tools.registry import build_all_tools
        with patch.dict(os.environ, {'AGENT_AUTH_MODE': 'multiuser', 'AGENT_WORKER_BACKEND': 'docker'}):
            names = {tool.name for tool in build_all_tools('unused')}
            self.assertIn('code_test', names)
            self.assertIn('python_execute', names)
            self.assertIn('pipeline_shell', names)
            self.assertIn('pipeline_specialist', names)
            self.assertIn('knowledge_ingest', names)
            self.assertIn('web_fetch', names)
            self.assertIn('pdb_download', names)
            self.assertIn('structure_inspect', names)
            self.assertEqual(sandbox.sandbox_capabilities(), [])


@unittest.skipUnless(os.getenv('AGENT_TEST_DOCKER') == '1', 'Set AGENT_TEST_DOCKER=1 to run real containers')
class DockerWorkerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        environment = patch.dict(os.environ, {
            'AGENT_AUTH_MODE': 'multiuser', 'AGENT_WORKER_BACKEND': 'docker',
            'AGENT_METADATA_DIR': str(self.root / 'metadata'),
            'AGENT_SESSIONS_DIR': str(self.root / 'sessions'),
            'OPENROUTER_API_KEY': 'host-only-secret-marker',
        })
        environment.start(); self.addCleanup(environment.stop)
        self.store = SessionMetadataStore(self.root / 'metadata')
        self.access = WorkspaceAccess(self.store.ownership, self.root / 'sessions')
        for target, name, value in [(runtime, 'STATE_STORE', self.store),
                                     (runtime, 'SESSION_DB', self.root / 'history.sqlite3'),
                                     (sandbox, 'WORKSPACES_DIR', self.root / 'sessions')]:
            change = patch.object(target, name, value); change.start(); self.addCleanup(change.stop)
        scope = principal_scope(Principal('alice'))
        scope.__enter__(); self.addCleanup(scope.__exit__, None, None, None)
        session = self.store.create_session(session_id='alice-session')
        self.metadata = {'session_id': session.session_id, 'owner_user_id': 'alice', **sandbox.prepare_run(session)}
        self.workspace = sandbox.session_root(session.session_id)
        self.workspace.mkdir(parents=True)
        self.handler = importlib.import_module('tools.function_tools.coding.code_test')._operation

    def calculate(self, **kwargs):
        return asyncio.run(isolated.calculate(self.handler, kwargs or {'command': 'python -m unittest'}, self.metadata, 'code_test', access=self.access))

    def test_pdb_download_imports_broker_bytes_into_owned_workspace(self):
        from isolation import network
        content = b'data_1A3N\n_entry.id 1A3N\n'
        reply = {'status': 200, 'headers': {'Content-Type': 'application/octet-stream'},
                 'body': base64.b64encode(content).decode()}
        handler = importlib.import_module('tools.function_tools.biology.pdb_download')._operation
        with patch.object(network, 'fetch', return_value=reply) as fetch:
            result = asyncio.run(isolated.calculate(handler, {'pdb_id': '1A3N', 'file_format': 'cif'},
                self.metadata, 'pdb_download', access=self.access))
        fetch.assert_called_once_with('https://files.rcsb.org/download/1A3N.cif', 'pdb_download')
        path = result['data']['structure_path']
        self.assertFalse(Path(path).is_absolute())
        self.assertEqual((self.workspace / path).read_bytes(), content)
        self.assertEqual(result['files'][0]['kind'], 'structure')

    def test_real_code_cannot_reach_host_other_user_network_or_credentials(self):
        sibling = self.root / 'sessions' / 'bob-session'
        sibling.mkdir()
        secret = sibling / 'private.txt'; secret.write_text('Bob private content')
        probe = f'''
import os, socket, unittest
from pathlib import Path
class Isolation(unittest.TestCase):
    def test_boundary(self):
        self.assertNotEqual(os.getuid(), 0)
        self.assertNotIn('OPENROUTER_API_KEY', os.environ)
        self.assertFalse(Path({str(secret)!r}).exists())
        self.assertFalse(Path({str(self.store.ownership.path)!r}).exists())
        self.assertFalse(Path('/var/run/docker.sock').exists())
        self.assertIn('CapEff:\\t0000000000000000', Path('/proc/self/status').read_text())
        if Path('/sys/fs/cgroup/memory.max').exists():
            self.assertEqual(Path('/sys/fs/cgroup/memory.max').read_text().strip(), '1073741824')
            self.assertEqual(Path('/sys/fs/cgroup/pids.max').read_text().strip(), '64')
        sock = socket.socket(); sock.settimeout(1)
        self.assertNotEqual(sock.connect_ex(('1.1.1.1', 443)), 0); sock.close()
        with self.assertRaises(OSError): Path('/app/host-write.txt').write_text('no')
        Path('report.txt').write_text('isolated result')
'''
        (self.workspace / 'test_boundary.py').write_text(probe)
        result = self.calculate()
        self.assertEqual(result['data']['returncode'], 0, result)
        self.assertEqual((self.workspace / 'report.txt').read_text(), 'isolated result')
        self.assertEqual(secret.read_text(), 'Bob private content')

    def test_symlink_output_never_reaches_host_workspace(self):
        (self.workspace / 'test_symlink.py').write_text("from pathlib import Path\nPath('escape').symlink_to('/etc/passwd')\n")
        with self.assertRaisesRegex(ValueError, 'links'):
            self.calculate()
        self.assertFalse((self.workspace / 'escape').exists())

    def test_async_tool_runs_through_sdk_in_container_and_saves_history(self):
        from agents.testing import ScriptedModel, ModelStep, function_call, assistant_message
        (self.workspace / 'test_sdk.py').write_text("from pathlib import Path\nPath('sdk-result.txt').write_text('container sdk result')\n")
        model = ScriptedModel([
            ModelStep(output=[function_call('code_test', {'command': 'python -m unittest'}, call_id='isolated-test')]),
            ModelStep(output=[assistant_message('Tests completed.')]),
        ])
        result = asyncio.run(runtime.async_run_agent('Test the uploaded Python code', session_id='alice-session', model=model))
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual((self.workspace / 'sdk-result.txt').read_text(), 'container sdk result')
        self.assertEqual(self.store.get_session('alice-session').metadata['message_count'], 2)

    def test_python_executor_uses_container_and_returns_artifact(self):
        handler = importlib.import_module('tools.function_tools.coding.python_execute')._operation
        value = asyncio.run(isolated.calculate(handler, {
            'code': "from pathlib import Path\nPath('answer.txt').write_text('42')",
            'input_paths': [], 'output_paths': ['answer.txt'], 'timeout_seconds': 10,
        }, self.metadata, 'python_execute', access=self.access))
        artifacts = [item for item in value['files'] if item['name'] == 'answer.txt']
        self.assertEqual(len(artifacts), 1, value)
        self.assertEqual((self.workspace / artifacts[0]['path']).read_text(), '42')

    def test_large_preview_and_generated_output_use_disk_staging(self):
        large = self.workspace / 'large.txt'
        with large.open('wb') as stream: stream.truncate(40 * 1024 * 1024)
        handler = importlib.import_module('tools.function_tools.workspace.file_inspection')._operation
        metadata = {**self.metadata, 'files': [{'path': 'large.txt', 'workspace_path': 'large.txt'}]}
        result = asyncio.run(isolated.calculate(handler, {'path': 'large.txt', 'max_preview_lines': 2}, metadata, 'file_inspection', access=self.access))
        self.assertTrue(result['data']['truncated'])
        handler = importlib.import_module('tools.function_tools.coding.python_execute')._operation
        result = asyncio.run(isolated.calculate(handler, {
            'code': "with open('result.bin', 'wb') as f:\n    for _ in range(40): f.write(b'x' * 1024 * 1024)",
            'input_paths': [], 'output_paths': ['result.bin'], 'timeout_seconds': 20,
        }, self.metadata, 'python_execute', access=self.access))
        artifact = next(item for item in result['files'] if item['name'] == 'result.bin')
        self.assertEqual((self.workspace / artifact['path']).stat().st_size, 40 * 1024 * 1024)
        self.assertEqual(large.stat().st_size, 40 * 1024 * 1024)

    def test_disk_budget_failure_imports_nothing(self):
        (self.workspace / 'test_budget.py').write_text("from pathlib import Path\nPath('too-big').write_bytes(b'x' * 3 * 1024 * 1024)\n")
        with patch.dict(os.environ, {'AGENT_WORKER_STORAGE_BYTES': str(2 * 1024 * 1024)}):
            with self.assertRaisesRegex(ValueError, 'budget'):
                self.calculate()
        self.assertFalse((self.workspace / 'too-big').exists())

    def test_timeout_kills_container_without_importing_partial_files(self):
        (self.workspace / 'test_slow.py').write_text('import time\ntime.sleep(60)\n')
        names = []
        original = isolated.command
        def capture(name):
            names.append(name)
            return original(name)
        with patch.object(isolated, 'WORKER_TIMEOUT', 2), patch.object(isolated, 'command', side_effect=capture):
            with self.assertRaises(asyncio.TimeoutError): self.calculate()
        result = subprocess.run(['docker', 'inspect', names[0]], capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    def test_reaper_removes_expired_orphan_but_preserves_live_worker(self):
        names = ['bioagent-test-' + uuid4().hex for _ in range(2)]
        try:
            for name, deadline in zip(names, [time.time() - 1, time.time() + 60]):
                subprocess.run(['docker', 'run', '-d', '--name', name, '--network=none', '--read-only',
                    '--cap-drop=ALL', '--security-opt=no-new-privileges', '--user=10001:10001',
                    '--label', f'{isolated.DEADLINE_LABEL}={deadline}', '--entrypoint=python',
                    os.getenv('AGENT_WORKER_IMAGE', isolated.IMAGE), '-c', 'import time; time.sleep(60)'],
                    check=True, capture_output=True, timeout=15)
            isolated.reap_expired_workers()
            self.assertNotEqual(subprocess.run(['docker', 'inspect', names[0]], capture_output=True).returncode, 0)
            self.assertEqual(subprocess.run(['docker', 'inspect', names[1]], capture_output=True).returncode, 0)
        finally:
            subprocess.run(['docker', 'rm', '-f', *names], capture_output=True, timeout=15)


if __name__ == '__main__':
    unittest.main()
