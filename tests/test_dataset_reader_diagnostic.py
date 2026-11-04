# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import io
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from ops import dataset_reader_diagnostic as diagnostic
from ops.dataset_reader_rotation import DATASET_ID, MAX_POINTER_BYTES, POINTER_FILES


ROOT = Path(__file__).resolve().parents[1]
REVISION = "b" * 40
TOKEN = "hf_synthetic_test_reader"
SENTINEL = "PRIVATE_SENTINEL_NEVER_PRINT"


class Reader:
    """Only the three authorized read methods exist on this client."""

    def __init__(self):
        self.calls = []
        self.role = "fineGrained"
        self.revision = REVISION
        self.failure = None
        self.payloads = {}
        for index, filename in enumerate(POINTER_FILES.values(), start=1):
            digest = f"{index:064x}"
            lane = filename.removeprefix("latest/").removesuffix(".json")
            prefix = "snapshots" if lane == "echo-exporter" else f"snapshots/{lane}"
            self.payloads[filename] = json.dumps({
                "pointer_version": 1,
                "snapshot_id": f"sha256:{digest}",
                "snapshot_digest": digest,
                "path": f"{prefix}/2026-11-02/{digest}",
            }).encode()
        self.metadata = [SimpleNamespace(path=p, size=len(b)) for p, b in self.payloads.items()]

    def _call(self, name, args, kwargs):
        self.calls.append((name, args, kwargs))
        if self.failure == name:
            raise RuntimeError(SENTINEL)

    def whoami(self, **kwargs):
        self._call("whoami", (), kwargs)
        return {"auth": {"accessToken": {"role": self.role}}, "private": SENTINEL}

    def dataset_info(self, *args, **kwargs):
        self._call("dataset_info", args, kwargs)
        return SimpleNamespace(sha=self.revision)

    def get_paths_info(self, *args, **kwargs):
        self._call("get_paths_info", args, kwargs)
        return self.metadata


@pytest.fixture
def probe(monkeypatch):
    monkeypatch.setenv("DAVID_DATASET_READ_TOKEN", TOKEN)
    monkeypatch.setenv("HF_TOKEN", "hf_publisher_must_never_be_used")
    reader = Reader()
    opened = []
    received_tokens = []

    def factory(token):
        received_tokens.append(token)
        return reader

    def opener(url, **kwargs):
        prefix = f"https://huggingface.co/datasets/{DATASET_ID}/resolve/{REVISION}/"
        assert url.startswith(prefix)
        assert kwargs["timeout"] == 15
        opened.append(url)
        return io.BytesIO(reader.payloads[url.removeprefix(prefix)])

    def run():
        return diagnostic.diagnose_reader(api_factory=factory, pointer_opener=opener)

    return SimpleNamespace(reader=reader, opened=opened, tokens=received_tokens, run=run)


def test_reader_only_preflight_binds_four_bounded_pointers_at_one_revision(probe):
    report = probe.run()
    assert report["complete"] is True
    assert report["pointer_bindings_valid"] is True
    assert report["runtime_reader_verified"] is False
    assert report["space_mutations_performed"] is False
    assert probe.tokens == [TOKEN]
    assert len(probe.opened) == 4
    assert [call[0] for call in probe.reader.calls] == ["whoami", "dataset_info", "get_paths_info"]
    for _, _, kwargs in probe.reader.calls:
        assert kwargs["token"] == TOKEN
    _, args, kwargs = probe.reader.calls[-1]
    assert args == (DATASET_ID, list(POINTER_FILES.values()))
    assert kwargs["revision"] == REVISION
    assert kwargs["repo_type"] == "dataset"
    assert all(type(v) is bool for k, v in report.items() if k != "schema")


