# SPDX-License-Identifier: Apache-2.0
"""Fail-closed evidence helpers for the private dataset reader rotation."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any


DATASET_ID = "SZLHOLDINGS/david-leads-data"
POINTER_FILES = {
    "dol-form5500-benefit-timing": "latest/form5500.json",
    "fmcsa-company-census": "latest/fmcsa.json",
    "usaspending-contract-activity": "latest/usaspending.json",
    "epa-echo-monitoring-activity": "latest/echo-exporter.json",
}
_PATH_PATTERNS = {
    "dol-form5500-benefit-timing": re.compile(
        r"snapshots/form5500/[0-9]{4}-[0-9]{2}-[0-9]{2}/([0-9a-f]{64})"
    ),
    "fmcsa-company-census": re.compile(
        r"snapshots/fmcsa/[0-9]{4}-[0-9]{2}-[0-9]{2}/([0-9a-f]{64})"
    ),
    "usaspending-contract-activity": re.compile(
        r"snapshots/usaspending/[0-9]{4}-[0-9]{2}-[0-9]{2}/([0-9a-f]{64})"
    ),
    "epa-echo-monitoring-activity": re.compile(
        r"snapshots/[0-9]{4}-[0-9]{2}-[0-9]{2}/([0-9a-f]{64})"
    ),
}
_SHA40 = re.compile(r"[0-9a-f]{40}")
_DIGEST64 = re.compile(r"[0-9a-f]{64}")
MAX_POINTER_BYTES = 8192


class RotationContractError(RuntimeError):
    """The reader or runtime did not satisfy the rotation evidence contract."""


def require_fine_grained_role(identity: Any) -> str:
    """Prove token type without claiming permissions the API does not expose."""
    if not isinstance(identity, Mapping):
        raise RotationContractError("reader identity is unavailable")
    auth = identity.get("auth")
    access_token = auth.get("accessToken") if isinstance(auth, Mapping) else None
    role = access_token.get("role") if isinstance(access_token, Mapping) else None
    normalized = re.sub(r"[^a-z]", "", str(role or "").lower())
    if normalized != "finegrained":
        raise RotationContractError("reader token is not fine-grained")
    return str(role)


def require_dataset_revision(value: Any) -> str:
    revision = str(value or "").lower()
    if not _SHA40.fullmatch(revision) or revision == "0" * 40:
        raise RotationContractError("private dataset revision is not immutable")
    return revision


def require_rotation_generation(value: Any, expected: Any) -> str:
    """Bind an individual live response to the protected rotation process."""
    observed_generation = str(value or "").lower()
    expected_generation = str(expected or "").lower()
    if (
        not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_generation)
        or observed_generation != expected_generation
    ):
        raise RotationContractError("live response rotation generation does not match")
    return observed_generation


def require_pointer_sizes(sizes: Mapping[str, Any]) -> None:
    if set(sizes) != set(POINTER_FILES.values()):
        raise RotationContractError("dataset pointer metadata is incomplete")
    for size in sizes.values():
        if type(size) is not int or not 0 < size <= MAX_POINTER_BYTES:
            raise RotationContractError("dataset pointer exceeds the byte budget")


def _strict_object(path: Path) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise RotationContractError("dataset pointer contains duplicate keys")
            value[key] = item
        return value

    try:
        size = path.stat().st_size
        if not 0 < size <= MAX_POINTER_BYTES:
            raise RotationContractError("dataset pointer exceeds the byte budget")
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except RotationContractError:
        raise
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise RotationContractError("dataset pointer is not strict JSON") from exc
    if not isinstance(value, dict):
        raise RotationContractError("dataset pointer is not an object")
    return value


def load_pointer_expectations(
    paths: Mapping[str, str | Path],
) -> dict[str, dict[str, str]]:
    """Bind each runtime lane to a pointer read at one immutable dataset SHA."""
    if set(paths) != set(POINTER_FILES):
        raise RotationContractError("dataset pointer set is incomplete")
    expectations: dict[str, dict[str, str]] = {}
    for source_id in POINTER_FILES:
        pointer = _strict_object(Path(paths[source_id]))
        snapshot_id = pointer.get("snapshot_id")
        digest = pointer.get("snapshot_digest")
        immutable_path = pointer.get("path")
        path_match = (
            _PATH_PATTERNS[source_id].fullmatch(immutable_path)
            if isinstance(immutable_path, str)
            else None
        )
        if (
            type(pointer.get("pointer_version")) is not int
            or pointer.get("pointer_version") != 1
            or not isinstance(digest, str)
            or not _DIGEST64.fullmatch(digest)
            or digest == "0" * 64
            or snapshot_id != f"sha256:{digest}"
            or path_match is None
            or path_match.group(1) != digest
        ):
            raise RotationContractError("dataset pointer binding is invalid")
        expectations[source_id] = {
            "snapshot_id": snapshot_id,
            "immutable_path": immutable_path,
        }
    return expectations


def validate_runtime_report(
    report: Any,
    *,
    expected_source_revision: str,
    expected_rotation_generation: str,
    dataset_revision: str,
    pointer_expectations: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    """Require the restarted Space to read the exact preflighted snapshots."""
    source_revision = require_dataset_revision(expected_source_revision)
    dataset_revision = require_dataset_revision(dataset_revision)
    rotation_generation = require_rotation_generation(
        expected_rotation_generation,
        expected_rotation_generation,
    )
    if (
        not isinstance(report, Mapping)
        or report.get("schema") != "szl.david-frontier-live-canary/v1"
        or report.get("complete") is not True
    ):
        raise RotationContractError("runtime canary is incomplete")
    if report.get("records_exported") is not False:
        raise RotationContractError("runtime canary exported records")
    deployment = report.get("deployment")
    if not isinstance(deployment, Mapping) or (
        deployment.get("source_revision") != source_revision
        or deployment.get("expected_revision") != source_revision
        or deployment.get("source_bound") is not True
        or deployment.get("release_attested") is not True
        or deployment.get("rotation_generation") != rotation_generation
        or deployment.get("expected_rotation_generation") != rotation_generation
        or deployment.get("rotation_generation_bound") is not True
    ):
        raise RotationContractError("runtime source or release binding is incomplete")
    record_contract = report.get("record_contract")
    if (
        not isinstance(record_contract, Mapping)
        or record_contract.get("complete") is not True
    ):
        raise RotationContractError("runtime record contract is incomplete")

    lanes = report.get("required_lanes")
    if not isinstance(lanes, list):
        raise RotationContractError("runtime lane evidence is unavailable")
    observed: dict[str, dict[str, str]] = {}
    for lane in lanes:
        if not isinstance(lane, Mapping):
            raise RotationContractError("runtime lane evidence is malformed")
        source_id = lane.get("source_id")
        snapshot = lane.get("snapshot")
        if (
            not isinstance(source_id, str)
            or source_id not in POINTER_FILES
            or source_id in observed
            or lane.get("operational") is not True
            or not isinstance(snapshot, Mapping)
            or snapshot.get("complete") is not True
        ):
            raise RotationContractError("runtime lane is not operational")
        expectation = pointer_expectations.get(source_id)
        if not isinstance(expectation, Mapping) or (
            snapshot.get("snapshot_id") != expectation.get("snapshot_id")
            or snapshot.get("immutable_path") != expectation.get("immutable_path")
        ):
            raise RotationContractError(
                "runtime lane does not match the dataset pointer"
            )
        observed[str(source_id)] = {
            "snapshot_id": str(snapshot["snapshot_id"]),
            "immutable_path": str(snapshot["immutable_path"]),
        }
    if set(observed) != set(POINTER_FILES):
        raise RotationContractError("runtime lane set is incomplete")
    return {
        "schema": "szl.david-dataset-reader-runtime/v1",
        "source_revision": source_revision,
        "dataset_revision": dataset_revision,
        "rotation_generation": rotation_generation,
        "snapshots": observed,
        "record_contract_complete": True,
        "records_exported": False,
    }
