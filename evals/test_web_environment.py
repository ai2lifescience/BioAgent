import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


@unittest.skipIf(os.name == "nt", "BioAgent's web stack requires the POSIX fcntl module.")
class WebEnvironmentTests(unittest.TestCase):
    def test_explicit_exports_override_env_file_and_ports_derive_urls(self):
        from interfaces.web import _configure_development_urls, _load_environment_file

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(
                "\n".join([
                    "AGENT_PROXY=socks5h://from-env-file:7890",
                    "BIOAGENT_PUBLIC_HOST=agent.local",
                    "OAUTH_PUBLIC_HOST=oauth.local",
                ]),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {
                "AGENT_AUTH_MODE": "oauth",
                "AGENT_PROXY": "socks5h://explicit-export:7890",
                "OAUTH_PORT": "8190",
            }, clear=True):
                _load_environment_file(path)
                _configure_development_urls(8123)
                self.assertEqual(os.environ["AGENT_PROXY"], "socks5h://explicit-export:7890")
                self.assertEqual(os.environ["AGENT_PUBLIC_ORIGIN"], "http://agent.local:8123")
                self.assertEqual(
                    os.environ["AGENT_OAUTH_SERVER_URL"], "http://oauth.local:8190"
                )
                self.assertEqual(
                    os.environ["AGENT_OAUTH_REDIRECT_URI"],
                    "http://agent.local:8123/auth/oauth/callback",
                )

    def test_multiuser_startup_allows_direct_lan_hosts(self):
        from interfaces.auth import configure_server
        from interfaces.web import _configure_development_urls

        with patch.dict(os.environ, {"AGENT_AUTH_MODE": "multiuser"}, clear=True):
            _configure_development_urls(8000)
            self.assertNotIn("AGENT_PUBLIC_ORIGIN", os.environ)
            self.assertNotIn("AGENT_PUBLIC_BASE_URL", os.environ)
            self.assertNotIn("AGENT_OAUTH_SERVER_URL", os.environ)
            self.assertNotIn("AGENT_OAUTH_REDIRECT_URI", os.environ)
            configure_server("0.0.0.0")
            self.assertEqual(os.environ["AGENT_DIRECT_HTTP"], "true")


if __name__ == "__main__":
    unittest.main()