@pytest.mark.parametrize("value", [None, "", "\r\n", "bad token", "bad\x01token", "x" * 4097])
def test_missing_or_malformed_reader_never_falls_back_to_publisher(probe, monkeypatch, value):
    if value is None:
        monkeypatch.delenv("DAVID_DATASET_READ_TOKEN")
    else:
        monkeypatch.setenv("DAVID_DATASET_READ_TOKEN", value)
    report = probe.run()
    assert report["reader_present"] is bool(value)
    assert report["reader_format_valid"] is False
    assert report["complete"] is False
    assert not probe.tokens and not probe.opened


def test_accidental_line_endings_are_normalized_without_changing_token(probe, monkeypatch):
    monkeypatch.setenv("DAVID_DATASET_READ_TOKEN", TOKEN + "\r\n")
    assert probe.run()["complete"] is True
    assert probe.tokens == [TOKEN]


@pytest.mark.parametrize("role", ["read", "write", None, SENTINEL])
def test_non_fine_grained_identity_stops_before_dataset_access(probe, role):
    probe.reader.role = role
    report = probe.run()
    assert report["fine_grained_token"] is False
    assert report["dataset_access"] is False
    assert not probe.opened


@pytest.mark.parametrize("stage", ["whoami", "dataset_info", "get_paths_info"])
def test_remote_access_failures_remain_boolean_and_fail_closed(probe, stage):
    probe.reader.failure = stage
    report = probe.run()
    assert report["complete"] is False
    assert SENTINEL not in json.dumps(report)
    assert report["dataset_access"] is (stage == "get_paths_info")
    assert not probe.opened


@pytest.mark.parametrize("revision", ["main", "0" * 40, SENTINEL])
def test_invalid_dataset_revision_prevents_pointer_reads(probe, revision):
    probe.reader.revision = revision
    report = probe.run()
    assert report["immutable_revision_valid"] is False
    assert report["complete"] is False
    assert not probe.opened


@pytest.mark.parametrize("fault", ["missing", "duplicate", "extra", "oversized", "zero", "boolean"])
def test_invalid_pointer_metadata_is_rejected_before_content_read(probe, fault):
    metadata = probe.reader.metadata
    if fault == "missing":
        metadata.pop()
    elif fault == "duplicate":
        metadata.append(metadata[0])
    elif fault == "extra":
        metadata.append(SimpleNamespace(path=SENTINEL, size=1))
    else:
        metadata[0].size = {"oversized": MAX_POINTER_BYTES + 1, "zero": 0, "boolean": True}[fault]
    report = probe.run()
    assert report["pointer_metadata_valid"] is False
    assert report["complete"] is False
    assert not probe.opened


@pytest.mark.parametrize("fault", ["truncated", "oversized", "duplicate_key", "wrong_digest", "wrong_lane"])
def test_invalid_pointer_bytes_or_binding_cannot_pass(probe, fault):
    filename = next(iter(probe.reader.payloads))
    payload = probe.reader.payloads[filename]
    if fault == "truncated":
        payload = payload[:-1]
    elif fault == "oversized":
        payload = b" " * (MAX_POINTER_BYTES + 1)
    elif fault == "duplicate_key":
        payload = payload[:-1] + b', "pointer_version": 1}'
    else:
        value = json.loads(payload)
        if fault == "wrong_digest":
            value["snapshot_id"] = "sha256:" + "f" * 64
        else:
            value["path"] = value["path"].replace("form5500", "fmcsa")
        payload = json.dumps(value).encode()
    probe.reader.payloads[filename] = payload
    if fault not in {"truncated", "oversized"}:
        probe.reader.metadata[0].size = len(payload)
    report = probe.run()
    assert report["pointer_bindings_valid"] is False
    assert report["complete"] is False


def test_each_pointer_read_is_bounded_before_any_local_write(probe):
    reads = []

    class BoundedStream(io.BytesIO):
        def read(self, limit=-1):
            reads.append(limit)
            return super().read(limit)

    def opener(url, **kwargs):
        filename = url.split(f"/{REVISION}/", 1)[1]
        return BoundedStream(probe.reader.payloads[filename])

    report = diagnostic.diagnose_reader(api_factory=lambda _: probe.reader, pointer_opener=opener)
    assert report["complete"] is True
    assert reads == [MAX_POINTER_BYTES + 1] * 4


