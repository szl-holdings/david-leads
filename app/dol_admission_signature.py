"""Private-admission authentication of the canonical federal DOL projection.

The public PurIQ receipt remains explicitly unsigned. This separate HMAC proves
possession of a configured deployment key, not a public signature or data rights.
"""
from __future__ import annotations

import hashlib
import hmac

from . import federal_snapshot as snapshots

FILENAME = "admission-signature.json"


def sign(snapshot: dict, receipt: dict, signing_key: bytes) -> dict:
    if type(signing_key) is not bytes or not 32 <= len(signing_key) <= 4096:
        raise snapshots.SnapshotError("DOL admission signing key is not configured")
    if snapshot.get("lane") != "form5500":
        raise snapshots.SnapshotError("DOL admission signature requires form5500")
    body = {
        "schema": "szl.david.dol-admission-signature/v1",
        "algorithm": "HMAC-SHA256",
        "key_id": hashlib.sha256(signing_key).hexdigest(),
        "snapshot_sha256": snapshots.digest(snapshots.canonical(snapshot)),
        "receipt_sha256": snapshots.digest(snapshots.canonical(receipt)),
        "records_file_sha256": snapshot["records_file_sha256"],
        "parser_source_revision": snapshot["parser"]["source_revision"],
    }
    return {**body, "value": hmac.new(signing_key, snapshots.canonical(body), hashlib.sha256).hexdigest()}


def verify(value: dict, snapshot: dict, receipt: dict, signing_key: bytes) -> None:
    expected = sign(snapshot, receipt, signing_key)
    if not isinstance(value, dict) or not hmac.compare_digest(snapshots.canonical(value), snapshots.canonical(expected)):
        raise snapshots.SnapshotError("DOL admission signature is invalid")
