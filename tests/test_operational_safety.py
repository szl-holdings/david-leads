# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import os
import re
import hashlib
import socket
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import data_policy, dealdesk, frontier, receipts, scoring  # noqa: E402


class PublicCredentialSafety(unittest.TestCase):
    def test_rotation_secrets_are_scoped_to_the_steps_that_use_them(self):
        workflow = (
            ROOT / ".github" / "workflows" / "rotate-space-credentials.yml"
        ).read_text(encoding="utf-8")
        job_configuration = workflow.split("    steps:", 1)[0]
        for name in (
            "HF_TOKEN",
            "DAVID_USER",
            "DAVID_PASS",
            "DAVID_ACCESS_KEY",
            "DAVID_DATABASE_URL",
        ):
            reference = f"{name}: ${{{{ secrets.{name} }}}}"
            self.assertNotIn(reference, job_configuration)
            self.assertEqual(workflow.count(reference), 2)

    def test_rotation_preserves_an_unexposed_factor_during_partial_writes(self):
        workflow = (
            ROOT / ".github" / "workflows" / "rotate-space-credentials.yml"
        ).read_text(encoding="utf-8")
        order = workflow.split("          rotation_order = (", 1)[1].split(
            "          )", 1
        )[0]
        self.assertLess(order.index('"DAVID_ACCESS_KEY"'), order.index('"DAVID_USER"'))
        self.assertIn("          for key in rotation_order:", workflow)

    def test_restart_poll_waits_for_replacement_login(self):
        workflow = (
            ROOT / ".github" / "workflows" / "rotate-space-credentials.yml"
        ).read_text(encoding="utf-8")
        poll = workflow.split(
            "          while time.monotonic() < deadline:", 1
        )[1].split("          if health is None:", 1)[0]
        self.assertIn('requests.post(', poll)
        self.assertIn('f"{base_url}/api/login"', poll)
        self.assertIn("if login.status_code == 200:", poll)
        self.assertIn("session_token = candidate_token", poll)

    _REVOKED_VALUE_SHA256 = {
        "cbc2b2bf6496d7126045ae1948a1134f287623b8611ec3543e25ab6ce726ddf9",
        "9c33ff3e69a11bed324b9aebd2b7d526293c55981f6eb5ae1e493422ef355820",
        "3b438c1eaf81e68459eb33b9c3da897352af93a63fb646dec92dc2a512b91e1d",
    }
    _TOKEN_CANDIDATE = re.compile(r"[A-Za-z0-9][A-Za-z0-9!@#$%^&*_.\-]{7,127}")
    _HTML_SENSITIVE_VALUE = re.compile(
        r"""<input\b(?=[^>]*(?:type=["']password["']|name=["'][^"']*(?:pass|access.?key|token)[^"']*["']))"""
        r"""[^>]*\bvalue=["']([^"']+)["']""",
        re.IGNORECASE,
    )

    def test_no_hardcoded_auth_defaults_in_current_tree(self):
        forbidden_patterns = [
            re.compile(r"""os\.environ\.get\(\s*["']DAVID_(?:USER|PASS|ACCESS_KEY)["']\s*,"""),
            re.compile(r"""(?:DAVID_PASS|DAVID_ACCESS_KEY)\s*=\s*["'][^"']+["']"""),
        ]
        hits = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if path.suffix.lower() == ".docx":
                with zipfile.ZipFile(path) as archive:
                    text = "\n".join(
                        archive.read(name).decode("utf-8", "ignore")
                        for name in archive.namelist()
                    )
            else:
                try:
                    text = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
            for pattern in forbidden_patterns:
                if pattern.search(text):
                    hits.append(str(path.relative_to(ROOT)))
        self.assertEqual(hits, [])

    def test_legacy_fingerprint_is_revoked_without_retaining_values(self):
        from app import server

        self.assertIn(
            "3377808eda65b578cac8927ff49cf9d511dafe83b81ce8780905cc96641e3abd",
            server._REVOKED_CREDENTIAL_FINGERPRINTS,
        )
        self.assertTrue(
            all(re.fullmatch(r"[0-9a-f]{64}", item) for item in server._REVOKED_CREDENTIAL_FINGERPRINTS)
        )

    def test_revoked_credentials_are_absent_from_public_document_surfaces(self):
        hits: set[str] = set()
        allowed_suffixes = {".md", ".markdown", ".html", ".htm", ".txt", ".docx"}
        for path in ROOT.rglob("*"):
            if (
                not path.is_file()
                or ".git" in path.parts
                or "__pycache__" in path.parts
                or path.suffix.lower() not in allowed_suffixes
            ):
                continue
            try:
                if path.suffix.lower() == ".docx":
                    with zipfile.ZipFile(path) as archive:
                        text = "\n".join(
                            archive.read(name).decode("utf-8", "ignore")
                            for name in archive.namelist()
                            if name.lower().endswith((".xml", ".rels", ".txt"))
                        )
                    text = re.sub(r"<[^>]+>", " ", text)
                else:
                    text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError, zipfile.BadZipFile):
                continue
            candidates = self._TOKEN_CANDIDATE.findall(text)
            if path.suffix.lower() in {".html", ".htm"}:
                candidates.extend(self._HTML_SENSITIVE_VALUE.findall(text))
            if any(
                hashlib.sha256(candidate.encode("utf-8")).hexdigest()
                in self._REVOKED_VALUE_SHA256
                for candidate in candidates
            ):
                hits.add(str(path.relative_to(ROOT)))
        self.assertEqual(sorted(hits), [])


