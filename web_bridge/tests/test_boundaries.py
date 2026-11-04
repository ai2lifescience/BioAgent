"""The core must operate without importing BioAgent; its adapter is replaceable."""
import ast
from pathlib import Path
import subprocess
import sys
import unittest


class BoundaryTests(unittest.TestCase):
    def test_core_does_not_import_host_implementation(self):
        forbidden = {'harness', 'interfaces', 'auth', 'isolation', 'tools', 'agents'}
        root = Path(__file__).resolve().parents[1]
        sources = [*root.glob('*.py'), *root.glob('browser/*.py'), *root.glob('transfer/*.py')]
        for source in sources:
            for node in ast.walk(ast.parse(source.read_text())):
                modules = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ''] if isinstance(node, ast.ImportFrom) and not node.level else []
                self.assertFalse(forbidden & {name.split('.')[0] for name in modules}, source.name)

    def test_protocol_accepts_another_host_without_loading_bioagent(self):
        program = '''
import sys, importlib.abc, os, tempfile
from types import SimpleNamespace
class NoBioAgent(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'auth','harness','interfaces','isolation','tools','agents'}:
            raise AssertionError('Unexpected host dependency: ' + fullname)
sys.meta_path.insert(0, NoBioAgent())
from web_bridge import configure_host
from web_bridge.bridge import WebsiteBridge, issue_ticket
from web_bridge.browser.service import observe_page
from web_bridge.transfer.service import Transfers
class AlternateHost:
    access_denied = PermissionError
    auth_error = PermissionError
    def current_user(self): return SimpleNamespace(user_id='external', username='Example')
    def ensure_session(self, session_id):
        assert session_id == 'example-session'
        return {}
    def require_session(self, session_id): assert session_id == 'example-session'
configure_host(AlternateHost())
os.environ['AGENT_WEBSITE_SITES']='{"example":["https://example.test"]}'
os.environ['AGENT_WEBSITE_CLIENTS']='{}'
os.environ['AGENT_WEBSITE_SECRET']='x'*40
with tempfile.TemporaryDirectory() as directory:
    bridge = WebsiteBridge(directory+'/bridge.sqlite3')
    token = issue_ticket('x'*40, site_id='example', origin='https://example.test', subject='external')
    binding = bridge.connect(ticket=token, site_id='example', origin='https://example.test',
        instance_id='browser', session_id='example-session', context={'revision':'one'}, capabilities=[])
    assert bridge.get_binding(binding['binding_id'], binding['token'])['session_id']=='example-session'
'''
        subprocess.run([sys.executable, '-B', '-c', program], check=True, capture_output=True, text=True)


if __name__ == '__main__': unittest.main()
