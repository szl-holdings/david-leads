from html.parser import HTMLParser
import pathlib
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import dealdesk
from app import server


class _DataStatePillParser(HTMLParser):
    """Capture the direct DOM contract used by renderDataState()."""

    def __init__(self):
        super().__init__()
        self.attributes = {}
        self.direct_children = []
        self.direct_text = []
        self.found = False
        self._inside = False
        self._depth = 0
        self._tag = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if not self._inside and attributes.get("id") == "dataStatePill":
            self.attributes = attributes
            self.found = True
            self._inside = True
            self._tag = tag
            return
        if self._inside:
            self._depth += 1
            if self._depth == 1:
                self.direct_children.append(tag)

    def handle_endtag(self, tag):
        if not self._inside:
            return
        if self._depth == 0 and tag == self._tag:
            self._inside = False
            return
        self._depth -= 1

    def handle_data(self, data):
        if self._inside and self._depth == 0 and data.strip():
            self.direct_text.append(data.strip())


class PublicBoardProjectionTests(unittest.TestCase):
    def test_public_board_excludes_broker_state_and_never_unlocks_contact(self):
        board = dealdesk.public_board(
            [
                {
                    "name": "Example Logistics LLC",
                    "address": "125 Private Residence Risk Lane",
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
        self.assertNotIn("address", item)
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
        body = response.json()
        self.assertEqual(body["decision_unit"], "organization")
        self.assertEqual(body["contact_boundary"]["default"], "PUBLIC_RESEARCH_ONLY")
        self.assertIn("Social-profile scraping", body["excluded_inputs"])
        self.assertNotIn("wealth_tier", body)

    def test_legacy_household_scoring_endpoint_is_retired(self):
        response = self.client.post("/api/run", json={"live": False})
        self.assertEqual(response.status_code, 410)
        self.assertIn("Legacy household archetype scoring is retired", response.json()["detail"])

    def test_authenticated_mode_still_gates_public_projection_routes(self):
        with patch.object(server, "_PUBLIC_READONLY", False):
            response = self.client.get("/api/frontier-desk?states=PA")
        self.assertEqual(response.status_code, 401)

    def test_frontier_rejects_invalid_or_out_of_scope_territory(self):
        with patch.object(server, "_PUBLIC_READONLY", True):
            response = self.client.get("/api/frontier-desk?states=NY,ZZ")
        self.assertEqual(response.status_code, 422)
        self.assertIn("ZZ", response.json()["detail"])

    def test_canonical_territory_order_deduplicates_cache_keys(self):
        self.assertEqual(
            server._canonical_eastern_states("VA,NY,VA", server.EASTERN_STATES),
            ["NY", "VA"],
        )

    def test_mutation_actor_is_bound_to_authenticated_session(self):
        token = "identity-bound-operator-test"
        server._TOKENS[token] = {
            "expires_at": time.time() + 60,
            "username": "David Abraham",
        }
        headers = {"Authorization": f"Bearer {token}"}
        try:
            with (
                patch.object(server.dd, "persistence_ready", return_value=True),
                patch.object(server.dd, "update", return_value={"opportunity_id": "op-1"}) as update,
            ):
                response = self.client.post(
                    "/api/deal-desk/op-1",
                    headers=headers,
                    json={"stage": "REVIEW", "actor": "Spoofed Actor"},
                )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(update.call_args.kwargs["actor"], "David Abraham")
        finally:
            server._TOKENS.pop(token, None)

    def test_all_production_lead_routes_reject_example_records(self):
        sample_record = {
            "name": "[SAMPLE] Example Company",
            "employer": "[SAMPLE] Example Company",
            "state": "NY",
            "source_status": "sample",
            "_sample": True,
        }
        headers = {"Authorization": f"Bearer {self.token}"}

        with patch.object(
            server.rl,
            "real_callable_leads",
            return_value={"leads": [dict(sample_record)], "sources": [], "summary": {}},
        ):
            response = self.client.get("/api/real-leads?states=NY", headers=headers)
            self.assertEqual(response.status_code, 503)

        server._PUBLIC_BOARD_CACHE.clear()
        with (
            patch.object(server, "_PUBLIC_READONLY", True),
            patch.object(
                server.rl,
                "real_callable_leads",
                return_value={"leads": [dict(sample_record)], "sources": [], "summary": {}},
            ),
        ):
            response = self.client.get("/api/deal-desk?states=NY")
            self.assertEqual(response.status_code, 503)

        with patch.object(
            server.wl,
            "warn_leads",
            return_value={"leads": [dict(sample_record)]},
        ):
            response = self.client.get("/api/warn-leads?states=NY", headers=headers)
            self.assertEqual(response.status_code, 503)

        with patch.object(
            server.tx,
            "real_tax_territories",
            return_value={
                "affluent_zips": [],
                "money_in_motion": [],
                "sources": [{"mode": "SAMPLE"}],
                "_receipt": None,
            },
        ):
            response = self.client.get("/api/tax-territories?states=NY", headers=headers)
            self.assertEqual(response.status_code, 503)

        server._PUBLIC_BOARD_CACHE.clear()
        with (
            patch.object(server, "_PUBLIC_READONLY", True),
            patch.object(
                server.frontier_data,
                "frontier_opportunities",
                return_value={"leads": [dict(sample_record)], "sources": []},
            ),
        ):
            response = self.client.get("/api/frontier-desk?states=NY")
            self.assertEqual(response.status_code, 503)

    def test_public_shell_and_live_routes_disable_stale_release_caching(self):
        page = self.client.get("/")
        script = self.client.get("/app.js")
        with patch.object(server, "_PUBLIC_READONLY", True):
            access = self.client.get("/api/access-mode")

        self.assertEqual(page.status_code, 200)
        self.assertIn("no-store", page.headers["cache-control"])
        self.assertIn("no-cache", script.headers["cache-control"])
        self.assertIn("no-store", access.headers["cache-control"])

    def test_frontend_bootstraps_directly_into_public_market_cockpit(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        script = (root / "app" / "static" / "app.js").read_text(encoding="utf-8")
        page = (root / "app" / "static" / "index.html").read_text(encoding="utf-8")

        self.assertIn('await api("/api/access-mode")', script)
        self.assertIn('access.mode !== "public_readonly"', script)
        self.assertIn("EASTERN_REGIONS", script)
        self.assertIn("stateButtons", page)
        self.assertIn("stateAtlas", page)
        self.assertIn("mobileStateSelect", page)
        self.assertIn("quickTerritorySelect", page)
        self.assertIn("errorState", page)
        self.assertIn("PUBLIC VIEW: CHECKING", page)
        self.assertIn('role="tablist"', page)
        self.assertIn('id="leadDrawer" class="lead-drawer"', page)
        self.assertIn("broker-workflow", page)
        self.assertIn("laneFilters", page)
        self.assertIn("Life-plan timing", page)
        self.assertIn("metricWindows", page)
        self.assertIn("releaseBanner", page)
        self.assertIn("Investor view", page)
        self.assertIn('selectOnlyState(button.dataset.state)', script)
        self.assertIn('cache: "no-store"', script)
        self.assertIn("checkForNewRelease", script)
        self.assertIn("T12:00:00", script)
        self.assertIn("corroborating_signals", script)
        self.assertNotIn('id="login"', page)
        self.assertNotIn("Assigned username", page)
        self.assertNotIn("Password", page)
        self.assertNotIn("Developer quickstart", page)
        self.assertIn('id="boot"', page)
        self.assertNotIn("Export governed CSV", page)

    def test_data_state_status_has_accessible_dom_contract(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

        parser = _DataStatePillParser()
        parser.feed(response.text)

        self.assertTrue(parser.found)
        self.assertEqual(parser.attributes["role"], "status")
        self.assertEqual(parser.attributes["aria-live"], "polite")
        self.assertIn("checking", parser.attributes["class"].split())
        self.assertNotIn("measured", parser.attributes["class"].split())
        self.assertNotIn("unavailable", parser.attributes["class"].split())
        self.assertEqual(parser.attributes["title"], "Loading current source records")
        self.assertEqual(parser.direct_children, ["i"])
        self.assertEqual(parser.direct_text, ["DATA: CHECKING"])

    def test_data_state_rendering_is_source_derived_and_fails_closed(self):
        script = self.client.get("/app.js").text.replace("\r\n", "\n")
        function = script.split("function renderDataState() {", 1)[1].split(
            "\n}\n\nfunction renderMetrics", 1
        )[0]

        self.assertIn(
            'state.sources.filter((source) => source.mode === "LIVE")',
            function,
        )
        self.assertIn('if (liveSources.length > 0)', function)
        self.assertIn('LIVE / MEASURED · ${liveSources.length}/${totalSources}', function)
        self.assertIn('else if (state.board)', function)
        self.assertIn('UNAVAILABLE · 0/${totalSources}', function)
        self.assertIn('pill.lastChild.textContent = "DATA: UNAVAILABLE"', function)
        self.assertNotIn("state.leads.length", function)
        self.assertNotIn("summary.live ?? state.leads.length", script)
        self.assertIn(
            'sources.some((source) => source.mode === "LIVE")',
            script,
        )
        self.assertIn(
            "renderDataState();\n  renderFilters();\n  if (!state.board || state.loadError)",
            script,
        )
        self.assertIn("if (!state.board || state.loadError) {", script)
        self.assertIn("if (!state.loadError) {\n      $(\"freshness\")", script)
        self.assertIn("renderUnavailableEvidence();", script)
        self.assertIn("renderMetrics();\n  renderDailyBrief();", script)
        self.assertIn('pill.classList.remove("checking")', function)

    def test_access_mode_failure_makes_all_header_states_terminal(self):
        script = self.client.get("/app.js").text.replace("\r\n", "\n")
        unavailable = script.split("function renderWorkspaceUnavailable() {", 1)[1].split(
            "\n}\n\nfunction renderMetrics", 1
        )[0]
        bootstrap = script.split("async function bootstrap() {", 1)[1].split(
            "\n}\n\nfunction bindEvents", 1
        )[0]

        self.assertIn('access.mode !== "public_readonly"', bootstrap)
        self.assertIn("renderWorkspaceUnavailable();", bootstrap)
        self.assertIn('pill.classList.remove("measured")', unavailable)
        self.assertIn('pill.classList.add("unavailable")', unavailable)
        self.assertIn('pill.lastChild.textContent = "DATA: UNAVAILABLE"', unavailable)
        self.assertIn('$("sourceStamp").textContent = "Release unavailable"', unavailable)
        self.assertIn('$("sourceStamp").classList.remove("observed")', unavailable)
        self.assertIn('$("freshness").textContent = "Live sources unavailable"', unavailable)


if __name__ == "__main__":
    unittest.main()
