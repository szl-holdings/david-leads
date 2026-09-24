"""Publication invariants migrated from legacy v1 to the strict v3 bundle."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from tests.test_publish_snapshot import (
    DATASET_ID, PARENT_COMMIT, FakeApi, FakeOperation,
    FakeRemoteEntryNotFoundError, FakeNetworkError,
)
from tests.test_verify_snapshot import _bundle
from tools.ingestor import publish_snapshot as pub


def publish(directory, receipt, api, **kwargs):
    return pub.publish_snapshot(
        DATASET_ID, directory, receipt, token="test-token",
        api_factory=lambda _token: api, operation_factory=FakeOperation,
        remote_entry_not_found=FakeRemoteEntryNotFoundError, **kwargs,
    )


def test_lazy_missing_prefix_is_consumed_before_atomic_commit(tmp_path):
    directory = _bundle(tmp_path)
    class LazyApi(FakeApi):
        def list_repo_tree(self, **kwargs):
            self.events.append("iterated")
            raise FakeRemoteEntryNotFoundError()
            yield None
    api = LazyApi([])
    result = publish(directory, tmp_path / "publication.json", api)
    assert "iterated" in api.events
    assert result["status"] == "VERIFIED_PUBLISHED"
    assert len(api.commit_calls) == 1
    paths = {operation.path_in_repo for operation in api.commit_calls[0]["operations"]}
    assert {f"{result['path']}/{name}" for name in pub.FILES} <= paths
    assert {"latest.json", "latest/echo-exporter.json"} <= paths


@pytest.mark.parametrize("error", [
    FakeNetworkError("401"), FakeNetworkError("403"), FakeNetworkError("429"),
    FakeNetworkError("500"), FakeNetworkError("repository-not-found"), TimeoutError(),
])
def test_provider_failures_never_become_absence(tmp_path, error):
    directory = _bundle(tmp_path)
    api = FakeApi([], tree_error=error)
    with pytest.raises(type(error)):
        publish(directory, tmp_path / "publication.json", api)
    assert not api.commit_calls


def test_existing_prefix_is_never_overwritten(tmp_path):
    directory = _bundle(tmp_path)
    api = FakeApi([], tree_result=[object()])
    with pytest.raises(pub.PublicationError, match="already exists"):
        publish(directory, tmp_path / "publication.json", api)
    assert not api.commit_calls


def test_concurrent_change_fails_closed_without_success_receipt(tmp_path):
    directory = _bundle(tmp_path)
    class ConflictApi(FakeApi):
        def create_commit(self, **kwargs):
            assert kwargs["parent_commit"] == PARENT_COMMIT
            raise FakeNetworkError("409")
    api = ConflictApi([], tree_error=FakeRemoteEntryNotFoundError())
    receipt = tmp_path / "publication.json"
    with pytest.raises(FakeNetworkError):
        publish(directory, receipt, api)
    assert not receipt.exists()


def test_newer_lane_pointer_cannot_be_regressed(tmp_path):
    directory = _bundle(tmp_path)
    pointer = tmp_path / "pointer.json"
    pointer.write_text(json.dumps({"created_at": "2999-01-01T00:00:00Z"}))
    class NewerApi(FakeApi):
        def hf_hub_download(self, **kwargs):
            if kwargs["revision"] == PARENT_COMMIT:
                return str(pointer)
            return super().hf_hub_download(**kwargs)
    api = NewerApi([], tree_error=FakeRemoteEntryNotFoundError())
    with pytest.raises(pub.PublicationError, match="regress"):
        publish(directory, tmp_path / "publication.json", api)
    assert not api.commit_calls


def _echo_bundle_with_source_age(tmp_path, days):
    from tests.test_echo_ingestor import _base_row, _fixture_zip
    from tools.ingestor.echo_ingestor_cli import ingest_zip

    source_date = datetime.now(timezone.utc) - timedelta(days=days)
    archive = tmp_path / "dated-echo.zip"
    archive.write_bytes(_fixture_zip([_base_row()], source_date=source_date))
    directory = tmp_path / "dated-snapshot"
    ingest_zip(archive, directory, source_revision="b" * 40, minimum_records=1)
    return directory


def _api_with_prior_echo(tmp_path, directory, previous_as_of):
    from tools.ingestor.echo_ingestor import canonical_json, sha256_bytes

    previous = json.loads((directory / "snapshot.json").read_bytes())
    previous["created_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    previous["source"]["source_as_of"] = previous_as_of
    core = {key: value for key, value in previous.items() if key not in {"snapshot_id", "snapshot_digest"}}
    previous["snapshot_digest"] = sha256_bytes(canonical_json(core))
    previous["snapshot_id"] = f"sha256:{previous['snapshot_digest']}"
    prefix = pub._publication_prefix(previous)[0]
    pointer = tmp_path / "previous-pointer.json"
    pointer.write_text(json.dumps(pub._pointer(previous, prefix)), encoding="utf-8")
    manifest = tmp_path / "previous-manifest.json"
    manifest.write_text(json.dumps(previous), encoding="utf-8")
    filename = f"{prefix}/snapshot.json"

    class PriorEchoApi(FakeApi):
        def __init__(self):
            super().__init__([], tree_error=FakeRemoteEntryNotFoundError())
            self.path_info_calls = []
            self.parent_downloads = []
            self.size_override = None
            self.missing_manifest = False
            self.manifest_error = None

        def get_paths_info(self, **kwargs):
            self.path_info_calls.append(kwargs)
            assert kwargs["revision"] == PARENT_COMMIT
            assert kwargs["paths"] == [filename]
            if self.missing_manifest:
                return []
            return [SimpleNamespace(path=filename, size=self.size_override if self.size_override is not None else manifest.stat().st_size)]

        def hf_hub_download(self, **kwargs):
            if kwargs["revision"] == PARENT_COMMIT:
                self.parent_downloads.append(kwargs)
                if kwargs["filename"] == "latest.json":
                    return str(pointer)
                assert kwargs["filename"] == filename
                if self.manifest_error is not None:
                    raise self.manifest_error
                return str(manifest)
            return super().hf_hub_download(**kwargs)

    return PriorEchoApi(), pointer, manifest


def test_newly_processed_echo_cannot_replace_newer_source_export(tmp_path):
    directory = _echo_bundle_with_source_age(tmp_path, 2)
    previous_date = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
    api, _, _ = _api_with_prior_echo(tmp_path, directory, previous_date)
    receipt = tmp_path / "publication.json"
    with pytest.raises(pub.PublicationError, match="regress the ECHO source export date"):
        publish(directory, receipt, api)
    assert not api.commit_calls
    assert not receipt.exists()
    assert [call["filename"] for call in api.parent_downloads][0] == "latest.json"
    assert len(api.parent_downloads) == 2
    assert all(call["revision"] == PARENT_COMMIT for call in api.parent_downloads)


@pytest.mark.parametrize("previous_age", [2, 3, 20])
def test_equal_or_newer_echo_export_can_replace_pinned_prior(tmp_path, previous_age):
    directory = _echo_bundle_with_source_age(tmp_path, 2)
    previous_date = (datetime.now(timezone.utc) - timedelta(days=previous_age)).date().isoformat()
    api, _, _ = _api_with_prior_echo(tmp_path, directory, previous_date)
    result = publish(directory, tmp_path / "publication.json", api)
    assert result["status"] == "VERIFIED_PUBLISHED"
    assert len(api.commit_calls) == 1
    assert api.path_info_calls[0]["revision"] == PARENT_COMMIT


@pytest.mark.parametrize("invalid_date", ["2026-02-30", "2026-9-01", "not-a-date", None])
def test_invalid_prior_echo_source_date_fails_before_commit(tmp_path, invalid_date):
    directory = _echo_bundle_with_source_age(tmp_path, 2)
    api, _, _ = _api_with_prior_echo(tmp_path, directory, invalid_date)
    with pytest.raises(pub.PublicationError, match="integrity or source date"):
        publish(directory, tmp_path / "publication.json", api)
    assert not api.commit_calls


def test_prior_echo_manifest_tamper_cannot_influence_source_admission(tmp_path):
    directory = _echo_bundle_with_source_age(tmp_path, 2)
    previous_date = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
    api, _, manifest = _api_with_prior_echo(tmp_path, directory, previous_date)
    document = json.loads(manifest.read_bytes())
    document["source"]["source_as_of"] = "2020-01-01"
    manifest.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(pub.PublicationError, match="integrity or source date"):
        publish(directory, tmp_path / "publication.json", api)
    assert not api.commit_calls


def test_unsafe_prior_echo_path_never_reaches_manifest_download(tmp_path):
    directory = _echo_bundle_with_source_age(tmp_path, 2)
    api, pointer, _ = _api_with_prior_echo(tmp_path, directory, "2020-01-01")
    document = json.loads(pointer.read_bytes())
    document["path"] = "../other-dataset"
    pointer.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(pub.PublicationError, match="path binding"):
        publish(directory, tmp_path / "publication.json", api)
    assert not api.path_info_calls
    assert not api.commit_calls


def test_prior_echo_manifest_size_is_bounded_before_download(tmp_path):
    directory = _echo_bundle_with_source_age(tmp_path, 2)
    api, _, _ = _api_with_prior_echo(tmp_path, directory, "2020-01-01")
    api.size_override = pub.MAX_PRIOR_MANIFEST_BYTES + 1
    with pytest.raises(pub.PublicationError, match="metadata budget"):
        publish(directory, tmp_path / "publication.json", api)
    assert len(api.parent_downloads) == 1
    assert not api.commit_calls


@pytest.mark.parametrize("failure", [FakeNetworkError("403"), FakeRemoteEntryNotFoundError(), TimeoutError()])
def test_prior_manifest_read_errors_never_become_first_publication(tmp_path, failure):
    directory = _echo_bundle_with_source_age(tmp_path, 2)
    api, _, _ = _api_with_prior_echo(tmp_path, directory, "2020-01-01")
    api.manifest_error = failure
    with pytest.raises(type(failure)):
        publish(directory, tmp_path / "publication.json", api)
    assert not api.commit_calls


def test_missing_prior_echo_manifest_fails_closed(tmp_path):
    directory = _echo_bundle_with_source_age(tmp_path, 2)
    api, _, _ = _api_with_prior_echo(tmp_path, directory, "2020-01-01")
    api.missing_manifest = True
    with pytest.raises(pub.PublicationError, match="manifest is missing"):
        publish(directory, tmp_path / "publication.json", api)
    assert not api.commit_calls


@pytest.mark.parametrize("name,key,value", [
    ("snapshot.json", "record_count", 9),
    ("snapshot.json", "created_at", "2999-01-01T00:00:00Z"),
    ("receipt.json", "payload_hash", "a" * 64),
    ("records.jsonl", "org_name", "TAMPERED"),
    ("records.jsonl", "raw", {"private_contact": "FORBIDDEN"}),
])
def test_invalid_evidence_never_reaches_provider(tmp_path, name, key, value):
    directory = _bundle(tmp_path)
    target = directory / name
    document = json.loads(target.read_bytes())
    document[key] = value
    target.write_text(json.dumps(document) + "\n", encoding="utf-8")
    api = FakeApi([], tree_error=FakeRemoteEntryNotFoundError())
    with pytest.raises(pub.PublicationError):
        publish(directory, tmp_path / "publication.json", api)
    assert not api.create_repo_calls


def test_missing_credentials_are_a_hard_publication_failure(tmp_path):
    directory = _bundle(tmp_path)
    api = FakeApi([])
    with pytest.raises(pub.PublicationError, match="HF_TOKEN"):
        pub.publish_snapshot(DATASET_ID, directory, tmp_path / "publication.json",
                             token="", api_factory=lambda _: api)
    assert not api.create_repo_calls


def test_frozen_bytes_are_used_even_if_original_changes_after_verification(tmp_path):
    directory = _bundle(tmp_path)
    original = (directory / "records.jsonl").read_bytes()
    def verifier(frozen):
        result = pub.verify(frozen)
        (directory / "records.jsonl").write_text("changed after verification")
        return result
    api = FakeApi([], tree_error=FakeRemoteEntryNotFoundError())
    result = publish(directory, tmp_path / "publication.json", api, verifier=verifier)
    assert api.remote[f"{result['path']}/records.jsonl"] == original


def test_wrong_dataset_is_rejected_before_provider_access(tmp_path):
    directory = _bundle(tmp_path)
    with pytest.raises(pub.PublicationError, match="canonical dataset"):
        pub.publish_snapshot("OTHER/data", directory, tmp_path / "p.json", token="test")


@pytest.mark.parametrize("lane", ["fmcsa", "form5500", "usaspending"])
def test_scheduled_lane_commit_does_not_overwrite_echo_pointer(tmp_path, lane):
    from app.federal_snapshot import write_bundle
    from tests.test_frontier_snapshot import make_bundle

    directory = tmp_path / "snapshot"
    write_bundle(make_bundle(lane), directory)
    api = FakeApi([], tree_error=FakeRemoteEntryNotFoundError())
    result = publish(directory, tmp_path / "publication.json", api)
    assert result["status"] == "VERIFIED_PUBLISHED"
    assert result["path"].startswith(f"snapshots/{lane}/")
    assert len(api.commit_calls) == 1
    paths = {op.path_in_repo for op in api.commit_calls[0]["operations"]}
    assert f"latest/{lane}.json" in paths
    assert "latest.json" not in paths
    assert "latest/echo-exporter.json" not in paths
    assert "README.md" not in paths
    assert len(paths) == 4
