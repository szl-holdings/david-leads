from __future__ import annotations

import re
import unittest
from pathlib import Path


WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "federal-refresh.yml"


class FederalRefreshWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_non_cancelling_serial_concurrency(self) -> None:
        self.assertIn("group: federal-refresh", self.workflow)
        self.assertIn("cancel-in-progress: false", self.workflow)

    def test_all_actions_are_immutable_pins(self) -> None:
        uses = re.findall(r"uses:\s+([^\s#]+)", self.workflow)
        self.assertEqual(len(uses), 5)
        for action in uses:
            self.assertRegex(action, r"^[^@]+@[0-9a-f]{40}$")
        self.assertIn(
            "step-security/harden-runner@05e31511f85b41b11d1cf0ef85d0992719546e2c",
            uses,
        )
        self.assertIn(
            "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
            uses,
        )
        self.assertIn(
            "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
            uses,
        )
        self.assertIn(
            "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
            uses,
        )
        self.assertIn(
            "actions/attest@36051bcae73b7c2a8a6945a48cbf80953c6baa35",
            uses,
        )

    def test_exact_snapshot_manifest_gets_oidc_attestation(self) -> None:
        self.assertIn("id-token: write", self.workflow)
        self.assertIn("attestations: write", self.workflow)
        self.assertIn("subject-path: snapshot/snapshot.json", self.workflow)
        self.assertIn(
            "${{ steps.attest_snapshot.outputs.bundle-path }}", self.workflow
        )

    def test_download_is_fail_closed_and_source_is_bound(self) -> None:
        for contract in (
            "--fail",
            "--proto '=https'",
            "--proto-redir '=https'",
            "--tlsv1.2",
            "--retry-all-errors",
            "--dump-header evidence/download-headers.txt",
            "test -s echo_exporter.zip",
            "sha256sum echo_exporter.zip",
            '--source-revision "$GITHUB_SHA"',
        ):
            self.assertIn(contract, self.workflow)

    def test_local_verification_precedes_publisher(self) -> None:
        verify_at = self.workflow.index(
            "python -m tools.ingestor.verify_snapshot snapshot"
        )
        publish_at = self.workflow.index(
            "python -m tools.ingestor.publish_snapshot"
        )
        self.assertLess(verify_at, publish_at)
        self.assertIn("Verify standalone receipt integrity", self.workflow)
        self.assertNotIn("Verify receipt hash-chain", self.workflow)

    def test_publisher_is_pinned_and_token_is_step_scoped(self) -> None:
        self.assertIn("huggingface_hub==1.19.0", self.workflow)
        self.assertIn("--dataset SZLHOLDINGS/david-leads-data", self.workflow)
        self.assertIn("--receipt-out publication.json", self.workflow)
        self.assertEqual(self.workflow.count("secrets.HF_TOKEN"), 1)
        self.assertNotRegex(self.workflow, r"(?m)^env:")

    def test_always_uploads_only_bounded_evidence_for_90_days(self) -> None:
        upload = self.workflow[self.workflow.index("- name: Upload bounded refresh evidence") :]
        self.assertIn("if: ${{ always() }}", upload)
        self.assertIn("retention-days: 90", upload)
        self.assertIn("snapshot/snapshot.json", upload)
        self.assertIn("snapshot/receipt.json", upload)
        self.assertIn("publication.json", upload)
        self.assertIn('evidence / "run-status.json"', self.workflow)
        self.assertIn("evidence/verification.txt", self.workflow)
        self.assertIn("evidence/attestation.json", self.workflow)
        self.assertIn("if-no-files-found: error", upload)
        self.assertNotIn("echo_exporter.zip", upload)
        self.assertNotIn("snapshot/records.jsonl", upload)


if __name__ == "__main__":
    unittest.main()
