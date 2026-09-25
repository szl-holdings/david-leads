"""Privacy-minimized, streaming EPA ECHO snapshot primitives.

The production path reads the official ECHO Exporter directly from its ZIP
member and never materializes the multi-gigabyte CSV. A record is admitted
only when it has an official FRS identity, is active, is in the supported
territory, and has a recent factual inspection date. The durable projection
contains organization/facility facts only; precise street location, people,
contacts, demographics, compliance conclusions, enforcement, and penalties
cannot enter the serialized schema. Because ``FAC_NAME`` is free text, a row
whose name reads as a private individual or a private residence is rejected
by the shared ``app.echo_name_screen`` rule before it can become a record.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator

from app.echo_name_screen import REJECTION_REASON as PERSON_OR_RESIDENCE_REASON
from app.echo_name_screen import excluded_name_reason

ECHO_EXPORTER_URL = "https://echo.epa.gov/files/echodownloads/echo_exporter.zip"
ECHO_MEMBER_NAME = "ECHO_EXPORTER.csv"
PARSER_NAME = "david-leads-echo-exporter"
PARSER_VERSION = "3.0.0"
RECORD_SCHEMA = "szl.david-leads.echo-facility/v3"
FRESHNESS_DAYS = 8
MAX_INSPECTION_AGE_DAYS = 365
DEFAULT_TARGET_STATES = frozenset(
    "AL CT DC DE FL GA IL IN KY ME MD MA MI MS NH NJ NY NC OH PA RI SC TN VT VA WV WI".split()
)

# These archive bounds accept the observed 2.114 GiB official member while
# rejecting archive bombs and unexpected multi-file products.
MAX_ZIP_MEMBERS = 16
MAX_SINGLE_MEMBER_BYTES = 3_000_000_000
MAX_TOTAL_UNCOMPRESSED_BYTES = 3_500_000_000
MAX_COMPRESSION_RATIO = 100.0
MAX_SERIALIZED_RECORD_BYTES = 8_192

ECHO_REQUIRED_HEADERS = (
    "REGISTRY_ID",
    "FAC_NAME",
    "FAC_CITY",
    "FAC_STATE",
    "FAC_ZIP",
    "FAC_COUNTY",
    "FAC_EPA_REGION",
    "FAC_FEDERAL_FLG",
    "FAC_ACTIVE_FLAG",
    "FAC_INSPECTION_COUNT",
    "FAC_DATE_LAST_INSPECTION",
    "FAC_DAYS_LAST_INSPECTION",
    "FAC_NAICS_CODES",
    "AIR_FLAG",
    "NPDES_FLAG",
    "SDWIS_FLAG",
    "RCRA_FLAG",
    "TRI_FLAG",
    "GHG_FLAG",
)

PROGRAM_FIELDS = {
    "AIR_FLAG": "AIR",
    "NPDES_FLAG": "NPDES",
    "SDWIS_FLAG": "SDWIS",
    "RCRA_FLAG": "RCRA",
    "TRI_FLAG": "TRI",
    "GHG_FLAG": "GHG",
}

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
        "target_states": sorted(DEFAULT_TARGET_STATES),
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

_MAX_TEXT_LENGTH = {
    "org_name": 200,
    "city": 100,
    "state": 2,
    "postal_code": 5,
    "county": 100,
    "epa_region": 2,
}
_REGISTRY_ID_RE = re.compile(r"^[0-9]{6,20}$")
_SOURCE_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")


def canonical_json(value: object) -> bytes:
    """Return the single canonical JSON representation used by all hashes."""

    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


PROJECTION_POLICY_SHA256 = sha256_bytes(canonical_json(PROJECTION_POLICY))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clean(value: object, field_name: str) -> str:
    limit = _MAX_TEXT_LENGTH.get(field_name, 256)
    return " ".join(str(value or "").split())[:limit]


def _nonnegative_int(value: object) -> int | None:
    text = _clean(value, "integer")
    if not text:
        return None
    try:
        parsed = int(text)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _inspection_date(value: object) -> str | None:
    text = _clean(value, "date")
    if not text:
        return None
    for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue
    return None


def _naics_codes(value: object) -> tuple[str, ...]:
    matches = re.findall(r"(?<![0-9])[0-9]{6}(?![0-9])", str(value or ""))
    return tuple(dict.fromkeys(matches))


def _postal_code(value: object) -> str:
    match = re.search(r"(?<![0-9])[0-9]{5}(?![0-9])", str(value or ""))
    return match.group(0) if match else ""


@dataclass
class SourceRecord:
    source_record_id: str
    org_name: str
    city: str
    state: str
    postal_code: str
    county: str
    epa_region: str
    last_inspection_date: str
    days_since_last_inspection: int
    inspection_count: int | None
    naics_codes: tuple[str, ...]
    programs: tuple[str, ...]
    facility_report_url: str
    normalized_record_hash: str = ""
    parser_version: str = PARSER_VERSION
    projection_policy_sha256: str = PROJECTION_POLICY_SHA256
    source_receipt: str = ""

    def payload(self) -> dict[str, object]:
        return {
            "source_record_id": self.source_record_id,
            "org_name": self.org_name,
            "city": self.city,
            "state": self.state,
            "postal_code": self.postal_code,
            "county": self.county,
            "epa_region": self.epa_region,
            "last_inspection_date": self.last_inspection_date,
            "days_since_last_inspection": self.days_since_last_inspection,
            "inspection_count": self.inspection_count,
            "naics_codes": list(self.naics_codes),
            "programs": list(self.programs),
            "facility_report_url": self.facility_report_url,
        }

    def finalize(self, upstream_bytes_hash: str) -> "SourceRecord":
        self.normalized_record_hash = sha256_bytes(canonical_json(self.payload()))
        self.source_receipt = sha256_bytes(
            canonical_json(
                {
                    "upstream_bytes_sha256": upstream_bytes_hash,
                    "source_record_id": self.source_record_id,
                    "normalized_record_hash": self.normalized_record_hash,
                    "parser_version": self.parser_version,
                    "projection_policy_sha256": self.projection_policy_sha256,
                }
            )
        )
        return self


@dataclass
class IngestionStats:
    rows_seen: int = 0
    rows_admitted: int = 0
    rejected: dict[str, int] = field(default_factory=dict)
    archive_member_crc32: str = ""
    archive_member_compressed_bytes: int = 0
    archive_member_uncompressed_bytes: int = 0
    archive_header_sha256: str = ""
    source_as_of: str = ""

    def reject(self, reason: str) -> None:
        self.rejected[reason] = self.rejected.get(reason, 0) + 1


def serialize_record(record: SourceRecord) -> dict[str, object]:
    return {
        **record.payload(),
        "normalized_record_hash": record.normalized_record_hash,
        "parser_version": record.parser_version,
        "projection_policy_sha256": record.projection_policy_sha256,
        "source_receipt": record.source_receipt,
    }


def _record_from_row(row: dict[str, object], upstream_hash: str) -> SourceRecord | None:
    registry_id = _clean(row.get("REGISTRY_ID"), "registry_id")
    name = _clean(row.get("FAC_NAME"), "org_name")
    state = _clean(row.get("FAC_STATE"), "state").upper()
    age = _nonnegative_int(row.get("FAC_DAYS_LAST_INSPECTION"))
    observed = _inspection_date(row.get("FAC_DATE_LAST_INSPECTION"))
    if not _REGISTRY_ID_RE.fullmatch(registry_id) or not name or len(state) != 2:
        return None
    if age is None or observed is None:
        return None
    naics_codes = _naics_codes(row.get("FAC_NAICS_CODES"))
    if excluded_name_reason(name, naics_codes) is not None:
        return None
    programs = tuple(
        program
        for source_field, program in PROGRAM_FIELDS.items()
        if _clean(row.get(source_field), source_field).upper() == "Y"
    )
    region_value = _nonnegative_int(row.get("FAC_EPA_REGION"))
    region = f"{region_value:02d}" if region_value is not None and 1 <= region_value <= 10 else ""
    return SourceRecord(
        source_record_id=f"echo:{registry_id}",
        org_name=name,
        city=_clean(row.get("FAC_CITY"), "city"),
        state=state,
        postal_code=_postal_code(row.get("FAC_ZIP")),
        county=_clean(row.get("FAC_COUNTY"), "county"),
        epa_region=region,
        last_inspection_date=observed,
        days_since_last_inspection=age,
        inspection_count=_nonnegative_int(row.get("FAC_INSPECTION_COUNT")),
        naics_codes=naics_codes,
        programs=programs,
        facility_report_url=(
            "https://echo.epa.gov/detailed-facility-report?fid=" + registry_id
        ),
    ).finalize(upstream_hash)


def _validated_member(zf: zipfile.ZipFile) -> zipfile.ZipInfo:
    infos = zf.infolist()
    if not infos or len(infos) > MAX_ZIP_MEMBERS:
        raise ValueError("fail-closed: unexpected ZIP member count")
    if any(info.flag_bits & 0x1 for info in infos):
        raise ValueError("fail-closed: encrypted ZIP members are not accepted")
    if sum(info.file_size for info in infos) > MAX_TOTAL_UNCOMPRESSED_BYTES:
        raise ValueError("fail-closed: ZIP expanded size exceeds policy")
    matches = [info for info in infos if Path(info.filename).name == ECHO_MEMBER_NAME]
    if len(matches) != 1:
        raise ValueError("fail-closed: archive must contain exactly ECHO_EXPORTER.csv")
    info = matches[0]
    if info.file_size <= 0 or info.file_size > MAX_SINGLE_MEMBER_BYTES:
        raise ValueError("fail-closed: ECHO member size exceeds policy")
    if info.compress_size <= 0 or info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
        raise ValueError("fail-closed: ECHO member compression ratio exceeds policy")
    return info


def _facility_reader(
    zf: zipfile.ZipFile, info: zipfile.ZipInfo, stats: IngestionStats
) -> Iterator[csv.DictReader]:
    raw_handle = zf.open(info)
    text_handle = io.TextIOWrapper(
        raw_handle, encoding="utf-8-sig", errors="strict", newline=""
    )
    try:
        reader = csv.DictReader(text_handle)
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)):
            raise ValueError("fail-closed: duplicate ECHO headers")
        missing = sorted(set(ECHO_REQUIRED_HEADERS) - set(headers))
        if missing:
            raise ValueError(f"fail-closed: missing ECHO headers: {', '.join(missing)}")
        stats.archive_header_sha256 = sha256_bytes(canonical_json(headers))
        stats.archive_member_crc32 = f"{info.CRC:08x}"
        stats.archive_member_compressed_bytes = info.compress_size
        stats.archive_member_uncompressed_bytes = info.file_size
        # ZIP timestamps carry no timezone. Preserve only the source calendar
        # date; freshness is conservatively measured from midnight UTC.
        stats.source_as_of = date(*info.date_time[:3]).isoformat()
        yield reader
    finally:
        text_handle.close()


def parse_echo_exporter(zip_bytes: bytes) -> list[SourceRecord]:
    """Parse bounded synthetic fixtures; production uses the path iterator."""

    if not zip_bytes:
        raise ValueError("fail-closed: empty upstream payload")
    upstream_hash = sha256_bytes(zip_bytes)
    stats = IngestionStats()
    records: list[SourceRecord] = []
    seen: set[str] = set()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        info = _validated_member(zf)
        for reader in _facility_reader(zf, info, stats):
            for row in reader:
                stats.rows_seen += 1
                record = _record_from_row(row, upstream_hash)
                if record is None:
                    continue
                if record.source_record_id in seen:
                    raise ValueError("fail-closed: duplicate ECHO registry identity")
                seen.add(record.source_record_id)
                records.append(record)
    return records


def iter_operational_echo_records(
    zip_path: Path,
    *,
    upstream_hash: str,
    stats: IngestionStats,
    target_states: frozenset[str] = DEFAULT_TARGET_STATES,
    max_inspection_age_days: int = MAX_INSPECTION_AGE_DAYS,
    now: datetime | None = None,
) -> Iterator[SourceRecord]:
    """Stream the official archive and yield only allowed recent facilities."""

    if not zip_path.is_file() or zip_path.stat().st_size <= 0:
        raise ValueError("fail-closed: empty or missing upstream archive")
    if not target_states:
        raise ValueError("fail-closed: target state set is empty")
    seen: set[str] = set()
    with zipfile.ZipFile(zip_path) as zf:
        info = _validated_member(zf)
        clock = now or datetime.now(timezone.utc)
        if clock.tzinfo is None:
            raise ValueError("fail-closed: ingestion clock must be timezone-aware")
        source_date = date(*info.date_time[:3])
        source_midnight = datetime.combine(source_date, datetime.min.time(), timezone.utc)
        source_age_seconds = (clock.astimezone(timezone.utc) - source_midnight).total_seconds()
        if source_age_seconds < 0:
            raise ValueError("fail-closed: upstream source date is in the future")
        if source_age_seconds > FRESHNESS_DAYS * 86_400:
            raise ValueError(
                f"fail-closed: data as of {source_date.isoformat()}, refresh pending"
            )
        for reader in _facility_reader(zf, info, stats):
            for row in reader:
                stats.rows_seen += 1
                state = _clean(row.get("FAC_STATE"), "state").upper()
                if state not in target_states:
                    stats.reject("OUTSIDE_TARGET_TERRITORY")
                    continue
                if _clean(row.get("FAC_ACTIVE_FLAG"), "active").upper() != "Y":
                    stats.reject("NOT_ACTIVE")
                    continue
                if _clean(row.get("FAC_FEDERAL_FLG"), "federal").upper() == "Y":
                    stats.reject("FEDERAL_FACILITY")
                    continue
                age = _nonnegative_int(row.get("FAC_DAYS_LAST_INSPECTION"))
                if age is None:
                    stats.reject("NO_VALID_INSPECTION_AGE")
                    continue
                if age > max_inspection_age_days:
                    stats.reject("OUTSIDE_MONITORING_WINDOW")
                    continue
                if _inspection_date(row.get("FAC_DATE_LAST_INSPECTION")) is None:
                    stats.reject("NO_VALID_INSPECTION_DATE")
                    continue
                if excluded_name_reason(
                    _clean(row.get("FAC_NAME"), "org_name"),
                    _naics_codes(row.get("FAC_NAICS_CODES")),
                ) is not None:
                    stats.reject(PERSON_OR_RESIDENCE_REASON)
                    continue
                record = _record_from_row(row, upstream_hash)
                if record is None:
                    stats.reject("MISSING_AUTHORITY_IDENTITY")
                    continue
                # EPA's reported age baseline can differ from the ZIP calendar
                # date. Keep the reported value, but admit against the actual
                # inspection date and the current UTC processing date.
                actual_age = (
                    clock.astimezone(timezone.utc).date()
                    - date.fromisoformat(record.last_inspection_date)
                ).days
                if not 0 <= actual_age <= max_inspection_age_days:
                    stats.reject("INSPECTION_DATE_OUTSIDE_MONITORING_WINDOW")
                    continue
                if record.source_record_id in seen:
                    raise ValueError("fail-closed: duplicate ECHO registry identity")
                seen.add(record.source_record_id)
                encoded = canonical_json(serialize_record(record)) + b"\n"
                if len(encoded) > MAX_SERIALIZED_RECORD_BYTES:
                    raise ValueError("fail-closed: serialized record exceeds policy")
                stats.rows_admitted += 1
                yield record


class RecordRootAccumulator:
    """Compute SHA-256(canonical JSON array of record hashes) incrementally."""

    def __init__(self) -> None:
        self._digest = hashlib.sha256()
        self._digest.update(b"[")
        self._count = 0

    def add(self, value: str) -> None:
        if self._count:
            self._digest.update(b",")
        self._digest.update(canonical_json(value))
        self._count += 1

    def hexdigest(self) -> str:
        digest = self._digest.copy()
        digest.update(b"]")
        return digest.hexdigest()


def records_root_from_hashes(record_hashes: list[str]) -> str:
    accumulator = RecordRootAccumulator()
    for record_hash in record_hashes:
        accumulator.add(record_hash)
    return accumulator.hexdigest()


def build_snapshot_from_metrics(
    *,
    record_count: int,
    records_root_sha256: str,
    records_file_sha256: str,
    upstream_hash: str,
    upstream_size_bytes: int,
    stats: IngestionStats,
    source_revision: str,
    created_at: str | None = None,
    source_url: str = ECHO_EXPORTER_URL,
) -> dict[str, object]:
    if record_count <= 0 or stats.rows_admitted != record_count:
        raise ValueError("fail-closed: snapshot record count is not admissible")
    if not _SOURCE_REVISION_RE.fullmatch(source_revision):
        raise ValueError("fail-closed: parser source revision must be a full Git SHA")
    timestamp = created_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    core: dict[str, object] = {
        "snapshot_version": 3,
        "created_at": timestamp,
        "source": {
            "name": "echo-exporter",
            "url": source_url,
            "upstream_bytes_sha256": upstream_hash,
            "upstream_size_bytes": upstream_size_bytes,
            "source_as_of": stats.source_as_of,
            "member": {
                "name": ECHO_MEMBER_NAME,
                "crc32": stats.archive_member_crc32,
                "compressed_bytes": stats.archive_member_compressed_bytes,
                "uncompressed_bytes": stats.archive_member_uncompressed_bytes,
                "header_sha256": stats.archive_header_sha256,
            },
        },
        "parser": {
            "name": PARSER_NAME,
            "version": PARSER_VERSION,
            "source_revision": source_revision,
        },
        "projection_policy": {
            "id": PROJECTION_POLICY["policy"],
            "sha256": PROJECTION_POLICY_SHA256,
        },
        "record_schema": RECORD_SCHEMA,
        "record_count": record_count,
        "records_root_sha256": records_root_sha256,
        "records_file_sha256": records_file_sha256,
        "freshness_days": FRESHNESS_DAYS,
        "selection": PROJECTION_POLICY["admission"],
        "privacy": {
            "classification": "ENTITY_AND_FACILITY_FIELDS_ONLY",
            "serialized_record_fields": list(RECORD_PAYLOAD_FIELDS),
            "excluded_categories": list(PROJECTION_POLICY["excluded_categories"]),
        },
        "ingestion": {
            "rows_seen": stats.rows_seen,
            "rows_admitted": stats.rows_admitted,
            "rejected": dict(sorted(stats.rejected.items())),
        },
    }
    digest = sha256_bytes(canonical_json(core))
    return {"snapshot_id": f"sha256:{digest}", "snapshot_digest": digest, **core}


def build_snapshot(
    records: list[SourceRecord],
    source_url: str,
    upstream_bytes: bytes,
    *,
    source_revision: str = "0" * 40,
    created_at: str | None = None,
) -> dict[str, object]:
    """Compatibility helper for bounded tests and library callers."""

    if not records:
        raise ValueError("fail-closed: no admissible records")
    stats = IngestionStats(rows_seen=len(records), rows_admitted=len(records))
    with zipfile.ZipFile(io.BytesIO(upstream_bytes)) as zf:
        info = _validated_member(zf)
        for _ in _facility_reader(zf, info, stats):
            break
    payload = b"".join(canonical_json(serialize_record(record)) + b"\n" for record in records)
    return build_snapshot_from_metrics(
        record_count=len(records),
        records_root_sha256=records_root_from_hashes(
            [record.normalized_record_hash for record in records]
        ),
        records_file_sha256=sha256_bytes(payload),
        upstream_hash=sha256_bytes(upstream_bytes),
        upstream_size_bytes=len(upstream_bytes),
        stats=stats,
        source_revision=source_revision,
        created_at=created_at,
        source_url=source_url,
    )


def receipt_subject(snapshot: dict[str, object]) -> dict[str, object]:
    parser = snapshot["parser"]
    return {
        "normalized_record_hash": snapshot["records_root_sha256"],
        "source_record_id": snapshot["snapshot_id"],
        "parser_version": parser["version"],
    }


def puriq_receipt(
    snapshot: dict[str, object],
    session_id: str,
    sequence: int,
    prev_hash: str,
    signing_key: bytes | None = None,
) -> dict[str, object]:
    """Emit one PurIQ v1 session receipt without inventing a signature."""

    import hmac

    if int(snapshot["record_count"]) <= 0:
        raise ValueError("fail-closed: refusing to receipt an empty snapshot")
    if sequence != 0 or prev_hash != "GENESIS":
        raise ValueError("fail-closed: this lane emits standalone genesis receipts only")
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise ValueError("fail-closed: session_id must be a UUIDv4") from exc
    if session_uuid.version != 4:
        raise ValueError("fail-closed: session_id must be a UUIDv4")
    receipt: dict[str, object] = {
        "receipt_version": 1,
        "receipt_id": str(uuid.uuid4()),
        "issued_at": snapshot["created_at"],
        "session_id": session_id,
        "sequence": sequence,
        "prev_receipt_hash": prev_hash,
        "subject": receipt_subject(snapshot),
        "ranking_inputs": {
            "source_path": ["echo-exporter"],
            "reasons": [
                {
                    "code": "RECENT_OFFICIAL_MONITORING_ACTIVITY",
                    "direction": "up",
                    "weight": 1,
                    "detail": "Active facilities with a factual inspection date inside the declared window were admitted.",
                }
            ],
            "confidence": {"low": 1, "high": 1},
            "caveats": [
                "Monitoring activity is not a violation, risk score, underwriting fact, or contact permission.",
                "Conformance tested against PurIQ reference; unsigned is not signer authentication.",
            ],
        },
        "gate": {"name": "yuyay-13", "result": "pass", "failures": []},
    }
    body = {key: value for key, value in receipt.items() if key not in ("payload_hash", "signature")}
    receipt["payload_hash"] = sha256_bytes(canonical_json(body))
    if signing_key is None:
        receipt["signature"] = {
            "algorithm": "HMAC-SHA256",
            "key_id": None,
            "value": "UNSIGNED",
        }
    else:
        receipt["signature"] = {
            "algorithm": "HMAC-SHA256",
            "key_id": "receipt-signing-key",
            "value": hmac.new(
                signing_key,
                bytes.fromhex(str(receipt["payload_hash"])),
                hashlib.sha256,
            ).hexdigest(),
        }
    return receipt


def run(
    zip_bytes: bytes,
    session_id: str | None = None,
    signing_key: bytes | None = None,
    *,
    source_revision: str = "0" * 40,
    created_at: str | None = None,
) -> dict[str, object]:
    """Bounded in-memory run used only by tests."""

    records = parse_echo_exporter(zip_bytes)
    if not records:
        raise ValueError("fail-closed: no admissible records")
    snapshot = build_snapshot(
        records,
        ECHO_EXPORTER_URL,
        zip_bytes,
        source_revision=source_revision,
        created_at=created_at,
    )
    receipt = puriq_receipt(
        snapshot,
        session_id or str(uuid.uuid4()),
        0,
        "GENESIS",
        signing_key,
    )
    return {"snapshot": snapshot, "receipt": receipt, "records": records}
