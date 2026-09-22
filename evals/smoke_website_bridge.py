"""Offline smoke checks for the trusted website bridge protocol."""
from __future__ import annotations
import asyncio
import json
import os
import tempfile
import unittest

from harness.website import WebsiteBridge, issue_ticket


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
