"""OAuth login/logout checks without external network access."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
