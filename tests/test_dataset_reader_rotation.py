# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import json

import pytest

from ops.dataset_reader_rotation import (
    DATASET_ID,
    POINTER_FILES,
    RotationContractError,
    load_pointer_expectations,
    require_dataset_revision,
    require_fine_grained_role,
    require_pointer_sizes,
    require_rotation_generation,
    validate_runtime_report,
)


SOURCE_SHA = "a" * 40
DATASET_SHA = "b" * 40
ROTATION_GENERATION = "sha256:" + "c" * 64


def _pointers(tmp_path):
    paths = {}
    for index, (source_id, filename) in enumerate(POINTER_FILES.items(), start=1):
        digest = f"{index:064x}"
        lane = {
            "dol-form5500-benefit-timing": "form5500",
            "fmcsa-company-census": "fmcsa",
            "usaspending-contract-activity": "usaspending",
        }.get(source_id)
        prefix = f"snapshots/{lane}" if lane else "snapshots"
        value = {
            "pointer_version": 1,
            "snapshot_id": f"sha256:{digest}",
            "snapshot_digest": digest,
            "path": f"{prefix}/2026-09-29/{digest}",
        }
        path = tmp_path / filename.replace("/", "-")
        path.write_text(json.dumps(value), encoding="utf-8")
        paths[source_id] = path
    return paths


def _report(expectations):
    return {
        "schema": "szl.david-frontier-live-canary/v1",
        "complete": True,
        "records_exported": False,
        "deployment": {
            "source_revision": SOURCE_SHA,
            "expected_revision": SOURCE_SHA,
            "source_bound": True,
            "release_attested": True,
            "rotation_generation": ROTATION_GENERATION,
            "expected_rotation_generation": ROTATION_GENERATION,
            "rotation_generation_bound": True,
        },
        "record_contract": {"complete": True},
        "required_lanes": [
            {
                "source_id": source_id,
                "operational": True,
                "snapshot": {**snapshot, "complete": True},
            }
            for source_id, snapshot in expectations.items()
        ],
    }


def test_reader_identity_and_dataset_revision_are_fail_closed():
    identity = {"auth": {"accessToken": {"role": "fineGrained"}}}
    assert require_fine_grained_role(identity) == "fineGrained"
    assert require_dataset_revision(DATASET_SHA) == DATASET_SHA
    with pytest.raises(RotationContractError, match="not fine-grained"):
        require_fine_grained_role({"auth": {"accessToken": {"role": "write"}}})
    with pytest.raises(RotationContractError, match="not immutable"):
        require_dataset_revision("main")


def test_live_response_requires_the_exact_rotation_generation():
    assert (
        require_rotation_generation(ROTATION_GENERATION, ROTATION_GENERATION)
        == ROTATION_GENERATION
    )
    with pytest.raises(RotationContractError, match="does not match"):
        require_rotation_generation("sha256:" + "d" * 64, ROTATION_GENERATION)
    with pytest.raises(RotationContractError, match="does not match"):
        require_rotation_generation(None, ROTATION_GENERATION)


def test_pointer_preflight_binds_all_four_lanes(tmp_path):
    require_pointer_sizes({name: 512 for name in POINTER_FILES.values()})
    expectations = load_pointer_expectations(_pointers(tmp_path))
    assert set(expectations) == set(POINTER_FILES)
    assert DATASET_ID == "SZLHOLDINGS/david-leads-data"

    incomplete = _pointers(tmp_path)
    incomplete.pop("epa-echo-monitoring-activity")
    with pytest.raises(RotationContractError, match="incomplete"):
        load_pointer_expectations(incomplete)

    invalid = _pointers(tmp_path)
    path = invalid["fmcsa-company-census"]
    value = json.loads(path.read_text(encoding="utf-8"))
    value["snapshot_id"] = "sha256:" + "f" * 64
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(RotationContractError, match="binding is invalid"):
        load_pointer_expectations(invalid)

    oversized = _pointers(tmp_path)
    path = oversized["dol-form5500-benefit-timing"]
    path.write_bytes(b" " * 8193)
    with pytest.raises(RotationContractError, match="byte budget"):
        load_pointer_expectations(oversized)

    with pytest.raises(RotationContractError, match="byte budget"):
        require_pointer_sizes({name: 9000 for name in POINTER_FILES.values()})


def test_runtime_report_requires_exact_source_and_dataset_pointers(tmp_path):
    expectations = load_pointer_expectations(_pointers(tmp_path))
    evidence = validate_runtime_report(
        _report(expectations),
        expected_source_revision=SOURCE_SHA,
        expected_rotation_generation=ROTATION_GENERATION,
        dataset_revision=DATASET_SHA,
        pointer_expectations=expectations,
    )
    assert evidence["source_revision"] == SOURCE_SHA
    assert evidence["dataset_revision"] == DATASET_SHA
    assert evidence["records_exported"] is False
    assert set(evidence["snapshots"]) == set(POINTER_FILES)

    stale = _report(expectations)
    stale["deployment"]["source_revision"] = "c" * 40
    with pytest.raises(RotationContractError, match="source or release"):
        validate_runtime_report(
            stale,
            expected_source_revision=SOURCE_SHA,
            expected_rotation_generation=ROTATION_GENERATION,
            dataset_revision=DATASET_SHA,
            pointer_expectations=expectations,
        )

    mismatch = _report(expectations)
    mismatch["required_lanes"][0]["snapshot"]["snapshot_id"] = "sha256:" + "f" * 64
    with pytest.raises(RotationContractError, match="does not match"):
        validate_runtime_report(
            mismatch,
            expected_source_revision=SOURCE_SHA,
            expected_rotation_generation=ROTATION_GENERATION,
            dataset_revision=DATASET_SHA,
            pointer_expectations=expectations,
        )


@pytest.mark.parametrize(
    "mutator, message",
    [
        (lambda value: value.update(complete=False), "canary is incomplete"),
        (
            lambda value: value["required_lanes"][0].update(operational=False),
            "lane is not operational",
        ),
        (
            lambda value: value["record_contract"].update(complete=False),
            "record contract is incomplete",
        ),
    ],
)
def test_runtime_report_rejects_nonconvergence(tmp_path, mutator, message):
    expectations = load_pointer_expectations(_pointers(tmp_path))
    report = copy.deepcopy(_report(expectations))
    mutator(report)
    with pytest.raises(RotationContractError, match=message):
        validate_runtime_report(
            report,
            expected_source_revision=SOURCE_SHA,
            expected_rotation_generation=ROTATION_GENERATION,
            dataset_revision=DATASET_SHA,
            pointer_expectations=expectations,
        )
