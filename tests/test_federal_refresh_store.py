# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timedelta, timezone

from app.federal_refresh_store import FederalRefreshStore, StoreState, verify_snapshot_payload
from tests.test_frontier_snapshot import make_bundle


def test_fresh_snapshot_uses_current_closed_contract():
    result = FederalRefreshStore(loader=make_bundle).fetch_snapshot_organizations(["NY"])
    assert result.state == StoreState.FRESH and len(result.records) == 1
    assert result.records[0]["research_gate"] == "PUBLIC_RESEARCH_ONLY"


def test_no_snapshot_reports_empty():
    result = FederalRefreshStore(loader=lambda: None).fetch_snapshot_organizations()
    assert result.state == StoreState.EMPTY and not result.records


def test_legacy_raw_record_contract_is_rejected():
    bundle = {"snapshot": {"record_count": 1}, "receipt": {}, "records": [{"raw": {}, "org_name": "Example"}]}
    result = FederalRefreshStore(loader=lambda: bundle).fetch_snapshot_organizations()
    assert result.state == StoreState.UNVERIFIED and not result.records
    assert verify_snapshot_payload(bundle["snapshot"], bundle["receipt"], bundle["records"])[0] is False


def test_stale_snapshot_has_honest_date_message_and_no_records():
    old = (datetime.now(timezone.utc) - timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = FederalRefreshStore(loader=lambda: make_bundle(created=old)).fetch_snapshot_organizations()
    assert result.state == StoreState.STALE and not result.records
    assert result.message == f"data as of {old[:10]}, refresh pending"


def test_wrong_lane_and_uncovered_state_fail_closed():
    assert FederalRefreshStore(loader=lambda: make_bundle("form5500")).fetch_snapshot_organizations().state == StoreState.UNVERIFIED
    assert FederalRefreshStore(loader=make_bundle).fetch_snapshot_organizations(["TX"]).state == StoreState.UNVERIFIED


def test_tampered_records_never_served():
    bundle = make_bundle()
    bundle["records_bytes"] = bundle["records_bytes"].replace(b"ALBANY", b"PRIVATE")
    result = FederalRefreshStore(loader=lambda: bundle).fetch_snapshot_organizations()
    assert result.state == StoreState.UNVERIFIED and result.records == []