def test_temporary_pointer_files_are_removed(probe, monkeypatch):
    paths_seen = []
    original = diagnostic.load_pointer_expectations

    def capture(paths):
        paths_seen.extend(paths.values())
        return original(paths)

    monkeypatch.setattr(diagnostic, "load_pointer_expectations", capture)
    assert probe.run()["complete"] is True
    assert paths_seen and not any(path.exists() for path in paths_seen)


def test_cli_emits_only_boolean_report_even_if_client_prints_private_data(probe, monkeypatch, capsys):
    def noisy_whoami(**kwargs):
        print(SENTINEL)
        print(SENTINEL, file=sys.stderr)
        logging.critical(SENTINEL)
        raise RuntimeError(SENTINEL)

    probe.reader.whoami = noisy_whoami
    original = diagnostic.diagnose_reader
    monkeypatch.setattr(diagnostic, "diagnose_reader", lambda: original(api_factory=lambda _: probe.reader))
    assert diagnostic.main() == 1
    captured = capsys.readouterr()
    assert SENTINEL not in captured.out + captured.err
    assert captured.err == ""
    report = json.loads(captured.out)
    assert report["complete"] is False
    assert all(type(v) is bool for k, v in report.items() if k != "schema")


def _workflow():
    return yaml.load((ROOT / ".github/workflows/diagnose-dataset-reader.yml").read_text(), Loader=yaml.BaseLoader)


def test_manual_workflow_has_only_reader_secret_and_no_write_phase():
    workflow = _workflow()
    assert workflow["on"] == {"workflow_dispatch": {}}
    assert workflow["permissions"] == {"contents": "read"}
    assert set(workflow["jobs"]) == {"admit", "diagnose"}
    admit, diagnose = workflow["jobs"]["admit"], workflow["jobs"]["diagnose"]
    assert "environment" not in admit
    assert diagnose["needs"] == "admit"
    assert diagnose["environment"]["name"] == "david-space-credential-rotation"
    assert diagnose["timeout-minutes"] == "5"
    secret_steps = [step for step in diagnose["steps"] if "secrets." in json.dumps(step)]
    assert len(secret_steps) == 1
    assert secret_steps[0]["env"]["DAVID_DATASET_READ_TOKEN"] == "${{ secrets.DAVID_DATASET_READ_TOKEN }}"
    assert secret_steps[0]["run"] == "python3 -m ops.dataset_reader_diagnostic"
    assert "secrets." not in json.dumps(admit)
    assert "HF_TOKEN" not in json.dumps(workflow)
    for job in workflow["jobs"].values():
        checkout = next(step for step in job["steps"] if str(step.get("uses", "")).startswith("actions/checkout@"))
        assert checkout["with"] == {"ref": "${{ github.sha }}", "persist-credentials": "false"}


@pytest.mark.parametrize("ref,head,expected", [
    ("refs/heads/main", REVISION, 0),
    ("refs/heads/untrusted", REVISION, 1),
    ("refs/tags/main", REVISION, 1),
    ("refs/heads/main", "c" * 40, 1),
    ("refs/heads/main", "", 1),
])
def test_admission_shell_rejects_nonmain_and_superseded_sources(tmp_path, ref, head, expected):
    git = tmp_path / "git"
    git.write_text('#!/bin/sh\nprintf "%s\\trefs/heads/main\\n" "$DIAGNOSTIC_TEST_MAIN"\n')
    git.chmod(0o700)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}",
           "GITHUB_REF": ref, "GITHUB_SHA": REVISION, "DIAGNOSTIC_TEST_MAIN": head}
    workflow = _workflow()
    for job in workflow["jobs"].values():
        checks = [step["run"] for step in job["steps"] if "GITHUB_" in step.get("run", "")]
        result = subprocess.run(["bash", "-c", "\n".join(checks)], env=env, capture_output=True)
        assert result.returncode == expected
