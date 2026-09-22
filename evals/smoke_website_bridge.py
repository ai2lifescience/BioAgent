"""Offline smoke checks for the trusted website bridge protocol."""
from __future__ import annotations
import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from harness.website import WebsiteBridge, allowed_sites, check_site, configure_local_demo, issue_ticket


class WebsiteDemoConfigurationSmoke(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def test_wildcard_listener_trusts_discovered_address(self):
        with patch("harness.website.socket.getaddrinfo", return_value=[
            (2, 1, 6, "", ("192.168.75.56", 8000)),
        ]):
            configure_local_demo(8000, "0.0.0.0")
        for origin in ("http://localhost:8000", "http://127.0.0.1:8000", "http://192.168.75.56:8000"):
            check_site("assistant-demo", origin)
        for origin in ("http://0.0.0.0:8000", "http://192.168.75.57:8000", "http://192.168.75.56:8001", "https://192.168.75.56:8000"):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                check_site("assistant-demo", origin)
        self.assertGreaterEqual(len(os.environ["AGENT_WEBSITE_SECRET"]), 32)

    def test_specific_listener_trusts_bound_address(self):
        configure_local_demo(8765, "192.168.75.56")
        check_site("assistant-demo", "http://192.168.75.56:8765")
        with self.assertRaises(ValueError):
            check_site("assistant-demo", "http://192.168.75.56:8000")

    def test_explicit_settings_are_preserved(self):
        os.environ["AGENT_WEBSITE_SECRET"] = "existing-secret" * 3
        for sites in ({}, {"assistant-demo": ["http://localhost:8000"]}, {"portal": ["https://portal.test"]}):
            with self.subTest(sites=sites):
                os.environ["AGENT_WEBSITE_SITES"] = json.dumps(sites)
                configure_local_demo(8000, "0.0.0.0")
                self.assertEqual(allowed_sites(), sites)
                self.assertEqual(os.environ["AGENT_WEBSITE_SECRET"], "existing-secret" * 3)
                with self.assertRaises(ValueError):
                    check_site("assistant-demo", "http://192.168.75.56:8000")

    def test_address_lookup_failure_retains_localhost(self):
        with patch("harness.website.socket.getaddrinfo", side_effect=OSError("unresolved hostname")):
            configure_local_demo(8000, "0.0.0.0")
        self.assertEqual(allowed_sites(), {"assistant-demo": ["http://127.0.0.1:8000", "http://localhost:8000"]})


class WebsiteBridgeSmoke(unittest.IsolatedAsyncioTestCase):
    async def test_authenticated_request_round_trip(self):
        os.environ["AGENT_WEBSITE_SECRET"] = "w" * 40
        os.environ["AGENT_WEBSITE_SITES"] = json.dumps({"fixture": ["https://fixture.test"]})
        bridge = WebsiteBridge(tempfile.mktemp(prefix="website-smoke-", suffix=".sqlite3"))
        ticket = issue_ticket("w" * 40, site_id="fixture", origin="https://fixture.test", subject="user")
        binding = bridge.connect(ticket=ticket, site_id="fixture", origin="https://fixture.test", instance_id="browser", session_id="session", context={"revision": "1"}, capabilities=["readTable"])
        credentials = {"binding_id": binding["binding_id"], "token": binding["token"]}

        async def host_response():
            while not bridge.pending(**credentials):
                await asyncio.sleep(0.01)
            call = bridge.pending(**credentials)[0]
            bridge.respond(**credentials, call_id=call["call_id"], result={"resource_id": "table", "rows": []})

        responder = asyncio.create_task(host_response())
        result = await bridge.request(credentials, run_id="run", method="readTable", arguments={"resource_id": "table"})
        await responder
        self.assertEqual(result["resource_id"], "table")

    def test_ticket_replay_is_rejected(self):
        os.environ["AGENT_WEBSITE_SECRET"] = "w" * 40
        os.environ["AGENT_WEBSITE_SITES"] = json.dumps({"fixture": ["https://fixture.test"]})
        bridge = WebsiteBridge(tempfile.mktemp(prefix="website-smoke-", suffix=".sqlite3"))
        ticket = issue_ticket("w" * 40, site_id="fixture", origin="https://fixture.test", subject="user")
        kwargs = dict(ticket=ticket, site_id="fixture", origin="https://fixture.test", instance_id="browser", session_id="session", context={}, capabilities=[])
        bridge.connect(**kwargs)
        with self.assertRaises(ValueError):
            bridge.connect(**kwargs)


if __name__ == "__main__":
    unittest.main()
