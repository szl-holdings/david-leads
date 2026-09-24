# SPDX-License-Identifier: Apache-2.0
"""Synthetic fixtures exercise the published contract; never runtime fallback."""
import copy
import json
import re
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pytest

from app import federal_snapshot as snap
from tools.ingestor.frontier_refresh_cli import DEFAULT_STATES, collect_bundle, main, _collect_with_retry

REVISION = "1234567890abcdef1234567890abcdef12345678"


def fixture_record(lane="fmcsa", state="NY", identity="12345", as_of=None):
    row = {key: "Fixture observation" for key in snap.TEXT_FIELDS}
    row.update(name="Synthetic Fixture Corporation", state=state, city="ALBANY", zip="12207",
               credential=f"Public identifier {identity}", license_or_issue_date="2026-08-01",
               trigger_date="2026-08-01", citation={"label": "Official source", "url": snap.LANES[lane]["url"]},
               source_record={"label": "Official source", "url": snap.LANES[lane]["url"]},
               limitations=["Research observation; no contact permission."],
               receipt_id="PROCESS_RECEIPT_MUST_NOT_PERSIST", raw={"phone": "MUST_NOT_PERSIST"},
               address="MUST_NOT_PERSIST", phone="MUST_NOT_PERSIST")
    system = {"fmcsa": "USDOT", "form5500": "DOL Form 5500 ACK ID", "usaspending": "Federal Award ID"}[lane]
    row["authoritative_entity_ids"] = [{"system": system, "value": identity}]
    if lane == "fmcsa":
        row["operational_snapshot"] = {"power_units": 4, "drivers": 5, "trucks": 3, "buses": 0, "street": "MUST_NOT_PERSIST"}
    elif lane == "form5500":
        basis = datetime.strptime(as_of, "%Y-%m-%d").date() if as_of else datetime.now(timezone.utc).date()
        row["operational_snapshot"] = {"participants_reported": 50, "benefit_categories": ["Life", "Medical", "HMO"], "plan_name": "MUST_NOT_PERSIST", "reported_carriers": ["MUST_NOT_PERSIST"]}
        row["timing"] = {"label": "0-90 days", "next_anniversary": (basis + timedelta(days=40)).isoformat(), "days_to_anniversary": 40, "basis": "reported period", "hypothesis_only": True}
    else:
        row["award"] = {"award_id": identity, "amount": 100000.0, "agency": "Test federal agency", "start_date": "2026-08-01", "end_date": "2027-08-01", "description": "MUST_NOT_PERSIST"}
        row["citation"]["url"] = f"https://www.usaspending.gov/award/CONT_AWD_{identity}_7529_FIXTUREPARENT_7529/latest"
    return row


def fixture_collector(lane="fmcsa", as_of=None):
    def collect(states, limit):
        assert limit == 50
        state = states[0]
        basis = datetime.strptime(as_of, "%Y-%m-%d").date() if as_of else datetime.now(timezone.utc).date()
        window = {"anniversary_start": basis.isoformat(), "anniversary_end": (basis + timedelta(days=365)).isoformat()} if lane == "form5500" else {"start": "2026-08-01", "end": "2026-08-21"}
        return {"mode": "LIVE", "count": 1, "records": [fixture_record(lane, state, f"ID-{state}", basis.isoformat())], "query_window": window}
    return collect


def make_bundle(lane="fmcsa", created=None):
    return collect_bundle(lane, REVISION, states=["NY"], collector=fixture_collector(lane, created[:10] if created else None), created_at=created)


@pytest.mark.parametrize("lane", tuple(snap.LANES))
def test_real_contract_round_trip_minimizes_payload(lane):
    bundle = make_bundle(lane)
    result = snap.verify_bundle(bundle["snapshot"], bundle["receipt"], bundle["records_bytes"])
    assert result["receipt_state"] == "PAYLOAD_VERIFIED_UNSIGNED"
    assert result["records"][0]["research_gate"] == "PUBLIC_RESEARCH_ONLY"
    assert b"MUST_NOT_PERSIST" not in bundle["records_bytes"]
    assert b"PROCESS_RECEIPT" not in bundle["records_bytes"]
    assert bundle["receipt"]["ranking_inputs"]["reasons"][0]["weight"] == 1
    assert type(bundle["receipt"]["ranking_inputs"]["confidence"]["low"]) is int
    assert snap.pointer_for(bundle["snapshot"])["path"].startswith(f"snapshots/{lane}/")


