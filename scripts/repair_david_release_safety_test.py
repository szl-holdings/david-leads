#!/usr/bin/env python3
"""Repair stale David deployment assertions after release-orchestrator redesign."""
from __future__ import annotations

from pathlib import Path


PATH = Path(__file__).resolve().parents[1] / "tests" / "test_operational_safety.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one legacy block, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''        self.assertIn(
            "github.event.workflow_run.conclusion == 'success'",
            deploy_workflow,
        )
        self.assertIn(
            "github.event.workflow_run.event == 'push'",
            deploy_workflow,
        )
        self.assertIn(
            "github.event.workflow_run.head_branch == 'main'",
            deploy_workflow,
        )
        self.assertIn(
            "github.event.workflow_run.head_sha == github.sha",
            deploy_workflow,
        )
        self.assertIn(
            "ref: ${{ github.event.workflow_run.head_sha }}",
            deploy_workflow,
        )
        self.assertNotIn("workflow_dispatch", deploy_workflow)
''',
        '''        self.assertIn(
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
''',
        "workflow-run admission assertions",
    )
    PATH.write_text(text, encoding="utf-8")
    print("Updated David operational release-safety assertions")


if __name__ == "__main__":
    main()
