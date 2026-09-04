"""Tests for the Federal Refresh ECHO ingestor.

Fixtures are synthetic and live ONLY in this test file. The runtime ingestor
never ships fixture data (no-sample-substitution rule).
"""

import csv
import io
import zipfile

import pytest

from tools.ingestor.echo_ingestor import (
    ECHO_EXPORTER_URL,
    build_snapshot,
    parse_echo_exporter,
    run,
)


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


ROWS = [
    {"REGISTRY_ID": "110000000001", "FAC_NAME": "Fixture Alpha Corp", "FAC_STATE": "PA"},
    {"REGISTRY_ID": "110000000002", "FAC_NAME": "Fixture Beta LLC", "FAC_STATE": "OH"},
]


def test_parse_binds_by_header_name():
    records = parse_echo_exporter(_fixture_zip(ROWS))
    assert len(records) == 2
    assert records[0].source_record_id == "echo:110000000001"
    assert records[0].org_name == "Fixture Alpha Corp"
    assert records[0].state == "PA"


def test_record_hashes_are_sha256_hex():
    r = parse_echo_exporter(_fixture_zip(ROWS))[0]
    assert len(r.normalized_record_hash) == 64
    assert len(r.source_receipt) == 64
    int(r.normalized_record_hash, 16)


def test_snapshot_binds_upstream_bytes():
    zb = _fixture_zip(ROWS)
    records = parse_echo_exporter(zb)
    snap = build_snapshot(records, ECHO_EXPORTER_URL, zb)
    assert snap["record_count"] == 2
    assert len(snap["records_hash"]) == 64
    assert snap["source"]["upstream_bytes_sha256"]


def test_receipt_unsigned_is_honest_and_valid():
    result = run(_fixture_zip(ROWS), session_id="s-test")
    sig = result["receipt"]["signature"]
    assert sig["value"] == "UNSIGNED"
    assert sig["key_id"] is None


def test_fail_closed_on_empty_payload():
    with pytest.raises(ValueError):
        run(b"")


def test_fail_closed_on_zip_without_csv():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "no csv here")
    with pytest.raises(ValueError):
        run(buf.getvalue())


def test_zero_record_snapshot_carries_caveat():
    result = run(_fixture_zip([]), session_id="s-empty")
    assert result["snapshot"]["record_count"] == 0
    assert "zero records" in result["receipt"]["ranking_inputs"]["caveats"][0]