def test_each_capture_mints_new_standalone_receipt():
    a, b = make_bundle(), make_bundle()
    assert a["receipt"]["receipt_id"] != b["receipt"]["receipt_id"]
    assert a["receipt"]["session_id"] != b["receipt"]["session_id"]
    assert a["receipt"]["prev_receipt_hash"] == "GENESIS"


def _awards_bundle(records):
    def collector(states, limit):
        return {"mode": "LIVE", "count": len(records), "records": records,
                "query_window": {"start": "2026-09-03", "end": "2026-09-24"}}
    return collect_bundle("usaspending", REVISION, states=["MI"], collector=collector)


def test_same_piid_and_uei_with_distinct_parent_awards_are_preserved():
    first = fixture_record("usaspending", state="MI", identity="75N95021F00011")
    first["authoritative_entity_ids"].insert(0, {"system": "UEI", "value": "SAMEUEI12345"})
    second = copy.deepcopy(first)
    first["citation"]["url"] = "https://www.usaspending.gov/award/CONT_AWD_75N95021F00011_7529_75N95021D00012_7529/latest"
    second["citation"]["url"] = "https://www.usaspending.gov/award/CONT_AWD_75N95021F00011_7529_75N95021D00015_7529/latest"
    bundle = _awards_bundle([first, second])
    assert bundle["snapshot"]["record_count"] == 2
    verified = snap.verify_bundle(bundle["snapshot"], bundle["receipt"], bundle["records_bytes"])
    verified["path"] = snap.pointer_for(bundle["snapshot"])["path"]
    with mock.patch.object(snap, "load_verified", return_value=verified):
        runtime = snap.load_lane("usaspending", ["MI"])["records"]
    assert [row["source_record_id"] for row in runtime] == [
        "CONT_AWD_75N95021F00011_7529_75N95021D00012_7529",
        "CONT_AWD_75N95021F00011_7529_75N95021D00015_7529",
    ]
    assert all(row["operational_snapshot"]["dataset_source_record_id"] == row["source_record_id"] for row in runtime)
    assert "source_record_id" not in verified["records"][0]


def test_same_generated_award_still_rejected_when_reported_identifiers_differ():
    first = fixture_record("usaspending", state="MI", identity="75N95021F00011")
    second = copy.deepcopy(first)
    second["authoritative_entity_ids"] = [{"system": "UEI", "value": "DIFFERENTUEI"}, {"system": "Federal Award ID", "value": "DIFFERENTPIID"}]
    second["award"]["award_id"] = "DIFFERENTPIID"
    second["credential"] = "UEI DIFFERENTUEI"
    with pytest.raises(snap.SnapshotError, match="duplicate record identity"):
        _awards_bundle([first, second])


@pytest.mark.parametrize("url", [
    "https://www.usaspending.gov/search",
    "https://www.usaspending.gov/award//latest",
    "https://www.usaspending.gov/award/12345/latest",
    "https://www.usaspending.gov/award/CONT_AWD_/latest",
    "https://api.usaspending.gov/award/CONT_AWD_ID_7529_PARENT_7529/latest",
    "https://www.usaspending.gov:443/award/CONT_AWD_ID_7529_PARENT_7529/latest",
    "https://www.usaspending.gov/award/CONT_AWD_ID_7529_PARENT_7529/latest?version=1",
    "https://www.usaspending.gov/award/CONT_AWD_ID_7529_PARENT_7529/latest#fragment",
    "https://www.usaspending.gov/award/CONT_AWD_ID_7529_PARENT_7529/latest/",
    "https://www.usaspending.gov/award/CONT_AWD_ID%5F7529_PARENT_7529/latest",
])
def test_missing_or_noncanonical_generated_award_identity_fails_closed(url):
    row = fixture_record("usaspending", state="MI")
    row["citation"]["url"] = url
    with pytest.raises(snap.SnapshotError, match="canonical USAspending"):
        _awards_bundle([row])


