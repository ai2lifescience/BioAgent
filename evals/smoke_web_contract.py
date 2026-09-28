"""Browser-facing contract checks for the two web clients."""

from __future__ import annotations

import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import threading
import unittest
from urllib.request import urlopen

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from interfaces.web import AgentRequestHandler


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
        with urlopen(self.base_url + path, timeout=10) as response:
            return response.status, response.headers.get_content_type(), response.read().decode("utf-8")

    def test_root_and_assistant_use_module_clients(self):
        status, content_type, body = self.fetch("/")
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "text/html")
        self.assertIn('type="module" src="/static/app.js"', body)

        status, content_type, body = self.fetch("/assistant")
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "text/html")
        self.assertIn('type="module" src="./static/assistant.js"', body)

    def test_shared_transport_and_split_module_are_served(self):
        for path, marker in (
            ("/static/api-client.js", "export function createApiClient"),
            ("/static/session-sidebar.js", "export function createSessionSidebar"),
            ("/static/workspace-panel.js", "export function createWorkspacePanel"),
            ("/static/app.js", 'from "/static/api-client.js"'),
            ("/static/assistant.js", 'from "/static/api-client.js"'),
        ):
            status, content_type, body = self.fetch(path)
            self.assertEqual(status, 200, path)
            self.assertEqual(content_type, "application/javascript", path)
            self.assertIn(marker, body, path)

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
        self.assertIn('id="status"', completed.stdout)
        self.assertIn("Ready", completed.stdout)


if __name__ == "__main__":
    unittest.main()
