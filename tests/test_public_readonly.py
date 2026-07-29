import pathlib
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import dealdesk
from app import server


class PublicBoardProjectionTests(unittest.TestCase):
    def test_public_board_excludes_broker_state_and_never_unlocks_contact(self):
        board = dealdesk.public_board(
            [
                {
                    "name": "Example Logistics LLC",
                    "state": "NY",
                    "zip": "10001",
                    "credential": "USDOT 123456",
                    "contact_quality": "business address (public)",
                    "license_or_issue_date": "2026-07-01",
                    "citation": {
                        "label": "FMCSA Company Census",
                        "url": "https://safer.fmcsa.dot.gov/",
                    },
                    "recommended_next_action": "Research the official business website",
                    "owner": "David",
                    "last_note": "private broker note",
                    "history": [{"type": "CONTACTED"}],
                    "channels": [{"value": "private@example.test"}],
                    "clearance": {"expires_at": "2099-01-01T00:00:00Z"},
                    "clearance_expires_at": "2099-01-01T00:00:00Z",
                    "business_channel": "private@example.test",
                    "business_channel_type": "BUSINESS_EMAIL",
                    "disposition": "MEETING_BOOKED",
                    "follow_up_at": "2099-01-02T00:00:00Z",
                    "phone": "555-0100",
                    "email": "private@example.test",
                    "future_private_field": "must fail closed",
                }
            ]
        )

        self.assertEqual(board["access_mode"], "PUBLIC_READONLY")
        self.assertEqual(board["persistence"], "PUBLIC_READONLY")
        self.assertEqual(board["summary"]["call_ready"], 0)
        item = board["opportunities"][0]
        self.assertEqual(item["contact_gate"], "PUBLIC_RESEARCH_ONLY")
        self.assertEqual(item["stage"], "REVIEW")
        self.assertFalse(item["call_ready"])
        self.assertFalse(item["phone_call_ready"])
        for field in (
            "owner",
            "last_note",
            "history",
            "channels",
            "clearance",
            "clearance_expires_at",
            "business_channel",
            "business_channel_type",
            "disposition",
            "follow_up_at",
            "phone",
            "email",
            "future_private_field",
        ):
            self.assertNotIn(field, item)


class PublicReadOnlyApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(server.app)
        cls.token = "public-readonly-operator-test"
        server._TOKENS[cls.token] = time.time() + 60

    @classmethod
    def tearDownClass(cls):
        server._TOKENS.pop(cls.token, None)

    def test_access_mode_declares_public_view_and_protected_actions(self):
        with patch.object(server, "_PUBLIC_READONLY", True):
            response = self.client.get("/api/access-mode")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["mode"], "public_readonly")
        self.assertFalse(body["login_required_for_viewing"])
        self.assertTrue(body["operator_actions_require_login"])

    def test_public_frontier_projection_does_not_require_database_or_leak_state(self):
        receipt = {
            "id": "public-receipt-test",
            "payload": {"lead": {"name": "Public Carrier LLC"}},
        }

        class FakeFrontier:
            @staticmethod
            def frontier_opportunities(_states, limit_per_source=18):
                return {
                    "leads": [
                        {
                            "name": "Public Carrier LLC",
                            "state": "PA",
                            "zip": "19103",
                            "credential": "USDOT 789012",
                            "contact_quality": "entity id only",
                            "trigger_date": "2026-07-28",
                            "citation": {
                                "label": "FMCSA Company Census",
                                "url": "https://safer.fmcsa.dot.gov/",
                            },
                            "owner": "must not leak",
                            "last_note": "must not leak",
                            "_receipt": receipt,
                            "receipt_id": receipt["id"],
                        }
                    ],
                    "sources": [{"source": "FMCSA Company Census", "mode": "LIVE", "count": 1}],
                    "generated_at": "2026-07-29T00:00:00Z",
                    "states": ["PA"],
                    "doctrine": "public entity records",
                }

        prior_state = {key: value for key, value in server._STATE.items()}
        try:
            with (
                patch.object(server, "_PUBLIC_READONLY", True),
                patch.object(server, "frontier_data", FakeFrontier),
                patch.object(server.dd, "persistence_ready", return_value=False),
            ):
                response = self.client.get("/api/frontier-desk?states=PA")

            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["access_mode"], "PUBLIC_READONLY")
            self.assertEqual(body["summary"]["call_ready"], 0)
            item = body["opportunities"][0]
            self.assertNotIn("owner", item)
            self.assertNotIn("last_note", item)
            self.assertNotIn("frontier_desk", server._STATE)
            self.assertNotIn(receipt["id"], server._STATE["receipts"])
            self.assertEqual(server._PUBLIC_RECEIPTS[receipt["id"]], receipt)
        finally:
            server._PUBLIC_RECEIPTS.pop(receipt["id"], None)
            server._PUBLIC_BOARD_CACHE.clear()
            server._STATE.clear()
            server._STATE.update(prior_state)

    def test_operator_mutations_still_require_authentication(self):
        with patch.object(server, "_PUBLIC_READONLY", True):
            response = self.client.post("/api/logout")
        self.assertEqual(response.status_code, 401)

    def test_full_model_methodology_is_public_in_public_readonly_mode(self):
        with patch.object(server, "_PUBLIC_READONLY", True):
            response = self.client.get("/api/model")
        self.assertEqual(response.status_code, 200)

    def test_authenticated_mode_still_gates_public_projection_routes(self):
        with patch.object(server, "_PUBLIC_READONLY", False):
            response = self.client.get("/api/frontier-desk?states=PA")
        self.assertEqual(response.status_code, 401)

    def test_frontend_bootstraps_directly_into_public_market_cockpit(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        script = (root / "app" / "static" / "app.js").read_text(encoding="utf-8")
        page = (root / "app" / "static" / "index.html").read_text(encoding="utf-8")

        self.assertIn('await api("/api/access-mode")', script)
        self.assertIn('access.mode !== "public_readonly"', script)
        self.assertIn("EASTERN_REGIONS", script)
        self.assertIn("stateButtons", page)
        self.assertIn("stateAtlas", page)
        self.assertIn("Investor view", page)
        self.assertNotIn('id="login"', page)
        self.assertNotIn("Assigned username", page)
        self.assertNotIn("Password", page)
        self.assertIn('id="boot"', page)
        self.assertNotIn("Export governed CSV", page)


if __name__ == "__main__":
    unittest.main()
