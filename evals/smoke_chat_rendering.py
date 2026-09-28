"""Browser regressions for saved figures and collapsed execution details."""
from __future__ import annotations

import base64
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from interfaces.web import AgentRequestHandler, WEB_UI_DIR


SESSION_ID = "figure-history"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
)
ARTIFACTS = [
    {"path": f"outputs/figure.{extension}", "kind": "image", "size": len(PNG)}
    for extension in ("png", "jpeg", "webp", "bmp")
]
RESULT = {
    "session_id": SESSION_ID,
    "answer": "Saved the figures.",
    "status": "ok",
    "runtime": {"elapsed_seconds": 1, "model_key": "fixture"},
    "artifacts": ARTIFACTS,
    "workspace_files": ARTIFACTS,
    "evidence": {"tools": ["python_execute"]},
    "trace": [{"event": "run_finished", "data": {"tool_count": 1}}],
    "approval_decision": {
        "approved": True, "tool_name": "python_execute", "arguments": {"code": "print(42)"},
    },
}

# Exercise the real modules and DOM on first load, after approval, and on an
# actual reload. A separate browser profile keeps the user's sessions untouched.
PROBE = """
<script type="module">
try {
  const waitFor = async (condition) => {
    for (let i = 0; i < 500; i++) {
      if (condition()) return;
      await new Promise(resolve => setTimeout(resolve, 10));
    }
    throw new Error('UI did not become ready');
  };
  const assert = (value, message) => { if (!value) throw new Error(message); };
  await waitFor(() => !document.querySelector('#send').disabled
    && document.querySelectorAll('#chat .message.assistant').length);
  const configFailed = location.pathname === '/config-failure-test';
  const expected = configFailed ? 3 : 4;
  const figures = [...document.querySelectorAll('#chat .artifact-figure img')];
  assert(figures.length === expected, `Expected ${expected} figures, got ${figures.length}`);
  for (const img of figures) {
    img.loading = 'eager';
    await img.decode();
    assert(img.naturalWidth > 0, 'Figure could not load');
    assert(new URL(img.src).searchParams.get('session_id') === 'figure-history', 'Wrong session');
  }
  const checkDetails = (root) => {
    assert([...root.querySelectorAll('[data-runtime-panel]')].every(p => p.hidden), 'Runtime panel expanded by default');
    assert([...root.querySelectorAll('.run-plan-record')].every(p => !p.open), 'Reviewed plan expanded by default');
    const tab = root.querySelector('[data-runtime-tab="plan"]');
    const panel = root.querySelector('[data-runtime-panel="plan"]');
    tab.click();
    assert(!panel.hidden && tab.getAttribute('aria-selected') === 'true', 'Plan cannot expand');
    tab.click();
    assert(panel.hidden && tab.getAttribute('aria-selected') === 'false', 'Plan cannot collapse');
  };
  checkDetails(document.querySelector('#chat .message.assistant'));
  // The later plain reply sees workspace files but must not repeat the figures.
  const messages = document.querySelectorAll('#chat .message.assistant');
  assert(!messages[1].querySelector('.artifact-figure'), 'Unrelated reply repeated figures');
  if (!sessionStorage.getItem('reloaded')) {
    if (!configFailed) {
      const { createMessageRenderer } = await import('/static/message-renderer.js');
      const { createArtifactViewers } = await import('/static/artifact-viewers.js');
      const chat = document.createElement('div');
      document.body.append(chat);
      let completed = false;
      const renderer = createMessageRenderer({
        chat, getConfig: () => ({}), formatModelLabel: m => m.key,
        workspaceFileUrl: path => '/workspace/file?session_id=figure-history&path=' + encodeURIComponent(path),
        artifactViewers: createArtifactViewers({
          getImageSuffixes: () => ['.png', '.jpeg', '.webp', '.bmp'],
          workspaceFileUrl: path => '/workspace/file?path=' + encodeURIComponent(path),
        }),
        getRunning: () => false, getSessionLoading: () => false, onApprovalBusy: () => {},
        onApprovalResult: result => { renderer.renderMessage('assistant', result.answer, result); completed = true; },
      });
      renderer.renderMessage('assistant', 'Review the operation.', {
        session_id: 'figure-history', approval_required: true,
        approvals: [{approval_id: 'fixture', tool_name: 'python_execute', arguments: {code: 'print(42)'}}],
      });
      assert(chat.querySelector('.approval-plan').open, 'Pending approval must stay reviewable');
      [...chat.querySelectorAll('button')].find(b => b.textContent === 'Approve').click();
      await waitFor(() => completed);
      checkDetails(chat.querySelector('.message:last-child'));
      assert(chat.querySelector('.message:last-child .artifact-figure'), 'Approved result lost its image');
    }
    sessionStorage.setItem('reloaded', 'true');
    location.reload();
  } else {
    document.body.dataset.testResult = 'passed';
  }
} catch (error) {
  document.body.dataset.testResult = 'failed: ' + error.message;
}
</script>
"""


class FigureFixtureHandler(AgentRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path in {"/reload-test", "/config-failure-test"}:
            html = (WEB_UI_DIR / "index.html").read_text() + PROBE
            self._send_bytes(html.encode(), "text/html; charset=utf-8")
        elif path == "/config":
            if "/config-failure-test" in self.headers.get("Referer", ""):
                self._send_json({"error": "fixture unavailable"}, status=503)
            else:
                self._send_json({"models": [{"key": "fixture"}], "default_model_key": "fixture",
                                 "files": {"image_suffixes": [".png", ".jpeg", ".webp", ".bmp"]}})
        elif path == "/sessions":
            self._send_json({"sessions": [{"session_id": SESSION_ID, "title": "Figures"}]})
        elif path == f"/sessions/{SESSION_ID}/messages":
            self._send_json({"messages": [
                {"role": "user", "text": "Create figures."},
                {"role": "assistant", "text": RESULT["answer"], "result": RESULT},
                {"role": "user", "text": "Thanks"},
                {"role": "assistant", "text": "You're welcome.", "result": {"files": ARTIFACTS}},
            ]})
        elif path == "/workspace":
            self._send_json({"workspace": {"files": ARTIFACTS}})
        elif path == "/workspace/file":
            self._send_bytes(PNG, "image/png")
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == "/approve_stream":
            self._read_json()
            data = f"event: result\ndata: {json.dumps(RESULT)}\n\n".encode()
            self._send_bytes(data, "text/event-stream")
        else:
            super().do_POST()


@unittest.skipUnless(shutil.which("google-chrome"), "headless Chrome is not installed")
class ChatRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FigureFixtureHandler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def check_page(self, path):
        with TemporaryDirectory(prefix="chat-browser-") as profile:
            result = subprocess.run([
                shutil.which("google-chrome"), "--headless=new", "--no-sandbox",
                "--disable-gpu", "--disable-dev-shm-usage", "--no-proxy-server",
                f"--user-data-dir={profile}", "--virtual-time-budget=12000",
                "--dump-dom", self.base_url + path,
            ], capture_output=True, text=True, timeout=25, check=True)
        marker = result.stdout.split("data-test-result=", 1)[-1][:160]
        self.assertIn('data-test-result="passed"', result.stdout, marker)

    def test_saved_and_approved_figures_survive_reload_with_details_collapsed(self):
        self.check_page("/reload-test")

    def test_standard_figures_survive_unavailable_config(self):
        self.check_page("/config-failure-test")


if __name__ == "__main__":
    unittest.main()
