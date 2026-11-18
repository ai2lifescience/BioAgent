"""CAS identity and single-logout checks without external network access."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from auth import AuthStore
from auth.cas import begin_login, complete_login, consume_single_logout


class _Response:
    def __init__(self, data: bytes):
        self.data = data
        self.status_code = 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int):
        for offset in range(0, len(self.data), chunk_size):
            yield self.data[offset:offset + chunk_size]


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
            "AGENT_PROXY": "",
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
        with patch("auth.cas.requests.get", return_value=_Response(self.assertion())):
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
        with patch("auth.cas.requests.get", return_value=_Response(invalid)):
            with self.assertRaises(Exception):
                complete_login("ST-missing-user-id", state, state)
        with patch("auth.cas.requests.get", return_value=_Response(self.assertion())):
            with self.assertRaises(Exception):
                complete_login("ST-replayed-state", state, state)

if __name__ == "__main__":
    unittest.main()
