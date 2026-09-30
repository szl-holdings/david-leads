# SPDX-License-Identifier: Apache-2.0
"""Compatibility facade over the closed federal scheduled-snapshot verifier.

The retired raw-record format is deliberately unsupported. ECHO uses its own
v3 verifier in app.echo_snapshot; the other lanes use app.federal_snapshot.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from . import federal_snapshot as snapshots

DATASET_ID = snapshots.DATASET_ID


class StoreState(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    UNVERIFIED = "unverified"
    EMPTY = "empty"


@dataclass
class StoreResult:
    state: StoreState
    records: list[dict] = field(default_factory=list)
    snapshot_id: str | None = None
    created_at: str | None = None
    receipt: dict | None = None
    message: str = ""


def verify_snapshot_payload(snapshot: dict, receipt: dict, records: list[dict],
                            now: datetime | None = None) -> tuple[bool, str]:
    """Verify the complete current contract, never the deprecated raw schema."""
    try:
        payload = b"".join(snapshots.canonical(row) + b"\n" for row in records)
        snapshots.verify_bundle(snapshot, receipt, payload, now=now)
        return True, "ok"
    except snapshots.StaleSnapshot as exc:
        return False, str(exc)
    except (ValueError, TypeError, KeyError, AttributeError):
        return False, "snapshot contract or content verification failed"


class FederalRefreshStore:
    def __init__(self, loader=None, now=None, *, lane: str = "fmcsa"):
        if lane not in snapshots.LANES:
            raise snapshots.SnapshotError("unsupported scheduled snapshot lane")
        self.lane = lane
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._loader = loader or self.load_latest_from_hub

    def load_latest_from_hub(self) -> dict:
        return snapshots.load_verified(self.lane, now=self._now())

    def fetch_snapshot_organizations(self, states: list[str] | None = None,
                                     limit: int = 50) -> StoreResult:
        try:
            bundle = self._loader()
            if bundle is None:
                return StoreResult(StoreState.EMPTY, message="no snapshot available; refresh pending")
            snapshot = bundle["snapshot"]
            receipt = bundle["receipt"]
            payload = bundle.get("records_bytes")
            if payload is None:
                payload = b"".join(snapshots.canonical(row) + b"\n" for row in bundle["records"])
            verified = snapshots.verify_bundle(snapshot, receipt, payload, now=self._now())
            if snapshot["lane"] != self.lane:
                raise snapshots.SnapshotError("snapshot lane mismatch")
            wanted = {state.upper() for state in states} if states else set(snapshot["coverage"]["requested_states"])
            if not wanted <= set(snapshot["coverage"]["requested_states"]):
                raise snapshots.SnapshotError("selected state outside published coverage")
            records = [row for row in verified["records"] if row["state"] in wanted]
            return StoreResult(StoreState.FRESH, records=records[:max(1, min(int(limit), 50))],
                               snapshot_id=snapshot["snapshot_id"], created_at=snapshot["created_at"],
                               receipt=receipt)
        except snapshots.StaleSnapshot as exc:
            return StoreResult(StoreState.STALE, message=str(exc))
        except (ValueError, TypeError, KeyError, AttributeError):
            return StoreResult(StoreState.UNVERIFIED, message="snapshot failed verification; refresh pending")
        except Exception:
            return StoreResult(StoreState.EMPTY, message="snapshot unavailable; refresh pending")


@dataclass(frozen=True)
class DolSnapshotBundle:
    revision: str
    snapshot: dict
    receipt: dict
    records: tuple[dict, ...]
    observed_at: datetime
    expires_at: datetime
    signing_key_fingerprint: str


def _strict_json(data: bytes):
    from .domain.david_reference import Hold
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise Hold("SOURCE_SCHEMA_CHANGED")
            result[key] = value
        return result
    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, TypeError, UnicodeError):
        raise Hold("SOURCE_SCHEMA_CHANGED") from None


def load_dol_snapshot(revision: str, *, signing_key: bytes, now: datetime,
                      downloader=None, allow_stale: bool = False) -> DolSnapshotBundle:
    """Verify canonical DOL bytes plus private HMAC at one immutable dataset SHA.

    Uses the shared canonical snapshot verifier, retaining public projection,
    coverage, timing and receipt checks. The separate signature is required for
    operator admission even though public snapshot verification is unsigned.
    """
    import re
    from datetime import timedelta
    from pathlib import Path
    from . import dol_admission_signature as signatures
    from .domain.david_reference import Hold, aware
    now = aware(now)
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision) or revision == "0" * 40:
        raise Hold("SNAPSHOT_REVISION_REQUIRED")
    if type(signing_key) is not bytes or not 32 <= len(signing_key) <= 4096:
        raise Hold("SOURCE_SIGNING_KEY_NOT_CONFIGURED")
    budget = snapshots.MAX_BUNDLE_BYTES + 512 * 1024
    if downloader is None:
        def downloader(path, pinned_revision):
            from huggingface_hub import HfApi, hf_hub_download
            from .hf_dataset_transport import dataset_read_token
            # Admission must use the explicit dataset reader rather than a
            # developer's cached publisher or an overridden SDK endpoint.
            token = dataset_read_token() or False
            entries = HfApi(endpoint="https://huggingface.co", token=token).get_paths_info(
                DATASET_ID, [path], repo_type="dataset", revision=pinned_revision)
            if len(entries) != 1 or getattr(entries[0], "path", None) != path or type(getattr(entries[0], "size", None)) is not int or not 0 < entries[0].size <= budget:
                raise Hold("SOURCE_BYTE_BUDGET")
            local = hf_hub_download(DATASET_ID, path, repo_type="dataset", revision=pinned_revision,
                endpoint="https://huggingface.co", token=token)
            with Path(local).open("rb") as stream:
                return stream.read(budget + 1)
    def read(path, maximum):
        nonlocal budget
        try:
            data = downloader(path, revision)
        except Hold:
            raise
        except Exception:
            raise Hold("SOURCE_TRANSPORT_UNAVAILABLE") from None
        if type(data) is not bytes or len(data) > min(maximum, budget):
            raise Hold("SOURCE_BYTE_BUDGET")
        budget -= len(data)
        return data
    pointer = _strict_json(read("latest/form5500.json", 8192))
    if not isinstance(pointer, dict) or set(pointer) != {"pointer_version", "lane", "snapshot_id", "snapshot_digest", "created_at", "path"}:
        raise Hold("SOURCE_POINTER_SCHEMA")
    if (type(pointer["pointer_version"]) is not int or pointer["pointer_version"] != 1 or pointer["lane"] != "form5500"
            or not isinstance(pointer["path"], str) or not re.fullmatch(r"snapshots/form5500/\d{4}-\d{2}-\d{2}/[0-9a-f]{64}", pointer["path"])):
        raise Hold("SOURCE_POINTER_SCOPE")
    base = pointer["path"]
    snapshot = _strict_json(read(f"{base}/snapshot.json", 131072))
    receipt = _strict_json(read(f"{base}/receipt.json", 32768))
    records_bytes = read(f"{base}/records.jsonl", snapshots.MAX_BUNDLE_BYTES)
    # Authenticate exact canonical manifest and receipt before admitting any row.
    signature = _strict_json(read(f"{base}/{signatures.FILENAME}", 8192))
    try:
        signatures.verify(signature, snapshot, receipt, signing_key)
    except (snapshots.SnapshotError, TypeError, ValueError, KeyError):
        raise Hold("SOURCE_SIGNATURE_INVALID") from None
    try:
        if snapshot.get("lane") != "form5500" or snapshots.pointer_for(snapshot) != pointer:
            raise Hold("SOURCE_POINTER_SCOPE")
        verified = snapshots.verify_bundle(snapshot, receipt, records_bytes, now=now, allow_stale=allow_stale)
        observed = datetime.strptime(snapshot["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        expires = observed + timedelta(days=snapshots.FRESHNESS_DAYS)
        if observed > now:
            raise Hold("SOURCE_TIME_INVALID")
        if expires <= now and not allow_stale:
            raise Hold("SOURCE_STALE")
    except snapshots.StaleSnapshot:
        raise Hold("SOURCE_STALE") from None
    except (snapshots.SnapshotError, TypeError, ValueError, KeyError):
        raise Hold("SOURCE_INTEGRITY_FAILED") from None
    records = []
    for row in verified["records"]:
        identities = [item["value"] for item in row["authoritative_entity_ids"] if item["system"] == "DOL Form 5500 ACK ID"]
        if len(identities) != 1:
            raise Hold("SOURCE_MINIMIZATION_FAILED")
        # Keep the canonical row hash in classification evidence. This projection
        # never invents plan/form dates that the published snapshot does not retain.
        records.append({"source_record_id": "dol-5500:" + identities[0],
            "org_name": row["name"], "state": row["state"],
            "normalized_record_hash": row["normalized_record_hash"],
            "raw": {"participant_count": row["operational_snapshot"]["participants_reported"],
                    "reported_life_benefit": "Life" in row["operational_snapshot"]["benefit_categories"]}})
    return DolSnapshotBundle(revision, snapshot, receipt, tuple(records), observed, expires, hashlib.sha256(signing_key).hexdigest())