@pytest.mark.parametrize("lane", tuple(snap.LANES))
def test_generic_receipt_matches_immutable_javascript_reference(lane):
    from tests.test_puriq_v1_interop import reference_verdict
    verdict = reference_verdict([make_bundle(lane)["receipt"]])
    assert verdict["valid"] is True


@pytest.mark.parametrize("mutate", [
    lambda b: b["snapshot"].update(record_count=2),
    lambda b: b["snapshot"]["coverage"].update(completed_states=[]),
    lambda b: b["snapshot"]["coverage"]["admission_counts"]["NY"].update(adapter_returned=10),
    lambda b: b["snapshot"].update(snapshot_id="sha256:" + "0" * 64),
    lambda b: b["receipt"]["gate"].update(result="fail"),
    lambda b: b["receipt"]["signature"].update(value="abcd", key_id="untrusted"),
    lambda b: b["receipt"].update(receipt_id="not-a-uuid"),
    lambda b: b["receipt"].update(extra="unreviewed"),
    lambda b: b.update(records_bytes=b["records_bytes"].replace(b"ALBANY", b"TAMPER")),
    lambda b: b.update(records_bytes=b["records_bytes"] + b["records_bytes"]),
    lambda b: b.update(records_bytes=b["records_bytes"].replace(b"\n", b"\r\n")),
])
def test_tampered_bundle_is_rejected(mutate):
    bundle = make_bundle()
    mutate(bundle)
    with pytest.raises(snap.SnapshotError):
        snap.verify_bundle(bundle["snapshot"], bundle["receipt"], bundle["records_bytes"])


def test_record_extra_fields_cannot_be_covered_up_with_new_hash():
    record = snap.project_record("fmcsa", fixture_record())
    record["phone"] = "PRIVATE"
    record["normalized_record_hash"] = snap.digest(snap.canonical({k: v for k, v in record.items() if k != "normalized_record_hash"}))
    with pytest.raises(snap.SnapshotError, match="schema"):
        snap.validate_record("fmcsa", record)


def test_optional_malformed_source_postal_code_is_omitted_without_inference():
    row = fixture_record()
    row["zip"] = "1980"
    projected = snap.project_record("fmcsa", row)
    assert projected["zip"] == ""
    assert projected["authoritative_entity_ids"] == row["authoritative_entity_ids"]


@pytest.mark.parametrize("change", [
    {"days_to_anniversary": 7},
    {"label": "91-180 days"},
    {"next_anniversary": "2020-01-01"},
])
def test_forged_benefit_countdown_fails_even_when_new_hashes_are_built(change):
    bundle = make_bundle("form5500")
    row = copy.deepcopy(bundle["records"][0])
    row["timing"].update(change)
    with pytest.raises(snap.SnapshotError, match="countdown or label"):
        snap.build_bundle("form5500", [row], REVISION, bundle["snapshot"]["coverage"], bundle["snapshot"]["created_at"])


def test_benefit_query_basis_must_be_bound_to_capture_date():
    bundle = make_bundle("form5500")
    coverage = copy.deepcopy(bundle["snapshot"]["coverage"])
    coverage["query_windows"]["NY"] = {"anniversary_start": "2020-01-01", "anniversary_end": "2020-12-31"}
    with pytest.raises(snap.SnapshotError, match="bound to capture date"):
        snap.build_bundle("form5500", bundle["records"], REVISION, coverage, bundle["snapshot"]["created_at"])