class ContactPermissionTruth(unittest.TestCase):
    def test_public_record_defaults_to_not_evaluated(self):
        result = frontier.compliance_axis({})
        self.assertIsNone(result["clear"])
        self.assertEqual(result["status"], "NOT_EVALUATED")
        self.assertLess(result["value"], 1.0)

    def test_explicit_block_still_hard_gates(self):
        result = frontier.compliance_axis({"dnc_listed": True})
        self.assertFalse(result["clear"])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["value"], 0.0)

    def test_not_evaluated_preserves_research_priority(self):
        lead = {"score": 81.0, "bucket": "HOT", "axes": {}}
        scoring._attach_frontier(lead)
        self.assertEqual(lead["score"], 81.0)
        self.assertEqual(lead["compliance"]["status"], "NOT_EVALUATED")
        self.assertNotIn("blocked", lead)

    def test_observed_block_zeroes_priority(self):
        lead = {"score": 81.0, "bucket": "HOT", "axes": {}, "dnc_listed": True}
        scoring._attach_frontier(lead)
        self.assertEqual(lead["score"], 0.0)
        self.assertEqual(lead["bucket"], "BLOCKED")
        self.assertTrue(lead["blocked"])


class OpportunityDeskSafety(unittest.TestCase):
    def setUp(self):
        dealdesk.reset_for_tests()
        self.record = {
            "name": "Example Logistics LLC",
            "type": "business",
            "category": "Motor Carrier",
            "address": "10 Business Ave",
            "city": "Albany",
            "state": "NY",
            "zip": "12207",
            "license_or_issue_date": "2026-07-25",
            "contact_quality": "business address (public)",
            "citation": {"url": "https://example.gov/entity/1", "label": "Official registry"},
            "receipt_id": "rcpt_example",
        }

    def tearDown(self):
        dealdesk.reset_for_tests()

    def test_persistence_requires_absolute_usable_root(self):
        with (
            patch.object(dealdesk, "_DATABASE_URL", None),
            patch.object(dealdesk, "_PATH", "relative/dealdesk.json"),
        ):
            self.assertEqual(dealdesk.persistence_state(), "NOT_CONFIGURED")
            self.assertFalse(dealdesk.persistence_configured())

        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory) / "dealdesk.json"
            store.write_text('{"existing": {"stage": "REVIEW"}}', encoding="utf-8")
            before = store.read_bytes()
            with (
                patch.object(dealdesk, "_DATABASE_URL", None),
                patch.object(dealdesk, "_PATH", str(store)),
            ):
                self.assertEqual(dealdesk.persistence_state(), "FILE_BACKED")
                self.assertTrue(dealdesk.persistence_configured())
            self.assertEqual(store.read_bytes(), before)

            missing_root = Path(directory) / "missing" / "dealdesk.json"
            with (
                patch.object(dealdesk, "_DATABASE_URL", None),
                patch.object(dealdesk, "_PATH", str(missing_root)),
            ):
                self.assertEqual(dealdesk.persistence_state(), "FILE_UNAVAILABLE")
                self.assertTrue(dealdesk.persistence_configured())
                self.assertFalse(dealdesk.persistence_ready())

            with (
                patch.object(dealdesk, "_DATABASE_URL", None),
                patch.object(dealdesk, "_PATH", directory),
            ):
                self.assertEqual(dealdesk.persistence_state(), "FILE_UNAVAILABLE")
                self.assertTrue(dealdesk.persistence_configured())
                self.assertFalse(dealdesk.persistence_ready())

    def test_persistence_probe_fails_closed_when_atomic_replace_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory) / "dealdesk.json"
            with (
                patch.object(dealdesk, "_DATABASE_URL", None),
                patch.object(dealdesk, "_PATH", str(store)),
                patch.object(dealdesk.os, "replace", side_effect=OSError("read-only volume")),
            ):
                self.assertEqual(dealdesk.persistence_state(), "FILE_UNAVAILABLE")
                self.assertTrue(dealdesk.persistence_configured())
                self.assertFalse(dealdesk.persistence_ready())

    def test_database_state_preserves_runtime_health(self):
        with (
            patch.object(dealdesk, "_DATABASE_URL", "postgresql://configured"),
            patch.object(dealdesk, "_PERSISTENCE_HEALTH", "POSTGRES_UNAVAILABLE"),
        ):
            self.assertTrue(dealdesk.persistence_configured())
            self.assertEqual(dealdesk.persistence_state(), "POSTGRES_UNAVAILABLE")
            self.assertFalse(dealdesk.persistence_ready())

    def _research(self, oid):
        return dealdesk.record_research(
            oid,
            actor="David",
            channel_type="BUSINESS_PHONE",
            channel_value="212-555-0123",
            source_url="https://examplelogistics.com/contact",
            publisher_class="FIRST_PARTY_BUSINESS_WEBSITE",
            note="Main business line verified",
        )

    def _clear(self, oid, channel_id):
        return dealdesk.record_clearance(
            oid,
            actor="David",
            channel_id=channel_id,
            business_purpose="Licensed business coverage review",
            talk_track_version="DL-B2B-MANUAL-v1",
            broker_jurisdiction="NY",
            license_scope="NY commercial lines through appointed agency",
            federal_dnc_checked=True,
            state_dnc_checked=True,
            opt_out_checked=True,
            rules_reviewed=True,
            expires_hours=24,
        )

    def test_public_record_is_research_only_by_default(self):
        opportunity = dealdesk.board([self.record])["opportunities"][0]
        self.assertEqual(opportunity["contact_gate"], "RESEARCH_REQUIRED")
        self.assertFalse(opportunity["call_ready"])
        self.assertEqual(opportunity["stage"], "REVIEW")

    def test_ready_stage_requires_evidence_backed_clearance(self):
        opportunity = dealdesk.board([self.record])["opportunities"][0]
        with self.assertRaises(ValueError):
            dealdesk.update(opportunity["opportunity_id"], stage="READY")
        researched = self._research(opportunity["opportunity_id"])
        updated = self._clear(
            opportunity["opportunity_id"],
            researched["channels"][0]["channel_id"],
        )
        self.assertTrue(updated["call_ready"])
        self.assertEqual(updated["contact_gate"], "TIME_LIMITED_CLEARANCE")
        self.assertRegex(updated["clearance"]["clearance_receipt"], r"^clr_[0-9a-f]{24}$")

    def test_return_to_research_revokes_prior_clearance(self):
        opportunity = dealdesk.board([self.record])["opportunities"][0]
        researched = self._research(opportunity["opportunity_id"])
        ready = self._clear(
            opportunity["opportunity_id"],
            researched["channels"][0]["channel_id"],
        )
        self.assertTrue(ready["call_ready"])

        research = dealdesk.update(
            opportunity["opportunity_id"],
            stage="RESEARCH",
        )
        self.assertFalse(research["call_ready"])
        self.assertEqual(research["contact_gate"], "CLEARANCE_EXPIRED_OR_REVOKED")
        with self.assertRaises(ValueError):
            dealdesk.update(opportunity["opportunity_id"], stage="READY")

    def test_failed_persistence_does_not_change_in_memory_clearance(self):
        opportunity = dealdesk.board([self.record])["opportunities"][0]
        researched = self._research(opportunity["opportunity_id"])
        with patch.object(dealdesk, "_persist", side_effect=OSError("disk unavailable")):
            with self.assertRaisesRegex(OSError, "disk unavailable"):
                self._clear(
                    opportunity["opportunity_id"],
                    researched["channels"][0]["channel_id"],
                )

        observed = dealdesk.enrich(self.record)
        self.assertEqual(observed["stage"], "RESEARCH")
        self.assertFalse(observed["call_ready"])
        self.assertEqual(observed["contact_gate"], "RESEARCH_REQUIRED")

    def test_current_default_block_revokes_stale_prior_clearance(self):
        opportunity = dealdesk.board([self.record])["opportunities"][0]
        researched = self._research(opportunity["opportunity_id"])
        self._clear(
            opportunity["opportunity_id"],
            researched["channels"][0]["channel_id"],
        )
        currently_blocked = dict(self.record, contact_quality="[SAMPLE]")

        observed = dealdesk.enrich(currently_blocked)

        self.assertFalse(observed["call_ready"])
        self.assertEqual(observed["contact_gate"], "DO_NOT_CONTACT_SAMPLE")
        with self.assertRaises(ValueError):
            dealdesk.update(observed["opportunity_id"], stage="READY")

    def test_sample_can_never_be_cleared(self):
        sample = dict(self.record, name="[SAMPLE] Example", contact_quality="[SAMPLE]")
        opportunity = dealdesk.board([sample])["opportunities"][0]
        with self.assertRaises(ValueError):
            dealdesk.record_research(
                opportunity["opportunity_id"],
                actor="David",
                channel_type="BUSINESS_PHONE",
                channel_value="2125550123",
                source_url="https://example.com/contact",
                publisher_class="FIRST_PARTY_BUSINESS_WEBSITE",
            )

    def test_social_and_personal_channels_are_rejected(self):
        opportunity = dealdesk.board([self.record])["opportunities"][0]
        with self.assertRaisesRegex(ValueError, "social-profile"):
            dealdesk.record_research(
                opportunity["opportunity_id"],
                actor="David",
                channel_type="BUSINESS_EMAIL",
                channel_value="sales@examplelogistics.com",
                source_url="https://linkedin.com/company/example",
                publisher_class="FIRST_PARTY_BUSINESS_WEBSITE",
            )
        with self.assertRaisesRegex(ValueError, "personal/free-mail"):
            dealdesk.record_research(
                opportunity["opportunity_id"],
                actor="David",
                channel_type="BUSINESS_EMAIL",
                channel_value="owner@gmail.com",
                source_url="https://examplelogistics.com/contact",
                publisher_class="FIRST_PARTY_BUSINESS_WEBSITE",
            )

    def test_do_not_call_disposition_revokes_and_blocks(self):
        opportunity = dealdesk.board([self.record])["opportunities"][0]
        researched = self._research(opportunity["opportunity_id"])
        self._clear(opportunity["opportunity_id"], researched["channels"][0]["channel_id"])
        blocked = dealdesk.record_disposition(
            opportunity["opportunity_id"],
            actor="David",
            disposition="DO_NOT_CALL",
            note="Business requested no further contact",
        )
        self.assertEqual(blocked["stage"], "BLOCKED")
        self.assertFalse(blocked["call_ready"])
        with self.assertRaises(ValueError):
            dealdesk.call_sheet(opportunity["opportunity_id"])


