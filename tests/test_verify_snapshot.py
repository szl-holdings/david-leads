"""Streaming verifier regression and tamper tests using synthetic data."""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tools.ingestor.echo_ingestor import (
    ECHO_MEMBER_NAME,
    ECHO_REQUIRED_HEADERS,
    canonical_json,
    receipt_subject,
    sha256_bytes,
)
from tools.ingestor.echo_ingestor_cli import ingest_zip
from tools.ingestor.verify_snapshot import verify

SOURCE_REVISION = "b" * 40


def _fixture_zip() -> bytes:
    row = {field: "" for field in ECHO_REQUIRED_HEADERS}
    row.update(
        {
            "REGISTRY_ID": "110000000001",
            "FAC_NAME": "FIXTURE ALPHA MANUFACTURING LLC",
            "FAC_CITY": "ALBANY",
            "FAC_STATE": "NY",
            "FAC_ZIP": "12207",
            "FAC_COUNTY": "ALBANY",
            "FAC_EPA_REGION": "02",
            "FAC_FEDERAL_FLG": "N",
            "FAC_ACTIVE_FLAG": "Y",
            "FAC_INSPECTION_COUNT": "2",
            "FAC_DATE_LAST_INSPECTION": (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%m/%d/%Y"),
            "FAC_DAYS_LAST_INSPECTION": "3",
            "FAC_NAICS_CODES": "332710",
            "AIR_FLAG": "Y",
            "RCRA_FLAG": "Y",
        }
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=list(ECHO_REQUIRED_HEADERS))
        writer.writeheader()
        writer.writerow(row)
        member = zipfile.ZipInfo(ECHO_MEMBER_NAME, datetime.now(timezone.utc).timetuple()[:6])
        member.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(member, output.getvalue())
    return buffer.getvalue()


def _bundle(tmp_path: Path, *, created_at: str | None = None) -> Path:
    zip_path = tmp_path / "echo.zip"
    zip_path.write_bytes(_fixture_zip())
    bundle = tmp_path / "snapshot"
    ingest_zip(
        zip_path,
        bundle,
        source_revision=SOURCE_REVISION,
        created_at=created_at
        or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    return bundle


def _read(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: dict[str, object]) -> None:
    path.write_bytes(canonical_json(value) + b"\n")


def _rehash_receipt(receipt: dict[str, object]) -> None:
    body = {
        key: value
        for key, value in receipt.items()
        if key not in ("payload_hash", "signature")
    }
    receipt["payload_hash"] = sha256_bytes(canonical_json(body))


def _rebind_snapshot_and_receipt(bundle: Path) -> None:
    snapshot_path = bundle / "snapshot.json"
    receipt_path = bundle / "receipt.json"
    snapshot = _read(snapshot_path)
    core = {
        key: value
        for key, value in snapshot.items()
        if key not in ("snapshot_id", "snapshot_digest")
    }
    digest = sha256_bytes(canonical_json(core))
    snapshot["snapshot_digest"] = digest
    snapshot["snapshot_id"] = f"sha256:{digest}"
    receipt = _read(receipt_path)
    receipt["issued_at"] = snapshot["created_at"]
    receipt["subject"] = receipt_subject(snapshot)
    _rehash_receipt(receipt)
    _write(snapshot_path, snapshot)
    _write(receipt_path, receipt)


def test_valid_fresh_snapshot_verifies(tmp_path: Path):
    assert verify(_bundle(tmp_path)) == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("record_count", 2),
        ("records_root_sha256", "0" * 64),
        ("records_file_sha256", "0" * 64),
        ("snapshot_digest", "0" * 64),
        ("snapshot_id", "sha256:" + "0" * 64),
        ("freshness_days", 999),
        ("record_schema", "wrong"),
    ],
)
def test_snapshot_tamper_fails(tmp_path: Path, field: str, value: object):
    bundle = _bundle(tmp_path)
    snapshot_path = bundle / "snapshot.json"
    snapshot = _read(snapshot_path)
    snapshot[field] = value
    _write(snapshot_path, snapshot)
    assert verify(bundle) != 0


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("source", "url", "https://example.invalid/export.zip"),
        ("source", "upstream_bytes_sha256", "0" * 64),
        ("source", "upstream_size_bytes", 999),
        ("parser", "version", "99.0.0"),
        ("parser", "source_revision", "0" * 40),
        ("projection_policy", "sha256", "0" * 64),
        ("privacy", "classification", "ANYTHING_GOES"),
    ],
)
def test_nested_snapshot_tamper_fails(
    tmp_path: Path, section: str, field: str, value: object
):
    bundle = _bundle(tmp_path)
    snapshot_path = bundle / "snapshot.json"
    snapshot = _read(snapshot_path)
    snapshot[section][field] = value
    _write(snapshot_path, snapshot)
    assert verify(bundle) != 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("org_name", "TAMPERED LLC"),
        ("normalized_record_hash", "0" * 64),
        ("source_receipt", "0" * 64),
        ("parser_version", "99.0.0"),
        ("projection_policy_sha256", "0" * 64),
        ("postal_code", "not-zip"),
        ("facility_report_url", "https://example.invalid"),
    ],
)
def test_record_tamper_fails(tmp_path: Path, field: str, value: object):
    bundle = _bundle(tmp_path)
    records_path = bundle / "records.jsonl"
    record = json.loads(records_path.read_text(encoding="utf-8"))
    record[field] = value
    records_path.write_bytes(canonical_json(record) + b"\n")
    assert verify(bundle) != 0


