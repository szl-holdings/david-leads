# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import os
import re
import hashlib
import json
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
    def test_rotation_requires_the_named_protected_environment(self):
        workflow = (
            ROOT / ".github" / "workflows" / "rotate-space-credentials.yml"
        ).read_text(encoding="utf-8")
        job_configuration = workflow.split("    steps:", 1)[0]
        guide = (ROOT / "ops" / "credential-rotation.md").read_text(encoding="utf-8")

        self.assertIn(
            "    environment:\n      name: david-space-credential-rotation",
            job_configuration,
        )
        self.assertIn("deployment branches restricted to the protected `main` branch", guide)
        self.assertIn("a required owner approval", guide)
        self.assertIn("stored as\n  environment secrets", guide)
        self.assertIn("No `DAVID_*` value is stored at\nrepository scope", guide)
        self.assertIn("Protected run `30403607270` completed", guide)

    def test_deploy_follows_successful_exact_main_migration(self):
        deploy_workflow = (
            ROOT / ".github" / "workflows" / "hf-deploy.yml"
        ).read_text(encoding="utf-8")
        migration_workflow = (
            ROOT / ".github" / "workflows" / "migrate-neon-persistence.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("branches: [main]", migration_workflow)
        self.assertIn(
            'workflows: ["Migrate David Neon persistence"]',
            deploy_workflow,
        )
        self.assertIn(
            "WORKFLOW_CONCLUSION: ${{ github.event.workflow_run.conclusion || '' }}",
            deploy_workflow,
        )
        self.assertIn(
            "WORKFLOW_EVENT: ${{ github.event.workflow_run.event || '' }}",
            deploy_workflow,
        )
        self.assertIn(
            "WORKFLOW_BRANCH: ${{ github.event.workflow_run.head_branch || '' }}",
            deploy_workflow,
        )
        self.assertIn(
            "WORKFLOW_SHA: ${{ github.event.workflow_run.head_sha || '' }}",
            deploy_workflow,
        )
        self.assertIn('[ "$WORKFLOW_CONCLUSION" = "success" ]', deploy_workflow)
        self.assertIn('[ "$WORKFLOW_EVENT" = "push" ]', deploy_workflow)
        self.assertIn('[ "$WORKFLOW_BRANCH" = "main" ]', deploy_workflow)
        self.assertIn("git ls-remote origin refs/heads/main", deploy_workflow)
        self.assertIn('[ "$source_sha" = "$current_main" ]', deploy_workflow)
        self.assertIn("WAIT_FOR_SCHEMA_MIGRATION", deploy_workflow)
        self.assertIn("SCHEMA_MIGRATION_SUCCEEDED", deploy_workflow)
        self.assertIn("STALE_MIGRATION_RESULT", deploy_workflow)
        self.assertIn(
            "ref: ${{ needs.classify.outputs.source_sha }}",
            deploy_workflow,
        )
        self.assertIn("workflow_dispatch: {}", deploy_workflow)
        self.assertIn("OWNER_DISPATCH_REQUIRES_MAIN", deploy_workflow)
        self.assertNotIn("rotate-app-secrets", deploy_workflow)
        self.assertNotIn("secrets: inherit", deploy_workflow)
        self.assertIn("HF_TOKEN: ${{ secrets.HF_TOKEN }}", deploy_workflow)
        self.assertIn("id-token: write", deploy_workflow)
        self.assertIn("attestations: write", deploy_workflow)
        self.assertIn(
            "actions/attest@36051bcae73b7c2a8a6945a48cbf80953c6baa35",
            deploy_workflow,
        )
        self.assertIn(
            "subject-path: release-evidence/hf-deploy-manifest.json",
            deploy_workflow,
        )
        self.assertIn('key="RELEASE_ATTESTATION"', deploy_workflow)
        self.assertIn(
            'body.get("receipt_minted") is True',
            deploy_workflow,
        )
        self.assertIn(
            'body.get("build", {}).get("revision")',
            deploy_workflow,
        )
        self.assertIn(
            'body.get("source_revision")',
            deploy_workflow,
        )
        self.assertNotIn(
            'body.get("source_revision", {}).get("revision")',
            deploy_workflow,
        )
        for name in (
            "DAVID_USER",
            "DAVID_PASS",
            "DAVID_ACCESS_KEY",
            "DAVID_DATABASE_URL",
        ):
            self.assertNotIn(f"secrets.{name}", deploy_workflow)

    def test_repository_has_no_credential_stdout_reader(self):
        self.assertFalse((ROOT / "ops" / "get_david_credentials.ps1").exists())
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(
            "repository script reads credentials into terminal output",
            readme,
        )

    def test_neon_preflight_is_main_only_and_environment_bound(self):
        workflow = (
            ROOT / ".github" / "workflows" / "verify-neon-persistence.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("if: github.ref == 'refs/heads/main'", workflow)
        self.assertIn("name: david-space-credential-rotation", workflow)
        self.assertIn("SET TRANSACTION READ ONLY", workflow)
        self.assertIn("david_dealdesk_schema", workflow)
        self.assertIn("cursor.fetchone() != (2,)", workflow)
        self.assertIn("credential_values_recorded", workflow)
        self.assertNotIn("type(exc).__name__", workflow)

    def test_neon_migration_uses_a_separate_protected_admin_credential(self):
        workflow = (
            ROOT / ".github" / "workflows" / "migrate-neon-persistence.yml"
        ).read_text(encoding="utf-8")
        guide = (ROOT / "ops" / "neon-persistence.md").read_text(encoding="utf-8")
        self.assertIn("if: github.ref == 'refs/heads/main'", workflow)
        self.assertIn("name: david-space-credential-rotation", workflow)
        self.assertIn("secrets.DAVID_DATABASE_ADMIN_URL", workflow)
        self.assertIn("secrets.DAVID_DATABASE_URL", workflow)
        self.assertIn("sql.Identifier(runtime_role)", workflow)
        self.assertIn(
            '"david_dealdesk_state": {"SELECT", "INSERT", "UPDATE"}',
            workflow,
        )
        self.assertIn('sql.SQL("GRANT {} ON TABLE {}.{} TO {}")', workflow)
        self.assertIn("runtime_role in {admin_role, database_owner}", workflow)
        self.assertIn("runtime_attributes[0] is not True", workflow)
        self.assertIn("pg_has_role(", workflow)
        self.assertIn("runtime database role inherits privileged membership", workflow)
        self.assertIn('sql.SQL("ALTER TABLE {}.{} OWNER TO {}")', workflow)
        self.assertIn("REVOKE CREATE ON SCHEMA {} FROM PUBLIC", workflow)
        self.assertIn("REVOKE ALL PRIVILEGES ON TABLE {}.{} FROM {}", workflow)
        self.assertIn("has_schema_privilege(", workflow)
        self.assertIn("has_table_privilege(", workflow)
        self.assertIn(
            "legacy do-not-call identity requires governed backfill",
            workflow,
        )
        self.assertIn("schema_sha256", workflow)
        self.assertIn("least-privilege runtime secret", guide)
        self.assertIn("transfers service-table ownership", guide)
        self.assertIn("governed identity backfill", guide)
        self.assertIn("never attempts `CREATE TABLE`", guide)

    def test_rotation_secrets_are_scoped_to_the_steps_that_use_them(self):
        workflow = (
            ROOT / ".github" / "workflows" / "rotate-space-credentials.yml"
        ).read_text(encoding="utf-8")
        job_configuration = workflow.split("    steps:", 1)[0]
        for name in (
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
        self.assertIn("response.status_code in {200, 503}", poll)
        login_prefix = poll.split("requests.post(", 1)[0]
        self.assertNotIn("POSTGRES_READY", login_prefix)

    def test_rotation_uses_secret_triggered_restarts_with_bounded_convergence(self):
        workflow = (
            ROOT / ".github" / "workflows" / "rotate-space-credentials.yml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("api.restart_space(", workflow)
        self.assertIn("deadline = time.monotonic() + 900", workflow)
        self.assertIn("timeout-minutes: 25", workflow)

    def test_rotation_normalizes_only_accidental_secret_line_endings(self):
        workflow = (
            ROOT / ".github" / "workflows" / "rotate-space-credentials.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('os.environ[name].rstrip("\\r\\n")', workflow)
        self.assertIn(
            "protected environment secret is empty after line-ending normalization",
            workflow,
        )
        for name in (
            "HF_TOKEN",
            "DAVID_USER",
            "DAVID_PASS",
            "DAVID_ACCESS_KEY",
            "DAVID_DATABASE_URL",
        ):
            self.assertIn(f'normalized_secret("{name}")', workflow)
        self.assertNotIn(".strip()", workflow)

    def test_rotation_timeout_diagnostics_never_include_response_or_secret_values(self):
        workflow = (
            ROOT / ".github" / "workflows" / "rotate-space-credentials.yml"
        ).read_text(encoding="utf-8")
        timeout = workflow.split("          if health is None:", 1)[1].split(
            "          logout = requests.post(", 1
        )[0]
        for field in (
            "health_http_status",
            "authentication",
            "deal_desk_persistence",
            "login_http_status",
            "error_class",
            "credential_values_recorded",
        ):
            self.assertIn(f'"{field}"', timeout)
        self.assertNotIn("response.text", workflow)
        self.assertNotIn("response.content", workflow)
        self.assertNotIn("login.text", workflow)
        self.assertNotIn("login.content", workflow)
        self.assertNotIn("credentials[", timeout)
        self.assertNotIn("space_secrets[", timeout)

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

    def test_file_persistence_requires_an_absolute_usable_store(self):
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
                self.assertEqual(dealdesk.persistence_state(), "FILE_READY")
                self.assertTrue(dealdesk.persistence_ready())
            self.assertEqual(store.read_bytes(), before)

            missing_root = Path(directory) / "missing" / "dealdesk.json"
            with (
                patch.object(dealdesk, "_DATABASE_URL", None),
                patch.object(dealdesk, "_PATH", str(missing_root)),
            ):
                self.assertEqual(dealdesk.persistence_state(), "FILE_UNAVAILABLE")
                self.assertFalse(dealdesk.persistence_ready())

    def test_orphaned_file_lock_does_not_block_the_store(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory) / "dealdesk.json"
            lock = Path(str(store) + ".lock")
            store.write_text("{}", encoding="utf-8")
            lock.write_text("orphaned predecessor", encoding="utf-8")

            with patch.object(dealdesk, "_PATH", str(store)):
                with dealdesk._file_store_lock():
                    self.assertTrue(lock.exists())
                with dealdesk._file_store_lock():
                    self.assertTrue(lock.exists())

            with (
                patch.object(dealdesk, "_DATABASE_URL", None),
                patch.object(dealdesk, "_PATH", directory),
            ):
                self.assertEqual(dealdesk.persistence_state(), "FILE_UNAVAILABLE")
                self.assertFalse(dealdesk.persistence_ready())

    def test_file_persistence_probe_fails_closed_when_atomic_replace_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory) / "dealdesk.json"
            with (
                patch.object(dealdesk, "_DATABASE_URL", None),
                patch.object(dealdesk, "_PATH", str(store)),
                patch.object(dealdesk.os, "replace", side_effect=OSError("read-only volume")),
            ):
                self.assertEqual(dealdesk.persistence_state(), "FILE_UNAVAILABLE")
                self.assertFalse(dealdesk.persistence_ready())

    def test_file_probe_replaces_exact_target_under_shared_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory) / "dealdesk.json"
            original = b'{"existing":{"stage":"REVIEW"}}'
            store.write_bytes(original)
            real_replace = dealdesk.os.replace
            with (
                patch.object(dealdesk, "_DATABASE_URL", None),
                patch.object(dealdesk, "_PATH", str(store)),
                patch.object(dealdesk.os, "replace", wraps=real_replace) as replace,
            ):
                self.assertEqual(dealdesk.persistence_state(), "FILE_READY")

            replace.assert_called_once()
            self.assertEqual(Path(replace.call_args.args[1]), store)
            self.assertEqual(store.read_bytes(), original)
            self.assertTrue(Path(str(store) + ".lock").exists())
            with patch.object(dealdesk, "_PATH", str(store)):
                with dealdesk._file_store_lock():
                    pass

    def test_file_probe_never_replaces_malformed_store(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory) / "dealdesk.json"
            store.write_text("{malformed", encoding="utf-8")
            with (
                patch.object(dealdesk, "_DATABASE_URL", None),
                patch.object(dealdesk, "_PATH", str(store)),
                patch.object(dealdesk.os, "replace") as replace,
            ):
                self.assertEqual(dealdesk.persistence_state(), "FILE_UNAVAILABLE")

            replace.assert_not_called()
            self.assertEqual(store.read_text(encoding="utf-8"), "{malformed")

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

    def test_postgres_readiness_recovers_after_a_transient_startup_failure(self):
        recovered = {"opp_recovered": {"stage": "RESEARCH"}}
        with (
            patch.object(dealdesk, "_DATABASE_URL", "postgresql://configured"),
            patch.object(dealdesk, "_PERSISTENCE_HEALTH", "POSTGRES_UNAVAILABLE"),
            patch.object(dealdesk, "_PERSISTENCE_DIAGNOSTIC", "CONNECTION_TIMEOUT"),
            patch.object(dealdesk, "_LAST_PROBE_AT", 0.0),
            patch.object(
                dealdesk,
                "_database_snapshot",
                return_value=recovered,
            ) as load,
        ):
            self.assertEqual(dealdesk.persistence_state(), "POSTGRES_READY")
            self.assertEqual(dealdesk.persistence_diagnostic(), "OK")
        load.assert_called_once_with()

    def test_postgres_diagnostics_never_echo_connection_details(self):
        secret_host = "secret-db.example.invalid"
        error = RuntimeError(
            f"connection timeout while connecting to {secret_host}"
        )
        diagnostic = dealdesk._classify_database_error(error)
        self.assertEqual(diagnostic, "CONNECTION_TIMEOUT")
        self.assertNotIn(secret_host, diagnostic)

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

    def test_do_not_call_suppression_survives_a_new_signal_identity(self):
        opportunity = dealdesk.board([self.record])["opportunities"][0]
        researched = self._research(opportunity["opportunity_id"])
        self._clear(opportunity["opportunity_id"], researched["channels"][0]["channel_id"])
        dealdesk.record_disposition(
            opportunity["opportunity_id"],
            actor="David",
            disposition="DO_NOT_CALL",
            note="Business requested no further contact",
        )

        later = {
            **self.record,
            "license_or_issue_date": "2026-08-25",
            "citation": {"url": "https://another.gov/new-signal/99", "label": "Later signal"},
        }
        observed = dealdesk.board([later])["opportunities"][0]

        self.assertNotEqual(observed["opportunity_id"], opportunity["opportunity_id"])
        self.assertEqual(observed["subject_id"], opportunity["subject_id"])
        self.assertEqual(observed["stage"], "BLOCKED")
        self.assertEqual(observed["contact_gate"], "DO_NOT_CONTACT_SUPPRESSED")
        with self.assertRaisesRegex(ValueError, "cannot be researched"):
            self._research(observed["opportunity_id"])
        with self.assertRaisesRegex(ValueError, "cannot be reopened"):
            dealdesk.update(observed["opportunity_id"], stage="RESEARCH")

    def test_do_not_call_alias_survives_when_later_source_omits_official_id(self):
        identified = {
            **self.record,
            "credential": "USDOT 1234567",
            "authoritative_entity_ids": [
                {"system": "USDOT", "value": "1234567"},
            ],
        }
        opportunity = dealdesk.board([identified])["opportunities"][0]
        researched = self._research(opportunity["opportunity_id"])
        self._clear(opportunity["opportunity_id"], researched["channels"][0]["channel_id"])
        dealdesk.record_disposition(
            opportunity["opportunity_id"],
            actor="David",
            disposition="DO_NOT_CALL",
        )

        later = {
            **self.record,
            "license_or_issue_date": "2026-08-25",
            "citation": {"url": "https://another.gov/new-signal/99"},
        }
        observed = dealdesk.board([later])["opportunities"][0]
        self.assertEqual(observed["contact_gate"], "DO_NOT_CONTACT_SUPPRESSED")
        self.assertFalse(observed["call_ready"])

    def test_authoritative_id_suppression_survives_a_legal_name_change(self):
        identified = {
            **self.record,
            "authoritative_entity_ids": [
                {"system": "USDOT", "value": "1234567"},
            ],
        }
        opportunity = dealdesk.board([identified])["opportunities"][0]
        researched = self._research(opportunity["opportunity_id"])
        self._clear(opportunity["opportunity_id"], researched["channels"][0]["channel_id"])
        dealdesk.record_disposition(
            opportunity["opportunity_id"],
            actor="David",
            disposition="DO_NOT_CALL",
        )

        renamed = {
            **identified,
            "name": "Renamed Carrier Holdings LLC",
            "license_or_issue_date": "2026-08-25",
            "citation": {"url": "https://another.gov/new-signal/99"},
        }
        observed = dealdesk.board([renamed])["opportunities"][0]
        self.assertEqual(observed["contact_gate"], "DO_NOT_CONTACT_SUPPRESSED")
        self.assertFalse(observed["call_ready"])

    def test_authoritative_and_scalar_ids_normalize_to_the_same_alias(self):
        emitted = {
            **self.record,
            "authoritative_entity_ids": [
                {"system": "USDOT", "value": "1234567"},
            ],
        }
        scalar = {
            **self.record,
            "name": "Different Legal Name LLC",
            "usdot_number": "1234567",
        }

        self.assertTrue(
            set(dealdesk.subject_ids(emitted)).intersection(
                dealdesk.subject_ids(scalar)
            )
        )

    def test_legacy_do_not_call_row_is_persistently_backfilled(self):
        identified = {
            **self.record,
            "authoritative_entity_ids": [
                {"system": "USDOT", "value": "1234567"},
            ],
        }
        oid = dealdesk.opportunity_id(identified)
        dealdesk._STATE[oid] = {
            "stage": "BLOCKED",
            "last_disposition": "DO_NOT_CALL",
            "updated_at": "2026-07-25T12:00:00+00:00",
        }

        direct = dealdesk._active_suppression(identified)
        self.assertIsNotNone(direct)
        self.assertTrue(direct["active"])

        with patch.object(dealdesk, "_persist") as persist:
            observed = dealdesk.enrich(identified)

        persist.assert_called_once()
        self.assertEqual(observed["contact_gate"], "DO_NOT_CONTACT_SUPPRESSED")
        self.assertEqual(observed["stage"], "BLOCKED")
        saved = dealdesk._STATE[oid]
        self.assertTrue(saved["suppression"]["active"])
        self.assertEqual(saved["suppression"]["type"], "DO_NOT_CALL")
        self.assertEqual(
            saved["subject_identity"]["authoritative_entity_ids"],
            [{"system": "usdot", "value": "1234567"}],
        )
        self.assertEqual(
            saved["history"][-1]["type"],
            "LEGACY_DO_NOT_CALL_BACKFILLED",
        )

        renamed = {
            **identified,
            "name": "Renamed Carrier Holdings LLC",
            "license_or_issue_date": "2026-08-25",
            "citation": {"url": "https://another.gov/new-signal/99"},
        }
        self.assertEqual(
            dealdesk.enrich(renamed)["contact_gate"],
            "DO_NOT_CONTACT_SUPPRESSED",
        )

    def test_legacy_unnamed_suppression_survives_when_official_id_appears(self):
        original = {
            **self.record,
            "name": "",
            "license_or_issue_date": "2026-07-25",
            "citation": {"url": "https://example.gov/entity/legacy-blank"},
        }
        original_id = dealdesk.opportunity_id(original)
        legacy_identity = {"name": "", "state": original["state"]}
        legacy_raw = json.dumps(
            legacy_identity,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        legacy_id = "subj_" + hashlib.sha256(legacy_raw).hexdigest()[:24]
        dealdesk._STATE[original_id] = {
            "stage": "BLOCKED",
            "last_disposition": "DO_NOT_CALL",
            "suppression": {
                "subject_id": legacy_id,
                "subject_ids": [legacy_id],
                "type": "DO_NOT_CALL",
                "active": True,
                "recorded_at": "2026-07-25T12:00:00Z",
                "actor": "David",
            },
        }
        identified = {
            **original,
            "authoritative_entity_ids": [
                {"system": "USDOT", "value": "1234567"},
            ],
        }

        observed = dealdesk.enrich(identified)

        self.assertEqual(observed["contact_gate"], "DO_NOT_CONTACT_SUPPRESSED")
        self.assertEqual(observed["stage"], "BLOCKED")
        self.assertIn(
            dealdesk.subject_id(identified),
            dealdesk._STATE[original_id]["suppression"]["subject_ids"],
        )

    def test_unnamed_records_do_not_share_a_state_only_suppression_identity(self):
        first = {
            **self.record,
            "name": "",
            "opportunity_id": "opp_untrusted_shared_value",
            "license_or_issue_date": "2026-07-25",
            "citation": {"url": "https://example.gov/entity/blank-1"},
        }
        second = {
            **self.record,
            "name": "",
            "opportunity_id": "opp_untrusted_shared_value",
            "license_or_issue_date": "2026-07-26",
            "citation": {"url": "https://example.gov/entity/blank-2"},
        }
        opportunities = {
            item["opportunity_id"]: item
            for item in dealdesk.board([first, second])["opportunities"]
        }
        first_opportunity = opportunities[dealdesk.opportunity_id(first)]
        second_opportunity = opportunities[dealdesk.opportunity_id(second)]
        self.assertNotEqual(
            first_opportunity["opportunity_id"],
            second_opportunity["opportunity_id"],
        )
        self.assertNotEqual(
            first_opportunity["subject_id"],
            second_opportunity["subject_id"],
        )

        researched = self._research(first_opportunity["opportunity_id"])
        self._clear(
            first_opportunity["opportunity_id"],
            researched["channels"][0]["channel_id"],
        )
        dealdesk.record_disposition(
            first_opportunity["opportunity_id"],
            actor="David",
            disposition="DO_NOT_CALL",
        )

        observed_second = dealdesk.enrich(second)
        self.assertEqual(observed_second["contact_gate"], "RESEARCH_REQUIRED")
        self.assertEqual(observed_second["stage"], "REVIEW")

    def test_legacy_unnamed_suppression_survives_only_for_the_same_opportunity(self):
        original = {
            **self.record,
            "name": "",
            "license_or_issue_date": "2026-07-25",
            "citation": {"url": "https://example.gov/entity/legacy-blank"},
        }
        original_id = dealdesk.opportunity_id(original)
        legacy_identity = {
            "name": "",
            "state": original["state"],
        }
        legacy_raw = json.dumps(
            legacy_identity,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        legacy_id = "subj_" + hashlib.sha256(legacy_raw).hexdigest()[:24]
        dealdesk._STATE[original_id] = {
            "stage": "BLOCKED",
            "next_action": "Suppressed: do not contact",
            "suppression": {
                "subject_id": legacy_id,
                "subject_ids": [legacy_id],
                "type": "DO_NOT_CALL",
                "active": True,
                "recorded_at": "2026-07-25T12:00:00Z",
                "actor": "David",
            },
        }

        observed_original = dealdesk.enrich(original)
        self.assertEqual(
            observed_original["contact_gate"],
            "DO_NOT_CONTACT_SUPPRESSED",
        )
        self.assertEqual(observed_original["stage"], "BLOCKED")
        with self.assertRaisesRegex(ValueError, "cannot be reopened"):
            dealdesk.update(original_id, stage="RESEARCH")

        unrelated = {
            **original,
            "license_or_issue_date": "2026-07-26",
            "citation": {"url": "https://example.gov/entity/other-blank"},
        }
        observed_unrelated = dealdesk.enrich(unrelated)
        self.assertEqual(observed_unrelated["contact_gate"], "RESEARCH_REQUIRED")
        self.assertEqual(observed_unrelated["stage"], "REVIEW")

    def test_non_unique_credential_category_is_not_an_official_alias(self):
        first = {
            **self.record,
            "name": "First Connecticut Brokerage LLC",
            "state": "CT",
            "credential": "Real Estate Broker",
        }
        second = {
            **self.record,
            "name": "Second Connecticut Brokerage LLC",
            "state": "CT",
            "credential": "Real Estate Broker",
        }

        self.assertTrue(
            set(dealdesk.subject_ids(first)).isdisjoint(
                dealdesk.subject_ids(second)
            )
        )

    def test_persisted_legacy_do_not_call_is_backfilled_and_enforced(self):
        legacy = {
            "last_disposition": "DO_NOT_CALL",
            "stage": "BLOCKED",
        }
        legacy_oid = dealdesk.opportunity_id(self.record)
        dealdesk._STATE[legacy_oid] = legacy
        self.assertFalse(dealdesk._backfill_legacy_suppressions(dealdesk._STATE))
        self.assertNotIn("suppression", legacy)

        with patch.object(dealdesk, "_persist") as persist:
            current = dealdesk.enrich(self.record)

        saved = dealdesk._STATE[legacy_oid]
        self.assertTrue(saved["suppression"]["active"])
        self.assertEqual(
            saved["suppression"]["subject_ids"],
            list(dealdesk.subject_ids(self.record)),
        )
        self.assertEqual(saved["subject_identity"]["name"], self.record["name"])
        self.assertEqual(current["contact_gate"], "DO_NOT_CONTACT_SUPPRESSED")
        persist.assert_called_once()

        later = {
            **self.record,
            "license_or_issue_date": "2026-08-25",
            "citation": {"url": "https://another.gov/new-signal/99"},
        }
        self.assertIsNotNone(dealdesk._active_suppression(later))

    def test_not_interested_revokes_clearance(self):
        opportunity = dealdesk.board([self.record])["opportunities"][0]
        researched = self._research(opportunity["opportunity_id"])
        self._clear(opportunity["opportunity_id"], researched["channels"][0]["channel_id"])

        lost = dealdesk.record_disposition(
            opportunity["opportunity_id"],
            actor="David",
            disposition="NOT_INTERESTED",
            note="Declined",
        )

        self.assertEqual(lost["stage"], "LOST")
        self.assertFalse(lost["call_ready"])
        self.assertIsNotNone(
            dealdesk._STATE[opportunity["opportunity_id"]]["clearance"]["revoked_at"]
        )

    def test_call_clearance_requires_a_business_phone(self):
        opportunity = dealdesk.board([self.record])["opportunities"][0]
        researched = dealdesk.record_research(
            opportunity["opportunity_id"],
            actor="David",
            channel_type="BUSINESS_EMAIL",
            channel_value="sales@examplelogistics.com",
            source_url="https://examplelogistics.com/contact",
            publisher_class="FIRST_PARTY_BUSINESS_WEBSITE",
        )
        with self.assertRaisesRegex(ValueError, "business phone"):
            self._clear(
                opportunity["opportunity_id"],
                researched["channels"][0]["channel_id"],
            )
        observed = dealdesk.enrich(self.record)
        self.assertEqual(observed["stage"], "RESEARCH")
        self.assertFalse(observed["call_ready"])
        self.assertIsNone(observed["clearance"])

    def test_persisted_non_phone_clearance_never_advertises_call_ready(self):
        opportunity = dealdesk.board([self.record])["opportunities"][0]
        oid = opportunity["opportunity_id"]
        dealdesk._STATE[oid] = {
            "stage": "READY",
            "channels": [
                {
                    "channel_id": "chn_legacy_email",
                    "type": "BUSINESS_EMAIL",
                    "value": "sales@examplelogistics.com",
                }
            ],
            "clearance": {
                "channel_id": "chn_legacy_email",
                "clearance_receipt": "clr_legacy_email",
                "actor": "David",
                "expires_at": "2099-01-01T00:00:00+00:00",
                "federal_dnc_checked": True,
                "state_dnc_checked": True,
                "opt_out_checked": True,
                "rules_reviewed": True,
            },
        }

        observed = dealdesk.enrich(self.record)

        self.assertFalse(observed["call_ready"])
        self.assertEqual(observed["stage"], "RESEARCH")
        self.assertEqual(
            observed["contact_gate"],
            "CLEARANCE_EXPIRED_OR_REVOKED",
        )
        self.assertIsNone(observed["clearance"])
        with self.assertRaisesRegex(
            ValueError,
            "call sheet is locked",
        ):
            dealdesk.call_sheet(oid)


class PersistenceContractSafety(unittest.TestCase):
    def setUp(self):
        self.original_database_url = dealdesk._DATABASE_URL
        self.original_health = dealdesk._PERSISTENCE_HEALTH
        self.original_probe = dealdesk._LAST_PROBE_AT
        dealdesk.reset_for_tests()

    def tearDown(self):
        dealdesk._DATABASE_URL = self.original_database_url
        dealdesk._PERSISTENCE_HEALTH = self.original_health
        dealdesk._LAST_PROBE_AT = self.original_probe
        dealdesk.reset_for_tests()

    def test_unidentified_legacy_do_not_call_blocks_persistence_readiness(self):
        unresolved = {
            "opp_legacy": {
                "last_disposition": "DO_NOT_CALL",
                "stage": "BLOCKED",
                "suppression": {
                    "subject_id": "subj_legacy_unscoped",
                    "subject_ids": ["subj_legacy_unscoped"],
                    "active": True,
                },
            },
        }
        with self.assertRaises(dealdesk._LegacySuppressionIdentityRequired):
            dealdesk._assert_no_unresolved_legacy_suppressions(unresolved)

        dealdesk._DATABASE_URL = "postgresql://configured"
        with (
            patch.object(dealdesk, "_database_snapshot", return_value=unresolved),
            patch.object(dealdesk.time, "sleep"),
        ):
            dealdesk._load()
            self.assertFalse(dealdesk.persistence_ready())

        self.assertEqual(dealdesk._PERSISTENCE_HEALTH, "POSTGRES_UNAVAILABLE")
        self.assertEqual(
            dealdesk._PERSISTENCE_DIAGNOSTIC,
            "LEGACY_DNC_IDENTITY_REQUIRED",
        )

    def test_checked_in_schema_migration_is_versioned_and_complete(self):
        schema = (ROOT / "app" / "dealdesk_schema.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS david_dealdesk_schema", schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS david_dealdesk_state", schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS david_dealdesk_events", schema)
        self.assertIn("VALUES ('dealdesk', 2)", schema)
        self.assertIn("ADD CONSTRAINT david_dealdesk_state_version_check", schema)
        self.assertIn("VALIDATE CONSTRAINT david_dealdesk_state_version_check", schema)
        self.assertEqual(dealdesk._SCHEMA_VERSION, 2)
        self.assertLess(
            schema.index("DROP CONSTRAINT IF EXISTS david_dealdesk_state_version_check"),
            schema.index("ADD CONSTRAINT david_dealdesk_state_version_check"),
        )
        self.assertLess(
            schema.index("VALIDATE CONSTRAINT david_dealdesk_state_version_check"),
            schema.index("VALUES ('dealdesk', 2)"),
        )
        migrate = (
            ROOT / ".github" / "workflows" / "migrate-neon-persistence.yml"
        ).read_text(encoding="utf-8")
        verify = (
            ROOT / ".github" / "workflows" / "verify-neon-persistence.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("cursor.fetchone() != (2,)", migrate)
        self.assertIn("cursor.fetchone() != (2,)", verify)
        source = (ROOT / "app" / "dealdesk.py").read_text(encoding="utf-8")
        self.assertNotIn("CREATE TABLE", source)
        self.assertNotIn("CREATE INDEX", source)

    @staticmethod
    def _compatible_schema_results():
        columns = [
            (table, column, data_type, nullable)
            for (table, column), (data_type, nullable) in sorted(
                dealdesk._SCHEMA_COLUMNS.items()
            )
        ]
        primary_keys = [
            (table, column, position)
            for table, keys in sorted(dealdesk._SCHEMA_PRIMARY_KEYS.items())
            for position, column in enumerate(keys, start=1)
        ]
        constraints = sorted(dealdesk._SCHEMA_CONSTRAINTS)
        return [
            columns,
            primary_keys,
            constraints,
            [dealdesk._SCHEMA_EVENTS_INDEX],
        ]

    def test_database_schema_validation_is_complete_and_fail_closed(self):
        connection = mock.MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (dealdesk._SCHEMA_VERSION,)
        cursor.fetchall.side_effect = self._compatible_schema_results()

        dealdesk._assert_schema_contract(cursor)
        primary_key_query = cursor.execute.call_args_list[2].args[0]
        self.assertIn("pg_catalog.pg_index", primary_key_query)
        self.assertIn("index_meta.indisprimary", primary_key_query)
        self.assertNotIn("information_schema.table_constraints", primary_key_query)

        incomplete = self._compatible_schema_results()
        incomplete[0] = [
            row for row in incomplete[0]
            if row[0] != "david_dealdesk_events"
        ]
        incomplete_cursor = mock.MagicMock()
        incomplete_cursor.fetchone.return_value = (dealdesk._SCHEMA_VERSION,)
        incomplete_cursor.fetchall.side_effect = incomplete
        with self.assertRaises(dealdesk._DatabaseSchemaUnavailable):
            dealdesk._assert_schema_contract(incomplete_cursor)

        incompatible = self._compatible_schema_results()
        incompatible[0] = [
            (
                table,
                column,
                "int4" if column == "version" else data_type,
                nullable,
            )
            for table, column, data_type, nullable in incompatible[0]
        ]
        incompatible_cursor = mock.MagicMock()
        incompatible_cursor.fetchone.return_value = (dealdesk._SCHEMA_VERSION,)
        incompatible_cursor.fetchall.side_effect = incompatible
        with self.assertRaises(dealdesk._DatabaseSchemaIncompatible):
            dealdesk._assert_schema_contract(incompatible_cursor)

        unexpected_constraint = self._compatible_schema_results()
        unexpected_constraint[2] = [
            *unexpected_constraint[2],
            (
                "david_dealdesk_state",
                "u",
                "UNIQUE (updated_at)",
            ),
        ]
        constraint_cursor = mock.MagicMock()
        constraint_cursor.fetchone.return_value = (dealdesk._SCHEMA_VERSION,)
        constraint_cursor.fetchall.side_effect = unexpected_constraint
        with self.assertRaises(dealdesk._DatabaseSchemaIncompatible):
            dealdesk._assert_schema_contract(constraint_cursor)

        predecessor_contract = self._compatible_schema_results()
        predecessor_contract[2] = [
            constraint
            for constraint in predecessor_contract[2]
            if constraint != (
                "david_dealdesk_state",
                "c",
                "CHECK (version > 0)",
            )
        ]
        predecessor_cursor = mock.MagicMock()
        predecessor_cursor.fetchone.return_value = (dealdesk._SCHEMA_VERSION,)
        predecessor_cursor.fetchall.side_effect = predecessor_contract
        with self.assertRaises(dealdesk._DatabaseSchemaIncompatible):
            dealdesk._assert_schema_contract(predecessor_cursor)

    def test_ready_probe_periodically_revalidates_schema_drift(self):
        dealdesk._DATABASE_URL = "postgresql://configured"
        dealdesk._PERSISTENCE_HEALTH = "POSTGRES_READY"
        dealdesk._PERSISTENCE_DIAGNOSTIC = "OK"
        dealdesk._LAST_PROBE_AT = 0.0
        connection = mock.MagicMock()
        connection.__enter__.return_value = connection
        incompatible = dealdesk._DatabaseSchemaIncompatible(
            "unexpected foreign key"
        )

        with (
            patch.object(dealdesk, "_db_connect", return_value=connection),
            patch.object(
                dealdesk,
                "_assert_schema_contract",
                side_effect=incompatible,
            ) as validate,
        ):
            observed = dealdesk.persistence_state()

        self.assertEqual(observed, "POSTGRES_UNAVAILABLE")
        self.assertEqual(
            dealdesk._PERSISTENCE_DIAGNOSTIC,
            "SCHEMA_INCOMPATIBLE",
        )
        validate.assert_called_once()

    def test_database_load_persists_legacy_suppression_backfill(self):
        dealdesk._DATABASE_URL = "postgresql://configured"
        legacy = {
            "opp_legacy": {
                "subject_identity": {
                    "name": "Example Logistics LLC",
                    "state": "NY",
                },
                "last_disposition": "DO_NOT_CALL",
                "stage": "BLOCKED",
            }
        }

        with (
            patch.object(dealdesk, "_database_snapshot", return_value=legacy),
            patch.object(dealdesk, "_persist") as persist,
        ):
            dealdesk._load()

        persist.assert_called_once_with(dealdesk._STATE)
        self.assertTrue(
            dealdesk._STATE["opp_legacy"]["suppression"]["active"]
        )

    def test_transient_startup_failure_recovers_and_reloads_state(self):
        dealdesk._DATABASE_URL = "postgresql://configured"
        dealdesk._PERSISTENCE_HEALTH = "POSTGRES_UNAVAILABLE"
        dealdesk._LAST_PROBE_AT = 0.0
        recovered = {"opp_recovered": {"stage": "RESEARCH"}}

        with patch.object(dealdesk, "_database_snapshot", return_value=recovered) as load:
            observed = dealdesk.persistence_state()

        self.assertEqual(observed, "POSTGRES_READY")
        self.assertEqual(dealdesk._STATE, recovered)
        load.assert_called_once_with()

    def test_live_probe_downgrades_stale_ready_state(self):
        dealdesk._DATABASE_URL = "postgresql://configured"
        dealdesk._PERSISTENCE_HEALTH = "POSTGRES_READY"
        dealdesk._LAST_PROBE_AT = 0.0

        with patch.object(
            dealdesk,
            "_db_connect",
            side_effect=RuntimeError("private database endpoint"),
        ):
            observed = dealdesk.persistence_state()

        self.assertEqual(observed, "POSTGRES_UNAVAILABLE")

    def test_failed_transaction_is_sanitized_and_does_not_commit_memory(self):
        dealdesk._DATABASE_URL = "postgresql://configured"
        dealdesk._PERSISTENCE_HEALTH = "POSTGRES_READY"
        dealdesk._STATE["opp_existing"] = {"stage": "REVIEW"}

        connection = mock.MagicMock()
        connection.__enter__.return_value = connection
        cursor = mock.MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor

        def fail_event(statement, *_args):
            if "INSERT INTO david_dealdesk_events" in statement:
                raise RuntimeError("private database endpoint")

        cursor.execute.side_effect = fail_event
        candidate = {"stage": "RESEARCH"}
        event = {
            "at": "2026-07-28T00:00:00+00:00",
            "opportunity_id": "opp_new",
            "type": "BUSINESS_CHANNEL_RECORDED",
            "actor": "David",
        }

        with (
            patch.object(dealdesk, "_db_connect", return_value=connection),
            patch.object(dealdesk, "_assert_schema_contract"),
            self.assertRaisesRegex(
                dealdesk.PersistenceUnavailable,
                "^deal-desk persistence is unavailable$",
            ),
        ):
            dealdesk._commit("opp_new", candidate, event)

        self.assertEqual(dealdesk._STATE, {"opp_existing": {"stage": "REVIEW"}})
        self.assertEqual(dealdesk._PERSISTENCE_HEALTH, "POSTGRES_UNAVAILABLE")
        connection.__exit__.assert_called_once()


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

    def test_login_accepts_utf8_secret_factors_without_server_error(self):
        with (
            patch.object(self.server, "_CREDS_ROTATION_REQUIRED", False),
            patch.object(self.server, "_CREDS_CONFIGURED", True),
            patch.object(self.server, "USERS", {"operador-ñ": "frase-🔒"}),
            patch.object(self.server, "ACCESS_KEY", "llave-🗝️"),
        ):
            response = self.client.post(
                "/api/login",
                json={
                    "username": "operador-ñ",
                    "password": "frase-🔒",
                    "access_key": "llave-🗝️",
                },
            )
            self.assertEqual(response.status_code, 200)
            token = response.json()["token"]
            logout = self.client.post(
                "/api/logout",
                headers={"Authorization": "Bearer " + token},
            )
            self.assertEqual(logout.status_code, 200)

    def test_login_rejects_wrong_utf8_secret_with_401_not_500(self):
        with (
            patch.object(self.server, "_CREDS_ROTATION_REQUIRED", False),
            patch.object(self.server, "_CREDS_CONFIGURED", True),
            patch.object(self.server, "USERS", {"operador-ñ": "frase-🔒"}),
            patch.object(self.server, "ACCESS_KEY", "llave-🗝️"),
        ):
            response = self.client.post(
                "/api/login",
                json={
                    "username": "operador-ñ",
                    "password": "frase-incorrecta-🔒",
                    "access_key": "llave-🗝️",
                },
            )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Invalid credentials or access key")

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

    def test_webhook_validation_deduplicates_validated_addresses(self):
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

    def test_webhook_address_failover_shares_one_total_timeout(self):
        parsed = self.server.urllib.parse.urlparse("https://crm.example.com/import")
        failed = mock.Mock()
        failed.connect.side_effect = TimeoutError("first address timed out")

        with (
            patch.object(
                self.server,
                "_PinnedHTTPSConnection",
                return_value=failed,
            ) as connection_type,
            patch.object(
                self.server.time,
                "monotonic",
                side_effect=[100.0, 100.0, 108.1],
            ),
        ):
            with self.assertRaisesRegex(TimeoutError, "first address timed out"):
                self.server._post_validated_webhook(
                    parsed,
                    "crm.example.com",
                    ("2001:4860:4860::8888", "93.184.216.34"),
                    b"{}",
                )

        connection_type.assert_called_once()

    def test_health_and_readiness_fail_closed_for_auth_and_persistence(self):
        with (
            patch.object(self.server, "_CREDS_CONFIGURED", False),
            patch.object(self.server, "_CREDS_ROTATION_REQUIRED", True),
            patch.object(self.server.dd, "persistence_state", return_value="FILE_READY"),
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
        self.assertFalse(body["receipt_minted"])

    def test_build_info_accepts_only_exact_revision_github_oidc_receipt(self):
        revision = "a" * 40
        attestation_id = "123456"
        receipt = json.dumps({
            "schema": "szl.github-oidc-release-attestation/v1",
            "source_revision": revision,
            "manifest_sha256": "b" * 64,
            "attestation_id": attestation_id,
            "attestation_url": (
                "https://github.com/szl-holdings/david-leads/attestations/"
                + attestation_id
            ),
        })
        with patch.dict(
            os.environ,
            {
                "SOURCE_GITHUB_SHA": revision,
                "RELEASE_ATTESTATION": receipt,
            },
        ):
            body = self.server._runtime_bundle_manifest()
        self.assertTrue(body["receipt_minted"])
        self.assertEqual(body["release_receipt"]["state"], "GITHUB_OIDC_ATTESTED")
        self.assertEqual(body["release_receipt"]["subject_sha256"], "b" * 64)

        stale = json.loads(receipt)
        stale["source_revision"] = "c" * 40
        with patch.dict(
            os.environ,
            {
                "SOURCE_GITHUB_SHA": revision,
                "RELEASE_ATTESTATION": json.dumps(stale),
            },
        ):
            body = self.server._runtime_bundle_manifest()
        self.assertFalse(body["receipt_minted"])
        self.assertEqual(body["release_receipt"]["state"], "UNAVAILABLE")

    def test_conformance_routes_expose_exact_sha_and_honest_partial_evidence(self):
        revision = "d" * 40
        with patch.dict(
            os.environ,
            {
                "SOURCE_GITHUB_SHA": revision.upper(),
                "GITHUB_SHA": "",
                "HF_SPACE_COMMIT_SHA": "",
                "RELEASE_ATTESTATION": "",
            },
        ):
            version = self.client.get("/version")
            evidence = self.client.get("/evidence")

        self.assertEqual(version.status_code, 200)
        self.assertEqual(
            version.json(),
            {
                "schemaVersion": "szl.vertical-conformance.version.v1",
                "service": "david-leads",
                "surface": "insurance",
                "gitSha": revision,
            },
        )
        self.assertEqual(evidence.status_code, 200)
        body = evidence.json()
        self.assertEqual(
            body["schemaVersion"],
            "szl.vertical-conformance.evidence.v1",
        )
        self.assertEqual(body["surface"], "insurance")
        self.assertEqual(body["evidenceState"], "PARTIAL")
        self.assertEqual(body["gitSha"], revision)
        self.assertEqual(body["receipts"], [])
        self.assertEqual(body["releaseReceipt"]["state"], "UNAVAILABLE")
        self.assertIsInstance(body["applicationReceiptCount"], int)
        self.assertIn(
            "No portable cross-repository root-to-target DSSE receipt pair",
            body["limitations"][0],
        )
        self.assertIn("no-store", version.headers["cache-control"])
        self.assertIn("no-store", evidence.headers["cache-control"])

    def test_conformance_routes_fail_closed_without_exact_sha(self):
        invalid = "not-a-sha SECRET_VALUE"
        with patch.dict(
            os.environ,
            {
                "SOURCE_GITHUB_SHA": invalid,
                "GITHUB_SHA": "a" * 39,
                "HF_SPACE_COMMIT_SHA": "g" * 40,
            },
        ):
            version = self.client.get("/version")
            evidence = self.client.get("/evidence")

        self.assertEqual(version.status_code, 503)
        self.assertEqual(version.json()["state"], "UNAVAILABLE")
        self.assertEqual(evidence.status_code, 503)
        self.assertEqual(evidence.json()["state"], "UNAVAILABLE")
        self.assertNotIn(invalid, version.text)
        self.assertNotIn(invalid, evidence.text)
        self.assertNotIn("SECRET_VALUE", version.text)
        self.assertNotIn("SECRET_VALUE", evidence.text)

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
