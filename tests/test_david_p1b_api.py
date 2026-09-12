"""P1b public capability, READY gate, and honest source-status tests."""
from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import server
from app.domain.source_policy import SOURCE_CATALOG, public_capabilities, ready_blockers


class PublicCapabilitiesTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)

    def test_capabilities_are_sanitized_and_honest(self):
        response = self.client.get("/api/v1/public/capabilities")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["schema"], "szl.david.public-capabilities/v1")
        self.assertEqual(body["integrity"], "LOCAL_SHA256_UNSIGNED")
        self.assertFalse(body["receipt_minted"])
        self.assertEqual(body["ready_patch"], "DENIED")
        self.assertEqual(body["contact_permission"], "NOT_EVALUATED")
        sources = {item["id"]: item for item in body["sources"]}
        self.assertEqual(sources["dol-form5500-benefit-timing"]["status"], "ENABLED")
        self.assertEqual(sources["dol-form5500-benefit-timing"]["order"], 1)
        self.assertEqual(sources["irs-form990"]["status"], "POLICY_HOLD")
        self.assertEqual(sources["nyc-acris"]["status"], "POLICY_HOLD")
        self.assertEqual(sources["chicago-new-business-licenses"]["status"], "AUTH_REQUIRED")
        self.assertEqual(sources["sam-active-entity-updates"]["status"], "AUTH_REQUIRED")
        self.assertEqual(sources["fcc-uls-organization-licenses"]["status"], "NOT_IMPLEMENTED")
        serialized = json.dumps(body).lower()
        for secret in (
            "password",
            "postgres://",
            "neon.tech",
            "david_database_url",
            "sam_gov_api_key",
            "chicago_socrata_app_token",
            "token",
        ):
            self.assertNotIn(secret, serialized)
        self.assertEqual(list(body), list(public_capabilities()))

    def test_catalog_does_not_enable_held_sources(self):
        enabled = [item["id"] for item in SOURCE_CATALOG if item["enabled"]]
        self.assertEqual(enabled, ["dol-form5500-benefit-timing"])


class ReadyGateTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)

    def test_browser_patch_ready_is_denied_with_named_blockers(self):
        with patch.object(server, "_PUBLIC_READONLY", True):
            response = self.client.patch("/api/deal-desk/opp-1", json={"stage": "READY"})
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertEqual(body["denied"], "READY")
        self.assertIn("BROWSER_PATCH_DENIED", body["blockers"])
        self.assertIn("PUBLIC_VIEW", body["blockers"])
        self.assertIn("GATES_INCOMPLETE", body["blockers"])
        self.assertIn("READY_REQUIRES_CLEARANCE", body["blockers"])

    def test_public_patch_alias_is_denied(self):
        response = self.client.patch(
            "/api/v1/public/opportunities/opp-1",
            json={"stage": "READY"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("PUBLIC_VIEW", response.json()["blockers"])

    def test_post_ready_is_denied_with_named_blockers(self):
        token = "p1b-operator"
        server._TOKENS[token] = {"expires_at": 10**12, "username": "David Abraham"}
        try:
            response = self.client.post(
                "/api/deal-desk/opp-1",
                headers={"Authorization": f"Bearer {token}"},
                json={"stage": "READY"},
            )
        finally:
            server._TOKENS.pop(token, None)
        self.assertEqual(response.status_code, 403)
        self.assertIn("READY_REQUIRES_CLEARANCE", response.json()["blockers"])
        self.assertNotIn("PUBLIC_VIEW", response.json()["blockers"])

    def test_incomplete_gates_are_named(self):
        blockers = ready_blockers(
            principal="operator",
            method="POST",
            gates_complete=False,
        )
        self.assertEqual(
            blockers,
            ("GATES_INCOMPLETE", "READY_REQUIRES_CLEARANCE"),
        )


class CorrectionApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)
        self.token = "p1b-correct"
        server._TOKENS[self.token] = {"expires_at": 10**12, "username": "David Abraham"}
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self):
        server._TOKENS.pop(self.token, None)

    def test_public_correction_is_denied(self):
        with patch.object(server, "_PUBLIC_READONLY", True):
            response = self.client.post(
                "/api/deal-desk/opp-1/correct",
                json={"node_id": "abc", "reason": "SOURCE_CORRECTED"},
            )
        self.assertEqual(response.status_code, 401)

    def test_operator_correction_revokes_descendants(self):
        class FakeLedger:
            def correct(self, tenant, node, reason, now):
                self.seen = (tenant, node, reason, now.tzinfo is not None)
                return 5

            def close(self):
                self.closed = True

        fake = FakeLedger()
        with (
            patch.dict(os.environ, {"DAVID_DATABASE_URL": "postgresql://test"}, clear=False),
            patch.object(server, "connect_postgres_ledger", return_value=fake),
        ):
            response = self.client.post(
                "/api/deal-desk/opp-1/correct",
                headers=self.headers,
                json={"node_id": "source-node", "reason": "SOURCE_CORRECTED"},
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["revoked"], 5)
        self.assertEqual(list(body["cancels"]), ["brief", "clearance", "crm_task"])
        self.assertEqual(body["integrity"], "LOCAL_SHA256_UNSIGNED")
        self.assertEqual(fake.seen[0], "operator")
        self.assertEqual(fake.seen[1], "source-node")
        self.assertTrue(fake.closed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
