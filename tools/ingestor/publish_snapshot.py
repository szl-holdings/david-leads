"""Verify and atomically publish lane-isolated Federal Refresh snapshots.

A snapshot's three files and lane pointer share one optimistic-concurrency
commit. Existing snapshots are never overwritten. ``latest.json`` remains an
ECHO-only compatibility pointer; other lanes use ``latest/<lane>.json``.
Missing credentials mean verified-but-unpublished, never a publication claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.ingestor.verify_snapshot import verify

DATASET_ID = "SZLHOLDINGS/david-leads-data"
FILES = ("snapshot.json", "receipt.json", "records.jsonl")
MAX_BUNDLE_BYTES = 1024 * 1024 * 1024
MAX_POINTER_BYTES = 16 * 1024
SAFE_COMPONENT = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}\Z")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")


class PublicationError(RuntimeError):
    """A failed contract; no new dataset pointer may be published."""


def _timestamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def verified_bundle(directory: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Freeze the input, verify those exact bytes, and bind receipt to snapshot."""
    payloads: dict[str, bytes] = {}
    remaining = MAX_BUNDLE_BYTES
    for name in FILES:
        with (directory / name).open("rb") as stream:
            payloads[name] = stream.read(remaining + 1)
        remaining -= len(payloads[name])
        if remaining < 0:
            raise PublicationError("snapshot exceeds the 1 GiB publication budget")
    with tempfile.TemporaryDirectory(prefix="federal-verify-") as folder:
        frozen = Path(folder)
        for name, data in payloads.items():
            (frozen / name).write_bytes(data)
        if verify(frozen) != 0:
            raise PublicationError("snapshot verification failed")
    snapshot = json.loads(payloads["snapshot.json"])
    receipt = json.loads(payloads["receipt.json"])
    lane = snapshot["source"]["name"]
    snapshot_id = snapshot["snapshot_id"]
    if not all(isinstance(v, str) and SAFE_COMPONENT.fullmatch(v) for v in (lane, snapshot_id)):
        raise PublicationError("invalid lane or snapshot identifier")
    if _timestamp(snapshot["created_at"]) > datetime.now(timezone.utc):
        raise PublicationError("snapshot timestamp is in the future")
    count = sum(bool(line.strip()) for line in payloads["records.jsonl"].splitlines())
    if type(snapshot["record_count"]) is not int or snapshot["record_count"] != count:
        raise PublicationError("snapshot record count mismatch")
    subject = receipt.get("subject", {})
    if (subject.get("source_record_id") != snapshot_id
            or subject.get("normalized_record_hash") != snapshot["records_hash"]
            or receipt.get("issued_at") != snapshot["created_at"]
            or receipt.get("ranking_inputs", {}).get("source_path") != [lane]):
        raise PublicationError("receipt is not bound to this snapshot and lane")
    return snapshot, payloads


def publish_bundle(api: Any, dataset: str, snapshot: dict[str, Any],
                   payloads: dict[str, bytes], *, max_attempts: int = 4) -> dict[str, Any]:
    """Publish already-verified bytes; retry only bounded concurrent-head conflicts."""
    from huggingface_hub import CommitOperationAdd
    from huggingface_hub.errors import EntryNotFoundError, HfHubHTTPError

    if dataset != DATASET_ID:
        raise PublicationError("publisher is restricted to the existing canonical dataset")
    if not 1 <= max_attempts <= 4:
        raise PublicationError("max_attempts must be between 1 and 4")
    lane = snapshot["source"]["name"]
    snapshot_id = snapshot["snapshot_id"]
    dated_path = f"snapshots/{lane}/{snapshot['created_at'][:10]}/{snapshot_id}"
    pointer_path = f"latest/{lane}.json"
    pointer = {
        "snapshot_id": snapshot_id, "created_at": snapshot["created_at"],
        "path": dated_path, "lane": lane,
        "files_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()},
    }
    pointer_bytes = (json.dumps(pointer, indent=2, sort_keys=True) + "\n").encode()
    for attempt in range(max_attempts):
        parent = api.repo_info(repo_id=dataset, repo_type="dataset", revision="main").sha
        if not isinstance(parent, str) or not SHA40.fullmatch(parent):
            raise PublicationError("dataset head is not an immutable revision")
        try:
            # list_repo_tree is lazy: iteration performs the request and raises 404.
            next(iter(api.list_repo_tree(repo_id=dataset, repo_type="dataset",
                                         path_in_repo=dated_path, revision=parent)), None)
        except EntryNotFoundError as exc:
            if getattr(exc.response, "status_code", None) != 404:
                raise
        else:
            raise PublicationError("immutable snapshot path already exists")
        try:
            local_pointer = api.hf_hub_download(repo_id=dataset, repo_type="dataset",
                                                filename=pointer_path, revision=parent)
        except EntryNotFoundError as exc:
            if getattr(exc.response, "status_code", None) != 404:
                raise
        else:
            with Path(local_pointer).open("rb") as stream:
                old_bytes = stream.read(MAX_POINTER_BYTES + 1)
            if len(old_bytes) > MAX_POINTER_BYTES:
                raise PublicationError("existing pointer exceeds the size budget")
            old = json.loads(old_bytes)
            if old.get("lane") != lane:
                raise PublicationError("existing pointer belongs to another lane")
            if _timestamp(old["created_at"]) > _timestamp(snapshot["created_at"]):
                raise PublicationError("refusing to regress the lane's latest snapshot")
        operations = [CommitOperationAdd(path_in_repo=f"{dated_path}/{name}",
                                          path_or_fileobj=data) for name, data in payloads.items()]
        operations.append(CommitOperationAdd(path_in_repo=pointer_path, path_or_fileobj=pointer_bytes))
        if lane == "echo-exporter":
            operations.append(CommitOperationAdd(path_in_repo="latest.json", path_or_fileobj=pointer_bytes))
        try:
            commit = api.create_commit(repo_id=dataset, repo_type="dataset", revision="main",
                                       parent_commit=parent, operations=operations,
                                       commit_message=f"federal-refresh: {lane} snapshot {snapshot_id}")
        except HfHubHTTPError as exc:
            if getattr(exc.response, "status_code", None) != 409 or attempt + 1 == max_attempts:
                raise
            time.sleep(0.25 * (2 ** attempt))
            continue
        return {"status": "PUBLISHED", "dataset": dataset, "revision": commit.oid,
                "path": dated_path, "pointer": pointer_path, "attempts": attempt + 1,
                "secret_values_recorded": False}
    raise PublicationError("concurrent publication attempts exhausted")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--snapshot", required=True)
    args = parser.parse_args(argv)
    try:
        if args.dataset != DATASET_ID:
            raise PublicationError("unexpected dataset target")
        snapshot, payloads = verified_bundle(Path(args.snapshot))
        token = os.environ.get("HF_TOKEN", "").strip()
        if not token:
            print(json.dumps({"status": "VERIFIED_NOT_PUBLISHED", "reason": "HF_TOKEN_NOT_SET"}))
            return 0
        from huggingface_hub import HfApi
        result = publish_bundle(HfApi(token=token), args.dataset, snapshot, payloads)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        # Provider exceptions can include URLs or headers; emit only the type.
        print(json.dumps({"status": "NOT_PUBLISHED", "error_type": type(exc).__name__,
                          "secret_values_recorded": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
