"""Real HTTP and service-boundary checks; no model or external services."""
from __future__ import annotations

import http.client
from http.server import ThreadingHTTPServer
import json
import os
import io
import sys
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from harness import runtime, sandbox, jobs
from web_bridge import bridge as website
from auth import AccessDenied, AuthError, AuthStore, Principal, current_principal, principal_scope, database
from harness.sessions import SessionMetadataStore
from interfaces import api
from interfaces.auth import validate_server
from interfaces.web import AgentRequestHandler


class UserIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, {
            "AGENT_AUTH_MODE": "multiuser", "AGENT_AUTH_DB": str(self.root / "auth.sqlite3"),
            "AGENT_AUTH_COOKIE_SECURE": "false", "AGENT_PUBLIC_ORIGIN": "",
            "AGENT_METADATA_DIR": str(self.root / "metadata"), "AGENT_SESSIONS_DIR": str(self.root / "workspaces"),
            "AGENT_RUN_DB": str(self.root / "runs.sqlite3"), "AGENT_KNOWLEDGE_DB": str(self.root / "knowledge.sqlite3"),
            "AGENT_ALLOW_SHARED_EXECUTION": "false",
            "AGENT_WORKER_BACKEND": "local", "AGENT_REGISTRATION": "false", "AGENT_DIRECT_HTTP": "false",
            "AGENT_WEBSITE_SECRET": "x" * 40,
            "AGENT_WEBSITE_SITES": json.dumps({"fixture": ["https://fixture.test"]}),
        })
        env.start(); self.addCleanup(env.stop)
        self.store = SessionMetadataStore(self.root / "metadata")
        self.queue = jobs.RunQueue(self.root / "runs.sqlite3")
        self.bridge = website.WebsiteBridge(self.root / "bridge.sqlite3")
        for target, name, value in [
            (runtime, "STATE_STORE", self.store), (runtime, "SESSION_DB", str(self.root / "history.sqlite3")),
            (sandbox, "WORKSPACES_DIR", self.root / "workspaces"), (jobs, "_queue", self.queue),
            (website, "_bridge", self.bridge),
        ]:
            mock = patch.object(target, name, value); mock.start(); self.addCleanup(mock.stop)
        dispatcher = patch.object(self.queue, "dispatch"); dispatcher.start(); self.addCleanup(dispatcher.stop)
        self.accounts = AuthStore()
        self.alice = Principal(self.accounts.add_user("alice", "alice-password-123"), "alice")
        self.bob = Principal(self.accounts.add_user("bob", "bob-password-123"), "bob")
        with principal_scope(self.alice):
            self.sid = api.create_session()["session_id"]
            self.job = self.queue.enqueue("private prompt", self.sid, "unused", 1)
            self.queue.update(self.job["run_id"], "pending_approval", result={"approvals": [{"approval_id": "approve-alice"}]})
            self.file = api.write_workspace_file(self.sid, "private.txt", b"Alice's private data")
        with principal_scope(self.bob):
            self.bob_sid = api.create_session()["session_id"]
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), AgentRequestHandler)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True); thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.alice_cookie = self.login("alice", "alice-password-123")
        self.bob_cookie = self.login("bob", "bob-password-123")

    def request(self, path, *, method="GET", body=None, cookie=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        request_headers = dict(headers or {})
        if cookie:
            request_headers["Cookie"] = cookie
        if body is not None and not isinstance(body, bytes):
            body = json.dumps(body)
            request_headers["Content-Type"] = "application/json"
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        data = response.read()
        result = response.status, dict(response.getheaders()), data
        connection.close()
        return result

    def login(self, username, password):
        status, headers, _ = self.request("/auth/login", method="POST", body={"username": username, "password": password})
        self.assertEqual(status, 200)
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        return headers["Set-Cookie"].split(";", 1)[0]

    def test_authentication_required_and_no_identity_from_body(self):
        for path in ["/sessions", "/runs", "/config", f"/workspace?session_id={self.sid}"]:
            self.assertEqual(self.request(path)[0], 401)
        self.assertEqual(self.request("/run", method="POST", body={"user_id": self.alice.user_id, "session_id": self.sid, "request": "hello"})[0], 401)
        self.assertEqual(self.request("/auth/login", method="POST", body={"username": "alice", "password": "wrong"})[0], 401)

    def test_resumable_upload_and_range_download_over_old_worker_limit(self):
        from urllib.parse import quote
        size = 33 * 1024 * 1024 + 3
        status, _, body = self.request('/workspace/uploads', method='POST', cookie=self.alice_cookie,
            body={'session_id': self.sid, 'filename': 'large.txt', 'size': size})
        self.assertEqual(status, 201, body)
        row = json.loads(body); route = '/workspace/uploads/' + row['upload_id']
        self.assertEqual(self.request(route, cookie=self.bob_cookie)[0], 404)
        while row['offset'] < size:
            chunk = b'x' * min(8 * 1024 * 1024, size - row['offset'])
            status, _, body = self.request(route, method='PATCH', cookie=self.alice_cookie,
                body=chunk, headers={'Upload-Offset': str(row['offset'])})
            self.assertEqual(status, 200, body); row = json.loads(body)
        status, _, body = self.request(route + '/complete', method='POST', cookie=self.alice_cookie)
        self.assertEqual(status, 200, body)
        file = json.loads(body)['files'][0]
        url = '/workspace/file?session_id=' + self.sid + '&path=' + quote(file['path'])
        status, headers, data = self.request(url, cookie=self.alice_cookie, headers={'Range': 'bytes=33554432-33554434'})
        self.assertEqual((status, data), (206, b'xxx'))
        self.assertEqual(headers['Content-Range'], f'bytes 33554432-33554434/{size}')
        self.assertEqual(self.request(url, cookie=self.bob_cookie)[0], 404)
        self.assertEqual(self.request(url, cookie=self.alice_cookie, headers={'Range': f'bytes={size}-'})[0], 416)

    def test_onboarding_catalog_is_complete_in_isolated_mode(self):
        from tools.infrastructure.pipeline_engine import broker, service
        from isolation.pipeline_policy import RESTRICTED_WORKFLOWS

        expected = {entry['name'] for entry in service.catalog(compact=True)}
        eligible = expected - RESTRICTED_WORKFLOWS
        for endpoint in ('', 'http://cromwell.invalid'):
            with self.subTest(endpoint=endpoint), patch.dict(os.environ, {
                'AGENT_WORKER_BACKEND': 'docker', 'CROMWELL_URL': endpoint,
            }):
                status, _, body = self.request('/config', cookie=self.alice_cookie)
                self.assertEqual(status, 200)
                payload = json.loads(body)
                self.assertTrue(payload['isolated_execution'])
                self.assertEqual({entry['name'] for entry in payload['pipelines']}, expected)
                executable = {entry['name'] for entry in broker.catalog()}
                local = {entry['name'] for entry in service.catalog(compact=True) if entry.get('engine') != 'wdl'}
                self.assertEqual(executable, eligible if endpoint else eligible & local)

    def test_public_registration_and_immediate_private_session(self):
        with patch.dict(os.environ, {"AGENT_REGISTRATION": "true"}):
            self.assertTrue(json.loads(self.request('/auth/status')[2])['registration_enabled'])
            status, headers, body = self.request('/auth/register', method='POST', body={
                'username': 'new-user', 'password': 'a-new-password-123', 'user_id': self.alice.user_id})
            self.assertEqual(status, 201)
            self.assertNotEqual(json.loads(body)['user']['id'], self.alice.user_id)
            cookie = headers['Set-Cookie'].split(';', 1)[0]
            self.assertEqual(json.loads(self.request('/sessions', cookie=cookie)[2])['sessions'], [])
            self.assertEqual(self.request(f'/sessions/{self.sid}/messages', cookie=cookie)[0], 404)
            self.assertEqual(self.request('/sessions', method='POST', body={}, cookie=cookie)[0], 201)
            self.assertEqual(self.request('/auth/register', method='POST', body={
                'username': 'new-user', 'password': 'a-new-password-123'})[0], 409)
            self.assertEqual(self.request('/auth/register', method='POST', body={
                'username': 'short', 'password': 'short'})[0], 400)
        self.assertEqual(self.request('/auth/register', method='POST', body={
            'username': 'disabled', 'password': 'a-new-password-123'})[0], 403)

    def test_registration_rate_limits_and_rejects_cross_origin(self):
        with patch.dict(os.environ, {"AGENT_REGISTRATION": "true"}):
            body = {'username': 'x', 'password': 'short'}
            self.assertEqual(self.request('/auth/register', method='POST', body=body,
                headers={'Origin': 'http://evil.test'})[0], 401)
            for _ in range(5):
                self.assertEqual(self.request('/auth/register', method='POST', body=body)[0], 400)
            self.assertEqual(self.request('/auth/register', method='POST', body=body)[0], 429)

    def test_network_startup_chooses_accounts_and_accepts_ip_origin(self):
        from interfaces.auth import configure_server, secure_cookie
        with patch.dict(os.environ):
            os.environ.pop('AGENT_AUTH_MODE', None)
            os.environ.pop('AGENT_AUTH_COOKIE_SECURE', None)
            configure_server('0.0.0.0')
            self.assertEqual(os.environ['AGENT_AUTH_MODE'], 'multiuser')
            self.assertFalse(secure_cookie())
            self.assertEqual(self.request('/sessions', headers={'Host': '192.168.1.20:8000'})[0], 401)
            self.assertEqual(self.request('/auth/login', method='POST', body={
                'username': 'alice', 'password': 'alice-password-123'},
                headers={'Host': '192.168.1.20:8000', 'Origin': 'http://192.168.1.20:8000'})[0], 200)
            self.assertEqual(self.request('/auth/status', headers={'Host': 'evil.test'})[0], 401)
            self.assertEqual(self.request('/auth/logout', method='POST', body={}, cookie=self.alice_cookie,
                headers={'Host': '192.168.1.20:8000', 'Origin': 'http://evil.test'})[0], 401)

    def test_open_registration_cannot_enable_shared_execution(self):
        with patch.dict(os.environ, {'AGENT_ALLOW_SHARED_EXECUTION': 'true', 'AGENT_REGISTRATION': 'true'}):
            self.assertEqual(self.request('/run', method='POST', cookie=self.bob_cookie,
                body={'session_id': self.bob_sid, 'request': 'hello'})[0], 403)

    def test_stop_is_owned_idempotent_and_cannot_overwrite_a_completed_run(self):
        with principal_scope(self.alice):
            self.queue.update(self.job['run_id'], 'running')
        path = f"/runs/{self.job['run_id']}/cancel"
        self.assertEqual(self.request(path, method='POST', body={}, cookie=self.bob_cookie)[0], 404)
        self.assertEqual(self.request(path, method='POST', body={}, cookie=self.alice_cookie,
                                      headers={'Origin': 'http://evil.test'})[0], 401)
        code, _, data = self.request(path, method='POST', body={}, cookie=self.alice_cookie)
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(data)['cancel_requested'])
        self.request(path, method='POST', body={}, cookie=self.alice_cookie)
        with principal_scope(self.alice):
            events = self.queue.events(self.job['run_id'])
            self.assertEqual(sum(item['event'] == 'cancelling' for item in events), 1)
            self.queue.update(self.job['run_id'], 'succeeded', result={'status': 'ok', 'answer': 'Completed before Stop.'})
        payload = json.loads(self.request(path, method='POST', body={}, cookie=self.alice_cookie)[2])
        self.assertEqual(payload['status'], 'succeeded')

    def test_queued_stop_never_launches_or_accepts_a_late_worker_result(self):
        with principal_scope(self.bob):
            job = self.queue.enqueue('queued fixture', self.bob_sid, 'fixture', 1)
        path = f"/runs/{job['run_id']}/cancel"
        payload = json.loads(self.request(path, method='POST', body={}, cookie=self.bob_cookie)[2])
        self.assertEqual(payload['status'], 'cancelled')
        self.assertEqual(payload['result']['answer'], 'Stopped before execution.')
        with principal_scope(self.bob):
            self.assertEqual(jobs.execute_job(self.queue, job['run_id']), 0)
            self.assertEqual(self.queue.update(job['run_id'], 'succeeded')['status'], 'cancelled')

    def test_list_filters_and_owner_can_download(self):
        payload = json.loads(self.request("/sessions", cookie=self.bob_cookie)[2])
        self.assertEqual([s["session_id"] for s in payload["sessions"]], [self.bob_sid])
        self.assertEqual(json.loads(self.request("/runs", cookie=self.bob_cookie)[2])["runs"], [])
        status, _, data = self.request(f"/workspace/file?session_id={self.sid}&path={self.file['path']}", cookie=self.alice_cookie)
        self.assertEqual(status, 200)
        self.assertEqual(data, b"Alice's private data")

    def test_cross_user_ids_rejected_everywhere(self):
        cases = [
            ("GET", f"/sessions/{self.sid}/messages", None),
            ("GET", f"/workspace?session_id={self.sid}", None),
            ("GET", f"/workspace/file?session_id={self.sid}&path={self.file['path']}", None),
            ("GET", f"/runs?session_id={self.sid}", None),
            ("GET", f"/runs/{self.job['run_id']}", None),
            ("GET", f"/runs/{self.job['run_id']}/events", None),
            ("GET", f"/knowledge/jobs/unknown/events?session_id={self.sid}", None),
            ("PATCH", f"/sessions/{self.sid}", {"title": "stolen"}),
            ("DELETE", f"/sessions/{self.sid}", None),
            ("DELETE", f"/workspace/files/{self.file['path']}?session_id={self.sid}", None),
            ("POST", "/approve", {"session_id": self.sid, "approved": True, "approval_id": "approve-alice"}),
            ("POST", "/approve_stream", {"session_id": self.sid, "approved": True, "approval_id": "approve-alice"}),
            ("POST", "/approve_async", {"session_id": self.sid, "approved": True, "approval_id": "approve-alice"}),
            ("POST", "/run", {"session_id": self.sid, "request": "steal"}),
            ("POST", "/run_stream", {"session_id": self.sid, "request": "steal"}),
        ]
        for method, path, body in cases:
            with self.subTest(method=method, path=path):
                self.assertEqual(self.request(path, method=method, body=body, cookie=self.bob_cookie)[0], 404)
        with principal_scope(self.alice):
            self.assertIsNotNone(self.store.get_session(self.sid))
            self.assertEqual(api.read_workspace_file(self.sid, self.file["path"]), b"Alice's private data")

    def test_service_boundary_and_deleted_id_cannot_be_claimed(self):
        with principal_scope(self.bob):
            for call in [lambda: api.read_workspace_file(self.sid, "private.txt"),
                         lambda: api.write_workspace_file(self.sid, "new.txt", b"bad"),
                         lambda: self.store.create_session(session_id=self.sid),
                         lambda: api.handle_approval(self.sid, True, "approve-alice")]:
                with self.assertRaises(AccessDenied): call()
        with principal_scope(self.alice):
            self.store.delete_session(self.sid)
        for user in [self.alice, self.bob]:
            with principal_scope(user), self.assertRaises(AccessDenied):
                self.store.create_session(session_id=self.sid)

    def test_website_identity_and_stolen_binding(self):
        ticket = website.issue_ticket("x" * 40, site_id="fixture", origin="https://fixture.test", subject=self.alice.user_id)
        payload = dict(ticket=ticket, site_id="fixture", origin="https://fixture.test", instance_id="browser", session_id=self.sid, context={"revision": "1"}, capabilities=["readTable"])
        self.assertEqual(self.request("/website/connect", method="POST", body=payload, cookie=self.bob_cookie)[0], 404)
        status, _, body = self.request("/website/connect", method="POST", body=payload, cookie=self.alice_cookie)
        self.assertEqual(status, 200)
        credentials = json.loads(body)
        self.assertEqual(self.request("/website/poll", method="POST", body=credentials, cookie=self.bob_cookie)[0], 404)
        # A valid Bob ticket still cannot select Alice's session.
        payload["ticket"] = website.issue_ticket("x" * 40, site_id="fixture", origin="https://fixture.test", subject=self.bob.user_id)
        self.assertEqual(self.request("/website/connect", method="POST", body=payload, cookie=self.bob_cookie)[0], 404)

    def test_logout_expiry_and_csrf(self):
        self.assertEqual(self.request("/auth/logout", method="POST", body={}, cookie=self.alice_cookie, headers={"Origin": "https://evil.test"})[0], 401)
        principal = self.accounts.authenticate(self.alice_cookie.split("=", 1)[1])
        self.assertEqual(self.request("/auth/logout", method="POST", body={}, cookie=self.alice_cookie)[0], 200)
        self.assertEqual(self.request("/sessions", cookie=self.alice_cookie)[0], 401)
        with principal_scope(principal), self.assertRaises(AuthError):
            self.queue.events(self.job["run_id"])
        self.assertEqual(self.request("/sessions", cookie=self.bob_cookie)[0], 200)
        with database(self.accounts.path) as db:
            db.execute("UPDATE logins SET expires_at=0")
        self.assertEqual(self.request("/sessions", cookie=self.bob_cookie)[0], 401)

    def test_shared_execution_requires_explicit_opt_in(self):
        status, _, body = self.request("/run", method="POST", body={"session_id": self.bob_sid, "request": "hello"}, cookie=self.bob_cookie)
        self.assertEqual(status, 403)
        self.assertIn(b"AGENT_ALLOW_SHARED_EXECUTION", body)
        with patch.dict(os.environ, {"AGENT_ALLOW_SHARED_EXECUTION": "true"}):
            status, _, _ = self.request("/run", method="POST", body={"session_id": self.bob_sid, "request": "hello"}, cookie=self.bob_cookie)
        self.assertEqual(status, 202)

    def test_cross_user_multipart_upload_is_rejected(self):
        body = (f'--fixture\r\nContent-Disposition: form-data; name="session_id"\r\n\r\n{self.sid}\r\n'
                '--fixture\r\nContent-Disposition: form-data; name="files"; filename="stolen.txt"\r\n'
                'Content-Type: text/plain\r\n\r\nwrong owner\r\n--fixture--\r\n').encode()
        self.assertEqual(self.request("/workspace/files", method="POST", body=body, cookie=self.bob_cookie,
                                      headers={"Content-Type": "multipart/form-data; boundary=fixture"})[0], 404)

    def test_explicit_legacy_migration_preserves_owner_and_stops_replay(self):
        from auth.__main__ import main
        (self.store.root / "legacy.json").write_text(json.dumps({"session_id": "legacy"}))
        with self.queue.db(write=True) as db:
            db.execute("INSERT INTO runs(run_id,session_id,request,model_key,max_turns,status,created_at,updated_at) VALUES ('legacy-run','legacy','old','unused',1,'queued','old','old')")
        argv = ["auth", "adopt-legacy", "--user", "alice"]
        with patch.object(sys, "argv", argv), patch("sys.stdout", new_callable=io.StringIO): main()
        with principal_scope(self.alice), self.assertRaises(AccessDenied): self.store.get_session("legacy")
        with patch.object(sys, "argv", argv + ["--apply"]), patch("sys.stdout", new_callable=io.StringIO): main()
        with principal_scope(self.alice):
            self.assertIsNotNone(self.store.get_session("legacy"))
            self.assertEqual(self.queue.get("legacy-run")["status"], "interrupted")
        with patch.object(sys, "argv", ["auth", "adopt-legacy", "--user", "bob", "--apply"]), patch("sys.stdout", new_callable=io.StringIO): main()
        with principal_scope(self.bob), self.assertRaises(AccessDenied): self.store.get_session("legacy")

    def test_knowledge_service_checks_actual_session_owner(self):
        from tools.infrastructure.knowledge import KnowledgeService
        from tools.infrastructure.knowledge.jobs import KnowledgeJobQueue
        service = KnowledgeService()
        with principal_scope(self.alice), patch.object(KnowledgeJobQueue, "dispatch"):
            job = service.enqueue(session_id=self.sid, request="fixture", collection_id=None, seed_urls=["https://example.org"], allowed_domains=["example.org"], max_pages=1, max_depth=0, refresh=False)
        with principal_scope(self.bob):
            for call in [lambda: service.collection(job["collection_id"], session_id=self.sid),
                         lambda: service.get_job(job["job_id"], session_id=self.sid),
                         lambda: service.events(job["job_id"], session_id=self.sid)]:
                with self.assertRaises(AccessDenied): call()
        self.assertEqual(self.request(f"/knowledge/jobs/{job['job_id']}?session_id={self.sid}", cookie=self.bob_cookie)[0], 404)

    def test_worker_recovers_owner_without_request_context(self):
        with principal_scope(self.alice):
            self.queue.update(self.job["run_id"], "queued")
        seen = []
        def fake_run(*args, **kwargs):
            seen.append(current_principal().user_id)
            self.store.ownership.require(kwargs["session_id"])
            return {"answer": "done", "status": "ok"}
        with patch.object(runtime, "run_agent", side_effect=fake_run), principal_scope(self.bob):
            self.assertEqual(jobs.execute_job(self.queue, self.job["run_id"]), 0)
            self.assertEqual(current_principal().user_id, self.bob.user_id)
        self.assertEqual(seen, [self.alice.user_id])

    def test_legacy_is_not_claimed_by_first_visitor(self):
        (self.store.root / "legacy.json").write_text(json.dumps({"session_id": "legacy"}))
        for principal in [self.alice, self.bob]:
            with principal_scope(principal):
                with self.assertRaises(AccessDenied): self.store.get_or_create_session("legacy")
                self.assertNotIn("legacy", [s["session_id"] for s in self.store.list_sessions()])

    def test_local_mode_and_network_restrictions(self):
        with patch.dict(os.environ, {"AGENT_AUTH_MODE": "local"}):
            self.assertEqual(self.request("/auth/status")[0], 200)
            payload = json.loads(self.request("/auth/status")[2])
            self.assertEqual(payload["user"]["id"], "local")
            with self.assertRaises(ValueError): validate_server("0.0.0.0")
            self.assertEqual(self.request("/sessions", headers={"Host": "evil.test"})[0], 401)
        with self.assertRaises(ValueError): validate_server("0.0.0.0")


if __name__ == "__main__":
    unittest.main()
