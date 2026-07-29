# SPDX-License-Identifier: Apache-2.0
"""Regression tests for the operator-first decision trace and public UI copy."""
from pathlib import Path
import importlib.util
import time
import unittest

_APP_TEST_DEPS_AVAILABLE = all(
    importlib.util.find_spec(name) is not None
    for name in ("fastapi", "httpx", "pydantic")
)
if _APP_TEST_DEPS_AVAILABLE:
    from fastapi.testclient import TestClient
    from app import server


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(_APP_TEST_DEPS_AVAILABLE, "application test dependencies are not installed")
class OperatorDecisionTraceTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)
        self.token = "operator-trace-test-token"
        server._TOKENS[self.token] = time.time() + 60
        server._STATE.clear()
        server._STATE.update(
            meta={"mode": "SAMPLE (offline)", "total_signals": 3, "live_count": 0},
            signals=[],
            receipts={},
            leads=[
                {
                    "id": "L-TRACE-1",
                    "name": "Example new-parent household",
                    "score": 87.2,
                    "bucket": "HOT",
                    "why": "New dependents create a time-sensitive coverage review.",
                    "axes": {
                        "life_event_strength": 0.95,
                        "income_fit": 0.75,
                        "age_window_fit": 0.85,
                        "product_propensity": 0.90,
                        "recency": 0.90,
                    },
                    "moments": [
                        {"source": "CDC Natality", "label": "Birth trend supports the life-stage signal"},
                        {"source": "U.S. Census ACS", "label": "Public household context"},
                    ],
                    "confidence": {
                        "level": "Medium",
                        "lo": 72.3,
                        "hi": 100.0,
                        "n_sources": 2,
                        "advisory": True,
                        "note": "Estimate, not certainty.",
                    },
                    "compliance": {"clear": True, "reasons": ["DNC clear; no opt-out recorded"]},
                    "nba": {"action": "Review before calling.", "talk_track": "Open with the life event."},
                    "likely_gap": {"held_policies_known": False},
                    "est_premium_advisory": True,
                    "est_premium_note": "Illustrative estimate, not a quote.",
                    "receipt_id": "rcpt_test_1",
                    "receipt_signed": False,
                }
            ],
        )

    def tearDown(self):
        server._TOKENS.pop(self.token, None)

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def test_trace_requires_authentication(self):
        response = self.client.get("/api/operator/trace/L-TRACE-1")
        self.assertEqual(response.status_code, 401)

    def test_trace_exposes_honest_operator_path(self):
        response = self.client.get("/api/operator/trace/L-TRACE-1", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        trace = response.json()
        self.assertEqual(trace["schema"], "szl.operator-decision-trace/v1")
        self.assertEqual(trace["run"]["state"], "EXAMPLE")
        self.assertEqual(trace["contact_gate"]["state"], "CLEAR")
        self.assertEqual(trace["proof"]["state"], "UNSIGNED")
        self.assertEqual(trace["conflict_check"]["state"], "NOT_EVALUATED")
        self.assertEqual([step["step"] for step in trace["decision_path"]],
                         ["SIGNAL", "PRIORITY", "CONTACT", "ACTION", "PROOF"])
        self.assertEqual(trace["drivers"][0]["label"], "Life-event need")
        self.assertTrue(any("offline example" in note.lower() for note in trace["caveats"]))
        self.assertTrue(any("unsigned" in note.lower() for note in trace["caveats"]))

    def test_trace_refuses_unknown_lead(self):
        response = self.client.get("/api/operator/trace/UNKNOWN", headers=self.headers)
        self.assertEqual(response.status_code, 404)


class OperatorSurfaceCopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")

    def test_public_workspace_is_broker_first(self):
        self.assertIn("Broker view", self.html)
        self.assertIn("Lead explorer", self.html)
        self.assertIn("Choose the market", self.html)
        self.assertNotIn("More tools", self.html)
        self.assertNotIn("Ouroboros Director", self.html)
        self.assertNotIn("HOLO MODE", self.html)

    def test_public_lead_detail_is_addressable_without_operator_state(self):
        self.assertIn("data-lead-id", self.js)
        self.assertIn("/api/verify/", self.js)
        self.assertIn("Open official record", self.js)
        self.assertNotIn("/api/operator/trace/", self.js)
        self.assertNotIn("Conflict check", self.js)

    def test_investor_truth_view_does_not_render_raw_formula(self):
        self.assertNotIn("${m.formula}", self.js)
        self.assertIn("not company revenue", self.js.lower())
        self.assertIn("Observed activity is not revenue", self.html)

    def test_public_card_is_operator_copy(self):
        self.assertIn("Operator Lead Command", self.readme)
        self.assertIn("Decision Trace", self.readme)
        self.assertNotIn("Λ", self.readme)
        self.assertNotIn("Ouroboros", self.readme)


if __name__ == "__main__":
    unittest.main()
