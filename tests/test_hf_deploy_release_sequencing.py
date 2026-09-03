# SPDX-License-Identifier: Apache-2.0
"""Prove David releases deploy every payload while schema changes migrate first."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / ".github" / "workflows" / "hf-deploy.yml"
MIGRATE = ROOT / ".github" / "workflows" / "migrate-neon-persistence.yml"
DOCKERFILE = ROOT / "Dockerfile"


class DavidReleaseSequencingTests(unittest.TestCase):
    def test_deploy_trigger_covers_every_docker_payload_input(self) -> None:
        deploy = DEPLOY.read_text(encoding="utf-8")
        dockerfile = DOCKERFILE.read_text(encoding="utf-8")
        required = (
            "Dockerfile",
            "requirements.txt",
            "app/**",
            "PUBLICATION_READINESS.md",
            "PUBLIC_DATA_OPERATING_MODEL.md",
            "SPACE_PROVENANCE.json",
            "THIRD_PARTY_NOTICES.md",
            "research/COMPETITIVE_SYNTHESIS_2026-08-26.md",
            "ops/credential-rotation.md",
            ".github/workflows/hf-deploy.yml",
            ".github/workflows/migrate-neon-persistence.yml",
        )
        for relative_path in required:
            with self.subTest(relative_path=relative_path):
                self.assertIn(f'      - "{relative_path}"', deploy)
        for copied in (
            "requirements.txt",
            "app",
            "PUBLICATION_READINESS.md",
            "PUBLIC_DATA_OPERATING_MODEL.md",
            "SPACE_PROVENANCE.json",
            "THIRD_PARTY_NOTICES.md",
            "research/COMPETITIVE_SYNTHESIS_2026-08-26.md",
            "ops/credential-rotation.md",
        ):
            self.assertIn(copied, dockerfile)

    def test_schema_push_waits_for_exact_successful_migration(self) -> None:
        deploy = DEPLOY.read_text(encoding="utf-8")
        self.assertIn('workflows: ["Migrate David Neon persistence"]', deploy)
        self.assertIn("WAIT_FOR_SCHEMA_MIGRATION", deploy)
        self.assertIn("SCHEMA_MIGRATION_SUCCEEDED", deploy)
        self.assertIn("STALE_MIGRATION_RESULT", deploy)
        self.assertIn("git ls-remote origin refs/heads/main", deploy)
        self.assertIn("grep -Fxq 'app/dealdesk_schema.sql'", deploy)
        self.assertIn("needs.classify.outputs.source_sha", deploy)

    def test_privileged_migration_remains_automatic_for_schema_only(self) -> None:
        migration = MIGRATE.read_text(encoding="utf-8")
        automatic = migration.split("  workflow_call: {}", 1)[0]
        self.assertIn('      - "app/dealdesk_schema.sql"', automatic)
        for prohibited in (
            '"app/**"',
            '"requirements.txt"',
            '"Dockerfile"',
            '"THIRD_PARTY_NOTICES.md"',
            '"research/COMPETITIVE_SYNTHESIS_2026-08-26.md"',
            '"ops/credential-rotation.md"',
        ):
            self.assertNotIn(prohibited, automatic)
        self.assertIn("name: david-space-credential-rotation", migration)
        self.assertIn("DAVID_DATABASE_ADMIN_URL", migration)
        self.assertIn('Path("app/dealdesk_schema.sql")', migration)


if __name__ == "__main__":
    unittest.main()
