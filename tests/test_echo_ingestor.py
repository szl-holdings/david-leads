"""Federal Refresh ingestion safety tests using synthetic data only."""

from __future__ import annotations

import csv
import io
import json
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tools.ingestor.echo_ingestor import (
    ECHO_MEMBER_NAME,
    ECHO_REQUIRED_HEADERS,
    PARSER_VERSION,
    PROJECTION_POLICY_SHA256,
    RECORD_METADATA_FIELDS,
    RECORD_PAYLOAD_FIELDS,
    parse_echo_exporter,
    run,
    serialize_record,
)
from tools.ingestor.echo_ingestor_cli import ingest_zip

SOURCE_REVISION = "a" * 40


def _base_row(**overrides: str) -> dict[str, str]:
    row = {field: "" for field in ECHO_REQUIRED_HEADERS}
    row.update(
        {
            "REGISTRY_ID": "110000000001",
            "FAC_NAME": "FIXTURE ALPHA MANUFACTURING LLC",
            "FAC_CITY": "ALBANY",
            "FAC_STATE": "NY",
            "FAC_ZIP": "12207-1234",
            "FAC_COUNTY": "ALBANY",
            "FAC_EPA_REGION": "02",
            "FAC_FEDERAL_FLG": "N",
            "FAC_ACTIVE_FLAG": "Y",
            "FAC_INSPECTION_COUNT": "4",
            "FAC_DATE_LAST_INSPECTION": (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%m/%d/%Y"),
            "FAC_DAYS_LAST_INSPECTION": "3",
            "FAC_NAICS_CODES": "332710 541330",
            "AIR_FLAG": "Y",
            "NPDES_FLAG": "N",
            "SDWIS_FLAG": "N",
            "RCRA_FLAG": "Y",
            "TRI_FLAG": "N",
            "GHG_FLAG": "N",
        }
    )
    row.update(overrides)
    return row


def _fixture_zip(
    rows: list[dict[str, str]],
    *,
    extra_fields: tuple[str, ...] = (),
    missing_field: str | None = None,
    source_date: datetime | None = None,
) -> bytes:
    fields = [field for field in ECHO_REQUIRED_HEADERS if field != missing_field]
    fields.extend(extra_fields)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        member = zipfile.ZipInfo(ECHO_MEMBER_NAME, (source_date or datetime.now(timezone.utc)).timetuple()[:6])
        member.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(member, output.getvalue())
    return buffer.getvalue()


def _write_zip(path: Path, rows: list[dict[str, str]], **kwargs: object) -> Path:
    path.write_bytes(_fixture_zip(rows, **kwargs))
    return path


def _created_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_parse_emits_only_explicit_v3_projection():
    record = parse_echo_exporter(_fixture_zip([_base_row()]))[0]
    serialized = serialize_record(record)
    assert set(serialized) == set(RECORD_PAYLOAD_FIELDS + RECORD_METADATA_FIELDS)
    assert "raw" not in serialized
    assert serialized["source_record_id"] == "echo:110000000001"
    assert serialized["postal_code"] == "12207"
    assert serialized["naics_codes"] == ["332710", "541330"]
    assert serialized["programs"] == ["AIR", "RCRA"]
    assert serialized["parser_version"] == PARSER_VERSION
    assert serialized["projection_policy_sha256"] == PROJECTION_POLICY_SHA256


def test_privacy_sentinels_never_enter_any_output_byte(tmp_path: Path):
    forbidden = {
        "FAC_STREET": "SENTINEL_PRIVATE_STREET",
        "FAC_LAT": "SENTINEL_LATITUDE",
        "FAC_LONG": "SENTINEL_LONGITUDE",
        "FAC_PERCENT_MINORITY": "SENTINEL_DEMOGRAPHIC",
        "FAC_COMPLIANCE_STATUS": "SENTINEL_COMPLIANCE",
        "FAC_TOTAL_PENALTIES": "SENTINEL_PENALTY",
        "FAC_CONTACT_NAME": "SENTINEL_PERSON",
        "FAC_CONTACT_EMAIL": "SENTINEL_EMAIL",
        "FAC_CONTACT_PHONE": "SENTINEL_PHONE",
    }
    row = _base_row(**forbidden)
    zip_path = _write_zip(
        tmp_path / "echo.zip", [row], extra_fields=tuple(forbidden)
    )
    out = tmp_path / "snapshot"
    ingest_zip(
        zip_path,
        out,
        source_revision=SOURCE_REVISION,
        created_at=_created_now(),
    )
    emitted = b"\n".join(path.read_bytes() for path in sorted(out.iterdir()))
    for key, value in forbidden.items():
        assert key.encode() not in emitted
        assert value.encode() not in emitted
    assert b'"raw"' not in emitted


def test_streaming_filters_non_operational_rows_and_balances_counts(tmp_path: Path):
    rows = [
        _base_row(),
        _base_row(REGISTRY_ID="110000000002", FAC_STATE="CA"),
        _base_row(REGISTRY_ID="110000000003", FAC_ACTIVE_FLAG="N"),
        _base_row(REGISTRY_ID="110000000004", FAC_FEDERAL_FLG="Y"),
        _base_row(REGISTRY_ID="110000000005", FAC_DAYS_LAST_INSPECTION="999"),
        _base_row(REGISTRY_ID="110000000006", FAC_DATE_LAST_INSPECTION="BAD"),
    ]
    zip_path = _write_zip(tmp_path / "echo.zip", rows)
    result = ingest_zip(
        zip_path,
        tmp_path / "snapshot",
        source_revision=SOURCE_REVISION,
        created_at=_created_now(),
    )
    ingestion = result["snapshot"]["ingestion"]
    assert result["snapshot"]["record_count"] == 1
    assert ingestion["rows_seen"] == 6
    assert ingestion["rows_admitted"] + sum(ingestion["rejected"].values()) == 6


def test_content_hashes_are_deterministic_for_same_source_and_time(tmp_path: Path):
    zip_path = _write_zip(tmp_path / "echo.zip", [_base_row()])
    created_at = _created_now()
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_result = ingest_zip(
        zip_path,
        first,
        source_revision=SOURCE_REVISION,
        created_at=created_at,
    )
    second_result = ingest_zip(
        zip_path,
        second,
        source_revision=SOURCE_REVISION,
        created_at=created_at,
    )
    assert (first / "records.jsonl").read_bytes() == (second / "records.jsonl").read_bytes()
    assert first_result["snapshot"]["snapshot_id"] == second_result["snapshot"]["snapshot_id"]
    assert first_result["snapshot"]["records_file_sha256"] == second_result["snapshot"]["records_file_sha256"]


def test_zero_records_and_low_cardinality_leave_no_final_directory(tmp_path: Path):
    zip_path = _write_zip(tmp_path / "echo.zip", [])
    out = tmp_path / "snapshot"
    with pytest.raises(ValueError, match="below required floor"):
        ingest_zip(
            zip_path,
            out,
            source_revision=SOURCE_REVISION,
            created_at=_created_now(),
        )
    assert not out.exists()
    assert not list(tmp_path.glob(".snapshot-*"))


def test_minimum_cardinality_gate_fails_closed(tmp_path: Path):
    zip_path = _write_zip(tmp_path / "echo.zip", [_base_row()])
    out = tmp_path / "snapshot"
    with pytest.raises(ValueError, match="below required floor 2"):
        ingest_zip(
            zip_path,
            out,
            source_revision=SOURCE_REVISION,
            created_at=_created_now(),
            minimum_records=2,
        )
    assert not out.exists()


def test_missing_required_header_fails_closed(tmp_path: Path):
    zip_path = _write_zip(
        tmp_path / "echo.zip",
        [_base_row()],
        missing_field="REGISTRY_ID",
    )
    with pytest.raises(ValueError, match="missing ECHO headers"):
        ingest_zip(
            zip_path,
            tmp_path / "snapshot",
            source_revision=SOURCE_REVISION,
            created_at=_created_now(),
        )


def test_missing_registry_has_no_synthetic_fallback():
    assert parse_echo_exporter(_fixture_zip([_base_row(REGISTRY_ID="")])) == []


def test_duplicate_registry_identity_fails_closed(tmp_path: Path):
    zip_path = _write_zip(
        tmp_path / "echo.zip",
        [_base_row(), _base_row(FAC_NAME="SECOND NAME LLC")],
    )
    with pytest.raises(ValueError, match="duplicate ECHO registry"):
        ingest_zip(
            zip_path,
            tmp_path / "snapshot",
            source_revision=SOURCE_REVISION,
            created_at=_created_now(),
        )


def test_wrong_or_multiple_canonical_members_fail_closed():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("other.csv", "a,b\n1,2\n")
    with pytest.raises(ValueError, match="exactly ECHO_EXPORTER.csv"):
        parse_echo_exporter(buffer.getvalue())

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(ECHO_MEMBER_NAME, "a\n1\n")
        archive.writestr(f"nested/{ECHO_MEMBER_NAME}", "a\n2\n")
    with pytest.raises(ValueError, match="exactly ECHO_EXPORTER.csv"):
        parse_echo_exporter(buffer.getvalue())


def test_invalid_utf8_fails_instead_of_replacing_bytes(tmp_path: Path):
    header = ",".join(ECHO_REQUIRED_HEADERS).encode("utf-8") + b"\n"
    bad_row = b"110000000001," + b"\xff" + b"," * (len(ECHO_REQUIRED_HEADERS) - 2) + b"\n"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(ECHO_MEMBER_NAME, header + bad_row)
    path = tmp_path / "bad.zip"
    path.write_bytes(buffer.getvalue())
    with pytest.raises(UnicodeDecodeError):
        ingest_zip(
            path,
            tmp_path / "snapshot",
            source_revision=SOURCE_REVISION,
            created_at=_created_now(),
        )


def test_existing_output_is_never_overwritten(tmp_path: Path):
    zip_path = _write_zip(tmp_path / "echo.zip", [_base_row()])
    out = tmp_path / "snapshot"
    out.mkdir()
    marker = out / "owner.txt"
    marker.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        ingest_zip(
            zip_path,
            out,
            source_revision=SOURCE_REVISION,
            created_at=_created_now(),
        )
    assert marker.read_text(encoding="utf-8") == "keep"


def test_empty_payload_and_empty_admission_fail_closed():
    with pytest.raises(ValueError):
        run(b"")
    with pytest.raises(ValueError, match="no admissible records"):
        run(_fixture_zip([]))


def test_receipt_is_explicitly_unsigned_and_standalone():
    result = run(
        _fixture_zip([_base_row()]),
        session_id=str(uuid.uuid4()),
        created_at=_created_now(),
    )
    assert result["receipt"]["signature"] == {
        "algorithm": "HMAC-SHA256",
        "key_id": None,
        "value": "UNSIGNED",
    }
    assert result["receipt"]["sequence"] == 0
    assert result["receipt"]["prev_receipt_hash"] == "GENESIS"
    assert "unsigned is not signer authentication" in " ".join(
        result["receipt"]["ranking_inputs"]["caveats"]
    )
    assert type(result["receipt"]["ranking_inputs"]["reasons"][0]["weight"]) is int
    assert all(type(value) is int for value in result["receipt"]["ranking_inputs"]["confidence"].values())


def test_stale_upstream_cannot_be_refreshed_by_new_created_at(tmp_path: Path):
    upstream_date = datetime.now(timezone.utc) - timedelta(days=30)
    zip_path = _write_zip(tmp_path / "echo.zip", [_base_row()], source_date=upstream_date)
    with pytest.raises(ValueError, match=f"data as of {upstream_date.date().isoformat()}, refresh pending"):
        ingest_zip(zip_path, tmp_path / "snapshot", source_revision=SOURCE_REVISION, created_at=_created_now())
    assert not (tmp_path / "snapshot").exists()
    assert not list(tmp_path.glob(".snapshot-*"))


def test_admission_recomputes_inspection_age_without_rewriting_reported_age(tmp_path: Path):
    rows = [
        _base_row(FAC_DAYS_LAST_INSPECTION="4"),  # EPA age baseline may differ from ZIP date.
        _base_row(REGISTRY_ID="110000000002", FAC_DATE_LAST_INSPECTION=(datetime.now(timezone.utc) - timedelta(days=366)).strftime("%m/%d/%Y"), FAC_DAYS_LAST_INSPECTION="360"),
        _base_row(REGISTRY_ID="110000000003", FAC_DATE_LAST_INSPECTION=(datetime.now(timezone.utc) + timedelta(days=1)).strftime("%m/%d/%Y"), FAC_DAYS_LAST_INSPECTION="0"),
    ]
    zip_path = _write_zip(tmp_path / "echo.zip", rows)
    out = tmp_path / "snapshot"
    result = ingest_zip(zip_path, out, source_revision=SOURCE_REVISION)
    assert result["snapshot"]["record_count"] == 1
    assert result["snapshot"]["ingestion"]["rejected"]["INSPECTION_DATE_OUTSIDE_MONITORING_WINDOW"] == 2
    assert json.loads((out / "records.jsonl").read_text(encoding="utf-8"))["days_since_last_inspection"] == 4
