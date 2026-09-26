"""Atomically publish one verified Federal Refresh snapshot to the HF Hub.

The local three-file bundle is verified before the first Hub request. Publication
uses a content-addressed path and one compare-and-swap commit, then downloads all
committed files from the returned immutable revision and verifies their
bytes before writing a local publication receipt.

Usage::

    python -m tools.ingestor.publish_snapshot \
      --dataset SZLHOLDINGS/david-leads-data \
      --snapshot snapshot \
      --receipt-out publication.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from tools.ingestor.verify_snapshot import verify as verify_echo

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_OID_RE = re.compile(r"^[0-9a-f]{40}$")
DATASET_ID = "SZLHOLDINGS/david-leads-data"
FILES = ("snapshot.json", "receipt.json", "records.jsonl")
MAX_BUNDLE_BYTES = 512 * 1024 * 1024
MAX_PRIOR_MANIFEST_BYTES = 128 * 1024


def verify(snapshot_dir: Path) -> int:
    snapshot = _load_snapshot(snapshot_dir)
    if snapshot.get("record_schema") == "federal-frontier-record-v1":
        from app.federal_snapshot import verify_bundle

        verify_bundle(snapshot, json.loads((snapshot_dir / "receipt.json").read_bytes()),
                      (snapshot_dir / "records.jsonl").read_bytes())
        return 0
    return verify_echo(snapshot_dir)


class PublicationError(RuntimeError):
    """A fail-closed publication precondition or verification failure."""


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _payload_metadata(payload: Path | bytes) -> dict[str, object]:
    if isinstance(payload, Path):
        return {"sha256": _sha256_file(payload), "size_bytes": payload.stat().st_size}
    return {"sha256": hashlib.sha256(payload).hexdigest(), "size_bytes": len(payload)}


def _load_snapshot(snapshot_dir: Path) -> dict[str, object]:
    try:
        value = json.loads(
            (snapshot_dir / "snapshot.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PublicationError("verified snapshot metadata could not be loaded") from exc
    if not isinstance(value, dict):
        raise PublicationError("snapshot metadata must be an object")
    return value


def _publication_prefix(snapshot: dict[str, object]) -> tuple[str, str]:
    digest = snapshot.get("snapshot_digest")
    snapshot_id = snapshot.get("snapshot_id")
    created_at = snapshot.get("created_at")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise PublicationError("snapshot_digest is not a lowercase SHA-256 digest")
    if snapshot_id != f"sha256:{digest}":
        raise PublicationError("snapshot_id is not bound to snapshot_digest")
    try:
        created = datetime.strptime(str(created_at), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise PublicationError("created_at is not canonical UTC") from exc
    lane = snapshot.get("lane")
    if lane is not None:
        from app.federal_snapshot import LANES

        if lane not in LANES:
            raise PublicationError("unknown federal lane")
        return f"snapshots/{lane}/{created:%Y-%m-%d}/{digest}", digest
    return f"snapshots/{created:%Y-%m-%d}/{digest}", digest


def _pointer(snapshot: dict[str, object], prefix: str) -> dict[str, object]:
    if snapshot.get("record_schema") == "federal-frontier-record-v1":
        from app.federal_snapshot import pointer_for

        return pointer_for(snapshot)
    required = (
        "snapshot_id",
        "snapshot_digest",
        "created_at",
        "record_count",
        "records_root_sha256",
        "records_file_sha256",
    )
    if any(key not in snapshot for key in required):
        raise PublicationError("snapshot is missing latest-pointer bindings")
    return {
        "pointer_version": 1,
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot_digest": snapshot["snapshot_digest"],
        "created_at": snapshot["created_at"],
        "record_count": snapshot["record_count"],
        "records_root_sha256": snapshot["records_root_sha256"],
        "records_file_sha256": snapshot["records_file_sha256"],
        "path": prefix,
    }


def _require_echo_source_progression(
    api: Any,
    dataset_id: str,
    parent_commit: str,
    current_pointer: dict[str, object],
    snapshot: dict[str, object],
    token: str,
) -> None:
    """Reject older EPA exports using the manifest served by the pinned parent."""
    pointer_keys = {
        "pointer_version", "snapshot_id", "snapshot_digest", "created_at",
        "record_count", "records_root_sha256", "records_file_sha256", "path",
    }
    if set(current_pointer) != pointer_keys or type(current_pointer["pointer_version"]) is not int or current_pointer["pointer_version"] != 1:
        raise PublicationError("existing ECHO pointer schema is invalid")
    prefix, _ = _publication_prefix(current_pointer)
    if current_pointer["path"] != prefix:
        raise PublicationError("existing ECHO pointer path binding is invalid")
    filename = f"{prefix}/snapshot.json"
    entries = api.get_paths_info(
        repo_id=dataset_id, repo_type="dataset", paths=[filename],
        revision=parent_commit,
    )
    if len(entries) != 1 or getattr(entries[0], "path", None) != filename:
        raise PublicationError("existing ECHO manifest is missing")
    remote_size = getattr(entries[0], "size", None)
    if type(remote_size) is not int or not 0 < remote_size <= MAX_PRIOR_MANIFEST_BYTES:
        raise PublicationError("existing ECHO manifest exceeds metadata budget")
    downloaded = api.hf_hub_download(
        repo_id=dataset_id, repo_type="dataset", filename=filename,
        revision=parent_commit, token=token,
    )
    with Path(downloaded).open("rb") as handle:
        encoded = handle.read(MAX_PRIOR_MANIFEST_BYTES + 1)
    if len(encoded) != remote_size or len(encoded) > MAX_PRIOR_MANIFEST_BYTES:
        raise PublicationError("existing ECHO manifest size binding is invalid")
    try:
        previous = json.loads(encoded)
        if not isinstance(previous, dict):
            raise ValueError("non-object manifest")
        previous_prefix, previous_digest = _publication_prefix(previous)
        core = {key: value for key, value in previous.items() if key not in {"snapshot_id", "snapshot_digest"}}
        actual_digest = hashlib.sha256(json.dumps(
            core, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")).hexdigest()
        if previous_prefix != prefix or previous_digest != actual_digest or _pointer(previous, prefix) != current_pointer:
            raise ValueError("manifest pointer or content binding mismatch")
        previous_source = previous["source"]
        next_source = snapshot["source"]
        if previous_source["name"] != "echo-exporter" or next_source["name"] != "echo-exporter":
            raise ValueError("source identity mismatch")
        previous_as_of = datetime.strptime(previous_source["source_as_of"], "%Y-%m-%d").date()
        next_as_of = datetime.strptime(next_source["source_as_of"], "%Y-%m-%d").date()
        if previous_as_of.isoformat() != previous_source["source_as_of"] or next_as_of.isoformat() != next_source["source_as_of"]:
            raise ValueError("noncanonical source date")
        previous_created = datetime.strptime(previous["created_at"], "%Y-%m-%dT%H:%M:%SZ").date()
        if previous_as_of > previous_created:
            raise ValueError("source date follows manifest creation")
    except (KeyError, TypeError, ValueError, UnicodeError) as exc:
        raise PublicationError("existing ECHO manifest integrity or source date is invalid") from exc
    if next_as_of < previous_as_of:
        raise PublicationError("refusing to regress the ECHO source export date")


def _dataset_card(snapshot: dict[str, object], prefix: str) -> bytes:
    """Render the investor-readable Hub card without asserting a data license."""

    return (
        "---\n"
        "pretty_name: David Leads Verified Federal Refresh\n"
        "tags:\n"
        "- public-data\n"
        "- insurance\n"
        "- provenance\n"
        "- data-governance\n"
        "---\n\n"
        "# David Leads — verified Federal Refresh\n\n"
        "This dataset holds scheduled public-data inputs for the "
        "[David Leads](https://huggingface.co/spaces/SZLHOLDINGS/david-leads) "
        "broker-research demo. The EPA lane uses the official weekly ECHO Exporter. "
        "DOL uses published Form 5500 disclosures; FMCSA and USAspending use "
        "bounded captures from their official APIs. Coverage is declared per snapshot.\n\n"
        "Each lane is available only after verified publication: "
        "`latest/echo-exporter.json`, `latest/fmcsa.json`, `latest/form5500.json`, "
        "and `latest/usaspending.json`. `latest.json` is the ECHO compatibility pointer.\n\n"
        "## Latest EPA ECHO export\n\n"
        f"- Current snapshot: `{snapshot['snapshot_id']}`\n"
        f"- Source export date: `{snapshot['source']['source_as_of']}`\n"
        f"- Processed at: `{snapshot['created_at']}`\n"
        f"- Records: `{snapshot['record_count']}`\n"
        f"- Immutable path: `{prefix}`\n"
        f"- Parser source: `{snapshot['parser']['source_revision']}`\n\n"
        "## Truth and safety boundary\n\n"
        "The ECHO records contain minimized organization/facility facts and inspection "
        "dates for research. They exclude street addresses, coordinates, people, "
        "contacts, demographics, compliance or violation conclusions, enforcement, "
        "penalties, emissions, insurance fields, and risk scores. A record is never "
        "contact permission or an underwriting fact.\n\n"
        "Facility names are official EPA free text, so the ingestor also applies these "
        "exclusions to the name with a heuristic screen. It rejects rows with NAICS "
        "814110, a residential permit designation or dwelling word, a house or grid "
        "number with a street type or numbered route, or a personal-name shape (a "
        "common given name, an initial, a surname-first or honorific form, or a "
        "personal trust, estate, or heirs designation) without an organization word, "
        "and counts them as `PERSON_OR_RESIDENCE_NAME` in `snapshot.json`. The screen "
        "is not identity resolution: it can drop an organization whose name reads like "
        "a person, and it cannot recognize every personal name. It applies to "
        "snapshots built by a parser revision that includes it.\n\n"
        "`latest.json` points to a content-addressed directory. `snapshot.json` "
        "binds the upstream ZIP hash, exact parser revision, projection policy, "
        "record count, ordered record root, and exact JSONL byte hash. "
        "`receipt.json` is a PurIQ v1 payload-integrity receipt. It is explicitly "
        "`UNSIGNED`; GitHub OIDC provenance is retained separately by the publisher "
        "workflow and an unsigned receipt is never described as an authenticated "
        "signature.\n\n"
        "Source-data permission and repository code licensing are separate. Review "
        "the [EPA ECHO data downloads](https://echo.epa.gov/tools/data-downloads) "
        "and the source repository's Apache-2.0 license before reuse.\n"
    ).encode("utf-8")


def _write_publication_receipt(path: Path, receipt: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise PublicationError("publication receipt already exists") from exc


def _default_bindings(
    token: str,
) -> tuple[Any, Callable[..., object], type[BaseException]]:
    # Imported only after strict local verification, so a missing optional SDK
    # cannot weaken or replace the local bundle gate.
    from huggingface_hub import CommitOperationAdd, HfApi
    from huggingface_hub.errors import RemoteEntryNotFoundError

    return HfApi(token=token), CommitOperationAdd, RemoteEntryNotFoundError


def _publish_frozen(
    dataset_id: str,
    snapshot_dir: Path,
    publication_receipt: Path,
    *,
    token: str,
    api_factory: Callable[[str], Any] | None = None,
    operation_factory: Callable[..., object] | None = None,
    remote_entry_not_found: type[BaseException] | None = None,
    verifier: Callable[[Path], int] = verify,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """Verify, atomically publish, read back, and receipt one snapshot.

    Injectable Hub bindings make the transaction fully testable without network
    access. Only remote_entry_not_found is interpreted as proof that the
    immutable target prefix is absent; every other Hub failure propagates.
    """

    if not isinstance(token, str) or not token.strip():
        raise PublicationError("HF_TOKEN is required")

    snapshot_dir = snapshot_dir.resolve()
    publication_receipt = publication_receipt.resolve()
    if publication_receipt == snapshot_dir or snapshot_dir in publication_receipt.parents:
        raise PublicationError("publication receipt must be outside the snapshot bundle")
    if publication_receipt.exists():
        raise PublicationError("publication receipt already exists")

    # This is intentionally before API construction and every Hub call.
    if verifier(snapshot_dir) != 0:
        raise PublicationError("strict local snapshot verification failed")

    snapshot = _load_snapshot(snapshot_dir)
    prefix, digest = _publication_prefix(snapshot)
    latest_bytes = _canonical_json(_pointer(snapshot, prefix))
    lane = str(snapshot.get("lane") or "echo-exporter")
    pointer_path = f"latest/{lane}.json"
    payloads: dict[str, Path | bytes] = {
        f"{prefix}/snapshot.json": snapshot_dir / "snapshot.json",
        f"{prefix}/receipt.json": snapshot_dir / "receipt.json",
        f"{prefix}/records.jsonl": snapshot_dir / "records.jsonl",
        pointer_path: latest_bytes,
    }
    if lane == "echo-exporter":
        payloads["latest.json"] = latest_bytes
        payloads["README.md"] = _dataset_card(snapshot, prefix)
    file_metadata = {
        remote_path: _payload_metadata(payload)
        for remote_path, payload in payloads.items()
    }

    if api_factory is None:
        api, default_operation, default_not_found = _default_bindings(token)
        operation_factory = operation_factory or default_operation
        remote_entry_not_found = remote_entry_not_found or default_not_found
    else:
        api = api_factory(token)
    if operation_factory is None or remote_entry_not_found is None:
        raise TypeError("injected API requires operation and not-found bindings")

    api.create_repo(
        repo_id=dataset_id,
        repo_type="dataset",
        exist_ok=True,
        private=False,
    )
    repo_info = api.repo_info(
        repo_id=dataset_id,
        repo_type="dataset",
        revision="main",
    )
    parent_commit = getattr(repo_info, "sha", None)
    if not isinstance(parent_commit, str) or not _GIT_OID_RE.fullmatch(parent_commit):
        raise PublicationError("Hub main did not resolve to an exact Git commit")

    try:
        # list_repo_tree is lazy; consuming it is required to observe a remote 404.
        list(
            api.list_repo_tree(
                repo_id=dataset_id,
                repo_type="dataset",
                path_in_repo=prefix,
                revision=parent_commit,
            )
        )
    except remote_entry_not_found:
        pass
    else:
        raise PublicationError("content-addressed snapshot prefix already exists")

    try:
        current_pointer_file = api.hf_hub_download(
            # ECHO runtime consumes this compatibility pointer, including datasets
            # created before the per-lane alias existed.
            repo_id=dataset_id, repo_type="dataset",
            filename="latest.json" if lane == "echo-exporter" else pointer_path,
            revision=parent_commit, token=token,
        )
    except remote_entry_not_found:
        pass
    else:
        with Path(current_pointer_file).open("rb") as current_file:
            encoded = current_file.read(16_385)
        if len(encoded) > 16_384:
            raise PublicationError("existing pointer exceeds metadata budget")
        current = json.loads(encoded)
        previous_date = datetime.strptime(current["created_at"], "%Y-%m-%dT%H:%M:%SZ")
        next_date = datetime.strptime(str(snapshot["created_at"]), "%Y-%m-%dT%H:%M:%SZ")
        if previous_date > next_date:
            raise PublicationError("refusing to regress the lane latest pointer")
        if lane == "echo-exporter":
            _require_echo_source_progression(
                api, dataset_id, parent_commit, current, snapshot, token,
            )

    operations = [
        operation_factory(path_in_repo=remote_path, path_or_fileobj=payload)
        for remote_path, payload in payloads.items()
    ]
    commit_info = api.create_commit(
        repo_id=dataset_id,
        repo_type="dataset",
        revision="main",
        parent_commit=parent_commit,
        operations=operations,
        commit_message=f"federal-refresh: publish sha256:{digest}",
    )
    published_commit = getattr(commit_info, "oid", None)
    if not isinstance(published_commit, str) or not _GIT_OID_RE.fullmatch(
        published_commit
    ):
        raise PublicationError("Hub commit response did not contain an exact Git OID")

    with tempfile.TemporaryDirectory(prefix="david-hf-readback-") as readback_dir:
        for remote_path, expected in file_metadata.items():
            downloaded = Path(
                api.hf_hub_download(
                    repo_id=dataset_id,
                    filename=remote_path,
                    repo_type="dataset",
                    revision=published_commit,
                    token=token,
                    local_dir=readback_dir,
                    force_download=True,
                )
            )
            if not downloaded.is_file():
                raise PublicationError("pinned Hub readback did not return a file")
            if downloaded.stat().st_size != expected["size_bytes"]:
                raise PublicationError("pinned Hub readback size mismatch")
            if _sha256_file(downloaded) != expected["sha256"]:
                raise PublicationError("pinned Hub readback hash mismatch")

    now = clock() if clock is not None else datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise PublicationError("publication clock must be timezone-aware")
    publication = {
        "publication_version": 1,
        "status": "VERIFIED_PUBLISHED",
        "published_at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataset_id": dataset_id,
        "revision": "main",
        "observed_parent_commit": parent_commit,
        "published_commit": published_commit,
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot_digest": digest,
        "path": prefix,
        "files": file_metadata,
        "verification": {
            "local_bundle": "PASS",
            "pinned_hub_readback": "PASS",
        },
    }
    _write_publication_receipt(publication_receipt, publication)
    return publication


def publish_snapshot(
    dataset_id: str,
    snapshot_dir: Path,
    publication_receipt: Path,
    *,
    token: str,
    api_factory: Callable[[str], Any] | None = None,
    operation_factory: Callable[..., object] | None = None,
    remote_entry_not_found: type[BaseException] | None = None,
    verifier: Callable[[Path], int] = verify,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """Freeze one bounded bundle, verify those bytes, and publish those bytes."""
    if dataset_id != DATASET_ID:
        raise PublicationError("publisher is restricted to the canonical dataset")
    if not isinstance(token, str) or not token.strip():
        raise PublicationError("HF_TOKEN is required")
    if snapshot_dir.is_symlink():
        raise PublicationError("snapshot directory must not be a symlink")
    source = snapshot_dir.resolve(strict=True)
    output = publication_receipt.resolve()
    if output == source or source in output.parents or output.exists():
        raise PublicationError("publication receipt must be new and outside the bundle")
    if {p.name for p in source.iterdir()} != set(FILES):
        raise PublicationError("snapshot directory file set mismatch")
    if clock is not None and clock().tzinfo is None:
        raise PublicationError("publication clock must be timezone-aware")
    with tempfile.TemporaryDirectory(prefix="david-publication-frozen-") as folder:
        frozen = Path(folder)
        remaining = MAX_BUNDLE_BYTES
        for name in FILES:
            original = source / name
            if original.is_symlink() or not original.is_file():
                raise PublicationError("snapshot files must be regular files")
            with original.open("rb") as incoming, (frozen / name).open("xb") as outgoing:
                while True:
                    chunk = incoming.read(min(1024 * 1024, remaining + 1))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    if remaining < 0:
                        raise PublicationError("snapshot exceeds publication byte budget")
                    outgoing.write(chunk)
        return _publish_frozen(
            dataset_id, frozen, output, token=token,
            api_factory=api_factory, operation_factory=operation_factory,
            remote_entry_not_found=remote_entry_not_found,
            verifier=verifier, clock=clock,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        required=True,
        help="HF Dataset repo id, e.g. SZLHOLDINGS/david-leads-data",
    )
    parser.add_argument("--snapshot", required=True, help="Verified snapshot directory")
    parser.add_argument(
        "--receipt-out",
        required=True,
        help="New publication receipt path outside the snapshot directory",
    )
    args = parser.parse_args()

    token = os.environ.get("HF_TOKEN", "")
    try:
        publication = publish_snapshot(
            args.dataset,
            Path(args.snapshot),
            Path(args.receipt_out),
            token=token,
        )
    except Exception as exc:  # Deliberately omit exception text: it may be remote-controlled.
        print(
            f"FAIL: publication aborted ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 1

    print(
        "OK: verified publication "
        f"{publication['snapshot_id']} at {publication['dataset_id']}/"
        f"{publication['path']} commit={publication['published_commit']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
