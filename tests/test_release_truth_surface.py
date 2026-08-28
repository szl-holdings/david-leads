from __future__ import annotations

import html
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app import receipts
from app import server


class ReleaseTruthSurfaceTests(unittest.TestCase):
    root = Path(__file__).resolve().parents[1]

    @staticmethod
    def _docx_text(path: Path) -> str:
        with ZipFile(path) as archive:
            xml_parts = [
                archive.read(name).decode("utf-8", errors="replace")
                for name in archive.namelist()
                if name.startswith("word/") and name.endswith(".xml")
            ]
        return html.unescape(re.sub(r"<[^>]+>", " ", " ".join(xml_parts)))

    def setUp(self):
        self.client = TestClient(server.app)

    def test_methodology_is_active_organization_contract_only(self):
        response = self.client.get("/api/methodology")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        card = body["model_card"]
        self.assertEqual(card["decision_unit"], "organization")
        self.assertEqual(card["contact_boundary"]["default"], "PUBLIC_RESEARCH_ONLY")
        self.assertFalse(
            card["evidence_constellation"]["proof_grade_is_sales_probability"]
        )
        serialized = json.dumps(body).lower()
        for retired_field in (
            "appointment_forecast",
            "wealth_tier",
            "income_fit",
            "age_window_fit",
            "baby",
            "marriage",
            "death",
        ):
            self.assertNotIn(retired_field, serialized)

    def test_openapi_is_curated_to_supported_public_research_contract(self):
        server.app.openapi_schema = None
        response = self.client.get("/openapi.json")

        self.assertEqual(response.status_code, 200)
        schema = response.json()
        self.assertEqual(
            schema["info"]["title"],
            "David Leads — Evidence-Backed Broker Research",
        )
        self.assertIn("/api/frontier-desk", schema["paths"])
        self.assertIn("/api/verify/{rid}", schema["paths"])
        self.assertNotIn("/api/run", schema["paths"])
        self.assertNotIn("/api/outcome", schema["paths"])
        self.assertNotIn("/api/export.csv", schema["paths"])
        self.assertLessEqual(len(schema["paths"]), 12)

    def test_public_shell_has_compression_and_browser_security_headers(self):
        response = self.client.get("/", headers={"Accept-Encoding": "gzip"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-encoding"], "gzip")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(
            response.headers["referrer-policy"],
            "strict-origin-when-cross-origin",
        )
        self.assertIn("default-src 'self'", response.headers["content-security-policy"])

    def test_anonymous_static_surface_excludes_retired_prospect_semantics(self):
        responses = {
            path: self.client.get(path)
            for path in ("/", "/app.js", "/holo.js")
        }
        retired_semantics = (
            "new-parent household",
            "recently-promoted professional",
            "mid-career dual-income",
            "hot / warm / nurture",
            "leadconstellation",
            "pipeline3d",
            "est_premium",
            "qualified_appts",
            "qualified appointments",
            "wealth tier",
            "lapse-risk",
            "life_event_strength",
            "age_window_fit",
            "product_propensity",
            "who should i call first",
        )

        for path, response in responses.items():
            self.assertEqual(response.status_code, 200, path)
            content = response.text.lower()
            for retired_semantic in retired_semantics:
                with self.subTest(path=path, retired_semantic=retired_semantic):
                    self.assertNotIn(retired_semantic, content)

        shell = responses["/"].text
        holo = responses["/holo.js"].text
        self.assertIn("holo.css", shell)
        self.assertNotIn("holo.js", shell)
        self.assertLess(len(holo.encode("utf-8")), 2_000)
        self.assertIn("RETIRED / INERT COMPATIBILITY STUB", holo)

    def test_hugging_face_document_links_are_copied_and_trigger_deploy_chain(self):
        dockerfile = (self.root / "Dockerfile").read_text(encoding="utf-8")
        migration = (
            self.root / ".github" / "workflows" / "migrate-neon-persistence.yml"
        ).read_text(encoding="utf-8")
        required = (
            "THIRD_PARTY_NOTICES.md",
            "research/COMPETITIVE_SYNTHESIS_2026-08-26.md",
            "ops/credential-rotation.md",
        )

        for relative_path in required:
            with self.subTest(relative_path=relative_path):
                self.assertTrue((self.root / relative_path).is_file())
                self.assertIn(relative_path, dockerfile)
                self.assertIn(f'"{relative_path}"', migration)

    def test_policy_prohibits_modeled_commercial_forecasts(self):
        policy = (
            self.root / "PUBLIC_DATA_OPERATING_MODEL.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(policy.lower().split())

        self.assertIn(
            "modeled appointments, premium, pipeline, revenue, conversion, and "
            "buying-likelihood forecasts are out of scope for this release, even "
            "when labeled",
            normalized,
        )
        self.assertNotIn("may remain secondary", normalized)

    def test_ci_paths_cover_all_publication_and_collateral_inputs(self):
        workflow = (
            self.root / ".github" / "workflows" / "ci.yml"
        ).read_text(encoding="utf-8")
        push_block = workflow.split("  push:", 1)[1].split(
            "  pull_request:", 1
        )[0]
        pull_request_block = workflow.split("  pull_request:", 1)[1].split(
            "  workflow_dispatch:", 1
        )[0]
        required_paths = (
            "tools/**",
            "research/**",
            "qa/**",
            "*.md",
            "*.txt",
            "*.html",
            "*.docx",
            "build_portable.py",
            "doc_build_make_doc.js",
            ".github/workflows/**",
        )

        for trigger, block in (
            ("push", push_block),
            ("pull_request", pull_request_block),
        ):
            for required_path in required_paths:
                with self.subTest(trigger=trigger, required_path=required_path):
                    self.assertIn(f'- "{required_path}"', block)

    def test_data_policy_covers_form5500_and_constellation(self):
        with patch.object(server, "_PUBLIC_READONLY", True):
            response = self.client.get("/api/data-policy")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["reviewed_on"], "2026-08-28")
        frontier_ids = {item["id"] for item in body["implemented_frontiers"]}
        self.assertIn("dol-form5500-benefit-timing", frontier_ids)
        fmcsa = next(
            item
            for item in body["implemented_frontiers"]
            if item["id"] == "fmcsa-company-census"
        )
        self.assertIn("recognized legal organization suffix", fmcsa["admission"])
        self.assertIn("physical street address", fmcsa["excluded_fields"])
        self.assertEqual(
            body["evidence_constellation"]["permission_default"],
            "PUBLIC_RESEARCH_ONLY",
        )
        self.assertIn(
            "unknown identifier systems",
            body["evidence_constellation"]["prohibited_identity_links"],
        )

    def test_receipt_verification_discloses_ephemeral_witness_mode(self):
        receipt = receipts.make_receipt(
            {
                "id": "lead-1",
                "name": "Example Organization",
                "bucket": "RESEARCH",
                "product": "Business protection research",
            },
            [{
                "source": "Official source",
                "signal": "Organization event observed",
                "public": True,
                "source_class": "PUBLIC",
            }],
            0.0,
            witness=True,
        )

        verification = receipts.verify_receipt(receipt)
        self.assertIn("witness", verification)
        if receipt.get("consensus"):
            self.assertIn(
                verification["witness"]["durability"],
                {"PROCESS_EPHEMERAL", "DECLARED_BY_RECEIPT"},
            )

    def test_current_facing_collateral_excludes_retired_product_claims(self):
        current_files = (
            "README.md",
            "FOR_DAVID.md",
            "HANDOFF_FOR_STEPHEN.md",
            "DAVID_ABRAHAM_WALKTHROUGH.md",
            "README_FOR_STEPHEN.txt",
            "PUBLICATION_READINESS.md",
            "PUBLIC_DATA_OPERATING_MODEL.md",
            "tools/build_broker_guide.py",
            "tools/build_david_broker_guide.py",
        )
        retired_claims = (
            "sovereign insurance intelligence",
            "eastern market cockpit",
            "verified deal moment",
            "hot / warm / nurture",
            "hot/warm/nurture",
            "qualified appointments / week",
            "qualified appts / week",
            "pipeline premium",
            "premium pipeline",
            "new-parent household",
            "life-event predictive scoring",
            "wealth tier",
            "wealth tiers",
            "lapse-risk",
            "private, login-gated",
            "login-gated console",
            "cached/sample",
        )

        for relative_path in current_files:
            content = (self.root / relative_path).read_text(encoding="utf-8").lower()
            for retired_claim in retired_claims:
                with self.subTest(
                    relative_path=relative_path,
                    retired_claim=retired_claim,
                ):
                    self.assertNotIn(retired_claim, content)

        for relative_path in (
            "David_Leads_Broker_Guide.docx",
            "David_Leads_Broker_Field_Guide_2026.docx",
        ):
            content = self._docx_text(self.root / relative_path).lower()
            for retired_claim in retired_claims:
                with self.subTest(
                    relative_path=relative_path,
                    retired_claim=retired_claim,
                ):
                    self.assertNotIn(retired_claim, content)

    def test_retired_collateral_is_unmistakable_and_non_operational(self):
        for relative_path in (
            "SPEC.md",
            "backend_frontend_qa.md",
            "qa/backend_frontend_qa.md",
            "live_audit.md",
            "app/INVESTOR_READY_SELFTEST.md",
            "app/FRONTIER_SELFTEST.md",
        ):
            prefix = (self.root / relative_path).read_text(encoding="utf-8")[:1200]
            with self.subTest(relative_path=relative_path):
                self.assertIn("LEGACY", prefix)
                self.assertIn("RETIRED", prefix)
                self.assertIn("DO NOT USE", prefix)
                self.assertIn("README.md", prefix)
                self.assertIn("FOR_DAVID.md", prefix)

        portable = (self.root / "David_Leads_PORTABLE.html").read_text(
            encoding="utf-8"
        )
        self.assertLess(len(portable.encode("utf-8")), 10_000)
        self.assertIn("LEGACY / RETIRED / DO NOT USE", portable)
        self.assertIn("README.md", portable)
        self.assertIn("FOR_DAVID.md", portable)
        self.assertNotIn("<script", portable.lower())
        self.assertNotIn("EMBEDDED", portable)

        access_notice = self._docx_text(
            self.root / "David_Leads_Access_and_Tour.docx"
        )
        self.assertIn("LEGACY / RETIRED / DO NOT USE", access_notice)
        self.assertIn("README.md", access_notice)
        self.assertIn("FOR_DAVID.md", access_notice)

        selftest = json.loads(
            (self.root / "V8_SELFTEST.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            selftest["artifact_status"],
            "LEGACY_RETIRED_DO_NOT_USE",
        )
        self.assertEqual(selftest["current_contract"], ["README.md", "FOR_DAVID.md"])

    def test_retired_builders_fail_closed_or_only_emit_tombstones(self):
        portable_builder = (self.root / "build_portable.py").read_text(
            encoding="utf-8"
        )
        access_builder = (self.root / "doc_build_make_doc.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("LEGACY / RETIRED / DO NOT USE", portable_builder)
        self.assertIn("TOMBSTONE", portable_builder)
        self.assertNotIn("offline_v4.json", portable_builder)
        self.assertNotIn("const EMBEDDED", portable_builder)
        self.assertIn("LEGACY / RETIRED / DO NOT USE", access_builder)
        self.assertIn("process.exitCode = 2", access_builder)
        self.assertNotIn('require("docx")', access_builder)


if __name__ == "__main__":
    unittest.main()
