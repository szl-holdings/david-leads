"""Federal Refresh dataset-backed store for the David Leads Space.

Reads the latest verified snapshot from SZLHOLDINGS/david-leads-data instead of
calling live federal sources at runtime (david-leads #103, PRs #104/#105).

Estate-law properties:
- Verification before service: every snapshot is checked with the same rules
  as tools.ingestor.verify_snapshot (per-record content hash, chain, receipt,
  gate, staleness). A snapshot that fails verification is never served.
- Honest staleness: when no verified fresh snapshot exists, the store reports
  STALE/EMPTY and the UI renders its existing placeholder — never fabricated
  or sample data.
- No live-web fallback: this module reads the HF Dataset only. There is no
  code path from here to the federal sources.

Interface mirrors the lane-fetch shape used in app/frontier_sources.py:
    fetch_* (states: list[str], limit: int) -> list[dict]
Here: fetch_snapshot_organizations(states, limit) -> StoreResult
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

DATASET_ID = "SZLHOLDINGS/david-leads-data"


class StoreState(str, Enum):
    FRESH = "fresh"            # verified snapshot within freshness window
    STALE = "stale"            # verified but past freshness window
    UNVERIFIED = "unverified"  # failed verification — never served
    EMPTY = "empty"            # no snapshot available


@dataclass
class StoreResult:
    state: StoreState
    records: list[dict] = field(default_factory=list)
    snapshot_id: str | None = None
    created_at: str | None = None
    receipt: dict | None = None
    message: str = ""


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _record_hash(r: dict) -> str:
    return hashlib.sha256(_canonical({
        "source_record_id": r["source_record_id"],
        "org_name": r["org_name"],
        "state": r["state"],
        "raw": r["raw"],
    })).hexdigest()


def verify_snapshot_payload(snapshot: dict, receipt: dict, records: list[dict],
                            now: datetime | None = None) -> tuple[bool, str]:
    """Same six checks as tools.ingestor.verify_snapshot, in-process."""
    now = now or datetime.now(timezone.utc)
    for i, r in enumerate(records):
        if _record_hash(r) != r.get("normalized_record_hash"):
            return False, f"record {i} content hash mismatch"
    records_hash = hashlib.sha256(_canonical([r["normalized_record_hash"] for r in records])).hexdigest()
    if records_hash != snapshot.get("records_hash"):
        return False, "records_hash mismatch"
    body = {k: v for k, v in receipt.items() if k not in ("payload_hash", "signature")}
    if hashlib.sha256(_canonical(body)).hexdigest() != receipt.get("payload_hash"):
        return False, "receipt payload_hash mismatch"
    sig = receipt.get("signature", {})
    if sig.get("value") != "UNSIGNED" and sig.get("key_id") is None:
        return False, "signed receipt missing key_id"
    if receipt.get("gate", {}).get("result") != "pass":
        return False, "receipt on gate failure"
    created = datetime.strptime(snapshot["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    if (now - created).total_seconds() / 86400 > snapshot.get("freshness_days", 8):
        return False, "stale"
    return True, "ok"


class FederalRefreshStore:
    """Dataset-backed store. `loader` is injected for testability; production
    uses load_latest_from_hub()."""

    def __init__(self, loader, now=None):
        self._loader = loader
        self._now = now or (lambda: datetime.now(timezone.utc))

    def load_latest_from_hub(self) -> dict | None:
        """Production loader: fetch latest.json + dated snapshot from the HF Dataset.
        Returns None when the dataset or pointer is unavailable (honest EMPTY)."""
        try:
            from huggingface_hub import hf_hub_download
            pointer_path = hf_hub_download(DATASET_ID, "latest.json", repo_type="dataset")
            pointer = json.loads(open(pointer_path).read())
            base = pointer["path"]
            out = {}
            for name in ("snapshot.json", "receipt.json", "records.jsonl"):
                p = hf_hub_download(DATASET_ID, f"{base}/{name}", repo_type="dataset")
                out[name] = open(p, "rb").read()
            return {
                "snapshot": json.loads(out["snapshot.json"]),
                "receipt": json.loads(out["receipt.json"]),
                "records": [json.loads(l) for l in out["records.jsonl"].decode().splitlines() if l],
            }
        except Exception:
            return None

    def fetch_snapshot_organizations(self, states: list[str] | None = None,
                                     limit: int = 50) -> StoreResult:
        bundle = self._loader()
        if bundle is None:
            return StoreResult(StoreState.EMPTY, message="no snapshot available; refresh pending")
        ok, why = verify_snapshot_payload(bundle["snapshot"], bundle["receipt"],
                                          bundle["records"], now=self._now())
        if not ok:
            if why == "stale":
                return StoreResult(StoreState.STALE,
                                   snapshot_id=bundle["snapshot"]["snapshot_id"],
                                   created_at=bundle["snapshot"]["created_at"],
                                   receipt=bundle["receipt"],
                                   message=f"data as of {bundle['snapshot']['created_at']}, refresh pending")
            return StoreResult(StoreState.UNVERIFIED,
                               snapshot_id=bundle["snapshot"].get("snapshot_id"),
                               message=f"snapshot failed verification: {why}")
        records = bundle["records"]
        if states:
            wanted = {s.upper() for s in states}
            records = [r for r in records if (r.get("state") or "").upper() in wanted]
        return StoreResult(StoreState.FRESH,
                           records=records[:limit],
                           snapshot_id=bundle["snapshot"]["snapshot_id"],
                           created_at=bundle["snapshot"]["created_at"],
                           receipt=bundle["receipt"])

# DOL v2 uses a separate exact-revision verifier. The ECHO compatibility reader
# above is deliberately not promoted to this stronger contract by implication.
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
    """Fetch publisher lane pointer and all bytes at the same immutable Hub SHA.

    Tests inject a downloader returning bytes. Production downloads only paths
    constructed from the closed dataset/lane contract; no caller URL is used.
    A valid HMAC proves possession of the configured key, not a public signature.
    """
    import hmac
    import re
    from datetime import timedelta
    from pathlib import Path
    from .domain.david_reference import Hold, aware
    # This contract must be available in the app-only production image.
    DOL_PARSER_VERSION = "2.0.0"
    SAFE_FIELDS = frozenset({"form_year", "plan_year_begin", "plan_year_end", "amended_filing", "participant_count", "reported_life_benefit"})
    now = aware(now)
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise Hold("SNAPSHOT_REVISION_REQUIRED")
    if not isinstance(signing_key, bytes) or len(signing_key) < 32:
        raise Hold("SOURCE_SIGNING_KEY_NOT_CONFIGURED")
    budget = 64 * 1024 * 1024
    if downloader is None:
        def downloader(path, pinned_revision):
            from huggingface_hub import HfApi, hf_hub_download
            # Metadata avoids beginning a known oversized download.
            entries = HfApi().get_paths_info(DATASET_ID, [path], repo_type="dataset", revision=pinned_revision)
            if len(entries) != 1 or type(getattr(entries[0], "size", None)) is not int or entries[0].size > budget:
                raise Hold("SOURCE_BYTE_BUDGET")
            local = hf_hub_download(DATASET_ID, path, repo_type="dataset", revision=pinned_revision)
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
        if not isinstance(data, bytes) or len(data) > min(maximum, budget):
            raise Hold("SOURCE_BYTE_BUDGET")
        budget -= len(data)
        return data
    pointer = _strict_json(read("latest/dol-5500-bulk.json", 16 * 1024))
    if not isinstance(pointer, dict) or set(pointer) != {"snapshot_id", "created_at", "path", "lane", "files_sha256"}:
        raise Hold("SOURCE_POINTER_SCHEMA")
    if pointer["lane"] != "dol-5500-bulk" or not isinstance(pointer["path"], str) or not re.fullmatch(r"snapshots/dol-5500-bulk/\d{4}-\d{2}-\d{2}/[A-Za-z0-9][A-Za-z0-9_-]{0,95}", pointer["path"]):
        raise Hold("SOURCE_POINTER_SCOPE")
    files = ("snapshot.json", "receipt.json", "records.jsonl")
    if not isinstance(pointer["files_sha256"], dict) or set(pointer["files_sha256"]) != set(files):
        raise Hold("SOURCE_POINTER_HASHES")
    payloads = {}
    for name in files:
        data = read(f"{pointer['path']}/{name}", 64 * 1024 * 1024 if name == "records.jsonl" else 256 * 1024)
        if not hmac.compare_digest(hashlib.sha256(data).hexdigest(), str(pointer["files_sha256"][name])):
            raise Hold("SOURCE_INTEGRITY_FAILED")
        payloads[name] = data
    snapshot = _strict_json(payloads["snapshot.json"])
    receipt = _strict_json(payloads["receipt.json"])
    lines = payloads["records.jsonl"].splitlines()
    if len(lines) > 100_000 or any(len(line) > 16_384 for line in lines):
        raise Hold("SOURCE_ROW_BUDGET")
    records = [_strict_json(line) for line in lines if line.strip()]
    try:
        if (snapshot["snapshot_version"] != 1 or snapshot["parser_version"] != DOL_PARSER_VERSION
                or snapshot["source"]["name"] != "dol-5500-bulk"
                or snapshot["source"]["url"] != "https://www.dol.gov/agencies/ebsa/about-ebsa/our-activities/public-disclosure/foia/form-5500-datasets"
                or not re.fullmatch(r"[0-9a-f]{64}", snapshot["source"]["upstream_bytes_sha256"])
                or snapshot["snapshot_id"] != pointer["snapshot_id"]
                or snapshot["created_at"] != pointer["created_at"]
                or pointer["path"] != f"snapshots/dol-5500-bulk/{snapshot['created_at'][:10]}/{snapshot['snapshot_id']}"):
            raise Hold("SOURCE_SCHEMA_CHANGED")
        if (type(snapshot["record_count"]) is not int or snapshot["record_count"] != len(records)
                or snapshot["counts"]["accepted"] != len(records)
                or set(snapshot["counts"]) != {"rows_seen", "accepted", "rejected", "quarantined"}
                or any(type(v) is not int or v < 0 for v in snapshot["counts"].values())
                or snapshot["counts"]["rows_seen"] != sum(snapshot["counts"][k] for k in ("accepted", "rejected", "quarantined"))):
            raise Hold("SOURCE_COMPLETENESS_FAILED")
        if snapshot["completeness"] != "COMPLETE" or snapshot["counts"]["quarantined"]:
            raise Hold("SOURCE_PARTIAL")
        observed = datetime.strptime(snapshot["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        days = snapshot["freshness_days"]
        if type(days) is not int or not 1 <= days <= 35 or observed > now:
            raise Hold("SOURCE_TIME_INVALID")
        expires = observed + timedelta(days=days)
        if expires <= now and not allow_stale:
            raise Hold("SOURCE_STALE")
        ids = set()
        for record in records:
            if (not isinstance(record, dict) or set(record) != {"source_record_id", "org_name", "state", "raw", "normalized_record_hash", "parser_version", "source_receipt"}
                    or not isinstance(record["raw"], dict) or not set(record["raw"]) <= SAFE_FIELDS
                    or record["parser_version"] != DOL_PARSER_VERSION
                    or not re.fullmatch(r"dol-5500:[A-Za-z0-9_-]{1,96}", record["source_record_id"])
                    or record["source_record_id"] in ids
                    or not isinstance(record["org_name"], str) or not 1 <= len(record["org_name"]) <= 240
                    or not re.fullmatch(r"[A-Z]{2}", record["state"])
                    or any(not isinstance(v, (str, int, bool)) for v in record["raw"].values())):
                raise Hold("SOURCE_MINIMIZATION_FAILED")
            ids.add(record["source_record_id"])
            if _record_hash(record) != record["normalized_record_hash"]:
                raise Hold("SOURCE_INTEGRITY_FAILED")
            expected_source_receipt = hashlib.sha256(_canonical({
                "upstream_bytes_sha256": snapshot["source"]["upstream_bytes_sha256"],
                "source_record_id": record["source_record_id"],
            })).hexdigest()
            if record["source_receipt"] != expected_source_receipt:
                raise Hold("SOURCE_INTEGRITY_FAILED")
        if hashlib.sha256(_canonical([r["normalized_record_hash"] for r in records])).hexdigest() != snapshot["records_hash"]:
            raise Hold("SOURCE_INTEGRITY_FAILED")
        body = {k: v for k, v in receipt.items() if k not in {"payload_hash", "signature"}}
        payload_hash = hashlib.sha256(_canonical(body)).hexdigest()
        subject = receipt["subject"]
        if (payload_hash != receipt["payload_hash"] or subject["source_record_id"] != snapshot["snapshot_id"]
                or subject["normalized_record_hash"] != snapshot["records_hash"]
                or subject["snapshot_sha256"] != hashlib.sha256(_canonical(snapshot)).hexdigest()
                or subject["parser_version"] != DOL_PARSER_VERSION or receipt["issued_at"] != snapshot["created_at"]
                or receipt["ranking_inputs"]["source_path"] != ["dol-5500-bulk"]
                or receipt["gate"] != {"name": "yuyay-13", "result": "pass", "failures": []}):
            raise Hold("SOURCE_RECEIPT_BINDING_FAILED")
        signature = receipt["signature"]
        expected = hmac.new(signing_key, bytes.fromhex(payload_hash), hashlib.sha256).hexdigest()
        if (signature.get("algorithm") != "HMAC-SHA256" or signature.get("key_id") != "receipt-signing-key"
                or not isinstance(signature.get("value"), str) or not hmac.compare_digest(expected, signature["value"])):
            raise Hold("SOURCE_SIGNATURE_INVALID")
    except Hold:
        raise
    except (KeyError, TypeError, ValueError, OverflowError):
        raise Hold("SOURCE_SCHEMA_CHANGED") from None
    return DolSnapshotBundle(revision, snapshot, receipt, tuple(records), observed, expires, hashlib.sha256(signing_key).hexdigest())
