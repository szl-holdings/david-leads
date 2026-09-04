"""Tests for verify_snapshot: roundtrip plus tamper cases.

Fixtures are synthetic and live ONLY in tests (no-sample-substitution rule).
"""

import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tools.ingestor.echo_ingestor import run
from tools.ingestor.verify_snapshot import verify


def _fixture_zip(rows):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        out = io.StringIO()
        w = csv.DictWriter(out, fieldnames=["REGISTRY_ID", "FAC_NAME", "FAC_STATE"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
        zf.writestr("ECHO_EXPORTER.csv", out.getvalue())
    return buf.getvalue()


ROWS = [{"REGISTRY_ID": "110000000001", "FAC_NAME": "Fixture Alpha Corp", "FAC_STATE": "PA"}]


def _write_snapshot_dir(tmp_path: Path) -> Path:
    result = run(_fixture_zip(ROWS), session_id="s-test")
    d = tmp_path / "snap"
    d.mkdir()
    (d / "snapshot.json").write_text(json.dumps(result["snapshot"]))
    (d / "receipt.json").write_text(json.dumps(result["receipt"]))
    with (d / "records.jsonl").open("w") as fh:
        for r in result["records"]:
            fh.write(json.dumps({
                "source_record_id": r.source_record_id,
                "org_name": r.org_name,
                "state": r.state,
                "raw": r.raw,
                "normalized_record_hash": r.normalized_record_hash,
                "parser_version": r.parser_version,
                "source_receipt": r.source_receipt,
            }) + "\n")
    return d


def test_valid_snapshot_verifies(tmp_path):
    assert verify(_write_snapshot_dir(tmp_path)) == 0


def test_tampered_record_content_fails(tmp_path):
    d = _write_snapshot_dir(tmp_path)
    rec = json.loads((d / "records.jsonl").read_text().strip())
    rec["org_name"] = "Tampered Inc"
    (d / "records.jsonl").write_text(json.dumps(rec) + "\n")
    assert verify(d) != 0


def test_tampered_records_hash_fails(tmp_path):
    d = _write_snapshot_dir(tmp_path)
    snap = json.loads((d / "snapshot.json").read_text())
    snap["records_hash"] = "0" * 64
    (d / "snapshot.json").write_text(json.dumps(snap))
    assert verify(d) != 0


def test_tampered_receipt_fails(tmp_path):
    d = _write_snapshot_dir(tmp_path)
    rc = json.loads((d / "receipt.json").read_text())
    rc["sequence"] = 99
    (d / "receipt.json").write_text(json.dumps(rc))
    assert verify(d) != 0


def test_gate_failure_receipt_fails(tmp_path):
    d = _write_snapshot_dir(tmp_path)
    rc = json.loads((d / "receipt.json").read_text())
    rc["gate"]["result"] = "fail"
    import hashlib as hl
    body = {k: v for k, v in rc.items() if k not in ("payload_hash", "signature")}
    rc["payload_hash"] = hl.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    (d / "receipt.json").write_text(json.dumps(rc))
    assert verify(d) != 0


def test_stale_snapshot_fails(tmp_path):
    d = _write_snapshot_dir(tmp_path)
    snap = json.loads((d / "snapshot.json").read_text())
    snap["created_at"] = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    (d / "snapshot.json").write_text(json.dumps(snap))
    assert verify(d) != 0


def test_unsigned_receipt_without_key_id_passes(tmp_path):
    d = _write_snapshot_dir(tmp_path)
    rc = json.loads((d / "receipt.json").read_text())
    assert rc["signature"]["value"] == "UNSIGNED"
    assert verify(d) == 0
