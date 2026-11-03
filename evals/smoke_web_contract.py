"""Browser-facing checks for the built Vite web clients."""

from __future__ import annotations

from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import interfaces.web as web
from interfaces.web import AgentRequestHandler, FRONTEND_DIST_DIR


class WebStartupTests(unittest.TestCase):
    def test_cli_network_listener_starts_in_multiuser_mode(self):
        # Exercise the actual entrypoint, including both background services.
        # Handler-only HTTP tests cannot detect run_server startup failures.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment = dict(os.environ)
            environment.pop('AGENT_AUTH_MODE', None)
            environment.update({
                'AGENT_WORKER_BACKEND': 'docker', 'AGENT_PUBLIC_ORIGIN': '',
                'AGENT_METADATA_DIR': str(root / 'metadata'),
                'AGENT_SESSIONS_DIR': str(root / 'sessions'),
                'AGENT_AUTH_DB': str(root / 'auth.sqlite3'),
                'AGENT_SESSION_DB': str(root / 'history.sqlite3'),
                'AGENT_RUN_DB': str(root / 'runs.sqlite3'),
                'AGENT_KNOWLEDGE_DB': str(root / 'knowledge.sqlite3'),
            })
            log_path = root / 'server.log'
            with log_path.open('w') as log:
                process = subprocess.Popen(
                    [sys.executable, '-B', '-m', 'interfaces.web', '--host', '0.0.0.0', '--port', '0'],
                    cwd=Path(__file__).resolve().parents[1], env=environment,
                    stdout=log, stderr=subprocess.STDOUT,
                )
                try:
                    deadline = time.monotonic() + 20
                    while time.monotonic() < deadline:
                        output = log_path.read_text()
                        self.assertIsNone(process.poll(), output)
                        match = re.search(r'http://0\.0\.0\.0:(\d+)', output)
                        if match:
                            base = f'http://127.0.0.1:{match[1]}'
                            try:
                                with urlopen(base + '/health', timeout=1) as response:
                                    self.assertEqual(json.load(response)['status'], 'ok')
                                with urlopen(base + '/auth/status', timeout=1) as response:
                                    self.assertEqual(json.load(response)['mode'], 'multiuser')
                                return
                            except OSError:
                                pass
                        time.sleep(.1)
                    self.fail('Server did not become healthy: ' + log_path.read_text())
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)


class WebContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), AgentRequestHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def fetch(self, path: str) -> tuple[int, str, str]:
        request = Request(self.base_url + path, method="GET")
        try:
            response = urlopen(request, timeout=10)
        except HTTPError as error:
            return error.code, error.headers.get_content_type(), error.read().decode("utf-8", errors="replace")
        with response:
            return response.status, response.headers.get_content_type(), response.read().decode("utf-8")

    def _assert_asset(self, path: str) -> None:
        status, content_type, body = self.fetch(path)
        self.assertEqual(status, 200, path)
        self.assertTrue(body, path)
        if path.endswith((".js", ".mjs")):
            self.assertEqual(content_type, "application/javascript", path)
        elif path.endswith(".css"):
            self.assertEqual(content_type, "text/css", path)

    def test_async_approval_returns_job_without_holding_a_stream(self):
        job = {"run_id": "fixture-run", "session_id": "fixture-session", "status": "queued", "request": "private prompt"}
        body = {"session_id": "fixture-session", "approval_id": "fixture-approval", "approved": True}
        with patch.object(web, "enqueue_approval", return_value=job) as enqueue, patch.object(AgentRequestHandler, "_stream_run") as stream:
            request = Request(self.base_url + "/approve_async", json.dumps(body).encode(), {"Content-Type": "application/json"})
            with urlopen(request, timeout=5) as response:
                self.assertEqual(response.status, 202)
                result = json.load(response)
            self.assertEqual(result["run_id"], "fixture-run")
            self.assertEqual(result["status"], "queued")
            self.assertNotIn("request", result)
            enqueue.assert_called_once_with("fixture-session", True, "fixture-approval")
            stream.assert_not_called()

        with patch.object(web, "enqueue_approval") as enqueue:
            for invalid in ({**body, "approved": "true"}, {**body, "approval_id": ""}):
                request = Request(self.base_url + "/approve_async", json.dumps(invalid).encode(), {"Content-Type": "application/json"})
                with self.assertRaises(HTTPError) as caught:
                    urlopen(request, timeout=5)
                self.assertEqual(caught.exception.code, 400)
            enqueue.assert_not_called()

    def test_all_route_shells_and_referenced_assets_are_served(self):
        for route, entry in (
            ("/", "index.html"),
            ("/index.html", "index.html"),
            ("/assistant", "assistant.html"),
            ("/assistant/", "assistant.html"),
            ("/assistant.html", "assistant.html"),
            ("/assistant-demo", "assistant-demo.html"),
            ("/assistant-demo/", "assistant-demo.html"),
            ("/assistant-demo.html", "assistant-demo.html"),
        ):
            status, content_type, body = self.fetch(route)
            self.assertEqual(status, 200, route)
            self.assertEqual(content_type, "text/html", route)
            self.assertTrue(re.search(r"(?:src|href)=[\"'](?:/static/|\./static/)[^\"']+", body), route)
            self.assertTrue((FRONTEND_DIST_DIR / entry).exists() or not FRONTEND_DIST_DIR.exists())
            for asset in re.findall(r"(?:src|href)=[\"']((?:/static/|\./static/)[^\"']+)[\"']", body):
                self._assert_asset("/" + asset.lstrip("./"))

    def test_public_embed_script_keeps_external_integration_url(self):
        self._assert_asset("/static/assistant-embed.js")
        status, _, body = self.fetch("/static/assistant-embed.js")
        self.assertEqual(status, 200)
        self.assertIn("assistant", body.lower())

    def test_favicon_and_missing_assets(self):
        status, content_type, _ = self.fetch("/favicon.svg")
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "image/svg+xml")
        for path in ("/static/does-not-exist.js", "/static/%2e%2e/index.html", "/static/%2Fetc/passwd"):
            status, _, _ = self.fetch(path)
            self.assertEqual(status, 404, path)

    def test_missing_frontend_build_has_actionable_diagnostic(self):
        original = web.FRONTEND_DIST_DIR
        try:
            web.FRONTEND_DIST_DIR = Path(original).parent / ".missing-frontend-dist-for-contract-test"
            status, content_type, body = self.fetch("/")
        finally:
            web.FRONTEND_DIST_DIR = original
        self.assertEqual(status, 503)
        self.assertEqual(content_type, "text/plain")
        self.assertIn("npm --prefix frontend ci", body)
        self.assertIn("npm --prefix frontend run build", body)

    def test_api_remains_available_without_frontend_build(self):
        original = web.FRONTEND_DIST_DIR
        try:
            web.FRONTEND_DIST_DIR = Path(original).parent / ".missing-frontend-dist-for-api-test"
            status, content_type, body = self.fetch("/health")
        finally:
            web.FRONTEND_DIST_DIR = original
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "application/json")
        self.assertIn('"status"', body)

    def test_config_is_json_contract(self):
        status, content_type, body = self.fetch("/config")
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "application/json")
        payload = json.loads(body)
        self.assertIn("models", payload)
        self.assertIn("files", payload)

    @unittest.skipUnless(shutil.which("google-chrome"), "headless Chrome is not installed")
    def test_assistant_loads_in_headless_browser(self):
        command = [
            shutil.which("google-chrome") or "google-chrome",
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--no-proxy-server",
            "--virtual-time-budget=2500",
            "--dump-dom",
            f"{self.base_url}/assistant",
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=20, check=True)
        self.assertIn("assistant", completed.stdout.lower())


if __name__ == "__main__":
    unittest.main()
