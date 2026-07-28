# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import os
import re
import sys
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
        for name in ("HF_TOKEN", "DAVID_USER", "DAVID_PASS", "DAVID_ACCESS_KEY"):
            reference = f"{name}: ${{{{ secrets.{name} }}}}"
            self.assertNotIn(reference, job_configuration)
            self.assertEqual(workflow.count(reference), 2)

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

    def test_public_record_is_research_only_by_default(self):
        opportunity = dealdesk.board([self.record])["opportunities"][0]
        self.assertEqual(opportunity["contact_gate"], "RESEARCH_REQUIRED")
        self.assertFalse(opportunity["call_ready"])
        self.assertEqual(opportunity["stage"], "REVIEW")

    def test_ready_stage_requires_manual_clearance(self):
        opportunity = dealdesk.board([self.record])["opportunities"][0]
        with self.assertRaises(ValueError):
            dealdesk.update(opportunity["opportunity_id"], stage="READY")
        updated = dealdesk.update(
            opportunity["opportunity_id"],
            stage="READY",
            clearance_confirmed=True,
        )
        self.assertTrue(updated["call_ready"])
        self.assertEqual(updated["contact_gate"], "MANUAL_CLEARANCE_RECORDED")

    def test_return_to_research_revokes_prior_clearance(self):
        opportunity = dealdesk.board([self.record])["opportunities"][0]
        ready = dealdesk.update(
            opportunity["opportunity_id"],
            stage="READY",
            clearance_confirmed=True,
        )
        self.assertTrue(ready["call_ready"])

        research = dealdesk.update(
            opportunity["opportunity_id"],
            stage="RESEARCH",
        )
        self.assertFalse(research["call_ready"])
        self.assertEqual(research["contact_gate"], "RESEARCH_REQUIRED")
        with self.assertRaises(ValueError):
            dealdesk.update(opportunity["opportunity_id"], stage="READY")

    def test_failed_persistence_does_not_change_in_memory_clearance(self):
        opportunity = dealdesk.board([self.record])["opportunities"][0]
        with patch.object(dealdesk, "_persist", side_effect=OSError("disk unavailable")):
            with self.assertRaisesRegex(OSError, "disk unavailable"):
                dealdesk.update(
                    opportunity["opportunity_id"],
                    stage="READY",
                    clearance_confirmed=True,
                )

        observed = dealdesk.enrich(self.record)
        self.assertEqual(observed["stage"], "REVIEW")
        self.assertFalse(observed["call_ready"])
        self.assertEqual(observed["contact_gate"], "RESEARCH_REQUIRED")

    def test_sample_can_never_be_cleared(self):
        sample = dict(self.record, name="[SAMPLE] Example", contact_quality="[SAMPLE]")
        opportunity = dealdesk.board([sample])["opportunities"][0]
        with self.assertRaises(ValueError):
            dealdesk.update(
                opportunity["opportunity_id"],
                stage="READY",
                clearance_confirmed=True,
            )


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


class DataPolicySafety(unittest.TestCase):
    def test_social_scraping_and_consumer_enrichment_fail_closed(self):
        policy = data_policy.policy_document()
        by_id = {item["id"]: item for item in policy["source_classes"]}
        self.assertEqual(by_id["social-platform"]["ingestion"], "NO_UNAPPROVED_SCRAPING")
        self.assertEqual(by_id["consumer-report"]["ingestion"], "PROHIBITED_BY_DEFAULT")
        live = {item["id"]: item for item in policy["implemented_frontiers"]}
        self.assertEqual(live["fmcsa-company-census"]["status"], "LIVE_ENTITY_FIELDS_ONLY")
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
            with mock.patch.object(
                self.server.frontier_data,
                "frontier_opportunities",
                return_value=payload,
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
