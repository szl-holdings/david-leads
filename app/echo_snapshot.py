# SPDX-License-Identifier: Apache-2.0
"""Fail-closed reader for the published EPA ECHO Federal Refresh dataset.

The Space never calls EPA's transactional web API.  It follows the public
Hugging Face ``latest.json`` pointer to an immutable snapshot and verifies the
complete bundle before returning any record.  Verification is deliberately
self-contained because the production image copies ``app/`` but not the
ingestion tooling.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any, BinaryIO


DATASET_REPO_ID = "SZLHOLDINGS/david-leads-data"
DATASET_BASE_URL = (
    "https://huggingface.co/datasets/"
    f"{DATASET_REPO_ID}/resolve/main"
)
DATASET_LANDING_URL = f"https://huggingface.co/datasets/{DATASET_REPO_ID}"
ECHO_EXPORTER_URL = "https://echo.epa.gov/files/echodownloads/echo_exporter.zip"
ECHO_MEMBER_NAME = "ECHO_EXPORTER.csv"
PARSER_NAME = "david-leads-echo-exporter"
PARSER_VERSION = "3.0.0"
RECORD_SCHEMA = "szl.david-leads.echo-facility/v3"
FRESHNESS_DAYS = 8
MAX_INSPECTION_AGE_DAYS = 365
MAX_METADATA_BYTES = 1_000_000
MAX_SERIALIZED_RECORD_BYTES = 8_192
MAX_RECORD_COUNT = 500_000
MAX_RECORDS_FILE_BYTES = 512 * 1024 * 1024
HTTP_TIMEOUT_SECONDS = 30
USER_AGENT = "SZL-David-Leads/1.3 research@szlholdings.com"

TARGET_STATES = frozenset(
    "AL CT DC DE FL GA IL IN KY ME MD MA MI MS NH NJ NY NC OH PA RI SC TN VT VA WV WI".split()
)
PROGRAMS = frozenset({"AIR", "NPDES", "SDWIS", "RCRA", "TRI", "GHG"})
RECORD_PAYLOAD_FIELDS = (
    "source_record_id",
    "org_name",
    "city",
    "state",
    "postal_code",
    "county",
    "epa_region",
    "last_inspection_date",
    "days_since_last_inspection",
    "inspection_count",
    "naics_codes",
    "programs",
    "facility_report_url",
)
RECORD_METADATA_FIELDS = (
    "normalized_record_hash",
    "parser_version",
    "projection_policy_sha256",
    "source_receipt",
)
SERIALIZED_RECORD_FIELDS = RECORD_PAYLOAD_FIELDS + RECORD_METADATA_FIELDS
PROJECTION_POLICY = {
    "policy": "szl.david-leads.echo-projection/v1",
    "serialized_record_fields": list(RECORD_PAYLOAD_FIELDS),
    "admission": {
        "official_registry_id_required": True,
        "active_only": True,
        "federal_facilities_excluded": True,
        "inspection_age_days_max": MAX_INSPECTION_AGE_DAYS,
        "target_states": sorted(TARGET_STATES),
    },
    "excluded_categories": [
        "street_or_geolocation",
        "person_or_contact",
        "demographic_or_protected_class",
        "compliance_or_violation",
        "enforcement_or_penalty",
        "emissions_or_risk_score",
    ],
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SOURCE_ID_RE = re.compile(r"^echo:[0-9]{6,20}$")
_SNAPSHOT_PATH_RE = re.compile(
    r"^snapshots/([0-9]{4}-[0-9]{2}-[0-9]{2})/([0-9a-f]{64})$"
)


class EchoSnapshotUnavailable(RuntimeError):
    """The durable ECHO snapshot could not be authenticated and used safely."""


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


PROJECTION_POLICY_SHA256 = _sha256(canonical_json(PROJECTION_POLICY))


def _open_url(url: str) -> BinaryIO:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        method="GET",
    )
    return urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS)


def _load_json(url: str, label: str) -> dict[str, Any]:
    with _open_url(url) as response:
        raw = response.read(MAX_METADATA_BYTES + 1)
    if not raw or len(raw) > MAX_METADATA_BYTES:
        raise EchoSnapshotUnavailable(f"{label} size outside policy")
    try:
        value = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise EchoSnapshotUnavailable(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise EchoSnapshotUnavailable(f"{label} must be a JSON object")
    return value


def _timestamp(value: object, label: str) -> datetime:
    try:
        return datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise EchoSnapshotUnavailable(f"invalid {label}") from exc


def _positive_int(value: object, label: str, maximum: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise EchoSnapshotUnavailable(f"invalid {label}")
    if maximum is not None and value > maximum:
        raise EchoSnapshotUnavailable(f"{label} exceeds runtime policy")
    return value


def _validate_pointer(latest: dict[str, Any]) -> str:
    if set(latest) != {
        "pointer_version",
        "snapshot_id",
        "snapshot_digest",
        "created_at",
        "record_count",
        "records_root_sha256",
        "records_file_sha256",
        "path",
    } or latest.get("pointer_version") != 1:
        raise EchoSnapshotUnavailable("latest pointer schema mismatch")
    path = latest.get("path")
    path_match = _SNAPSHOT_PATH_RE.fullmatch(path) if isinstance(path, str) else None
    if path_match is None:
        raise EchoSnapshotUnavailable("latest pointer path is not immutable")
    digest = latest.get("snapshot_digest")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise EchoSnapshotUnavailable("latest pointer digest is invalid")
    if latest.get("snapshot_id") != f"sha256:{digest}":
        raise EchoSnapshotUnavailable("latest pointer snapshot id is invalid")
    _positive_int(latest.get("record_count"), "latest record count", MAX_RECORD_COUNT)
    for field in ("records_root_sha256", "records_file_sha256"):
        value = latest.get(field)
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            raise EchoSnapshotUnavailable(f"latest pointer {field} is invalid")
    created = _timestamp(latest.get("created_at"), "latest created_at")
    if (
        path_match.group(1) != created.date().isoformat()
        or path_match.group(2) != digest
    ):
        raise EchoSnapshotUnavailable("latest pointer path/date mismatch")
    return path


def _expected_privacy() -> dict[str, object]:
    return {
        "classification": "ENTITY_AND_FACILITY_FIELDS_ONLY",
        "serialized_record_fields": list(RECORD_PAYLOAD_FIELDS),
        "excluded_categories": list(PROJECTION_POLICY["excluded_categories"]),
    }


def _validate_snapshot(
    snapshot: dict[str, Any],
    latest: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    expected_keys = {
        "snapshot_id",
        "snapshot_digest",
        "snapshot_version",
        "created_at",
        "source",
        "parser",
        "projection_policy",
        "record_schema",
        "record_count",
        "records_root_sha256",
        "records_file_sha256",
        "freshness_days",
        "selection",
        "privacy",
        "ingestion",
    }
    if set(snapshot) != expected_keys or snapshot.get("snapshot_version") != 3:
        raise EchoSnapshotUnavailable("snapshot schema/version mismatch")
    if snapshot.get("record_schema") != RECORD_SCHEMA:
        raise EchoSnapshotUnavailable("snapshot record schema mismatch")

    core = {
        key: value
        for key, value in snapshot.items()
        if key not in {"snapshot_id", "snapshot_digest"}
    }
    digest = _sha256(canonical_json(core))
    if snapshot.get("snapshot_digest") != digest:
        raise EchoSnapshotUnavailable("snapshot digest mismatch")
    if snapshot.get("snapshot_id") != f"sha256:{digest}":
        raise EchoSnapshotUnavailable("snapshot id mismatch")
    for field in (
        "snapshot_id",
        "snapshot_digest",
        "created_at",
        "record_count",
        "records_root_sha256",
        "records_file_sha256",
    ):
        if latest.get(field) != snapshot.get(field):
            raise EchoSnapshotUnavailable(f"latest pointer does not bind {field}")

    source = snapshot.get("source")
    if not isinstance(source, dict) or set(source) != {
        "name",
        "url",
        "upstream_bytes_sha256",
        "upstream_size_bytes",
        "member",
    }:
        raise EchoSnapshotUnavailable("snapshot source schema mismatch")
    if source.get("name") != "echo-exporter" or source.get("url") != ECHO_EXPORTER_URL:
        raise EchoSnapshotUnavailable("snapshot source identity mismatch")
    upstream_hash = source.get("upstream_bytes_sha256")
    if not isinstance(upstream_hash, str) or not _SHA256_RE.fullmatch(upstream_hash):
        raise EchoSnapshotUnavailable("invalid upstream bytes hash")
    upstream_size = _positive_int(source.get("upstream_size_bytes"), "upstream size")
    member = source.get("member")
    if not isinstance(member, dict) or set(member) != {
        "name",
        "crc32",
        "compressed_bytes",
        "uncompressed_bytes",
        "header_sha256",
    }:
        raise EchoSnapshotUnavailable("snapshot archive member schema mismatch")
    if member.get("name") != ECHO_MEMBER_NAME:
        raise EchoSnapshotUnavailable("snapshot archive member identity mismatch")
    if not isinstance(member.get("crc32"), str) or not re.fullmatch(
        r"[0-9a-f]{8}", member["crc32"]
    ):
        raise EchoSnapshotUnavailable("invalid archive member CRC")
    if not isinstance(member.get("header_sha256"), str) or not _SHA256_RE.fullmatch(
        member["header_sha256"]
    ):
        raise EchoSnapshotUnavailable("invalid archive header hash")
    compressed = _positive_int(member.get("compressed_bytes"), "compressed member size")
    _positive_int(member.get("uncompressed_bytes"), "uncompressed member size")
    if compressed > upstream_size:
        raise EchoSnapshotUnavailable("compressed member exceeds archive size")

    parser = snapshot.get("parser")
    if not isinstance(parser, dict) or set(parser) != {
        "name",
        "version",
        "source_revision",
    }:
        raise EchoSnapshotUnavailable("snapshot parser schema mismatch")
    if parser.get("name") != PARSER_NAME or parser.get("version") != PARSER_VERSION:
        raise EchoSnapshotUnavailable("snapshot parser identity mismatch")
    if not isinstance(parser.get("source_revision"), str) or not _GIT_SHA_RE.fullmatch(
        parser["source_revision"]
    ):
        raise EchoSnapshotUnavailable("snapshot parser revision mismatch")
    if snapshot.get("projection_policy") != {
        "id": PROJECTION_POLICY["policy"],
        "sha256": PROJECTION_POLICY_SHA256,
    }:
        raise EchoSnapshotUnavailable("snapshot projection policy mismatch")
    if snapshot.get("selection") != PROJECTION_POLICY["admission"]:
        raise EchoSnapshotUnavailable("snapshot selection policy mismatch")
    if snapshot.get("privacy") != _expected_privacy():
        raise EchoSnapshotUnavailable("snapshot privacy contract mismatch")
    if snapshot.get("freshness_days") != FRESHNESS_DAYS:
        raise EchoSnapshotUnavailable("snapshot freshness policy mismatch")

    count = _positive_int(
        snapshot.get("record_count"), "record count", MAX_RECORD_COUNT
    )
    for field in ("records_root_sha256", "records_file_sha256"):
        value = snapshot.get(field)
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            raise EchoSnapshotUnavailable(f"invalid {field}")
    ingestion = snapshot.get("ingestion")
    if not isinstance(ingestion, dict) or set(ingestion) != {
        "rows_seen",
        "rows_admitted",
        "rejected",
    }:
        raise EchoSnapshotUnavailable("snapshot ingestion schema mismatch")
    rejected = ingestion.get("rejected")
    if not isinstance(rejected, dict) or any(
        not isinstance(key, str)
        or not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
        for key, value in rejected.items()
    ):
        raise EchoSnapshotUnavailable("snapshot rejection accounting invalid")
    if ingestion.get("rows_admitted") != count:
        raise EchoSnapshotUnavailable("snapshot admitted count mismatch")
    rows_seen = ingestion.get("rows_seen")
    if (
        not isinstance(rows_seen, int)
        or isinstance(rows_seen, bool)
        or rows_seen != count + sum(rejected.values())
    ):
        raise EchoSnapshotUnavailable("snapshot ingestion accounting mismatch")

    created = _timestamp(snapshot.get("created_at"), "snapshot created_at")
    age_seconds = (now - created).total_seconds()
    if age_seconds < -300:
        raise EchoSnapshotUnavailable("snapshot created_at is in the future")
    if age_seconds > FRESHNESS_DAYS * 86_400:
        raise EchoSnapshotUnavailable(
            f"data as of {created.date().isoformat()}, refresh pending"
        )
    return {"record_count": count, "upstream_hash": upstream_hash, "created": created}


def _receipt_subject(snapshot: dict[str, Any]) -> dict[str, object]:
    return {
        "normalized_record_hash": snapshot["records_root_sha256"],
        "source_record_id": snapshot["snapshot_id"],
        "parser_version": snapshot["parser"]["version"],
    }


def _validate_receipt(
    receipt: dict[str, Any], snapshot: dict[str, Any]
) -> dict[str, str]:
    expected_keys = {
        "receipt_version",
        "receipt_id",
        "issued_at",
        "session_id",
        "sequence",
        "prev_receipt_hash",
        "subject",
        "ranking_inputs",
        "gate",
        "payload_hash",
        "signature",
    }
    if set(receipt) != expected_keys or receipt.get("receipt_version") != 1:
        raise EchoSnapshotUnavailable("receipt schema/version mismatch")
    try:
        receipt_id = uuid.UUID(str(receipt.get("receipt_id")))
        session_id = uuid.UUID(str(receipt.get("session_id")))
    except ValueError as exc:
        raise EchoSnapshotUnavailable("receipt identifiers are invalid") from exc
    if receipt_id.version != 4 or session_id.version != 4:
        raise EchoSnapshotUnavailable("receipt identifiers must be UUIDv4")
    if receipt.get("issued_at") != snapshot.get("created_at"):
        raise EchoSnapshotUnavailable("receipt issued_at mismatch")
    if receipt.get("sequence") != 0 or receipt.get("prev_receipt_hash") != "GENESIS":
        raise EchoSnapshotUnavailable("receipt one-record session state mismatch")
    if receipt.get("subject") != _receipt_subject(snapshot):
        raise EchoSnapshotUnavailable("receipt subject mismatch")

    ranking = receipt.get("ranking_inputs")
    if not isinstance(ranking, dict) or set(ranking) != {
        "source_path",
        "reasons",
        "confidence",
        "caveats",
    }:
        raise EchoSnapshotUnavailable("receipt ranking schema mismatch")
    if ranking.get("source_path") != ["echo-exporter"]:
        raise EchoSnapshotUnavailable("receipt source path mismatch")
    if ranking.get("confidence") != {"low": 1.0, "high": 1.0}:
        raise EchoSnapshotUnavailable("receipt confidence contract mismatch")
    reasons = ranking.get("reasons")
    if not isinstance(reasons, list) or not reasons:
        raise EchoSnapshotUnavailable("receipt reasons missing")
    for reason in reasons:
        if not isinstance(reason, dict) or set(reason) != {
            "code",
            "direction",
            "weight",
            "detail",
        }:
            raise EchoSnapshotUnavailable("receipt reason schema mismatch")
        if reason.get("direction") not in {"up", "down"}:
            raise EchoSnapshotUnavailable("receipt reason direction mismatch")
        weight = reason.get("weight")
        if not isinstance(weight, (int, float)) or isinstance(weight, bool):
            raise EchoSnapshotUnavailable("receipt reason weight mismatch")
    caveats = ranking.get("caveats")
    if not isinstance(caveats, list) or len(caveats) < 2:
        raise EchoSnapshotUnavailable("receipt caveats missing")
    if receipt.get("gate") != {
        "name": "yuyay-13",
        "result": "pass",
        "failures": [],
    }:
        raise EchoSnapshotUnavailable("receipt gate mismatch")

    body = {
        key: value
        for key, value in receipt.items()
        if key not in {"payload_hash", "signature"}
    }
    payload_hash = _sha256(canonical_json(body))
    if receipt.get("payload_hash") != payload_hash:
        raise EchoSnapshotUnavailable("receipt payload hash mismatch")
    signature = receipt.get("signature")
    if not isinstance(signature, dict) or set(signature) != {
        "algorithm",
        "key_id",
        "value",
    }:
        raise EchoSnapshotUnavailable("receipt signature schema mismatch")
    if signature.get("algorithm") != "HMAC-SHA256":
        raise EchoSnapshotUnavailable("receipt signature algorithm mismatch")
    if signature.get("value") != "UNSIGNED" or signature.get("key_id") is not None:
        raise EchoSnapshotUnavailable(
            "receipt signature cannot be authenticated by the public runtime"
        )
    return {
        "receipt_id": str(receipt_id),
        "payload_hash": payload_hash,
        "state": "PAYLOAD_VERIFIED_UNSIGNED",
    }


def _record_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {field: record[field] for field in RECORD_PAYLOAD_FIELDS}


def _validate_record(
    record: dict[str, Any], line_number: int, upstream_hash: str
) -> None:
    label = f"record {line_number}"
    if set(record) != set(SERIALIZED_RECORD_FIELDS):
        raise EchoSnapshotUnavailable(f"{label} schema mismatch")
    source_id = record.get("source_record_id")
    if not isinstance(source_id, str) or not _SOURCE_ID_RE.fullmatch(source_id):
        raise EchoSnapshotUnavailable(f"{label} source id invalid")
    name = record.get("org_name")
    if not isinstance(name, str) or not name or len(name) > 200:
        raise EchoSnapshotUnavailable(f"{label} organization name invalid")
    city = record.get("city")
    if not isinstance(city, str) or len(city) > 100:
        raise EchoSnapshotUnavailable(f"{label} city invalid")
    state = record.get("state")
    if state not in TARGET_STATES:
        raise EchoSnapshotUnavailable(f"{label} state outside policy")
    postal = record.get("postal_code")
    if not isinstance(postal, str) or (postal and not re.fullmatch(r"[0-9]{5}", postal)):
        raise EchoSnapshotUnavailable(f"{label} postal code invalid")
    county = record.get("county")
    if not isinstance(county, str) or len(county) > 100:
        raise EchoSnapshotUnavailable(f"{label} county invalid")
    region = record.get("epa_region")
    if not isinstance(region, str) or (
        region and not re.fullmatch(r"(?:0[1-9]|10)", region)
    ):
        raise EchoSnapshotUnavailable(f"{label} EPA region invalid")
    try:
        datetime.strptime(str(record.get("last_inspection_date")), "%Y-%m-%d")
    except ValueError as exc:
        raise EchoSnapshotUnavailable(f"{label} inspection date invalid") from exc
    age = record.get("days_since_last_inspection")
    if (
        not isinstance(age, int)
        or isinstance(age, bool)
        or not 0 <= age <= MAX_INSPECTION_AGE_DAYS
    ):
        raise EchoSnapshotUnavailable(f"{label} inspection age invalid")
    inspection_count = record.get("inspection_count")
    if inspection_count is not None and (
        not isinstance(inspection_count, int)
        or isinstance(inspection_count, bool)
        or inspection_count < 0
    ):
        raise EchoSnapshotUnavailable(f"{label} inspection count invalid")
    naics = record.get("naics_codes")
    if not isinstance(naics, list) or len(naics) != len(set(naics)) or any(
        not isinstance(code, str) or not re.fullmatch(r"[0-9]{6}", code)
        for code in naics
    ):
        raise EchoSnapshotUnavailable(f"{label} NAICS codes invalid")
    programs = record.get("programs")
    if not isinstance(programs, list) or len(programs) != len(set(programs)) or any(
        program not in PROGRAMS for program in programs
    ):
        raise EchoSnapshotUnavailable(f"{label} programs invalid")
    registry_id = source_id.removeprefix("echo:")
    if record.get("facility_report_url") != (
        "https://echo.epa.gov/detailed-facility-report?fid=" + registry_id
    ):
        raise EchoSnapshotUnavailable(f"{label} facility report URL mismatch")
    if record.get("parser_version") != PARSER_VERSION:
        raise EchoSnapshotUnavailable(f"{label} parser version mismatch")
    if record.get("projection_policy_sha256") != PROJECTION_POLICY_SHA256:
        raise EchoSnapshotUnavailable(f"{label} projection policy mismatch")
    normalized_hash = record.get("normalized_record_hash")
    if not isinstance(normalized_hash, str) or not _SHA256_RE.fullmatch(normalized_hash):
        raise EchoSnapshotUnavailable(f"{label} normalized hash invalid")
    if _sha256(canonical_json(_record_payload(record))) != normalized_hash:
        raise EchoSnapshotUnavailable(f"{label} normalized hash mismatch")
    expected_source_receipt = _sha256(
        canonical_json(
            {
                "upstream_bytes_sha256": upstream_hash,
                "source_record_id": source_id,
                "normalized_record_hash": normalized_hash,
                "parser_version": record["parser_version"],
                "projection_policy_sha256": record["projection_policy_sha256"],
            }
        )
    )
    if record.get("source_receipt") != expected_source_receipt:
        raise EchoSnapshotUnavailable(f"{label} source receipt mismatch")


def _selection_key(record: dict[str, Any]) -> tuple[object, ...]:
    return (
        record["days_since_last_inspection"],
        record["state"],
        record["org_name"].upper(),
        record["source_record_id"],
    )


def _stream_and_verify_records(
    url: str,
    snapshot: dict[str, Any],
    requested_states: frozenset[str],
    limit: int,
    upstream_hash: str,
) -> list[dict[str, Any]]:
    file_hash = hashlib.sha256()
    root_hash = hashlib.sha256()
    root_hash.update(b"[")
    seen_ids: set[str] = set()
    selected: list[dict[str, Any]] = []
    count = 0
    total_bytes = 0
    with _open_url(url) as response:
        headers = getattr(response, "headers", None)
        content_length = headers.get("Content-Length") if headers is not None else None
        if content_length:
            try:
                declared_length = int(content_length)
            except ValueError as exc:
                raise EchoSnapshotUnavailable("records Content-Length is invalid") from exc
            if declared_length <= 0 or declared_length > MAX_RECORDS_FILE_BYTES:
                raise EchoSnapshotUnavailable("records Content-Length outside policy")
        while True:
            raw_line = response.readline(MAX_SERIALIZED_RECORD_BYTES + 1)
            if not raw_line:
                break
            count += 1
            total_bytes += len(raw_line)
            if count > MAX_RECORD_COUNT or total_bytes > MAX_RECORDS_FILE_BYTES:
                raise EchoSnapshotUnavailable("records stream exceeds runtime policy")
            if len(raw_line) > MAX_SERIALIZED_RECORD_BYTES:
                raise EchoSnapshotUnavailable(f"record {count} exceeds size policy")
            if not raw_line.endswith(b"\n") or b"\r" in raw_line:
                raise EchoSnapshotUnavailable(f"record {count} framing mismatch")
            try:
                record = json.loads(raw_line)
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise EchoSnapshotUnavailable(f"record {count} is invalid JSON") from exc
            if not isinstance(record, dict) or raw_line != canonical_json(record) + b"\n":
                raise EchoSnapshotUnavailable(f"record {count} is not canonical JSONL")
            _validate_record(record, count, upstream_hash)
            source_id = record["source_record_id"]
            if source_id in seen_ids:
                raise EchoSnapshotUnavailable(f"record {count} duplicates a source id")
            seen_ids.add(source_id)
            file_hash.update(raw_line)
            if count > 1:
                root_hash.update(b",")
            root_hash.update(canonical_json(record["normalized_record_hash"]))
            if record["state"] in requested_states:
                selected.append(record)
                selected.sort(key=_selection_key)
                if len(selected) > limit:
                    selected.pop()
    root_hash.update(b"]")
    if count != snapshot["record_count"]:
        raise EchoSnapshotUnavailable("records count mismatch")
    if file_hash.hexdigest() != snapshot["records_file_sha256"]:
        raise EchoSnapshotUnavailable("records file hash mismatch")
    if root_hash.hexdigest() != snapshot["records_root_sha256"]:
        raise EchoSnapshotUnavailable("records root mismatch")
    return selected


def load_verified_records(
    states: list[str] | tuple[str, ...],
    limit: int,
    *,
    now: datetime | None = None,
    base_url: str = DATASET_BASE_URL,
) -> dict[str, Any]:
    """Verify the complete current bundle and return a bounded state selection."""

    requested_states = frozenset(str(state).strip().upper() for state in states)
    if not requested_states or not requested_states.issubset(TARGET_STATES):
        raise EchoSnapshotUnavailable("requested states are outside snapshot policy")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 50:
        raise EchoSnapshotUnavailable("requested record limit is outside policy")
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        raise EchoSnapshotUnavailable("verification clock must be timezone-aware")
    clock = clock.astimezone(timezone.utc)
    base = base_url.rstrip("/")
    try:
        latest = _load_json(f"{base}/latest.json", "latest pointer")
        snapshot_path = _validate_pointer(latest)
        snapshot_url = f"{base}/{snapshot_path}/snapshot.json"
        receipt_url = f"{base}/{snapshot_path}/receipt.json"
        records_url = f"{base}/{snapshot_path}/records.jsonl"
        snapshot = _load_json(snapshot_url, "snapshot")
        validated = _validate_snapshot(snapshot, latest, clock)
        receipt = _load_json(receipt_url, "receipt")
        receipt_meta = _validate_receipt(receipt, snapshot)
        records = _stream_and_verify_records(
            records_url,
            snapshot,
            requested_states,
            limit,
            validated["upstream_hash"],
        )
    except EchoSnapshotUnavailable:
        raise
    except Exception as exc:
        raise EchoSnapshotUnavailable(
            f"snapshot transport failed: {type(exc).__name__}"
        ) from exc
    return {
        "records": records,
        "dataset": {
            "repo_id": DATASET_REPO_ID,
            "url": DATASET_LANDING_URL,
            "immutable_path": snapshot_path,
        },
        "snapshot": {
            "snapshot_id": snapshot["snapshot_id"],
            "snapshot_digest": snapshot["snapshot_digest"],
            "created_at": snapshot["created_at"],
            "record_count": snapshot["record_count"],
            "records_root_sha256": snapshot["records_root_sha256"],
            "records_file_sha256": snapshot["records_file_sha256"],
            "parser_version": snapshot["parser"]["version"],
            "freshness_state": "FRESH",
            "freshness_days": FRESHNESS_DAYS,
        },
        "receipt": receipt_meta,
    }
