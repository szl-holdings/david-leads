# SPDX-License-Identifier: Apache-2.0
"""Verified, minimized scheduled captures of the established federal adapters.

No federal API is contacted by this module. A snapshot proves integrity of a
bounded query result, not exhaustive registry coverage or contact permission.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import tempfile
import threading
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DATASET_ID = "SZLHOLDINGS/david-leads-data"
DATASET_BASE = f"https://huggingface.co/datasets/{DATASET_ID}/resolve/main"
RECORD_SCHEMA = "federal-frontier-record-v1"
PARSER_VERSION = "1.0.0"
FRESHNESS_DAYS = 8
MAX_RECORDS = 2000
MAX_RECORD_BYTES = 16384
MAX_BUNDLE_BYTES = 32 * 1024 * 1024
STATES = frozenset("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())
TARGET_STATES = tuple("AL CT DC DE FL GA IL IN KY ME MD MA MI MS NH NJ NY NC OH PA RI SC TN VT VA WV WI".split())
LANES = {
    "fmcsa": {"source": "FMCSA Company Census", "source_id": "fmcsa-company-census", "source_path": ["fmcsa-company-census", "scheduled-public-api-capture"], "frontier": "FMCSA", "type": "carrier", "url": "https://data.transportation.gov/Trucking-and-Motorcoaches/Company-Census-File/az4n-8mr2/about_data"},
    "form5500": {"source": "DOL Form 5500 benefit-plan filings", "source_id": "dol-form5500-benefit-timing", "source_path": ["dol-form5500", "scheduled-official-bulk-projection"], "frontier": "BENEFIT_PLAN_TIMING", "type": "benefit_plan", "url": "https://www.dol.gov/agencies/ebsa/about-ebsa/our-activities/public-disclosure/foia/form-5500-datasets"},
    "usaspending": {"source": "USAspending federal contract activity", "source_id": "usaspending-contract-activity", "source_path": ["usaspending-contract-activity", "scheduled-public-api-capture"], "frontier": "FEDERAL_CONTRACT", "type": "federal_award", "url": "https://api.usaspending.gov/docs/intro-tutorial"},
}
TEXT_FIELDS = ("name", "category", "credential", "status", "city", "state", "zip", "license_or_issue_date", "observed_trigger", "trigger_date", "signal_summary", "product_angle", "product", "why", "recommended_next_action")
POLICY = {
    "id": "federal-frontier-organization-projection-v1",
    "record_schema": RECORD_SCHEMA,
    "admission": "LEGAL_ORGANIZATIONS_ONLY_PUBLIC_RESEARCH_ONLY",
    "optional_postal_code": "PRESERVE_VALID_FIVE_DIGIT_CODE_ELSE_EMPTY_NO_INFERENCE",
    "benefit_timing": "COUNTDOWN_BOUND_TO_CAPTURE_QUERY_DATE_DISPLAY_RECOMPUTED_WITH_CAPTURE_RETAINED",
    "excluded_categories": ["street_address", "person", "contact", "EIN", "raw_upstream", "award_description", "plan_name", "reported_carrier", "adverse", "underwriting"],
    "text_fields": list(TEXT_FIELDS),
    "nested_fields": {"citation": ["label", "url"], "source_record": ["label", "url"], "authoritative_entity_ids": ["system", "value"], "fmcsa": ["power_units", "drivers", "trucks", "buses"], "form5500": ["participants_reported", "benefit_categories"], "usaspending": ["award_id", "amount", "agency", "start_date", "end_date"], "timing": ["label", "next_anniversary", "days_to_anniversary", "basis", "hypothesis_only"]},
}
_SHA = re.compile(r"^[0-9a-f]{64}$")
_REV = re.compile(r"^[0-9a-f]{40}$")
_ORG = re.compile(r"(?:\bL\.?L\.?C\.?|\bINC(?:ORPORATED)?\.?|\bCORP(?:ORATION)?\.?|\bCO(?:MPANY)?\.?|\bLTD\.?|\bLIMITED(?:\s+PARTNERSHIP)?|\bL\.?L\.?P\.?|\bL\.?P\.?|\bP\.?L\.?L\.?C\.?|\bP\.?C\.?)$", re.I)
_CACHE: dict[str, tuple[datetime, dict[str, Any]]] = {}
_LOCK = threading.Lock()


class SnapshotError(ValueError):
    pass


class StaleSnapshot(SnapshotError):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


POLICY_SHA256 = digest(canonical(POLICY))


def _exact(value: Any, keys: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise SnapshotError(f"invalid {label} schema")


def _text(value: Any, limit: int = 1600) -> str:
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
        raise SnapshotError("invalid projected text")
    if re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}|\b\d{2}-\d{7}\b", value, re.I):
        raise SnapshotError("person/contact identifier in projected text")
    return value


def _int(value: Any, maximum: int = 10_000_000) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise SnapshotError("invalid projected count")
    return value


def _date(value: str, empty: bool = True) -> str:
    if empty and value == "":
        return value
    try:
        if datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d") != value:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise SnapshotError("invalid projected date") from exc
    return value


def _timestamp(value: Any) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError) as exc:
        raise SnapshotError("invalid snapshot timestamp") from exc


def _link(value: Any, lane: str) -> dict:
    _exact(value, {"label", "url"}, "citation")
    _text(value["label"], 240)
    url = _text(value["url"], 1000)
    from urllib.parse import urlsplit
    parsed = urlsplit(url)
    hosts = {"fmcsa": {"safer.fmcsa.dot.gov", "data.transportation.gov"}, "form5500": {"www.dol.gov", "dol.gov", "askebsa.dol.gov"}, "usaspending": {"www.usaspending.gov", "api.usaspending.gov"}}[lane]
    if parsed.scheme != "https" or parsed.hostname not in hosts or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise SnapshotError("invalid official citation URL")
    return dict(value)


def project_record(lane: str, row: dict) -> dict:
    """Copy only reviewed adapter fields; never serialize arbitrary raw rows."""
    if lane not in LANES or not isinstance(row, dict):
        raise SnapshotError("invalid lane or projected record")
    item = {key: row.get(key, "") for key in TEXT_FIELDS}
    # ZIP is optional context. An invalid source code is omitted, never padded or
    # inferred; the identity and source evidence remain independently required.
    if not isinstance(item["zip"], str) or not re.fullmatch(r"\d{5}", item["zip"]):
        item["zip"] = ""
    item.update({"type": LANES[lane]["type"], "source_frontier": LANES[lane]["frontier"], "source_class": "OFFICIAL_PUBLIC_FILING" if lane == "form5500" else "OFFICIAL_OPEN_DATA", "purpose": "PROSPECTING_ONLY", "not_for_underwriting": True, "research_gate": "PUBLIC_RESEARCH_ONLY", "contact_quality": "entity registry only", "citation": dict(row.get("citation", {})), "source_record": dict(row.get("source_record", {})), "authoritative_entity_ids": copy.deepcopy(row.get("authoritative_entity_ids", [])), "limitations": list(row.get("limitations", []))})
    if lane == "fmcsa":
        item["operational_snapshot"] = {key: row.get("operational_snapshot", {}).get(key, 0) for key in POLICY["nested_fields"][lane]}
    elif lane == "form5500":
        item["operational_snapshot"] = {key: copy.deepcopy(row.get("operational_snapshot", {}).get(key)) for key in POLICY["nested_fields"][lane]}
        item["timing"] = {key: row.get("timing", {}).get(key) for key in POLICY["nested_fields"]["timing"]}
    else:
        item["award"] = {key: row.get("award", {}).get(key) for key in POLICY["nested_fields"][lane]}
        # Match JavaScript's canonical representation for integral quantities.
        if isinstance(item["award"]["amount"], float) and item["award"]["amount"].is_integer():
            item["award"]["amount"] = int(item["award"]["amount"])
    validate_record(lane, item, hashed=False)
    return {**item, "normalized_record_hash": digest(canonical(item))}


def admits_organization(row: dict) -> bool:
    """Conservative published admission policy; excluded counts stay in coverage."""
    return isinstance(row, dict) and isinstance(row.get("name"), str) and bool(_ORG.search(row["name"].strip()))


def validate_record(lane: str, item: dict, *, hashed: bool = True) -> None:
    keys = set(TEXT_FIELDS) | {"type", "source_frontier", "source_class", "purpose", "not_for_underwriting", "research_gate", "contact_quality", "citation", "source_record", "authoritative_entity_ids", "limitations"}
    keys |= {"award"} if lane == "usaspending" else {"operational_snapshot"}
    if lane == "form5500":
        keys.add("timing")
    if hashed:
        keys.add("normalized_record_hash")
    _exact(item, keys, "record")
    for key in TEXT_FIELDS:
        _text(item[key])
    if not _ORG.search(item["name"].strip()) or item["state"] not in STATES or not item["credential"]:
        raise SnapshotError("record is not an identified legal organization")
    if item["zip"] and not re.fullmatch(r"\d{5}", item["zip"]):
        raise SnapshotError("invalid organization postal code")
    for key in ("license_or_issue_date", "trigger_date"):
        _date(item[key])
    constants = {"type": LANES[lane]["type"], "source_frontier": LANES[lane]["frontier"], "source_class": "OFFICIAL_PUBLIC_FILING" if lane == "form5500" else "OFFICIAL_OPEN_DATA", "purpose": "PROSPECTING_ONLY", "research_gate": "PUBLIC_RESEARCH_ONLY", "contact_quality": "entity registry only"}
    if any(item[k] != v for k, v in constants.items()) or item["not_for_underwriting"] is not True:
        raise SnapshotError("research/privacy gate mismatch")
    _link(item["citation"], lane)
    _link(item["source_record"], lane)
    ids = item["authoritative_entity_ids"]
    if not isinstance(ids, list) or not 1 <= len(ids) <= 2:
        raise SnapshotError("invalid authoritative IDs")
    for entry in ids:
        _exact(entry, {"system", "value"}, "entity identifier")
        if entry["system"] not in {"fmcsa": {"USDOT"}, "form5500": {"DOL Form 5500 ACK ID"}, "usaspending": {"UEI", "Federal Award ID"}}[lane]:
            raise SnapshotError("unapproved identifier system")
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", entry["value"]):
            raise SnapshotError("invalid public entity identifier")
    if not isinstance(item["limitations"], list) or not 1 <= len(item["limitations"]) <= 12:
        raise SnapshotError("invalid research limitations")
    for value in item["limitations"]:
        _text(value, 700)
    nested = item["award"] if lane == "usaspending" else item["operational_snapshot"]
    _exact(nested, set(POLICY["nested_fields"][lane]), "lane fields")
    if lane == "fmcsa":
        for value in nested.values():
            _int(value)
    elif lane == "form5500":
        _int(nested["participants_reported"], 5000)
        if nested["participants_reported"] < 10 or not isinstance(nested["benefit_categories"], list) or not 1 <= len(nested["benefit_categories"]) <= 8:
            raise SnapshotError("invalid organization benefit counts")
        for value in nested["benefit_categories"]:
            if value not in {"Life", "Medical", "Dental", "Vision", "Long-term disability", "Short-term disability", "Prescription", "Stop-loss", "HMO", "PPO"}:
                raise SnapshotError("unapproved benefit category")
        if "Life" not in nested["benefit_categories"]:
            raise SnapshotError("life benefit indicator required")
        timing = item["timing"]
        _exact(timing, set(POLICY["nested_fields"]["timing"]), "timing")
        _int(timing["days_to_anniversary"], 366)
        _date(timing["next_anniversary"], empty=False)
        for key in ("label", "basis"):
            _text(timing[key], 100)
        if timing["hypothesis_only"] is not True:
            raise SnapshotError("anniversary must remain a hypothesis")
    else:
        amount = nested["amount"]
        if type(amount) not in (int, float) or not math.isfinite(amount) or not 0 <= amount <= 1e12:
            raise SnapshotError("invalid public award amount")
        for key in ("award_id", "agency"):
            _text(nested[key], 200)
        for key in ("start_date", "end_date"):
            _date(nested[key])
    if hashed and item["normalized_record_hash"] != digest(canonical({k: v for k, v in item.items() if k != "normalized_record_hash"})):
        raise SnapshotError("record content hash mismatch")


def _coverage(value: dict, records: list[dict]) -> None:
    _exact(value, {"requested_states", "completed_states", "state_record_counts", "per_state_limit", "status", "selection", "query_windows", "admission_counts"}, "coverage")
    wanted = value["requested_states"]
    if not isinstance(wanted, list) or not 1 <= len(wanted) <= 27 or len(set(wanted)) != len(wanted) or any(s not in STATES for s in wanted):
        raise SnapshotError("invalid query states")
    if value["completed_states"] != wanted or value["status"] != "COMPLETE" or value["selection"] != "BOUNDED_ADAPTER_RESULTS_NOT_EXHAUSTIVE":
        raise SnapshotError("partial query coverage is not publishable")
    limit = _int(value["per_state_limit"], 50)
    if limit < 1:
        raise SnapshotError("invalid per-state query limit")
    counts = {state: sum(r["state"] == state for r in records) for state in wanted}
    if value["state_record_counts"] != counts or any(type(c) is not int or c > limit for c in value["state_record_counts"].values()) or sum(counts.values()) != len(records):
        raise SnapshotError("coverage counts do not match records")
    admissions = value["admission_counts"]
    if not isinstance(admissions, dict) or set(admissions) != set(wanted):
        raise SnapshotError("missing admission counts")
    for state, admission in admissions.items():
        _exact(admission, {"adapter_returned", "excluded_non_organization", "eligible_not_selected", "selected"}, "admission accounting")
        for count in admission.values():
            _int(count, 50)
        if admission["selected"] != counts[state] or admission["adapter_returned"] != sum(admission[k] for k in ("excluded_non_organization", "eligible_not_selected", "selected")):
            raise SnapshotError("admission accounting does not balance")
    windows = value["query_windows"]
    if not isinstance(windows, dict) or set(windows) != set(wanted):
        raise SnapshotError("missing query window")
    for window in windows.values():
        if not isinstance(window, dict) or set(window) not in ({"start", "end"}, {"anniversary_start", "anniversary_end"}):
            raise SnapshotError("invalid query window schema")
        for date_value in window.values():
            _date(date_value, empty=False)
        start, end = (window["start"], window["end"]) if "start" in window else (window["anniversary_start"], window["anniversary_end"])
        if start > end:
            raise SnapshotError("reversed query window")


def _timing_band(days: int) -> str:
    return "0-90 days" if days <= 90 else ("91-180 days" if days <= 180 else "181-365 days")


def _verify_capture_timing(snapshot: dict, records: list[dict]) -> None:
    """Bind the reported countdown to the actual DOL collection date/window."""
    if snapshot["lane"] != "form5500":
        return
    capture_day = _timestamp(snapshot["created_at"]).date()
    windows = snapshot["coverage"]["query_windows"]
    for window in windows.values():
        _exact(window, {"anniversary_start", "anniversary_end"}, "benefit timing query window")
        basis = datetime.strptime(window["anniversary_start"], "%Y-%m-%d").date()
        end = datetime.strptime(window["anniversary_end"], "%Y-%m-%d").date()
        # A bounded collection can finish after UTC midnight. Its query basis
        # remains explicit and may be at most the previous calendar date.
        if not 0 <= (capture_day - basis).days <= 1 or (end - basis).days != 365:
            raise SnapshotError("benefit timing query window is not bound to capture date")
    for row in records:
        timing = row["timing"]
        basis = datetime.strptime(windows[row["state"]]["anniversary_start"], "%Y-%m-%d").date()
        anniversary = datetime.strptime(timing["next_anniversary"], "%Y-%m-%d").date()
        days = (anniversary - basis).days
        if not 0 <= days <= 365 or timing["days_to_anniversary"] != days or timing["label"] != _timing_band(days):
            raise SnapshotError("benefit timing countdown or label differs from captured query basis")


def _receipt(snapshot: dict, *, receipt_id: str | None = None, session_id: str | None = None) -> dict:
    receipt = {"receipt_version": 1, "receipt_id": receipt_id or str(uuid.uuid4()), "issued_at": snapshot["created_at"], "session_id": session_id or str(uuid.uuid4()), "sequence": 0, "prev_receipt_hash": "GENESIS", "subject": {"normalized_record_hash": snapshot["records_root_sha256"], "source_record_id": snapshot["snapshot_id"], "parser_version": PARSER_VERSION}, "ranking_inputs": {"source_path": snapshot["source_path"], "reasons": [{"code": "VERIFIED_SCHEDULED_ORGANIZATION_CAPTURE", "direction": "up", "weight": 1, "detail": "The declared bounded queries completed and admitted only the reviewed organization projection."}], "confidence": {"low": 1, "high": 1}, "caveats": ["Integrity of a bounded query capture does not establish exhaustive coverage, contact permission, or an underwriting fact.", "UNSIGNED: payload hashes provide integrity; provider identity is established separately by release attestation."]}, "gate": {"name": "yuyay-13", "result": "pass", "failures": []}}
    receipt["payload_hash"] = digest(canonical(receipt))
    receipt["signature"] = {"algorithm": "HMAC-SHA256", "key_id": None, "value": "UNSIGNED"}
    return receipt


def build_bundle(lane: str, records: list[dict], source_revision: str, coverage: dict, created_at: str | None = None) -> dict:
    if lane not in LANES or not isinstance(source_revision, str) or not _REV.fullmatch(source_revision) or source_revision == "0" * 40:
        raise SnapshotError("lane and full parser Git SHA are required")
    projected = [project_record(lane, r) for r in records]
    payload = b"".join(canonical(r) + b"\n" for r in projected)
    core = {"snapshot_version": 1, "record_schema": RECORD_SCHEMA, "created_at": created_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "lane": lane, "source_path": LANES[lane]["source_path"], "parser": {"name": "frontier-scheduled-projection", "version": PARSER_VERSION, "source_revision": source_revision}, "projection_policy": {"id": POLICY["id"], "sha256": POLICY_SHA256}, "coverage": coverage, "record_count": len(projected), "records_root_sha256": digest(canonical([r["normalized_record_hash"] for r in projected])), "records_file_sha256": digest(payload), "freshness_days": FRESHNESS_DAYS}
    checksum = digest(canonical(core))
    snapshot = {"snapshot_id": f"sha256:{checksum}", "snapshot_digest": checksum, **core}
    receipt = _receipt(snapshot)
    verify_bundle(snapshot, receipt, payload, allow_stale=True)
    return {"snapshot": snapshot, "receipt": receipt, "records": projected, "records_bytes": payload}


def verify_bundle(snapshot: dict, receipt: dict, records_bytes: bytes, *, now: datetime | None = None, allow_stale: bool = False) -> dict:
    _exact(snapshot, {"snapshot_id", "snapshot_digest", "snapshot_version", "record_schema", "created_at", "lane", "source_path", "parser", "projection_policy", "coverage", "record_count", "records_root_sha256", "records_file_sha256", "freshness_days"}, "snapshot")
    lane = snapshot["lane"]
    if lane not in LANES or type(snapshot["snapshot_version"]) is not int or snapshot["snapshot_version"] != 1 or snapshot["record_schema"] != RECORD_SCHEMA or type(snapshot["freshness_days"]) is not int or snapshot["freshness_days"] != FRESHNESS_DAYS or snapshot["source_path"] != LANES[lane]["source_path"]:
        raise SnapshotError("unsupported snapshot contract")
    parser = snapshot["parser"]
    _exact(parser, {"name", "version", "source_revision"}, "parser")
    if parser["name"] != "frontier-scheduled-projection" or parser["version"] != PARSER_VERSION or not isinstance(parser["source_revision"], str) or not _REV.fullmatch(parser["source_revision"]) or parser["source_revision"] == "0" * 40:
        raise SnapshotError("unbound parser revision")
    if snapshot["projection_policy"] != {"id": POLICY["id"], "sha256": POLICY_SHA256}:
        raise SnapshotError("projection policy mismatch")
    created = _timestamp(snapshot["created_at"])
    clock = now or datetime.now(timezone.utc)
    if created > clock + timedelta(minutes=5):
        raise SnapshotError("future snapshot timestamp")
    if type(records_bytes) is not bytes or not 0 < len(records_bytes) <= MAX_BUNDLE_BYTES or not records_bytes.endswith(b"\n") or b"\r" in records_bytes:
        raise SnapshotError("invalid or oversized records payload")
    lines = records_bytes.splitlines(keepends=True)
    if not 1 <= len(lines) <= MAX_RECORDS or any(len(line) > MAX_RECORD_BYTES for line in lines):
        raise SnapshotError("records payload exceeds bounds")
    records = []
    seen = set()
    for line in lines:
        try:
            item = json.loads(line)
        except (ValueError, UnicodeDecodeError) as exc:
            raise SnapshotError("invalid record JSON") from exc
        if canonical(item) + b"\n" != line:
            raise SnapshotError("record JSON is not canonical")
        validate_record(lane, item)
        identity = canonical(item["authoritative_entity_ids"])
        if identity in seen:
            raise SnapshotError("duplicate record identity")
        seen.add(identity)
        records.append(item)
    if type(snapshot["record_count"]) is not int or snapshot["record_count"] != len(records) or snapshot["records_file_sha256"] != digest(records_bytes) or snapshot["records_root_sha256"] != digest(canonical([r["normalized_record_hash"] for r in records])):
        raise SnapshotError("snapshot record hashes/count mismatch")
    _coverage(snapshot["coverage"], records)
    _verify_capture_timing(snapshot, records)
    checksum = digest(canonical({k: v for k, v in snapshot.items() if k not in {"snapshot_id", "snapshot_digest"}}))
    if snapshot["snapshot_digest"] != checksum or snapshot["snapshot_id"] != f"sha256:{checksum}":
        raise SnapshotError("snapshot digest mismatch")
    if not isinstance(receipt, dict):
        raise SnapshotError("invalid PurIQ receipt")
    for key in ("receipt_id", "session_id"):
        try:
            parsed = uuid.UUID(receipt[key])
            if parsed.version != 4 or str(parsed) != receipt[key]:
                raise ValueError
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise SnapshotError("invalid PurIQ UUIDv4") from exc
    expected = _receipt(snapshot, receipt_id=receipt["receipt_id"], session_id=receipt["session_id"])
    if canonical(receipt) != canonical(expected):
        raise SnapshotError("PurIQ v1 receipt contract or payload mismatch")
    if not allow_stale and clock - created > timedelta(days=FRESHNESS_DAYS):
        raise StaleSnapshot(f"data as of {snapshot['created_at'][:10]}, refresh pending")
    return {"snapshot": snapshot, "receipt": receipt, "records": records, "receipt_state": "PAYLOAD_VERIFIED_UNSIGNED"}


def pointer_for(snapshot: dict) -> dict:
    return {"pointer_version": 1, "lane": snapshot["lane"], "snapshot_id": snapshot["snapshot_id"], "snapshot_digest": snapshot["snapshot_digest"], "created_at": snapshot["created_at"], "path": f"snapshots/{snapshot['lane']}/{snapshot['created_at'][:10]}/{snapshot['snapshot_digest']}"}


def write_bundle(bundle: dict, out: str | Path) -> None:
    target = Path(out).resolve()
    if target.exists():
        raise SnapshotError("snapshot destination already exists")
    verify_bundle(bundle["snapshot"], bundle["receipt"], bundle["records_bytes"])
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent))
    try:
        for filename, payload in (("records.jsonl", bundle["records_bytes"]), ("snapshot.json", canonical(bundle["snapshot"]) + b"\n"), ("receipt.json", canonical(bundle["receipt"]) + b"\n")):
            with (stage / filename).open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        os.replace(stage, target)
    except BaseException:
        # Keep staging data for diagnosis; never replace a verified destination.
        raise


def _download(path: str, limit: int) -> bytes:
    request = urllib.request.Request(f"{DATASET_BASE}/{path}", headers={"User-Agent": "SZL-David-Leads/FederalSnapshot-1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        result = response.read(limit + 1)
    if len(result) > limit:
        raise SnapshotError("dataset download exceeds bounds")
    return result


def load_verified(lane: str, *, now: datetime | None = None) -> dict:
    if lane not in LANES:
        raise SnapshotError("unknown federal snapshot lane")
    clock = now or datetime.now(timezone.utc)
    with _LOCK:
        cached = _CACHE.get(lane)
        if cached and cached[0] > clock and clock - _timestamp(cached[1]["snapshot"]["created_at"]) <= timedelta(days=FRESHNESS_DAYS):
            return copy.deepcopy(cached[1])
    try:
        pointer = json.loads(_download(f"latest/{lane}.json", 8192))
        _exact(pointer, {"pointer_version", "lane", "snapshot_id", "snapshot_digest", "created_at", "path"}, "pointer")
        if pointer["lane"] != lane or type(pointer["pointer_version"]) is not int or pointer["pointer_version"] != 1 or not isinstance(pointer["snapshot_digest"], str) or not _SHA.fullmatch(pointer["snapshot_digest"]):
            raise SnapshotError("invalid dataset pointer")
        _timestamp(pointer["created_at"])
        path = f"snapshots/{lane}/{pointer['created_at'][:10]}/{pointer['snapshot_digest']}"
        if pointer["path"] != path or pointer["snapshot_id"] != f"sha256:{pointer['snapshot_digest']}":
            raise SnapshotError("unsafe dataset pointer path")
        snapshot = json.loads(_download(f"{path}/snapshot.json", 131072))
        receipt = json.loads(_download(f"{path}/receipt.json", 32768))
        result = verify_bundle(snapshot, receipt, _download(f"{path}/records.jsonl", MAX_BUNDLE_BYTES), now=clock)
        if pointer_for(snapshot) != pointer:
            raise SnapshotError("dataset pointer does not match verified snapshot")
    except SnapshotError:
        raise
    except Exception as exc:
        raise SnapshotError("verified federal dataset unavailable; refresh pending") from exc
    result["path"] = path
    with _LOCK:
        _CACHE[lane] = (clock + timedelta(minutes=15), copy.deepcopy(result))
    return result


def load_lane(lane: str, states: list[str] | None = None, limit: int = 18, *, now: datetime | None = None) -> dict:
    if lane not in LANES:
        raise SnapshotError("unknown federal snapshot lane")
    meta = LANES[lane]
    clock = now or datetime.now(timezone.utc)
    result = load_verified(lane, now=clock)
    snapshot = result["snapshot"]
    requested = set(states or snapshot["coverage"]["requested_states"])
    if not requested <= set(snapshot["coverage"]["requested_states"]):
        raise SnapshotError("selected state is outside published query coverage; refresh pending")
    selected = [copy.deepcopy(r) for r in result["records"] if r["state"] in requested][:max(1, min(int(limit), 50))]
    for row in selected:
        if lane == "form5500":
            # Keep the verified source projection and its hash identifiable; the
            # runtime's separately minted receipt binds this derived display.
            row["timing_at_capture"] = copy.deepcopy(row["timing"])
            row["dataset_normalized_record_hash"] = row.pop("normalized_record_hash")
            row["timing"]["as_of"] = clock.date().isoformat()
            row["timing"]["captured_as_of"] = snapshot["coverage"]["query_windows"][row["state"]]["anniversary_start"]
            anniversary = datetime.strptime(row["timing"]["next_anniversary"], "%Y-%m-%d").date()
            days = (anniversary - clock.date()).days
            if days >= 0:
                row["timing"]["days_to_anniversary"] = days
                row["timing"]["label"] = _timing_band(days)
                row["why"] = (f"A reported benefit-plan anniversary is {days} days away as of {clock.date().isoformat()}. "
                              "That is a research timing hypothesis, not proof of a renewal, buying intent, dissatisfaction, eligibility, or insurability.")
            else:
                # Do not invent another renewal cycle or display a negative
                # countdown as an urgent upcoming anniversary in the UI.
                row["timing"].pop("days_to_anniversary")
                row["timing"]["observed_anniversary"] = row["timing"].pop("next_anniversary")
                row["timing"]["label"] = "Captured anniversary has passed"
                row["timing"]["days_since_anniversary"] = -days
                row["why"] = (f"The captured anniversary date {anniversary.isoformat()} has passed as of {clock.date().isoformat()}; "
                              "re-open the filing before asserting a future timing window. No new anniversary or renewal is inferred.")
        row.update({"delivery": "VERIFIED_SCHEDULED_SNAPSHOT", "source_path": list(snapshot["source_path"]), "source_state": "LIVE", "snapshot_as_of": snapshot["created_at"], "snapshot_id": snapshot["snapshot_id"], "dataset_snapshot_path": result["path"], "dataset_receipt_state": result["receipt_state"]})
        row.setdefault("operational_snapshot", {}).update({"dataset_snapshot_created_at": snapshot["created_at"], "dataset_immutable_path": result["path"], "dataset_source_path": " → ".join(snapshot["source_path"]), "dataset_receipt_state": result["receipt_state"], "delivery": "VERIFIED_SCHEDULED_SNAPSHOT"})
    return {"source": meta["source"], "source_id": meta["source_id"], "mode": "LIVE", "delivery": "VERIFIED_SCHEDULED_SNAPSHOT", "source_path": snapshot["source_path"], "count": len(selected), "records": selected, "citation": {"label": meta["source"], "url": meta["url"]}, "privacy": "LEGAL_ORGANIZATION_FIELDS_ONLY", "snapshot": {"id": snapshot["snapshot_id"], "as_of": snapshot["created_at"], "path": result["path"], "receipt_state": result["receipt_state"], "record_count": snapshot["record_count"]}, "coverage": snapshot["coverage"], "reason": None if selected else "No admitted organizations in the selected states within this bounded capture."}