def test_noncanonical_record_json_and_crlf_fail(tmp_path: Path):
    bundle = _bundle(tmp_path)
    records_path = bundle / "records.jsonl"
    record = json.loads(records_path.read_text(encoding="utf-8"))
    records_path.write_bytes(json.dumps(record, indent=2).encode("utf-8") + b"\r\n")
    assert verify(bundle) != 0


def test_duplicate_append_and_truncate_fail(tmp_path: Path):
    bundle = _bundle(tmp_path)
    records_path = bundle / "records.jsonl"
    original = records_path.read_bytes()
    records_path.write_bytes(original + original)
    assert verify(bundle) != 0
    records_path.write_bytes(original[:-1])
    assert verify(bundle) != 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sequence", 1),
        ("prev_receipt_hash", "0" * 64),
        ("chain_state", "HASH_CHAINED"),
        ("session_id", "different-lane"),
        ("issued_at", "1999-01-01T00:00:00Z"),
    ],
)
def test_receipt_tamper_fails_even_after_payload_rehash(
    tmp_path: Path, field: str, value: object
):
    bundle = _bundle(tmp_path)
    receipt_path = bundle / "receipt.json"
    receipt = _read(receipt_path)
    receipt[field] = value
    _rehash_receipt(receipt)
    _write(receipt_path, receipt)
    assert verify(bundle) != 0


def test_receipt_subject_and_gate_tamper_fail_after_rehash(tmp_path: Path):
    bundle = _bundle(tmp_path)
    receipt_path = bundle / "receipt.json"
    receipt = _read(receipt_path)
    receipt["subject"]["record_count"] = 999
    _rehash_receipt(receipt)
    _write(receipt_path, receipt)
    assert verify(bundle) != 0

    receipt = _read(receipt_path)
    receipt["subject"] = _read(bundle / "snapshot.json")
    receipt["gate"] = {"name": "yuyay-13", "result": "fail", "failures": ["x"]}
    _rehash_receipt(receipt)
    _write(receipt_path, receipt)
    assert verify(bundle) != 0


def test_fake_signature_never_passes(tmp_path: Path):
    bundle = _bundle(tmp_path)
    receipt_path = bundle / "receipt.json"
    receipt = _read(receipt_path)
    receipt["signature"] = {
        "algorithm": "HMAC-SHA256",
        "key_id": "receipt-signing-key",
        "value": "0" * 64,
    }
    _write(receipt_path, receipt)
    assert verify(bundle, signing_key=b"wrong") != 0
    assert verify(bundle) != 0


def test_valid_hmac_is_cryptographically_verified(tmp_path: Path):
    bundle = _bundle(tmp_path)
    key = b"unit-test-signing-key"
    receipt_path = bundle / "receipt.json"
    receipt = _read(receipt_path)
    receipt["signature"] = {
        "algorithm": "HMAC-SHA256",
        "key_id": "receipt-signing-key",
        "value": hmac.new(
            key,
            bytes.fromhex(str(receipt["payload_hash"])),
            hashlib.sha256,
        ).hexdigest(),
    }
    _write(receipt_path, receipt)
    assert verify(bundle, signing_key=key, require_signature=True) == 0
    assert verify(bundle, signing_key=b"other", require_signature=True) != 0


def test_unsigned_receipt_is_honest_but_strict_mode_rejects_it(tmp_path: Path):
    bundle = _bundle(tmp_path)
    assert verify(bundle) == 0
    assert verify(bundle, require_signature=True) != 0


def test_future_timestamp_fails_after_all_hashes_are_rebound(tmp_path: Path):
    bundle = _bundle(tmp_path)
    snapshot_path = bundle / "snapshot.json"
    snapshot = _read(snapshot_path)
    snapshot["created_at"] = (
        datetime.now(timezone.utc) + timedelta(hours=1)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write(snapshot_path, snapshot)
    _rebind_snapshot_and_receipt(bundle)
    assert verify(bundle) != 0


def test_historical_integrity_can_be_audited_but_publish_freshness_fails(tmp_path: Path):
    bundle = _bundle(tmp_path)
    future_clock = datetime.now(timezone.utc) + timedelta(days=30)
    assert verify(bundle, now=future_clock, require_fresh=True) != 0
    assert verify(bundle, now=future_clock, require_fresh=False) == 0


def test_fresh_created_at_cannot_launder_stale_source_date(tmp_path: Path):
    bundle = _bundle(tmp_path)
    snapshot_path = bundle / "snapshot.json"
    snapshot = _read(snapshot_path)
    snapshot["source"]["source_as_of"] = (
        datetime.now(timezone.utc) - timedelta(days=30)
    ).date().isoformat()
    _write(snapshot_path, snapshot)
    _rebind_snapshot_and_receipt(bundle)
    assert verify(bundle, require_fresh=True) != 0
    assert verify(bundle, require_fresh=False) == 0


def test_missing_extra_and_symlink_files_fail(tmp_path: Path):
    bundle = _bundle(tmp_path)
    (bundle / "extra.json").write_text("{}", encoding="utf-8")
    assert verify(bundle) != 0
    (bundle / "extra.json").unlink()
    (bundle / "receipt.json").unlink()
    assert verify(bundle) != 0


def test_zero_record_file_fails(tmp_path: Path):
    bundle = _bundle(tmp_path)
    (bundle / "records.jsonl").write_bytes(b"")
    assert verify(bundle) != 0
