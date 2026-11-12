"""OAuth login/logout checks without external network access."""
import hashlib
import hmac
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from auth import AuthStore
from auth.oauth import begin_login, begin_logout, complete_login, consume_backchannel_logout


class _Response:
    def __init__(self, payload: dict):
        self.payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class OAuthAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {
            "AGENT_AUTH_MODE": "oauth",
            "AGENT_AUTH_DB": str(Path(self.temp.name) / "auth.sqlite3"),
            "AGENT_PUBLIC_ORIGIN": "https://agent.test",
            "AGENT_OAUTH_SERVER_URL": "https://identity.test",
            "AGENT_OAUTH_CLIENT_ID": "bioagent",
            "AGENT_OAUTH_CLIENT_SECRET": "a" * 32,
            "AGENT_OAUTH_REDIRECT_URI": "https://agent.test/auth/oauth/callback",
            "AGENT_OAUTH_POST_LOGOUT_REDIRECT_URI": "https://agent.test/",
            "AGENT_PROXY": "socks5h://proxy.test:7890",
            "AGENT_OAUTH_PROXY": "",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_pkce_login_uses_dedicated_direct_connection(self):
        location, state = begin_login("/sessions?view=recent")
        query = parse_qs(urlparse(location).query)
        self.assertEqual(query["client_id"], ["bioagent"])
        self.assertEqual(query["redirect_uri"], ["https://agent.test/auth/oauth/callback"])
        self.assertEqual(query["code_challenge_method"], ["S256"])

        with patch("auth.oauth.requests.post", return_value=_Response({"access_token": "access"})) as token_request, \
                patch("auth.oauth.requests.get", return_value=_Response({
                    "user_id": "42", "username": "alice", "sid": "shared-session"
                })) as userinfo_request:
            token, principal, return_to = complete_login("oauth-code", state, state)

        self.assertEqual((principal.user_id, principal.username), ("42", "alice"))
        self.assertEqual(return_to, "/sessions?view=recent")
        self.assertEqual(AuthStore().authenticate(token).user_id, "42")
        self.assertEqual(AuthStore().authenticate(token).sid, "shared-session")
        self.assertIsNone(token_request.call_args.kwargs["proxies"])
        self.assertIsNone(userinfo_request.call_args.kwargs["proxies"])

    def test_logout_request_is_created_by_server_side_client(self):
        response = _Response({
            "logout_url": "https://identity.test/logout?request=opaque"
        })
        with patch("auth.oauth.requests.post", return_value=response) as request:
            location = begin_logout()
        self.assertEqual(location, "https://identity.test/logout?request=opaque")
        self.assertEqual(request.call_args.args[0], "https://identity.test/oauth/logout-request")
        self.assertEqual(
            request.call_args.kwargs["data"]["post_logout_redirect_uri"],
            "https://agent.test/",
        )
        self.assertIsNone(request.call_args.kwargs["proxies"])

    def test_logout_url_keeps_whatever_address_the_identity_service_returns(self):
        class _Http:
            def __init__(self, logout_url):
                self.logout_url = logout_url

            def post(self, url, data=None, timeout=None, allow_redirects=None):
                return _Response({"logout_url": self.logout_url})

            def close(self):
                return None

        for logout_url in (
            "http://localhost:8090/logout?request=opaque",
            "http://127.0.0.1:8090/logout?request=opaque",
            "http://192.168.164.46:8090/logout?request=opaque",
            "https://sso.example.org/cncb/logout?request=opaque",
        ):
            with patch.dict(os.environ, {"AGENT_OAUTH_SERVER_URL": "http://127.0.0.1:8090"}), \
                    patch("auth.oauth._oauth_http", return_value=_Http(logout_url)):
                self.assertEqual(begin_logout(), logout_url)

        with patch("auth.oauth._oauth_http", return_value=_Http("javascript:alert(1)")):
            with self.assertRaises(Exception):
                begin_logout()

    def test_state_is_single_use(self):
        _, state = begin_login("/")
        with patch("auth.oauth.requests.post", return_value=_Response({"access_token": "access"})), \
                patch("auth.oauth.requests.get", return_value=_Response({
                    "user_id": "42", "username": "alice", "sid": "shared-session"
                })):
            complete_login("oauth-code", state, state)
            with self.assertRaises(Exception):
                complete_login("replayed-code", state, state)

    def test_signed_backchannel_logout_revokes_sid(self):
        _, state = begin_login("/")
        with patch("auth.oauth.requests.post", return_value=_Response({"access_token": "access"})), \
                patch("auth.oauth.requests.get", return_value=_Response({
                    "user_id": "42", "username": "alice", "sid": "shared-session"
                })):
            token, _, _ = complete_login("oauth-code", state, state)
        payload = json.dumps(
            {"event": "logout", "sid": "shared-session"},
            separators=(",", ":"), sort_keys=True,
        ).encode()
        signature = hmac.new(("a" * 32).encode(), payload, hashlib.sha256).hexdigest()
        self.assertEqual(consume_backchannel_logout(payload, "sha256=" + signature), 1)
        with self.assertRaises(Exception):
            AuthStore().authenticate(token)

    def test_flexible_host_follows_the_browser_and_keeps_server_calls_local(self):
        class _Http:
            def __init__(self):
                self.posts = []

            def post(self, url, data=None, timeout=None, allow_redirects=None):
                self.posts.append((url, data))
                return _Response({"access_token": "access"})

            def get(self, url, headers=None, timeout=None, allow_redirects=None):
                return _Response({"user_id": "42", "username": "alice", "sid": "shared-session"})

            def close(self):
                return None

        with patch.dict(os.environ, {"AGENT_OAUTH_FLEXIBLE_HOST": "true"}):
            location, state = begin_login("/project", request_origin="http://192.168.1.20:8008")
            ignored, _ = begin_login("/", request_origin="https://evil.example")
        parsed = urlparse(location)
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "192.168.1.20")
        self.assertEqual(query["redirect_uri"], ["http://192.168.1.20:8008/auth/oauth/callback"])
        ignored_query = parse_qs(urlparse(ignored).query)
        self.assertEqual(urlparse(ignored).netloc, "identity.test")
        self.assertEqual(ignored_query["redirect_uri"], ["https://agent.test/auth/oauth/callback"])

        http = _Http()
        with patch("auth.oauth._oauth_http", return_value=http):
            complete_login("oauth-code", state, state)
        self.assertEqual(http.posts[0][1]["redirect_uri"], "http://192.168.1.20:8008/auth/oauth/callback")
        self.assertTrue(http.posts[0][0].startswith("https://identity.test/"))

    def test_flexible_host_accepts_a_lan_address(self):
        import importlib.util
        from auth import AuthError

        spec = importlib.util.spec_from_file_location(
            "bioagent_interfaces_auth_flexible",
            Path(__file__).resolve().parents[1] / "interfaces" / "auth.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        class Handler:
            command = "GET"
            headers = {"Host": "192.168.1.20:8008"}
            client_address = ("192.168.1.20", 1234)

        with patch.dict(os.environ, {"AGENT_OAUTH_FLEXIBLE_HOST": "true"}):
            module._check_origin(Handler())
        Handler.headers = {"Host": "evil.example"}
        with patch.dict(os.environ, {"AGENT_OAUTH_FLEXIBLE_HOST": "true"}):
            with self.assertRaises(AuthError):
                module._check_origin(Handler())

    def test_anonymous_home_redirects_straight_to_login(self):
        from interfaces.web import AgentRequestHandler

        server = ThreadingHTTPServer(("127.0.0.1", 0), AgentRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        self.addCleanup(lambda: thread.join(timeout=2))

        def get(path: str, cookie: str = "") -> tuple[int, str]:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            headers = {"Host": "agent.test"}
            if cookie:
                headers["Cookie"] = cookie
            connection.request("GET", path, headers=headers)
            response = connection.getresponse()
            response.read()
            location = response.getheader("Location") or ""
            status = response.status
            connection.close()
            return status, location

        status, location = get("/")
        self.assertEqual(status, 302)
        self.assertTrue(location.startswith("/auth/oauth/login?"), location)
        self.assertEqual(parse_qs(urlparse(location).query)["return_to"], ["/"])

        status, location = get("/index.html?logged_out=1&tab=files")
        self.assertEqual(status, 302)
        self.assertEqual(parse_qs(urlparse(location).query)["return_to"], ["/?tab=files"])

        AuthStore().add_user("alice", "alice-password-123")
        token, _ = AuthStore().login("alice", "alice-password-123", "127.0.0.1")
        status, location = get("/", cookie="bioagent_session=" + token)
        self.assertNotEqual(status, 302)
        self.assertNotIn("/auth/oauth/login", location)


if __name__ == "__main__":
    unittest.main()
