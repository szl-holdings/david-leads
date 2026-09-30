# SPDX-License-Identifier: Apache-2.0
"""Keep the GitHub Actions control plane immutable and least-privileged."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
PIN = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
USES = re.compile(r"uses:\s+([^\s#]+)")


def _workflow_texts() -> dict[str, str]:
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(WORKFLOWS.glob("*.yml"))
    }


def test_every_action_and_reusable_workflow_is_immutably_pinned() -> None:
    observed = 0
    for name, text in _workflow_texts().items():
        for action in USES.findall(text):
            observed += 1
            assert PIN.fullmatch(action), f"{name}: mutable action reference {action!r}"
    assert observed > 0


def test_retired_self_mutating_workflow_does_not_return() -> None:
    assert not (WORKFLOWS / "zz-fix-release-sequencing-test-once.yml").exists()
    for name, text in _workflow_texts().items():
        assert "persist-credentials: true" not in text, name
        assert "contents: write" not in text, name


def test_deprecated_node20_action_pins_do_not_return() -> None:
    retired = {
        "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683",
        "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065",
        "actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020",
        "actions/download-artifact@37930b1c2abaa49bbe596cd826c3c89aef350131",
    }
    corpus = "\n".join(_workflow_texts().values())
    for action in retired:
        assert action not in corpus
