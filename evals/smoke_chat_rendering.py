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

from interfaces.web import AgentRequestHandler, FRONTEND_DIST_DIR


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
APPROVED_RESULT = {
    **RESULT,
    "answer": "The approved operation saved the figures.",
    "approval_decision": {**RESULT["approval_decision"], "approval_id": "fixture"},
}
PENDING_APPROVAL = {
    "session_id": SESSION_ID,
    "answer": "Review the requested operation.",
    "status": "pending_approval",
    "approval_required": True,
    "approvals": [{
        "approval_id": "fixture",
        "tool_name": "python_execute",
        "arguments": {"code": "print(42)"},
    }],
}

# Exercise the built React app on first load, after approval, and on an actual
# reload. A separate browser profile keeps the user's sessions untouched.
PROBE = """
<script type="module">
try {
  const waitFor = async (condition, description) => {
    for (let i = 0; i < 500; i++) {
      if (condition()) return;
      await new Promise(resolve => setTimeout(resolve, 10));
    }
    throw new Error('Timed out: ' + description);
  };
  const assert = (value, message) => { if (!value) throw new Error(message); };
  const messages = () => [...document.querySelectorAll('#chat .message.assistant:not([data-approval-message="true"])')];
  const ready = () => {
    const send = document.querySelector('.composer #send');
    return send && !send.disabled && messages().length >= 2;
  };
  await waitFor(ready, 'React conversation and composer');
  const configFailed = location.pathname === '/config-failure-test';
  const expected = configFailed ? 3 : 4;
  const checkFigures = async (root) => {
    const figures = [...root.querySelectorAll('.artifact-figure img')];
    assert(figures.length === expected, `Expected ${expected} figures, got ${figures.length}`);
    for (const img of figures) {
      img.loading = 'eager';
      // `decode()` can remain pending in headless Chrome when a lazy image
      // was promoted after a reload. Wait for the network completion signal,
      // then keep the actual natural-size assertion below.
      await waitFor(() => img.complete, 'figure image load');
      assert(img.naturalWidth > 0, 'Figure could not load');
      assert(new URL(img.src).searchParams.get('session_id') === 'figure-history', 'Wrong figure session');
    }
  };
  const checkDetails = async (root) => {
    const panels = [...root.querySelectorAll('[data-runtime-panel]')];
    assert(panels.length === 4, 'Execution detail panels are missing');
    assert(panels.every(p => p.hidden), 'Runtime panel expanded by default');
    assert(!root.querySelector('.approval-item'), 'A duplicate approval box was added to the result');
    const tab = root.querySelector('[data-runtime-tab="plan"]');
    const panel = root.querySelector('[data-runtime-panel="plan"]');
    assert(tab && panel, 'Plan tab or panel missing');
    tab.click();
    await waitFor(() => !panel.hidden && tab.getAttribute('aria-selected') === 'true', 'Plan expands');
    tab.click();
    await waitFor(() => panel.hidden && tab.getAttribute('aria-selected') === 'false', 'Plan collapses');
  };
  await checkFigures(messages()[0]);
  await checkDetails(messages()[0]);
  // The later plain reply sees workspace files but must not repeat the figures.
  assert(messages()[1].textContent.includes("You're welcome."), 'Plain reply is missing');
  assert(!messages()[1].querySelector('.artifact-figure'), 'Unrelated reply repeated figures');
  if (configFailed) {
    assert(document.querySelector('.error-banner')?.textContent.includes('Configuration unavailable'),
      'Unavailable configuration did not show a recoverable error');
  }
  const approvedMessage = () => messages().find(message =>
    message.querySelector('.message-body')?.textContent.includes('The approved operation saved the figures.'));
  if (!sessionStorage.getItem('reloaded')) {
    if (!configFailed) {
      const approval = document.querySelector('#chat .approval-item[data-approval-id="fixture"]');
      assert(approval?.querySelector('.approval-plan')?.open, 'Pending approval must stay reviewable');
      const approve = [...approval.querySelectorAll('button')].find(button => button.textContent === 'Approve');
      assert(approve && !approve.disabled, 'React approval button is unavailable');
      approve.click();
      await waitFor(() => approvedMessage() && ready(), 'Approved result and unlocked composer');
      assert(approve.disabled, 'Completed approval can be submitted twice');
      assert(approval.isConnected, 'Original approval box was replaced after clicking');
      assert(!approval.querySelector('.approval-plan').open, 'Submitted approval must collapse');
      await checkDetails(approvedMessage());
      await checkFigures(approvedMessage());
    }
    sessionStorage.setItem('reloaded', 'true');
    location.reload();
  } else {
    if (!configFailed) {
      assert(approvedMessage(), 'Approved result was lost after reload');
      const approval = document.querySelector('#chat .approval-item[data-approval-id="fixture"]');
      assert(approval, 'Original approval disappeared after reload');
      assert(!approval.querySelector('.approval-plan').open, 'Restored decision must default to collapsed');
      assert([...approval.querySelectorAll('button')].every(button => button.disabled), 'Restored approval can be submitted twice');
      await checkDetails(approvedMessage());
      await checkFigures(approvedMessage());
    }
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
            html = (FRONTEND_DIST_DIR / "index.html").read_text() + PROBE
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
            payload = {"messages": [
                {"role": "user", "text": "Create figures."},
                {"role": "assistant", "text": RESULT["answer"], "result": RESULT},
                {"role": "user", "text": "Thanks"},
                {"role": "assistant", "text": "You're welcome.", "result": {"files": ARTIFACTS}},
            ]}
            if self.server.approved:
                payload["messages"].append({
                    "role": "assistant", "text": APPROVED_RESULT["answer"], "result": APPROVED_RESULT,
                })
            self._send_json(payload)
        elif path == "/runs":
            payload = {"runs": []}
            if not self.server.approved and "/config-failure-test" not in self.headers.get("Referer", ""):
                payload["runs"] = [{"status": "pending_approval", "result": PENDING_APPROVAL}]
            self._send_json(payload)
        elif path == "/workspace":
            self._send_json({"workspace": {"files": ARTIFACTS}})
        elif path == "/workspace/file":
            self._send_bytes(PNG, "image/png")
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == "/approve_stream":
            payload = self._read_json()
            self.server.approval_requests.append(payload)
            if payload != {"session_id": SESSION_ID, "approval_id": "fixture", "approved": True}:
                self._send_json({"error": "Incorrect approval request"}, status=400)
                return
            self.server.approved = True
            data = f"event: result\ndata: {json.dumps(APPROVED_RESULT)}\n\n".encode()
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
        self.server.approved = False
        self.server.approval_requests = []
        with TemporaryDirectory(prefix="chat-browser-") as profile:
            result = subprocess.run([
                shutil.which("google-chrome"), "--headless=new", "--no-sandbox",
                "--disable-gpu", "--disable-dev-shm-usage", "--no-proxy-server",
                # The probe performs a real approval round trip and then a full
                # page reload. Give the second React boot enough virtual time
                # to restore the approved history before dump-dom snapshots it.
                f"--user-data-dir={profile}", "--virtual-time-budget=30000",
                "--dump-dom", self.base_url + path,
            ], capture_output=True, text=True, timeout=25, check=True)
        marker = result.stdout.split("data-test-result=", 1)[-1][:160]
        self.assertIn('data-test-result="passed"', result.stdout, marker)
        self.assertEqual(self.server.approval_requests, [] if path == "/config-failure-test" else [{
            "session_id": SESSION_ID, "approval_id": "fixture", "approved": True,
        }])

    def test_saved_and_approved_figures_survive_reload_with_details_collapsed(self):
        self.check_page("/reload-test")

    def test_standard_figures_survive_unavailable_config(self):
        self.check_page("/config-failure-test")


if __name__ == "__main__":
    unittest.main()
