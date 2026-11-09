"""CAS identity and single-logout checks without external network access."""
import hashlib
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from auth import AuthStore, database
from auth.cas import begin_login, complete_login, consume_single_logout
from auth.mscan import begin_login as begin_mscan_login, complete_login as complete_mscan_login


class _Response:
    def __init__(self, data: bytes):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self, _limit: int) -> bytes:
        return self.data


class CasAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {
            "AGENT_AUTH_MODE": "cas",
            "AGENT_AUTH_DB": str(Path(self.temp.name) / "auth.sqlite3"),
            "AGENT_PUBLIC_ORIGIN": "https://agent.test",
            "AGENT_CAS_LOGIN_URL": "https://sso.test/login",
            "AGENT_CAS_VALIDATE_URL": "https://sso.test/p3/serviceValidate",
            "AGENT_CAS_LOGOUT_URL": "https://sso.test/logout",
            "AGENT_CAS_SERVICE_URL": "https://agent.test/auth/cas/callback",
            "AGENT_MSCAN_LOGIN_URL": "https://mscan.test/",
            "AGENT_MSCAN_ORIGIN": "https://mscan.test",
            "AGENT_MSCAN_SITE_ID": "mscan",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    @staticmethod
    def assertion(username: str = "alice") -> bytes:
        return f"""<?xml version="1.0"?>
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>{username}</cas:user>
    <cas:attributes>
      <cas:userId>42</cas:userId>
      <cas:userName>{username}</cas:userName>
    </cas:attributes>
  </cas:authenticationSuccess>
</cas:serviceResponse>""".encode()

    def test_stable_identity_ticket_validation_and_single_logout(self):
        location, state = begin_login("/sessions?view=recent")
        service = parse_qs(urlparse(location).query)["service"][0]
        self.assertIn("state=" + state, service)
        with patch("auth.cas.urlopen", return_value=_Response(self.assertion())):
            token, principal, return_to = complete_login("ST-example-ticket", state, state)
        self.assertEqual((principal.user_id, principal.username), ("42", "alice"))
        self.assertEqual(return_to, "/sessions?view=recent")
        self.assertEqual(AuthStore().authenticate(token).user_id, "42")

        logout = (
            b'<samlp:LogoutRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol">'
            b"<samlp:SessionIndex>ST-example-ticket</samlp:SessionIndex></samlp:LogoutRequest>"
        )
        self.assertTrue(consume_single_logout(logout, "application/xml"))
        with self.assertRaises(Exception):
            AuthStore().authenticate(token)

    def test_state_is_single_use_and_identity_requires_user_id(self):
        _, state = begin_login("/")
        invalid = self.assertion().replace(b"<cas:userId>42</cas:userId>", b"")
        with patch("auth.cas.urlopen", return_value=_Response(invalid)):
            with self.assertRaises(Exception):
                complete_login("ST-missing-user-id", state, state)
        with patch("auth.cas.urlopen", return_value=_Response(self.assertion())):
            with self.assertRaises(Exception):
                complete_login("ST-replayed-state", state, state)

    def test_mscan_handoff_uses_bridge_grant_instead_of_cas_ticket(self):
        store = AuthStore()
        user_id = store.add_user("mscan-alice", "a-secure-test-password")
        token = "bridge-login-token"
        with database(store.path) as db:
            db.execute(
                "INSERT INTO logins VALUES (?,?,?)",
                (hashlib.sha256(token.encode()).hexdigest(), user_id, time.time() + 120),
            )
        location, state = begin_mscan_login("/sessions")
        self.assertEqual(parse_qs(urlparse(location).query)["agent_sso_state"], [state])
        with patch("web_bridge.identity.Federation.exchange", return_value=(token, {})) as exchange:
            result, principal, return_to = complete_mscan_login("g" * 43, state, state)
        self.assertEqual((result, principal.user_id, return_to), (token, user_id, "/sessions"))
        exchange.assert_called_once_with("g" * 43, "mscan", "https://mscan.test")
        with self.assertRaises(Exception):
            complete_mscan_login("g" * 43, state, state)


if __name__ == "__main__":
    unittest.main()