class ReceiptTruthStates(unittest.TestCase):
    def setUp(self):
        receipts.reset_chain()

    def test_first_party_consent_is_classified_not_public(self):
        receipt = receipts.make_receipt(
            {"id": "consent-1", "name": "Opt in", "bucket": "OPT-IN", "product": "CONSENT"},
            [{
                "source": "self-submitted form",
                "signal": "express consent",
                "public": False,
                "source_class": "FIRST_PARTY_CONSENT",
            }],
            100,
            witness=False,
        )
        verdict = receipts.verify_receipt(receipt)
        self.assertFalse(receipt["payload"]["all_signals_public"])
        self.assertEqual(verdict["source_classes"], ["FIRST_PARTY_CONSENT"])
        self.assertEqual(verdict["verdict"], "HASH_INTEGRITY_VERIFIED")
        self.assertEqual(verdict["signature_state"], "UNSIGNED")

    def test_missing_source_classification_defaults_non_public_and_fails_closed(self):
        receipt = receipts.make_receipt(
            {"id": "unknown-1", "name": "Unknown", "bucket": "REVIEW", "product": "UNKNOWN"},
            [{"source": "unspecified", "signal": "unclassified evidence"}],
            0,
            witness=False,
        )

        verdict = receipts.verify_receipt(receipt)

        self.assertFalse(receipt["payload"]["signals_used"][0]["public"])
        self.assertEqual(receipt["payload"]["source_classes"], ["UNCLASSIFIED"])
        self.assertFalse(receipt["payload"]["all_sources_permitted"])
        self.assertEqual(verdict["verdict"], "FAILED")

    def test_permission_is_recomputed_from_bound_source_classes(self):
        receipt = receipts.make_receipt(
            {"id": "unknown-2", "name": "Unknown", "bucket": "REVIEW", "product": "UNKNOWN"},
            [{"source": "official", "signal": "observed", "public": True}],
            10,
            witness=False,
        )
        receipt["payload"]["signals_used"][0]["source_class"] = "UNCLASSIFIED"
        receipt["payload"]["source_classes"] = ["UNCLASSIFIED"]
        receipt["payload"]["all_sources_permitted"] = True
        receipt["payload_sha256"] = hashlib.sha256(
            receipts._canon(receipt["payload"])
        ).hexdigest()

        verdict = receipts.verify_receipt(receipt)
        checks = {item["check"]: item["pass"] for item in verdict["checks"]}

        self.assertFalse(checks["Evidence source classes are permitted"])
        self.assertFalse(checks["Permission summary matches source classes"])
        self.assertEqual(verdict["verdict"], "FAILED")


