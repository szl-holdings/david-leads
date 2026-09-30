# SPDX-License-Identifier: Apache-2.0
"""The v0 receipted vertical (backend/) is mounted under /v0 without touching the parent surface."""
from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app import server


class V0MountContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(server.app)

    def test_parent_liveness_is_unchanged(self) -> None:
        # The parent surface answers with its own honest readiness body (ready=200 / blocked=503),
        # proving the /v0 mount neither shadows nor alters it.
        response = self.client.get("/healthz")
        self.assertIn(response.status_code, (200, 503))
        body = response.json()
        self.assertEqual(body["service"], "david-leads")
        self.assertIn(body["status"], ("ready", "blocked"))
        self.assertIn("access_mode", body)
        self.assertNotIn("truth_state", body)

    def test_v0_liveness_declares_its_truth_state(self) -> None:
        response = self.client.get("/v0/healthz")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["service"], "david-leads")
        self.assertEqual(body["truth_state"], "VERIFIED")

    def test_v0_sources_report_honest_states(self) -> None:
        response = self.client.get("/v0/v1/sources")
        self.assertEqual(response.status_code, 200)
        states = {adapter["truth_state"] for adapter in response.json()["adapters"]}
        self.assertTrue(states <= {"VERIFIED", "UNKNOWN", "UNAVAILABLE", "INCOMPLETE"}, states)

    def test_v0_frontend_uses_relative_assets_under_the_prefix(self) -> None:
        index = self.client.get("/v0/", follow_redirects=True)
        self.assertEqual(index.status_code, 200)
        self.assertIn('href="static/style.css"', index.text)
        self.assertIn('src="static/app.js"', index.text)
        self.assertEqual(self.client.get("/v0/static/app.js").status_code, 200)
        self.assertNotIn('"/v1/', self.client.get("/v0/static/app.js").text)

    def test_v0_scoring_is_receipted(self) -> None:
        leads = self.client.get("/v0/v1/leads").json()["leads"]
        self.assertTrue(leads, "the labeled synthetic demo set must not be empty")
        scored = self.client.post("/v0/v1/score", json={"lead_id": leads[0]["id"]})
        self.assertEqual(scored.status_code, 200, scored.text)
        body = scored.json()
        self.assertIn("receipt", body)
        self.assertIn("truth_state", body)


if __name__ == "__main__":
    unittest.main()
