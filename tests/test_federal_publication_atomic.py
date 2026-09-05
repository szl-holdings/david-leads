"""No-network regressions for immutable Federal Refresh publication."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from huggingface_hub.errors import HfHubHTTPError, RemoteEntryNotFoundError, RepositoryNotFoundError

from tools.ingestor import publish_snapshot as pub


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def bundle(tmp_path, lane="echo-exporter", ident="snapshot-001", age=0):
    created = (datetime.now(timezone.utc) - timedelta(days=age)).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = {"source_record_id": "fixture:1", "org_name": "Fixture only", "state": "NY", "raw": {}}
    record["normalized_record_hash"] = digest(record)
    snap = {"snapshot_id": ident, "created_at": created, "source": {"name": lane},
            "record_count": 1, "records_hash": digest([record["normalized_record_hash"]]), "freshness_days": 8}
    receipt = {"issued_at": created, "subject": {"source_record_id": ident,
               "normalized_record_hash": snap["records_hash"]}, "gate": {"result": "pass"},
               "ranking_inputs": {"source_path": [lane]}}
    receipt["payload_hash"] = digest(receipt)
    receipt["signature"] = {"algorithm": "HMAC-SHA256", "key_id": None, "value": "UNSIGNED"}
    for name, data in {"snapshot.json": snap, "receipt.json": receipt, "records.jsonl": record}.items():
        (tmp_path / name).write_bytes(canonical(data) + b"\n")
    return snap


def remote_error(cls=HfHubHTTPError, code=503):
    return cls("provider error", response=httpx.Response(code, request=httpx.Request("GET", "https://huggingface.co/test")))


class FakeApi:
    def __init__(self, *, existing=False, failure=None, conflicts=0, pointer=None):
        self.existing, self.failure, self.conflicts, self.pointer = existing, failure, conflicts, pointer
        self.iterated = False
        self.commits = []
        self.parents = []
        self.reads = []

    def repo_info(self, **kwargs):
        self.reads.append(kwargs)
        return SimpleNamespace(sha=f"{len(self.parents)+1:040x}")

    def list_repo_tree(self, **kwargs):
        self.reads.append(kwargs)
        self.iterated = True  # this body does not execute until iteration
        if self.failure:
            raise self.failure
        if not self.existing:
            raise remote_error(RemoteEntryNotFoundError, 404)
        yield SimpleNamespace(path="snapshot.json")

    def hf_hub_download(self, **kwargs):
        self.reads.append(kwargs)
        if self.pointer:
            return self.pointer
        raise remote_error(RemoteEntryNotFoundError, 404)

    def create_commit(self, **kwargs):
        self.parents.append(kwargs["parent_commit"])
        if self.conflicts:
            self.conflicts -= 1
            raise remote_error(code=409)
        self.commits.append(kwargs)
        return SimpleNamespace(oid="f" * 40)


def test_absent_lazy_path_is_consumed_and_payloads_commit_together(tmp_path):
    bundle(tmp_path)
    snapshot, payloads = pub.verified_bundle(tmp_path)
    api = FakeApi()
    result = pub.publish_bundle(api, pub.DATASET_ID, snapshot, payloads)
    assert api.iterated and result["status"] == "PUBLISHED"
    assert len(api.commits) == 1
    operations = api.commits[0]["operations"]
    assert len(operations) == 5
    assert {op.path_in_repo for op in operations} == {
        *(f"{result['path']}/{name}" for name in pub.FILES), "latest/echo-exporter.json", "latest.json"}
    pointer = json.loads(operations[-1].path_or_fileobj)
    assert pointer["files_sha256"] == {k: hashlib.sha256(v).hexdigest() for k, v in payloads.items()}
    assert all(row["revision"] == api.parents[0] for row in api.reads if "filename" in row or "path_in_repo" in row)


def test_existing_snapshot_never_overwritten(tmp_path):
    bundle(tmp_path)
    snap, payloads = pub.verified_bundle(tmp_path)
    api = FakeApi(existing=True)
    with pytest.raises(pub.PublicationError, match="already exists"):
        pub.publish_bundle(api, pub.DATASET_ID, snap, payloads)
    assert api.iterated and not api.commits


@pytest.mark.parametrize("error", [remote_error(code=c) for c in (401, 403, 429, 500, 503)] +
                         [remote_error(RepositoryNotFoundError, 404), TimeoutError()])
def test_provider_failures_never_become_absence(tmp_path, error):
    bundle(tmp_path)
    snap, payloads = pub.verified_bundle(tmp_path)
    api = FakeApi(failure=error)
    with pytest.raises(type(error)):
        pub.publish_bundle(api, pub.DATASET_ID, snap, payloads)
    assert not api.parents


def test_lane_paths_do_not_collide_and_only_echo_owns_legacy_pointer(tmp_path):
    paths = []
    for lane in ("echo-exporter", "fmcsa-motus-carrier", "dol-5500-bulk", "usaspending-archive"):
        bundle(tmp_path, lane=lane)
        snap, payloads = pub.verified_bundle(tmp_path)
        api = FakeApi()
        result = pub.publish_bundle(api, pub.DATASET_ID, snap, payloads)
        paths.append(result["path"])
        written = {op.path_in_repo for op in api.commits[0]["operations"]}
        assert ("latest.json" in written) == (lane == "echo-exporter")
        assert f"latest/{lane}.json" in written
    assert len(set(paths)) == 4


def test_conflict_rechecks_new_parent_before_retry(tmp_path, monkeypatch):
    bundle(tmp_path)
    snap, payloads = pub.verified_bundle(tmp_path)
    sleeps = []
    monkeypatch.setattr(pub.time, "sleep", sleeps.append)
    api = FakeApi(conflicts=2)
    result = pub.publish_bundle(api, pub.DATASET_ID, snap, payloads)
    assert result["attempts"] == 3 and len(set(api.parents)) == 3
    assert sleeps == [0.25, 0.5]
    assert len(api.commits) == 1


def test_conflict_retry_is_bounded(tmp_path, monkeypatch):
    bundle(tmp_path)
    snap, payloads = pub.verified_bundle(tmp_path)
    monkeypatch.setattr(pub.time, "sleep", lambda _: None)
    api = FakeApi(conflicts=10)
    with pytest.raises(HfHubHTTPError):
        pub.publish_bundle(api, pub.DATASET_ID, snap, payloads)
    assert len(api.parents) == 4 and not api.commits


def test_newer_lane_pointer_cannot_be_regressed(tmp_path):
    bundle(tmp_path, age=1)
    snap, payloads = pub.verified_bundle(tmp_path)
    pointer = tmp_path / "pointer.json"
    pointer.write_bytes(canonical({"lane": "echo-exporter", "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}))
    api = FakeApi(pointer=pointer)
    with pytest.raises(pub.PublicationError, match="regress"):
        pub.publish_bundle(api, pub.DATASET_ID, snap, payloads)
    assert not api.commits


@pytest.mark.parametrize("change", ["record", "receipt_binding", "count", "future", "unsafe_lane"])
def test_invalid_local_evidence_never_admitted(tmp_path, change):
    bundle(tmp_path)
    filename = "snapshot.json"
    snap = json.loads((tmp_path / filename).read_bytes())
    if change == "record":
        filename = "records.jsonl"
        snap = json.loads((tmp_path / filename).read_bytes())
        snap["org_name"] = "tampered"
    elif change == "receipt_binding":
        snap["snapshot_id"] = "different-snapshot"
    elif change == "count":
        snap["record_count"] = 9
    elif change == "future":
        snap["created_at"] = "2999-01-01T00:00:00Z"
    else:
        snap["source"]["name"] = "../escape"
    (tmp_path / filename).write_bytes(canonical(snap))
    with pytest.raises(pub.PublicationError):
        pub.verified_bundle(tmp_path)


def test_no_token_still_verifies_and_never_claims_publication(tmp_path, monkeypatch, capsys):
    bundle(tmp_path)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    assert pub.main(["--dataset", pub.DATASET_ID, "--snapshot", str(tmp_path)]) == 0
    assert '"status": "VERIFIED_NOT_PUBLISHED"' in capsys.readouterr().out
    (tmp_path / "records.jsonl").write_text("{}")
    assert pub.main(["--dataset", pub.DATASET_ID, "--snapshot", str(tmp_path)]) == 1


def test_frozen_payloads_are_the_verified_bytes(tmp_path):
    bundle(tmp_path)
    _, payloads = pub.verified_bundle(tmp_path)
    original = payloads["records.jsonl"]
    (tmp_path / "records.jsonl").write_text("changed after verification")
    assert payloads["records.jsonl"] == original
