"""Canonical publication and private admission use the same immutable bytes."""
import json
from unittest import mock

import pytest

from app import dol_admission_signature as signatures
from app import federal_snapshot as snapshots
from app.domain.david_reference import Hold
from app.federal_refresh_store import load_dol_snapshot
from tests.dol_fixtures import KEY, NOW, fixture
from tests.test_publish_snapshot import (
    FakeApi, FakeOperation, FakeRemoteEntryNotFoundError, PUBLISHED_COMMIT,
)
from tools.ingestor import frontier_refresh_cli as cli
from tools.ingestor import publish_snapshot as publisher


def write_bundle(path, *, signature=True):
    bundle = fixture()
    snapshots.write_bundle(bundle, path)
    if signature:
        (path / signatures.FILENAME).write_bytes(snapshots.canonical(bundle["admission_signature"]))
    return bundle


def publish(path, receipt, api, *, key=KEY):
    return publisher.publish_snapshot(publisher.DATASET_ID, path, receipt, token="synthetic-token",
        admission_signing_key=key, api_factory=lambda _: api,
        operation_factory=FakeOperation, remote_entry_not_found=FakeRemoteEntryNotFoundError)


def test_publisher_and_operator_consumer_share_canonical_bundle(tmp_path):
    directory = tmp_path / "snapshot"
    original = write_bundle(directory)
    api = FakeApi([], tree_error=FakeRemoteEntryNotFoundError())
    publication = publish(directory, tmp_path / "publication.json", api)
    signature_path = f"{publication['path']}/{signatures.FILENAME}"
    assert signature_path in publication["files"]
    assert any(call["filename"] == signature_path and call["revision"] == PUBLISHED_COMMIT for call in api.download_calls)
    requested_revisions = []
    def download(path, revision):
        requested_revisions.append(revision)
        return api.remote[path]
    admitted = load_dol_snapshot(PUBLISHED_COMMIT, signing_key=KEY, now=NOW, downloader=download)
    assert set(requested_revisions) == {PUBLISHED_COMMIT}
    assert admitted.records[0]["normalized_record_hash"] == original["records"][0]["normalized_record_hash"]
    assert admitted.records[0]["raw"] == {"participant_count": 12, "reported_life_benefit": True}
    assert admitted.receipt["signature"]["value"] == "UNSIGNED"
    assert len(api.commit_calls) == 1


@pytest.mark.parametrize("key", [None, b"wrong-key-at-least-thirty-two-bytes", b"short"])
def test_invalid_signing_key_fails_before_hub_calls(tmp_path, key):
    directory = tmp_path / "snapshot"
    write_bundle(directory)
    api = FakeApi([], tree_error=FakeRemoteEntryNotFoundError())
    with pytest.raises(publisher.PublicationError, match="signature verification"):
        publish(directory, tmp_path / "publication.json", api, key=key)
    assert api.events == []


def test_corrupt_admission_signature_fails_before_hub_calls(tmp_path):
    directory = tmp_path / "snapshot"
    write_bundle(directory)
    path = directory / signatures.FILENAME
    value = json.loads(path.read_bytes())
    value["value"] = "0" * 64
    path.write_bytes(snapshots.canonical(value))
    api = FakeApi([], tree_error=FakeRemoteEntryNotFoundError())
    with pytest.raises(publisher.PublicationError, match="signature verification"):
        publish(directory, tmp_path / "publication.json", api)
    assert api.events == []


def test_signature_optional_for_public_bundle_but_mandatory_for_private_admission(tmp_path):
    directory = tmp_path / "snapshot"
    write_bundle(directory, signature=False)
    api = FakeApi([], tree_error=FakeRemoteEntryNotFoundError())
    publication = publish(directory, tmp_path / "publication.json", api, key=None)
    assert publication["status"] == "VERIFIED_PUBLISHED"
    with pytest.raises(Hold, match="SOURCE_TRANSPORT_UNAVAILABLE"):
        load_dol_snapshot(PUBLISHED_COMMIT, signing_key=KEY, now=NOW, downloader=lambda path, _: api.remote[path])


def test_signature_readback_tampering_prevents_publication_receipt(tmp_path):
    directory = tmp_path / "snapshot"
    bundle = write_bundle(directory)
    signature_path = snapshots.pointer_for(bundle["snapshot"])["path"] + "/" + signatures.FILENAME
    api = FakeApi([], tree_error=FakeRemoteEntryNotFoundError(), tamper_path=signature_path)
    receipt = tmp_path / "publication.json"
    with pytest.raises(publisher.PublicationError, match="readback"):
        publish(directory, receipt, api)
    assert not receipt.exists()


@pytest.mark.parametrize("configured", [True, False])
def test_scheduled_cli_keeps_unsigned_receipt_and_optional_private_signature(tmp_path, configured):
    directory = tmp_path / "snapshot"
    bundle = fixture()
    with mock.patch.object(cli, "collect_bundle", return_value=bundle), mock.patch.dict(
        cli.os.environ, {"DOL_SNAPSHOT_SIGNING_KEY": KEY.decode() if configured else ""}
    ):
        assert cli.main(["--lane", "form5500", "--out", str(directory), "--source-revision", "a" * 40]) == 0
    assert json.loads((directory / "receipt.json").read_bytes())["signature"]["value"] == "UNSIGNED"
    assert (directory / signatures.FILENAME).exists() == configured
    if configured:
        signatures.verify(json.loads((directory / signatures.FILENAME).read_bytes()), bundle["snapshot"], bundle["receipt"], KEY)
