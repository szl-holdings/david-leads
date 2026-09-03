# SPDX-License-Identifier: Apache-2.0
"""Keep privileged Neon migration execution bound to schema changes only."""
from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "migrate-neon-persistence.yml"


def _workflow() -> dict:
    value = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML 1.1 may parse the key `on` as boolean True.
    trigger = value.get("on", value.get(True))
    assert isinstance(trigger, dict)
    value["__trigger__"] = trigger
    return value


def test_automatic_migration_is_schema_only() -> None:
    value = _workflow()
    push = value["__trigger__"]["push"]
    assert push["branches"] == ["main"]
    assert push["paths"] == ["app/dealdesk_schema.sql"]


def test_explicit_governed_entrypoints_remain_available() -> None:
    value = _workflow()
    trigger = value["__trigger__"]
    assert "workflow_dispatch" in trigger
    assert "workflow_call" in trigger


def test_privileged_environment_and_schema_subject_remain_bound() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "name: david-space-credential-rotation" in text
    assert 'Path("app/dealdesk_schema.sql")' in text
    assert "DAVID_DATABASE_ADMIN_URL" in text
    assert "DAVID_DATABASE_URL" in text


def test_unrelated_application_and_document_paths_cannot_trigger_migration() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    trigger_prefix = text.split("  workflow_call: {}", 1)[0]
    for prohibited in (
        '"app/**"',
        '"app/static/**"',
        '"requirements.txt"',
        '"Dockerfile"',
        '"README.md"',
        '"PUBLICATION_READINESS.md"',
        '"PUBLIC_DATA_OPERATING_MODEL.md"',
        '"THIRD_PARTY_NOTICES.md"',
        '"SPACE_PROVENANCE.json"',
        '"research/COMPETITIVE_SYNTHESIS_2026-08-26.md"',
        '"ops/credential-rotation.md"',
        '".github/workflows/hf-deploy.yml"',
        '".github/workflows/migrate-neon-persistence.yml"',
    ):
        assert prohibited not in trigger_prefix
