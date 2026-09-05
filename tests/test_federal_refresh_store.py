"""Tests for the Federal Refresh dataset-backed store.

Fixtures are synthetic and live ONLY in tests (no-sample-substitution rule).
"""

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from app.federal_refresh_store import FederalRefreshStore, StoreState


def _canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _sha256(d):
    return hashlib.sha256(d).hexdigest()


def make_bundle(created=None, tamper_record=False, tamper_gate=False):
    created = created or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rec = {"source_record_id": "echo:1", "org_name": "Alpha", "state": "PA", "raw": {}}
    rec["normalized_record_hash"] = _sha256(_canon({
        "source_record_id": rec["source_record_id"], "org_name": rec["org_name"],
        "state": rec["state"], "raw": rec["raw"]}))
    rec["parser_version"] = "1.0.0"
    rec["source_receipt"] = "0" * 64
    if tamper_record:
        rec["org_name"] = "Tampered"
    snap = {"snapshot_version": 1, "snapshot_id": str(uuid.uuid4()), "created_at": created,
            "source": {"name": "echo-exporter"}, "record_count": 1,
            "records_hash": _sha256(_canon([rec["normalized_record_hash"]])), "freshness_days": 8}
    receipt = {"receipt_version": 1, "receipt_id": str(uuid.uuid4()), "issued_at": created,
               "session_id": "s", "sequence": 0, "prev_receipt_hash": "GENESIS",
               "subject": {"normalized_record_hash": snap["records_hash"],
                           "source_record_id": snap["snapshot_id"], "parser_version": "1.0.0"},
               "ranking_inputs": {"source_path": ["echo-exporter"], "reasons": [],
                                  "confidence": {"low": 1.0, "high": 1.0}, "caveats": []},
               "gate": {"name": "yuyay-13", "result": "fail" if tamper_gate else "pass", "failures": []}}
    receipt["payload_hash"] = _sha256(_canon({k: v for k, v in receipt.items()
                                              if k not in ("payload_hash", "signature")}))
    receipt["signature"] = {"algorithm": "HMAC-SHA256", "key_id": None, "value": "UNSIGNED"}
    return {"snapshot": snap, "receipt": receipt, "records": [rec]}


def test_fresh_snapshot_serves_records():
    store = FederalRefreshStore(loader=lambda: make_bundle())
    r = store.fetch_snapshot_organizations(["PA"], 10)
    assert r.state == StoreState.FRESH
    assert len(r.records) == 1
    assert r.receipt is not None


def test_state_filter():
    store = FederalRefreshStore(loader=lambda: make_bundle())
    assert store.fetch_snapshot_organizations(["OH"], 10).records == []


def test_empty_when_no_snapshot():
    r = FederalRefreshStore(loader=lambda: None).fetch_snapshot_organizations()
    assert r.state == StoreState.EMPTY
    assert "refresh pending" in r.message


def test_unverified_on_tampered_record():
    r = FederalRefreshStore(loader=lambda: make_bundle(tamper_record=True)).fetch_snapshot_organizations()
    assert r.state == StoreState.UNVERIFIED
    assert r.records == []


def test_unverified_on_gate_failure():
    r = FederalRefreshStore(loader=lambda: make_bundle(tamper_gate=True)).fetch_snapshot_organizations()
    assert r.state == StoreState.UNVERIFIED


def test_stale_is_honest_not_fresh():
    old = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = FederalRefreshStore(loader=lambda: make_bundle(created=old)).fetch_snapshot_organizations()
    assert r.state == StoreState.STALE
    assert "data as of" in r.message and "refresh pending" in r.message
