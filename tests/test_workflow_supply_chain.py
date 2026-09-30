# SPDX-License-Identifier: Apache-2.0
"""Keep the GitHub Actions control plane immutable and least-privileged."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterator

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
PIN = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


def _workflow_paths() -> list[Path]:
    return sorted({*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")})


def _workflow_documents() -> dict[str, Any]:
    return {
        path.name: yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in _workflow_paths()
    }


def _mappings(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _mappings(child)


def _action_references() -> Iterator[tuple[str, str]]:
    for name, document in _workflow_documents().items():
        for mapping in _mappings(document):
            if "uses" in mapping:
                yield name, mapping["uses"]


def test_every_action_and_reusable_workflow_is_immutably_pinned() -> None:
    observed = 0
    for name, action in _action_references():
        observed += 1
        assert isinstance(action, str), f"{name}: non-string action reference {action!r}"
        assert PIN.fullmatch(action), f"{name}: mutable action reference {action!r}"
    assert observed > 0


def test_retired_self_mutating_workflow_does_not_return() -> None:
    assert not (WORKFLOWS / "zz-fix-release-sequencing-test-once.yml").exists()
    assert not (WORKFLOWS / "zz-fix-release-sequencing-test-once.yaml").exists()
    for name, document in _workflow_documents().items():
        for mapping in _mappings(document):
            permissions = mapping.get("permissions")
            assert permissions != "write-all", name
            if isinstance(permissions, dict):
                assert permissions.get("contents") != "write", name

            if "persist-credentials" in mapping:
                persist_credentials = mapping["persist-credentials"]
                assert persist_credentials not in (True, "true", "True"), name


def test_deprecated_node20_action_pins_do_not_return() -> None:
    retired = {
        "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683",
        "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065",
        "actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020",
        "actions/download-artifact@37930b1c2abaa49bbe596cd826c3c89aef350131",
    }
    observed = {action for _, action in _action_references()}
    assert retired.isdisjoint(observed)