class DataPolicySafety(unittest.TestCase):
    def test_social_scraping_and_consumer_enrichment_fail_closed(self):
        policy = data_policy.policy_document()
        by_id = {item["id"]: item for item in policy["source_classes"]}
        self.assertEqual(by_id["social-platform"]["ingestion"], "NO_UNAPPROVED_SCRAPING")
        self.assertEqual(by_id["consumer-report"]["ingestion"], "PROHIBITED_BY_DEFAULT")
        live = {item["id"]: item for item in policy["implemented_frontiers"]}
        self.assertEqual(live["fmcsa-company-census"]["status"], "LIVE_ENTITY_FIELDS_ONLY")
        self.assertEqual(
            live["epa-echo-monitoring-activity"]["status"],
            "LIVE_ENTITY_AND_FACILITY_FIELDS_ONLY",
        )
        deferred = {item["id"]: item for item in policy["deferred_frontiers"]}
        self.assertEqual(deferred["faa-aircraft-registry"]["status"], "PRIVACY_REVIEW_REQUIRED")
        self.assertEqual(policy["legal_status"], "OPERATIONAL_GUARDRAIL_NOT_LEGAL_ADVICE")


class ApiSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from fastapi.testclient import TestClient
            from app import server
        except Exception as exc:  # pragma: no cover
            raise unittest.SkipTest(f"application dependencies unavailable: {exc}")
        cls.server = server
        cls.client = TestClient(server.app)
        cls.token = "test-operational-safety"
        server._TOKENS[cls.token] = time.time() + 60
        cls.headers = {"Authorization": "Bearer " + cls.token}

    @classmethod
    def tearDownClass(cls):
        cls.server._TOKENS.pop(cls.token, None)

    def test_unknown_outcome_is_rejected(self):
        self.server._STATE["leads"] = []
        response = self.client.post(
            "/api/outcome",
            json={"lead_id": "does-not-exist", "outcome": "meeting"},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 404)

    def test_webhook_is_disabled_without_allowlist(self):
        previous = os.environ.pop("DAVID_CRM_WEBHOOK_ALLOWLIST", None)
        try:
            response = self.client.post(
                "/api/webhook/test",
                json={"url": "http://127.0.0.1:8765/healthz"},
                headers=self.headers,
            )
        finally:
            if previous is not None:
                os.environ["DAVID_CRM_WEBHOOK_ALLOWLIST"] = previous
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["sent"])
        self.assertIn("disabled", body["reason"])

    def test_webhook_connects_to_validated_address_with_tls_hostname(self):
        context = mock.Mock()
        raw_socket = mock.Mock()
        wrapped_socket = mock.Mock()
        context.wrap_socket.return_value = wrapped_socket
        connection = self.server._PinnedHTTPSConnection(
            "crm.example.com",
            "93.184.216.34",
            context=context,
        )

        with patch.object(socket, "create_connection", return_value=raw_socket) as connect:
            connection.connect()

        connect.assert_called_once_with(("93.184.216.34", 443), 8, None)
        context.wrap_socket.assert_called_once_with(
            raw_socket,
            server_hostname="crm.example.com",
        )
        self.assertIs(connection.sock, wrapped_socket)

    def test_webhook_validation_deduplicates_and_pins_one_address(self):
        previous = os.environ.get("DAVID_CRM_WEBHOOK_ALLOWLIST")
        os.environ["DAVID_CRM_WEBHOOK_ALLOWLIST"] = "crm.example.com"
        answers = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
        ]
        try:
            with patch.object(socket, "getaddrinfo", return_value=answers):
                parsed, hostname, addresses = self.server._webhook_destination(
                    "https://crm.example.com/import"
                )
        finally:
            if previous is None:
                os.environ.pop("DAVID_CRM_WEBHOOK_ALLOWLIST", None)
            else:
                os.environ["DAVID_CRM_WEBHOOK_ALLOWLIST"] = previous

        self.assertEqual(parsed.path, "/import")
        self.assertEqual(hostname, "crm.example.com")
        self.assertEqual(addresses, ("93.184.216.34",))

    def test_webhook_tries_validated_addresses_until_connect_succeeds(self):
        parsed = self.server.urllib.parse.urlparse("https://crm.example.com/import")
        failed = mock.Mock()
        failed.connect.side_effect = OSError("IPv6 route unavailable")
        connected = mock.Mock()
        response = mock.Mock(status=204)
        connected.getresponse.return_value = response

        with patch.object(
            self.server,
            "_PinnedHTTPSConnection",
            side_effect=[failed, connected],
        ) as connection_type:
            status = self.server._post_validated_webhook(
                parsed,
                "crm.example.com",
                ("2001:4860:4860::8888", "93.184.216.34"),
                b"{}",
            )

        self.assertEqual(status, 204)
        failed.close.assert_called_once()
        connected.connect.assert_called_once()
        connected.request.assert_called_once()
        response.read.assert_called_once_with(1)
        connected.close.assert_called_once()
        self.assertEqual(
            [call.args[1] for call in connection_type.call_args_list],
            ["2001:4860:4860::8888", "93.184.216.34"],
        )

    def test_health_and_readiness_fail_closed_for_auth_and_persistence(self):
        with (
            patch.object(self.server, "_CREDS_CONFIGURED", False),
            patch.object(self.server, "_CREDS_ROTATION_REQUIRED", True),
            patch.object(self.server.dd, "persistence_state", return_value="FILE_BACKED"),
        ):
            health = self.client.get("/healthz")
        self.assertEqual(health.status_code, 503)
        self.assertEqual(health.json()["status"], "blocked")
        self.assertEqual(health.json()["authentication"], "ROTATION_REQUIRED")

        with (
            patch.object(self.server, "_CREDS_CONFIGURED", True),
            patch.object(self.server, "_CREDS_ROTATION_REQUIRED", False),
            patch.object(self.server.dd, "persistence_state", return_value="NOT_CONFIGURED"),
        ):
            readiness = self.client.get("/readyz")
        self.assertEqual(readiness.status_code, 503)
        self.assertEqual(readiness.json()["deal_desk_persistence"], "NOT_CONFIGURED")

        with (
            patch.object(self.server, "_CREDS_CONFIGURED", True),
            patch.object(self.server, "_CREDS_ROTATION_REQUIRED", False),
            patch.object(self.server.dd, "persistence_state", return_value="POSTGRES_READY"),
        ):
            readiness = self.client.get("/readyz")
        self.assertEqual(readiness.status_code, 200)
        self.assertEqual(readiness.json()["status"], "ready")

    def test_deal_desk_fails_closed_without_durable_persistence(self):
        with patch.object(self.server.dd, "persistence_ready", return_value=False):
            response = self.client.get("/api/deal-desk", headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertIn("DAVID_DATABASE_URL", response.json()["detail"])

    def test_build_info_is_explicitly_unverified_until_external_compare(self):
        response = self.client.get("/api/build-info")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["github_huggingface_alignment"], "UNVERIFIED")
        self.assertRegex(body["bundle_sha256"], r"^[0-9a-f]{64}$")

    def test_frontier_desk_requires_research_before_contact(self):
        record = {
            "name": "Example Carrier LLC",
            "type": "carrier",
            "category": "Motor carrier",
            "credential": "USDOT 1234567",
            "address": "10 Business Road",
            "city": "Albany",
            "state": "NY",
            "zip": "12207",
            "license_or_issue_date": "2026-07-27",
            "contact_quality": "business address (public)",
            "citation": {"label": "FMCSA", "url": "https://example.gov/fmcsa/1234567"},
            "source_frontier": "FMCSA",
            "purpose": "PROSPECTING_ONLY",
            "not_for_underwriting": True,
        }
        payload = {
            "leads": [record],
            "sources": [{
                "source": "FMCSA",
                "source_id": "fmcsa-company-census",
                "mode": "LIVE",
                "count": 1,
            }],
            "generated_at": "2026-07-28T00:00:00+00:00",
            "states": ["NY"],
            "doctrine": "entity fields only",
        }
        self.server.dd.reset_for_tests()
        try:
            with (
                mock.patch.object(self.server.dd, "persistence_ready", return_value=True),
                mock.patch.object(
                    self.server.frontier_data,
                    "frontier_opportunities",
                    return_value=payload,
                ),
            ):
                response = self.client.get(
                    "/api/frontier-desk?states=NY",
                    headers=self.headers,
                )
        finally:
            self.server.dd.reset_for_tests()
        self.assertEqual(response.status_code, 200)
        opportunity = response.json()["opportunities"][0]
        self.assertEqual(opportunity["contact_gate"], "RESEARCH_REQUIRED")
        self.assertFalse(opportunity["call_ready"])
        self.assertTrue(opportunity["not_for_underwriting"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