def test_runtime_next_day_countdown_preserves_verified_capture():
    bundle = make_bundle("form5500")
    capture_before = copy.deepcopy(bundle)
    result = snap.verify_bundle(bundle["snapshot"], bundle["receipt"], bundle["records_bytes"])
    result["path"] = snap.pointer_for(bundle["snapshot"])["path"]
    tomorrow = datetime.strptime(bundle["snapshot"]["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) + timedelta(days=1)
    with mock.patch.object(snap, "load_verified", return_value=result):
        row = snap.load_lane("form5500", ["NY"], now=tomorrow)["records"][0]
    assert row["timing"]["days_to_anniversary"] == 39
    assert row["timing"]["as_of"] == tomorrow.date().isoformat()
    assert "39 days away as of" in row["why"]
    assert row["timing_at_capture"]["days_to_anniversary"] == 40
    assert row["dataset_normalized_record_hash"] == bundle["records"][0]["normalized_record_hash"]
    assert "normalized_record_hash" not in row
    assert bundle == capture_before
    assert result["records"][0]["timing"]["days_to_anniversary"] == 40


def test_passed_anniversary_does_not_invent_a_future_cycle():
    bundle = make_bundle("form5500")
    row = copy.deepcopy(bundle["records"][0])
    row["timing"].update(next_anniversary=bundle["snapshot"]["created_at"][:10], days_to_anniversary=0)
    bundle = snap.build_bundle("form5500", [row], REVISION, bundle["snapshot"]["coverage"], bundle["snapshot"]["created_at"])
    result = snap.verify_bundle(bundle["snapshot"], bundle["receipt"], bundle["records_bytes"])
    result["path"] = snap.pointer_for(bundle["snapshot"])["path"]
    tomorrow = datetime.strptime(bundle["snapshot"]["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) + timedelta(days=1)
    with mock.patch.object(snap, "load_verified", return_value=result):
        served = snap.load_lane("form5500", ["NY"], now=tomorrow)["records"][0]
    assert "days_to_anniversary" not in served["timing"]
    assert "next_anniversary" not in served["timing"]
    assert served["timing"]["days_since_anniversary"] == 1
    assert served["timing_at_capture"]["days_to_anniversary"] == 0
    assert "has passed" in served["why"]


def test_transient_transport_failure_retries_with_a_bound():
    collector = mock.Mock(side_effect=[TimeoutError(), fixture_collector()(["NY"], 50)])
    with mock.patch("tools.ingestor.frontier_refresh_cli.time.sleep"):
        assert _collect_with_retry(collector, "NY")["mode"] == "LIVE"
    assert collector.call_count == 2
    collector = mock.Mock(side_effect=TimeoutError())
    with mock.patch("tools.ingestor.frontier_refresh_cli.time.sleep"):
        with pytest.raises(TimeoutError):
            _collect_with_retry(collector, "NY")
    assert collector.call_count == 3


def test_provider_access_block_is_never_retried():
    collector = mock.Mock(side_effect=urllib.error.HTTPError("https://official.gov", 403, "Blocked", {}, None))
    with pytest.raises(urllib.error.HTTPError):
        _collect_with_retry(collector, "NY")
    assert collector.call_count == 1


def test_default_capture_queries_every_declared_state():
    calls = []
    def collector(states, limit):
        calls.extend(states)
        return fixture_collector()(states, limit)
    bundle = collect_bundle("fmcsa", REVISION, collector=collector)
    assert calls == list(snap.TARGET_STATES)
    assert len(calls) == 27
    assert bundle["snapshot"]["coverage"]["requested_states"] == calls
    assert bundle["snapshot"]["coverage"]["completed_states"] == calls
    assert bundle["snapshot"]["record_count"] == 27


def test_default_snapshot_supports_every_selectable_browser_state():
    script = (Path(__file__).resolve().parents[1] / "app" / "static" / "app.js").read_text(encoding="utf-8")
    declaration = re.search(r"const EASTERN_REGIONS = \{(.*?)\n\};", script, re.DOTALL)
    assert declaration, "The browser region declaration must be checked against refresh coverage"
    regions = {name: json.loads(values) for name, values in re.findall(r'"([^\"]+)":\s*(\[[^\]]+\])', declaration.group(1))}
    all_selectable = set().union(*(set(states) for states in regions.values()))
    assert set(DEFAULT_STATES) == set(regions["All East"]) == all_selectable
    bundle = collect_bundle("fmcsa", REVISION, collector=fixture_collector())
    verified = snap.verify_bundle(bundle["snapshot"], bundle["receipt"], bundle["records_bytes"])
    verified["path"] = snap.pointer_for(bundle["snapshot"])["path"]
    with mock.patch.object(snap, "load_verified", return_value=verified):
        result = snap.load_lane("fmcsa", regions["All East"], limit=50)
    assert result["mode"] == "LIVE"
    assert result["count"] == 27
    assert {row["state"] for row in result["records"]} == all_selectable


def test_partial_provider_failure_prevents_capture():
    def collector(states, limit):
        if states == ["NJ"]:
            raise OSError("official provider unavailable")
        return fixture_collector()(states, limit)
    with pytest.raises(OSError):
        collect_bundle("fmcsa", REVISION, states=["NY", "NJ"], collector=collector)


def test_exclusion_counts_are_explicit_and_balanced():
    def collector(states, limit):
        result = fixture_collector()(states, limit)
        person = fixture_record(identity="person")
        person["name"] = "Synthetic Person"
        result["records"].append(person)
        result["count"] = 2
        return result
    bundle = collect_bundle("fmcsa", REVISION, states=["NY"], collector=collector)
    assert bundle["snapshot"]["coverage"]["admission_counts"]["NY"] == {"adapter_returned": 2, "excluded_non_organization": 1, "eligible_not_selected": 0, "selected": 1}


def test_empty_capture_is_not_published():
    with pytest.raises(snap.SnapshotError):
        collect_bundle("fmcsa", REVISION, states=["NY"], collector=lambda *a, **kw: {"mode": "LIVE", "count": 0, "records": [], "query_window": {"start": "2026-08-01", "end": "2026-08-21"}})


def test_stale_and_future_snapshots_are_not_served():
    old = (datetime.now(timezone.utc) - timedelta(days=9)).strftime("%Y-%m-%dT%H:%M:%SZ")
    bundle = make_bundle(created=old)
    with pytest.raises(snap.StaleSnapshot, match="data as of .* refresh pending"):
        snap.verify_bundle(bundle["snapshot"], bundle["receipt"], bundle["records_bytes"])
    future = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with pytest.raises(snap.SnapshotError, match="future"):
        make_bundle(created=future)


def test_atomic_write_refuses_existing_destination(tmp_path):
    bundle = make_bundle()
    target = tmp_path / "snapshot"
    snap.write_bundle(bundle, target)
    assert {path.name for path in target.iterdir()} == {"records.jsonl", "snapshot.json", "receipt.json"}
    with pytest.raises(snap.SnapshotError, match="already exists"):
        snap.write_bundle(bundle, target)


def test_hub_pointer_and_records_are_fully_verified():
    bundle = make_bundle()
    pointer = snap.pointer_for(bundle["snapshot"])
    values = {"latest/fmcsa.json": snap.canonical(pointer), f"{pointer['path']}/snapshot.json": snap.canonical(bundle["snapshot"]), f"{pointer['path']}/receipt.json": snap.canonical(bundle["receipt"]), f"{pointer['path']}/records.jsonl": bundle["records_bytes"]}
    snap._CACHE.clear()
    with mock.patch.object(snap, "_download", side_effect=lambda path, limit: values[path]):
        loaded = snap.load_lane("fmcsa", ["NY"], 2)
    assert loaded["delivery"] == "VERIFIED_SCHEDULED_SNAPSHOT"
    assert loaded["records"][0]["operational_snapshot"]["dataset_immutable_path"] == pointer["path"]
    assert "receipt_id" not in loaded["records"][0]
    with pytest.raises(snap.SnapshotError, match="coverage"):
        snap.load_lane("fmcsa", ["TX"], 2)
    snap._CACHE.clear()


def test_unsafe_pointer_is_rejected_before_following_path():
    bundle = make_bundle()
    pointer = snap.pointer_for(bundle["snapshot"])
    pointer["path"] = "../../secret"
    snap._CACHE.clear()
    with mock.patch.object(snap, "_download", return_value=snap.canonical(pointer)) as download:
        with pytest.raises(snap.SnapshotError, match="unsafe"):
            snap.load_verified("fmcsa")
    assert download.call_count == 1


def test_cli_failure_does_not_write_output_or_print_provider_body(tmp_path, capsys):
    with mock.patch("tools.ingestor.frontier_refresh_cli.collect_bundle", side_effect=OSError("SECRET_RESPONSE_BODY")):
        assert main(["--lane", "fmcsa", "--source-revision", REVISION, "--out", str(tmp_path / "snapshot")]) == 1
    assert not (tmp_path / "snapshot").exists()
    output = capsys.readouterr()
    assert "FAILED_CLOSED" in output.err and "SECRET" not in output.err
