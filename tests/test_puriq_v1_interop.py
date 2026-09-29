"""Cross-language conformance against an immutable SZL PurIQ v1 reference."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.test_echo_ingestor import _base_row, _fixture_zip
from tools.ingestor.echo_ingestor import run

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "tests" / "vendor" / "puriq_v1"


def reference_verdict(receipts: list[dict]) -> dict:
    script = """
const fs = require('node:fs');
const api = require('./tests/vendor/puriq_v1/puriq_receipt_v1.js');
const receipts = JSON.parse(fs.readFileSync(0, 'utf8'));
api.verifySession(receipts).then(v => process.stdout.write(JSON.stringify(v)))
  .catch(e => { process.stderr.write(e.message); process.exitCode = 1; });
"""
    result = subprocess.run(
        ["node", "-e", script], input=json.dumps(receipts, ensure_ascii=False),
        encoding="utf-8", capture_output=True, cwd=ROOT, timeout=20, check=True,
    )
    return json.loads(result.stdout)


def test_literal_upstream_vectors_keep_declared_verdicts():
    document = json.loads((VENDOR / "vectors.json").read_text(encoding="utf-8"))
    for vector in document["vectors"]:
        result = reference_verdict(vector["receipts"])
        for key, expected in vector["expected"].items():
            assert result[key] == expected, vector["name"]


def test_emitted_echo_receipt_verifies_in_immutable_javascript_reference():
    receipt = run(_fixture_zip([_base_row()]))["receipt"]
    verdict = reference_verdict([receipt])
    assert verdict["valid"], verdict
    assert verdict["results"][0]["payload_hash_valid"] is True
    assert verdict["results"][0]["signature_state"] == "UNSIGNED"
    assert verdict["results"][0]["signature_valid"] is None


def test_changed_python_receipt_is_rejected_by_reference():
    receipt = run(_fixture_zip([_base_row()]))["receipt"]
    receipt["subject"]["source_record_id"] = "changed"
    verdict = reference_verdict([receipt])
    assert verdict["valid"] is False
    assert "payload_hash_mismatch" in verdict["results"][0]["errors"]


@pytest.mark.parametrize("lane", ["fmcsa", "form5500", "usaspending"])
def test_scheduled_lane_receipts_verify_against_merged_reference(lane):
    from tests.test_frontier_snapshot import make_bundle

    verdict = reference_verdict([make_bundle(lane)["receipt"]])
    assert verdict["valid"], verdict
    assert verdict["results"][0]["signature_state"] == "UNSIGNED"
    assert verdict["results"][0]["signature_valid"] is None
