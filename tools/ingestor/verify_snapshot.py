"""Fail-closed verifier for an EPA ECHO Federal Refresh bundle."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.echo_name_screen import excluded_name_reason
from tools.ingestor.echo_ingestor import (
    DEFAULT_TARGET_STATES,
    ECHO_EXPORTER_URL,
    ECHO_MEMBER_NAME,
    FRESHNESS_DAYS,
    MAX_INSPECTION_AGE_DAYS,
    MAX_SERIALIZED_RECORD_BYTES,
    PARSER_NAME,
    PARSER_VERSION,
    PROGRAM_FIELDS,
    PROJECTION_POLICY,
    PROJECTION_POLICY_SHA256,
    RECORD_METADATA_FIELDS,
    RECORD_PAYLOAD_FIELDS,
    RECORD_SCHEMA,
    RecordRootAccumulator,
    canonical_json,
    receipt_subject,
    sha256_bytes,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_REGISTRY_ID_RE = re.compile(r"^echo:[0-9]{6,20}$")
_MAX_METADATA_BYTES = 1_000_000


def _fail(message: str) -> int:
    print(f"FAIL: {message}")
    return 1


def _load_json(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"required regular file missing: {path.name}")
    if path.stat().st_size <= 0 or path.stat().st_size > _MAX_METADATA_BYTES:
        raise ValueError(f"metadata file size outside policy: {path.name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"metadata must be an object: {path.name}")
    return value


def _record_payload(record: dict[str, object]) -> dict[str, object]:
    return {field: record[field] for field in RECORD_PAYLOAD_FIELDS}


def _expected_source_receipt(
    record: dict[str, object], upstream_hash: str
) -> str:
    return sha256_bytes(
        canonical_json(
            {
                "upstream_bytes_sha256": upstream_hash,
                "source_record_id": record["source_record_id"],
                "normalized_record_hash": record["normalized_record_hash"],
                "parser_version": record["parser_version"],
                "projection_policy_sha256": record["projection_policy_sha256"],
            }
        )
    )


def _validate_record(
    record: dict[str, object], line_number: int, created_at: datetime
) -> str | None:
    expected_keys = set(RECORD_PAYLOAD_FIELDS + RECORD_METADATA_FIELDS)
    if set(record) != expected_keys:
        return f"record {line_number}: schema mismatch"
    source_id = record.get("source_record_id")
    if not isinstance(source_id, str) or not _REGISTRY_ID_RE.fullmatch(source_id):
        return f"record {line_number}: invalid source_record_id"
    if not isinstance(record.get("org_name"), str) or not record["org_name"]:
        return f"record {line_number}: invalid org_name"
    if not isinstance(record.get("city"), str) or len(record["city"]) > 100:
        return f"record {line_number}: invalid city"
    state = record.get("state")
    if state not in DEFAULT_TARGET_STATES:
        return f"record {line_number}: state outside policy"
    postal = record.get("postal_code")
    if not isinstance(postal, str) or (postal and not re.fullmatch(r"[0-9]{5}", postal)):
        return f"record {line_number}: invalid postal_code"
    if not isinstance(record.get("county"), str) or len(record["county"]) > 100:
        return f"record {line_number}: invalid county"
    region = record.get("epa_region")
    if not isinstance(region, str) or (region and not re.fullmatch(r"(?:0[1-9]|10)", region)):
        return f"record {line_number}: invalid epa_region"
    try:
        inspection_date = datetime.strptime(str(record["last_inspection_date"]), "%Y-%m-%d")
    except ValueError:
        return f"record {line_number}: invalid last_inspection_date"
    age = record.get("days_since_last_inspection")
    if not isinstance(age, int) or isinstance(age, bool) or not (0 <= age <= MAX_INSPECTION_AGE_DAYS):
        return f"record {line_number}: invalid days_since_last_inspection"
    actual_age = (created_at.date() - inspection_date.date()).days
    if not 0 <= actual_age <= MAX_INSPECTION_AGE_DAYS:
        return f"record {line_number}: inspection date outside monitoring window at admission"
    count = record.get("inspection_count")
    if count is not None and (
        not isinstance(count, int) or isinstance(count, bool) or count < 0
    ):
        return f"record {line_number}: invalid inspection_count"
    naics = record.get("naics_codes")
    if not isinstance(naics, list) or len(naics) != len(set(naics)) or any(
        not isinstance(code, str) or not re.fullmatch(r"[0-9]{6}", code)
        for code in naics
    ):
        return f"record {line_number}: invalid naics_codes"
    excluded = excluded_name_reason(record["org_name"], naics)
    if excluded is not None:
        return f"record {line_number}: violates the person/residence exclusion ({excluded})"
    programs = record.get("programs")
    allowed_programs = frozenset(PROGRAM_FIELDS.values())
    if not isinstance(programs, list) or len(programs) != len(set(programs)) or any(
        value not in allowed_programs for value in programs
    ):
        return f"record {line_number}: invalid programs"
    expected_url = (
        "https://echo.epa.gov/detailed-facility-report?fid="
        + str(source_id).removeprefix("echo:")
    )
    if record.get("facility_report_url") != expected_url:
        return f"record {line_number}: facility_report_url mismatch"
    if record.get("parser_version") != PARSER_VERSION:
        return f"record {line_number}: parser_version mismatch"
    if record.get("projection_policy_sha256") != PROJECTION_POLICY_SHA256:
        return f"record {line_number}: projection policy mismatch"
    normalized_hash = record.get("normalized_record_hash")
    if not isinstance(normalized_hash, str) or not _SHA256_RE.fullmatch(normalized_hash):
        return f"record {line_number}: invalid normalized_record_hash"
    if sha256_bytes(canonical_json(_record_payload(record))) != normalized_hash:
        return f"record {line_number}: normalized_record_hash mismatch"
    return None


def verify(
    snapshot_dir: Path,
    now: datetime | None = None,
    *,
    signing_key: bytes | None = None,
    require_fresh: bool = True,
    require_signature: bool = False,
) -> int:
    """Verify schema, privacy, every byte binding, receipt, and freshness."""

    try:
        snapshot_dir = snapshot_dir.resolve(strict=True)
        if snapshot_dir.is_symlink() or not snapshot_dir.is_dir():
            return _fail("snapshot path must be a regular directory")
        if {path.name for path in snapshot_dir.iterdir()} != {
            "snapshot.json",
            "receipt.json",
            "records.jsonl",
        }:
            return _fail("snapshot directory file set mismatch")
        snapshot = _load_json(snapshot_dir / "snapshot.json")
        receipt = _load_json(snapshot_dir / "receipt.json")

        expected_snapshot_keys = {
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
        if set(snapshot) != expected_snapshot_keys or snapshot.get("snapshot_version") != 3:
            return _fail("snapshot schema/version mismatch")
        if snapshot.get("record_schema") != RECORD_SCHEMA:
            return _fail("unexpected record schema")

        source = snapshot.get("source")
        if not isinstance(source, dict) or set(source) != {
            "name", "url", "upstream_bytes_sha256", "upstream_size_bytes", "source_as_of", "member"
        }:
            return _fail("source schema mismatch")
        if source.get("name") != "echo-exporter" or source.get("url") != ECHO_EXPORTER_URL:
            return _fail("source identity mismatch")
        source_as_of = datetime.strptime(str(source.get("source_as_of")), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if source_as_of.date().isoformat() != source.get("source_as_of"):
            return _fail("source_as_of must be a canonical calendar date")
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            return _fail("verification clock must be timezone-aware")
        created = datetime.strptime(str(snapshot["created_at"]), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if source_as_of > now or source_as_of > created:
            return _fail("upstream source date is in the future")
        upstream_hash = source.get("upstream_bytes_sha256")
        if not isinstance(upstream_hash, str) or not _SHA256_RE.fullmatch(upstream_hash):
            return _fail("invalid upstream bytes hash")
        upstream_size = source.get("upstream_size_bytes")
        if not isinstance(upstream_size, int) or isinstance(upstream_size, bool) or upstream_size <= 0:
            return _fail("invalid upstream size")
        member = source.get("member")
        if not isinstance(member, dict) or set(member) != {
            "name", "crc32", "compressed_bytes", "uncompressed_bytes", "header_sha256"
        }:
            return _fail("archive member schema mismatch")
        if member.get("name") != ECHO_MEMBER_NAME:
            return _fail("archive member identity mismatch")
        if not isinstance(member.get("crc32"), str) or not re.fullmatch(r"[0-9a-f]{8}", member["crc32"]):
            return _fail("invalid archive member CRC")
        if not isinstance(member.get("header_sha256"), str) or not _SHA256_RE.fullmatch(member["header_sha256"]):
            return _fail("invalid archive header hash")
        for size_name in ("compressed_bytes", "uncompressed_bytes"):
            size = member.get(size_name)
            if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
                return _fail(f"invalid archive member {size_name}")
        if member["compressed_bytes"] > upstream_size:
            return _fail("compressed member exceeds upstream archive")

        parser = snapshot.get("parser")
        if not isinstance(parser, dict) or parser.get("name") != PARSER_NAME or parser.get("version") != PARSER_VERSION:
            return _fail("parser identity mismatch")
        if set(parser) != {"name", "version", "source_revision"} or not isinstance(parser.get("source_revision"), str) or not _GIT_SHA_RE.fullmatch(parser["source_revision"]):
            return _fail("parser source revision mismatch")
        policy = snapshot.get("projection_policy")
        if policy != {
            "id": PROJECTION_POLICY["policy"],
            "sha256": PROJECTION_POLICY_SHA256,
        }:
            return _fail("projection policy mismatch")
        if snapshot.get("selection") != PROJECTION_POLICY["admission"]:
            return _fail("selection policy mismatch")
        if snapshot.get("privacy") != {
            "classification": "ENTITY_AND_FACILITY_FIELDS_ONLY",
            "serialized_record_fields": list(RECORD_PAYLOAD_FIELDS),
            "excluded_categories": list(PROJECTION_POLICY["excluded_categories"]),
        }:
            return _fail("privacy contract mismatch")
        if snapshot.get("freshness_days") != FRESHNESS_DAYS:
            return _fail("freshness policy mismatch")

        core = {
            key: value
            for key, value in snapshot.items()
            if key not in ("snapshot_id", "snapshot_digest")
        }
        snapshot_digest = sha256_bytes(canonical_json(core))
        if snapshot.get("snapshot_digest") != snapshot_digest:
            return _fail("snapshot digest mismatch")
        if snapshot.get("snapshot_id") != f"sha256:{snapshot_digest}":
            return _fail("snapshot id mismatch")

        records_path = snapshot_dir / "records.jsonl"
        if records_path.is_symlink() or not records_path.is_file():
            return _fail("records.jsonl must be a regular file")
        records_file_hash = hashlib.sha256()
        record_root = RecordRootAccumulator()
        seen_ids: set[str] = set()
        count = 0
        with records_path.open("rb") as records_file:
            while True:
                raw_line = records_file.readline(MAX_SERIALIZED_RECORD_BYTES + 1)
                if not raw_line:
                    break
                count += 1
                if len(raw_line) > MAX_SERIALIZED_RECORD_BYTES:
                    return _fail(f"record {count}: serialized size exceeds policy")
                if not raw_line.endswith(b"\n") or b"\r" in raw_line:
                    return _fail(f"record {count}: JSONL must use canonical LF framing")
                record = json.loads(raw_line)
                if not isinstance(record, dict):
                    return _fail(f"record {count}: expected an object")
                if raw_line != canonical_json(record) + b"\n":
                    return _fail(f"record {count}: non-canonical JSON encoding")
                records_file_hash.update(raw_line)
                error = _validate_record(record, count, created)
                if error:
                    return _fail(error)
                source_id = str(record["source_record_id"])
                if source_id in seen_ids:
                    return _fail(f"record {count}: duplicate source_record_id")
                seen_ids.add(source_id)
                if record.get("source_receipt") != _expected_source_receipt(record, upstream_hash):
                    return _fail(f"record {count}: source receipt mismatch")
                record_root.add(str(record["normalized_record_hash"]))

        if count <= 0 or snapshot.get("record_count") != count:
            return _fail("record count mismatch or zero records")
        if snapshot.get("records_root_sha256") != record_root.hexdigest():
            return _fail("records root mismatch")
        if snapshot.get("records_file_sha256") != records_file_hash.hexdigest():
            return _fail("records file hash mismatch")
        ingestion = snapshot.get("ingestion")
        if not isinstance(ingestion, dict) or set(ingestion) != {
            "rows_seen", "rows_admitted", "rejected"
        }:
            return _fail("ingestion accounting schema mismatch")
        if ingestion.get("rows_admitted") != count:
            return _fail("ingestion admitted count mismatch")
        rejected = ingestion.get("rejected")
        if not isinstance(rejected, dict) or any(
            not isinstance(key, str)
            or not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            for key, value in rejected.items()
        ):
            return _fail("invalid rejection accounting")
        rows_seen = ingestion.get("rows_seen")
        if not isinstance(rows_seen, int) or isinstance(rows_seen, bool) or rows_seen != count + sum(rejected.values()):
            return _fail("ingestion accounting does not balance")

        expected_receipt_keys = {
            "receipt_version", "receipt_id", "issued_at", "session_id", "sequence",
            "prev_receipt_hash", "subject", "ranking_inputs", "gate",
            "payload_hash", "signature",
        }
        if set(receipt) != expected_receipt_keys or receipt.get("receipt_version") != 1:
            return _fail("receipt schema/version mismatch")
        try:
            receipt_uuid = uuid.UUID(str(receipt.get("receipt_id")))
            session_uuid = uuid.UUID(str(receipt.get("session_id")))
        except ValueError:
            return _fail("invalid receipt or session id")
        if receipt_uuid.version != 4 or session_uuid.version != 4:
            return _fail("receipt and session ids must be UUIDv4")
        if receipt.get("issued_at") != snapshot.get("created_at"):
            return _fail("receipt issued_at mismatch")
        if receipt.get("sequence") != 0 or receipt.get("prev_receipt_hash") != "GENESIS":
            return _fail("receipt one-record session state mismatch")
        if receipt.get("subject") != receipt_subject(snapshot):
            return _fail("receipt subject mismatch")
        ranking = receipt.get("ranking_inputs")
        if not isinstance(ranking, dict) or ranking.get("source_path") != ["echo-exporter"]:
            return _fail("receipt source path mismatch")
        confidence = ranking.get("confidence")
        if confidence != {"low": 1, "high": 1}:
            return _fail("receipt confidence contract mismatch")
        reasons = ranking.get("reasons")
        caveats = ranking.get("caveats")
        if not isinstance(reasons, list) or not reasons or not isinstance(caveats, list) or len(caveats) < 2:
            return _fail("receipt reasons/caveats missing")
        for reason in reasons:
            if not isinstance(reason, dict) or set(reason) != {
                "code", "direction", "weight", "detail"
            }:
                return _fail("receipt reason schema mismatch")
            if reason.get("direction") not in {"up", "down"}:
                return _fail("receipt reason direction mismatch")
            weight = reason.get("weight")
            if not isinstance(weight, (int, float)) or isinstance(weight, bool):
                return _fail("receipt reason weight mismatch")
        if receipt.get("gate") != {"name": "yuyay-13", "result": "pass", "failures": []}:
            return _fail("receipt gate mismatch")
        body = {key: value for key, value in receipt.items() if key not in ("payload_hash", "signature")}
        payload_hash = sha256_bytes(canonical_json(body))
        if receipt.get("payload_hash") != payload_hash:
            return _fail("receipt payload hash mismatch")
        signature = receipt.get("signature")
        if not isinstance(signature, dict) or set(signature) != {"algorithm", "key_id", "value"} or signature.get("algorithm") != "HMAC-SHA256":
            return _fail("unsupported receipt signature contract")
        signature_value = signature.get("value")
        if signature_value == "UNSIGNED":
            if require_signature:
                return _fail("a signature is required")
            if signature.get("key_id") is not None:
                return _fail("unsigned receipt claims a key id")
        else:
            if signing_key is None or signature.get("key_id") != "receipt-signing-key":
                return _fail("signed receipt cannot be authenticated")
            expected_signature = hmac.new(
                signing_key, bytes.fromhex(payload_hash), hashlib.sha256
            ).hexdigest()
            if not isinstance(signature_value, str) or not hmac.compare_digest(signature_value, expected_signature):
                return _fail("receipt signature mismatch")

        age_seconds = (now - created).total_seconds()
        if age_seconds < -300:
            return _fail("snapshot created_at is in the future")
        age_days = max(0.0, (now - source_as_of).total_seconds() / 86_400)
        if require_fresh and age_days > FRESHNESS_DAYS:
            return _fail(f"data as of {source_as_of.date().isoformat()}, refresh pending")

        freshness_state = "FRESH" if age_days <= FRESHNESS_DAYS else "STALE"
        print(
            f"OK: snapshot {snapshot['snapshot_id']} verifies "
            f"({count} records, freshness={freshness_state}, receipt={signature_value})"
        )
        return 0
    except (OSError, KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        return _fail(f"malformed snapshot bundle: {type(exc).__name__}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot_dir")
    parser.add_argument(
        "--allow-stale",
        action="store_true",
        help="Verify historical integrity without requiring current freshness",
    )
    parser.add_argument(
        "--require-signature",
        action="store_true",
        help="Reject an honestly unsigned receipt",
    )
    args = parser.parse_args()
    return verify(
        Path(args.snapshot_dir),
        require_fresh=not args.allow_stale,
        require_signature=args.require_signature,
    )


if __name__ == "__main__":
    sys.exit(main())
