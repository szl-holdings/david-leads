"""Source health from trusted ingestion facts, with explicit public DTOs.

Configuration never proves usable data. Callers persist health with ingestion
state; this module performs no collection and owns no memory-only success cache.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Literal, Mapping
import re

from pydantic import BaseModel, ConfigDict, Field
from .david_reference import SCHEMA, Grant, Hold, OPERATIONS, aware, nonempty, stamp

CAPABILITIES_SCHEMA = "szl.david.public-capabilities/v1"
INTEGRITY = "LOCAL_SHA256_UNSIGNED"
PUBLIC_CAPABILITY_KEYS = ("schema", "integrity", "receipt_minted", "access", "contact_permission", "ready_patch", "kernel", "sources", "operations", "unsigned_until")
SOURCE_CATALOG = (
    {"id": "dol-form5500-benefit-timing", "label": "DOL Form 5500 benefit-plan filings", "order": 1, "enabled": True, "policy": "NOT_EVALUATED", "credential": "NOT_REQUIRED", "implemented": True},
    {"id": "fmcsa-company-census", "label": "FMCSA Company Census", "order": 2, "enabled": True, "policy": "NOT_EVALUATED", "credential": "NOT_REQUIRED", "implemented": True},
    {"id": "usaspending-contract-activity", "label": "USAspending federal contract activity", "order": 3, "enabled": True, "policy": "NOT_EVALUATED", "credential": "NOT_REQUIRED", "implemented": True},
    {"id": "epa-echo-monitoring-activity", "label": "EPA ECHO facility inspection activity", "order": 4, "enabled": True, "policy": "NOT_EVALUATED", "credential": "NOT_REQUIRED", "implemented": True},
    {"id": "irs-form990", "label": "IRS Form 990 organization filings", "order": 5, "enabled": False, "policy": "POLICY_HOLD", "credential": "NOT_REQUIRED", "implemented": False},
    {"id": "nyc-acris", "label": "NYC ACRIS property records", "order": 6, "enabled": False, "policy": "POLICY_HOLD", "credential": "NOT_REQUIRED", "implemented": False},
    {"id": "chicago-new-business-licenses", "label": "Chicago new active business licenses", "order": 7, "enabled": False, "policy": "POLICY_HOLD", "credential": "AUTH_REQUIRED", "implemented": True},
    {"id": "sam-active-entity-updates", "label": "SAM.gov active entity updates", "order": 8, "enabled": False, "policy": "NOT_EVALUATED", "credential": "AUTH_REQUIRED", "implemented": True},
    {"id": "fcc-uls-organization-licenses", "label": "FCC ULS organization license activity", "order": 9, "enabled": False, "policy": "NOT_EVALUATED", "credential": "NOT_REQUIRED", "implemented": False},
)
FRONTIER_HOLDS = {
    "fcc-uls-organization-licenses": ("NOT_IMPLEMENTED", "NOT_IMPLEMENTED"),
    "chicago-new-business-licenses": ("POLICY_HOLD", "POLICY_HOLD_AND_AUTH_REQUIRED"),
    "sam-active-entity-updates": ("AUTH_REQUIRED", "AUTH_REQUIRED"),
}
_STATES = {
    "credential_state": {"NOT_REQUIRED", "AVAILABLE", "AUTH_REQUIRED", "NOT_EVALUATED"},
    "transport_state": {"NOT_EVALUATED", "SUCCESS", "UNAVAILABLE", "RATE_LIMITED"},
    "schema_state": {"NOT_EVALUATED", "SUPPORTED", "SCHEMA_CHANGED"},
    "integrity_state": {"NOT_EVALUATED", "VERIFIED_UNSIGNED", "VERIFIED_SIGNATURE", "INTEGRITY_FAILED"},
    "completeness_state": {"NOT_EVALUATED", "COMPLETE", "PARTIAL"},
}


@dataclass(frozen=True)
class SourceHealthRecord:
    """Protected service facts; never accept this object from a request body."""
    source_id: str
    grant: Grant | None = None
    credential_state: str = "NOT_EVALUATED"
    transport_state: str = "NOT_EVALUATED"
    schema_state: str = "NOT_EVALUATED"
    integrity_state: str = "NOT_EVALUATED"
    completeness_state: str = "NOT_EVALUATED"
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    snapshot_revision: str | None = None
    snapshot_observed_at: datetime | None = None
    snapshot_expires_at: datetime | None = None
    signing_key_fingerprint: str | None = None


def _valid_record(record: SourceHealthRecord) -> None:
    if not isinstance(record, SourceHealthRecord):
        raise Hold("SOURCE_HEALTH_CONTRACT")
    for field, choices in _STATES.items():
        if getattr(record, field) not in choices:
            raise Hold("SOURCE_HEALTH_CONTRACT")
    for field in ("last_attempt_at", "last_success_at", "snapshot_observed_at", "snapshot_expires_at"):
        if getattr(record, field) is not None:
            aware(getattr(record, field))
    if record.signing_key_fingerprint is not None and not re.fullmatch(r"[0-9a-f]{64}", record.signing_key_fingerprint):
        raise Hold("SOURCE_HEALTH_SIGNING_KEY")
    if record.snapshot_revision is not None and not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", record.snapshot_revision):
        raise Hold("SOURCE_HEALTH_REVISION")
    if record.last_success_at is not None and (record.last_attempt_at is None or record.last_success_at > record.last_attempt_at):
        raise Hold("SOURCE_HEALTH_TIME")
    if record.grant is not None and (not isinstance(record.grant, Grant) or record.grant.source_id != record.source_id):
        raise Hold("SOURCE_HEALTH_GRANT")


def record_source_attempt(previous: SourceHealthRecord, attempt: SourceHealthRecord) -> SourceHealthRecord:
    """Failed refreshes preserve last success and immutable snapshot identity."""
    _valid_record(previous)
    _valid_record(attempt)
    if previous.source_id != attempt.source_id or attempt.last_attempt_at is None:
        raise Hold("SOURCE_ATTEMPT_IDENTITY")
    if previous.last_attempt_at and attempt.last_attempt_at <= previous.last_attempt_at:
        raise Hold("SOURCE_ATTEMPT_ORDER")
    successful = (attempt.transport_state == "SUCCESS" and attempt.schema_state == "SUPPORTED"
        and attempt.integrity_state in {"VERIFIED_UNSIGNED", "VERIFIED_SIGNATURE"}
        and attempt.completeness_state == "COMPLETE" and attempt.snapshot_revision is not None
        and attempt.snapshot_observed_at is not None and attempt.snapshot_expires_at is not None
        and attempt.snapshot_observed_at <= attempt.last_attempt_at < attempt.snapshot_expires_at)
    if successful:
        return replace(attempt, last_success_at=attempt.last_attempt_at)
    return replace(attempt, last_success_at=previous.last_success_at,
        snapshot_revision=previous.snapshot_revision or attempt.snapshot_revision,
        snapshot_observed_at=previous.snapshot_observed_at or attempt.snapshot_observed_at,
        snapshot_expires_at=previous.snapshot_expires_at or attempt.snapshot_expires_at,
        signing_key_fingerprint=previous.signing_key_fingerprint or attempt.signing_key_fingerprint)


def source_status(source_id: str, *, health: SourceHealthRecord | None = None,
                  now: datetime | None = None) -> dict[str, Any]:
    nonempty(source_id, "source_id")
    item = next((entry for entry in SOURCE_CATALOG if entry["id"] == source_id), None)
    if item is None:
        raise Hold("UNKNOWN_SOURCE")
    now = aware(now or datetime.now(timezone.utc))
    health = health or SourceHealthRecord(source_id, credential_state=item["credential"])
    _valid_record(health)
    if health.source_id != source_id:
        raise Hold("SOURCE_HEALTH_IDENTITY")
    if any(value and value > now for value in (health.last_attempt_at, health.last_success_at, health.snapshot_observed_at)):
        raise Hold("SOURCE_HEALTH_TIME")
    policy = item["policy"]
    allowed: list[str] = []
    if health.grant is not None and policy != "POLICY_HOLD":
        policy = "EXPIRED" if aware(health.grant.expires_at) <= now else "POLICY_HOLD"
        for operation in sorted(OPERATIONS):
            try:
                health.grant.require(operation, now)
            except Hold:
                continue
            allowed.append(operation)
        if allowed:
            policy = "APPROVED"
    freshness = "NOT_EVALUATED"
    if health.snapshot_observed_at is not None and health.snapshot_expires_at is not None:
        freshness = "FRESH" if health.snapshot_observed_at <= now < health.snapshot_expires_at else "STALE"
    blockers = []
    if not item["enabled"]:
        blockers.append("CONFIGURED_DISABLED")
    if not item["implemented"]:
        blockers.append("NOT_IMPLEMENTED")
    if policy != "APPROVED":
        blockers.append("POLICY_" + ("EXPIRED" if policy == "EXPIRED" else "HOLD" if policy == "POLICY_HOLD" else "NOT_EVALUATED"))
    if health.credential_state not in {"AVAILABLE", "NOT_REQUIRED"}:
        blockers.append("AUTH_REQUIRED" if health.credential_state == "AUTH_REQUIRED" else "CREDENTIAL_NOT_EVALUATED")
    for field, good in (("transport_state", {"SUCCESS"}), ("schema_state", {"SUPPORTED"}),
                        ("integrity_state", {"VERIFIED_UNSIGNED", "VERIFIED_SIGNATURE"}),
                        ("completeness_state", {"COMPLETE"})):
        if getattr(health, field) not in good:
            blockers.append(field.removesuffix("_state").upper() + "_" + getattr(health, field))
    if freshness != "FRESH":
        blockers.append("FRESHNESS_" + freshness)
    if health.snapshot_revision is None:
        blockers.append("SNAPSHOT_NOT_EVALUATED")
    if health.last_success_at is None:
        blockers.append("SUCCESS_NOT_OBSERVED")
    if not blockers:
        status = "HEALTHY"
    elif policy == "POLICY_HOLD":
        status = "POLICY_HOLD"
    elif health.credential_state == "AUTH_REQUIRED":
        status = "AUTH_REQUIRED"
    elif not item["implemented"]:
        status = "NOT_IMPLEMENTED"
    elif health.transport_state in {"UNAVAILABLE", "RATE_LIMITED"}:
        status = health.transport_state
    elif health.integrity_state == "INTEGRITY_FAILED":
        status = "INTEGRITY_FAILED"
    elif health.schema_state == "SCHEMA_CHANGED":
        status = "SCHEMA_CHANGED"
    elif health.completeness_state == "PARTIAL":
        status = "PARTIAL"
    elif freshness == "STALE" or policy == "EXPIRED":
        status = "STALE"
    else:
        status = "NOT_EVALUATED"
    return {"id": source_id, "label": item["label"], "order": item["order"], "status": status,
        "enabled": item["enabled"], "configured_enabled": item["enabled"], "policy_state": policy,
        **{field: getattr(health, field) for field in _STATES}, "freshness_state": freshness,
        "last_attempt_at": stamp(health.last_attempt_at) if health.last_attempt_at else None,
        "last_success_at": stamp(health.last_success_at) if health.last_success_at else None,
        "snapshot_revision": health.snapshot_revision, "eligible_operations": allowed if not blockers else [],
        "blocking_reasons": blockers, "collector": "VERIFIED_SNAPSHOT_REQUIRED" if item["enabled"] else "NOT_ENABLED"}


def ready_blockers(*, principal: str, method: str, gates_complete: bool = False) -> tuple[str, ...]:
    blockers: list[str] = []
    if str(method or "").upper() == "PATCH":
        blockers.append("BROWSER_PATCH_DENIED")
    if principal != "operator":
        blockers.append("PUBLIC_VIEW")
    if gates_complete is not True:
        blockers.append("GATES_INCOMPLETE")
    blockers.append("READY_REQUIRES_CLEARANCE")
    return tuple(blockers)


def public_capabilities(*, source_health: Mapping[str, SourceHealthRecord] | None = None,
                        now: datetime | None = None) -> dict[str, Any]:
    source_health = source_health or {}
    if set(source_health) - {item["id"] for item in SOURCE_CATALOG}:
        raise Hold("UNKNOWN_SOURCE")
    return {"schema": CAPABILITIES_SCHEMA, "integrity": INTEGRITY, "receipt_minted": False,
        "access": "PUBLIC_READONLY", "contact_permission": "NOT_EVALUATED", "ready_patch": "DENIED", "kernel": SCHEMA,
        "sources": [source_status(item["id"], health=source_health.get(item["id"]), now=now) for item in SOURCE_CATALOG],
        "operations": {"collect": "SCHEDULED_FEDERAL_SNAPSHOTS", "research": "REVIEW", "public_display": "REVIEW", "redistribute": "DENY", "train": "DENY", "patch_ready": "DENY"},
        "unsigned_until": "existing Cosign/receipts path binds integrity"}


class _PublicDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _PublicSource(_PublicDTO):
    id: str
    label: str
    order: int
    status: Literal["HEALTHY", "POLICY_HOLD", "AUTH_REQUIRED", "NOT_IMPLEMENTED", "UNAVAILABLE", "RATE_LIMITED", "INTEGRITY_FAILED", "SCHEMA_CHANGED", "PARTIAL", "STALE", "NOT_EVALUATED"]
    enabled: bool
    configured_enabled: bool
    collector: Literal["VERIFIED_SNAPSHOT_REQUIRED", "NOT_ENABLED"]
    policy_state: Literal["APPROVED", "EXPIRED", "NOT_EVALUATED", "POLICY_HOLD"]
    credential_state: Literal["NOT_REQUIRED", "AVAILABLE", "AUTH_REQUIRED", "NOT_EVALUATED"]
    transport_state: Literal["NOT_EVALUATED", "SUCCESS", "UNAVAILABLE", "RATE_LIMITED"]
    schema_state: Literal["NOT_EVALUATED", "SUPPORTED", "SCHEMA_CHANGED"]
    integrity_state: Literal["NOT_EVALUATED", "VERIFIED_UNSIGNED", "VERIFIED_SIGNATURE", "INTEGRITY_FAILED"]
    completeness_state: Literal["NOT_EVALUATED", "COMPLETE", "PARTIAL"]
    freshness_state: Literal["FRESH", "STALE", "NOT_EVALUATED"]
    last_attempt_at: str | None
    last_success_at: str | None
    snapshot_revision: str | None
    eligible_operations: list[Literal["collect", "research", "public_display", "redistribute", "train"]]
    blocking_reasons: list[str]


class _PublicOperations(_PublicDTO):
    collect: Literal["SCHEDULED_FEDERAL_SNAPSHOTS"]
    research: Literal["REVIEW"]
    public_display: Literal["REVIEW"]
    redistribute: Literal["DENY"]
    train: Literal["DENY"]
    patch_ready: Literal["DENY"]


class _PublicCapabilities(_PublicDTO):
    schema_name: Literal["szl.david.public-capabilities/v1"] = Field(alias="schema")
    integrity: Literal["LOCAL_SHA256_UNSIGNED"]
    receipt_minted: Literal[False]
    access: Literal["PUBLIC_READONLY"]
    contact_permission: Literal["NOT_EVALUATED"]
    ready_patch: Literal["DENIED"]
    kernel: str
    sources: list[_PublicSource]
    operations: _PublicOperations
    unsigned_until: str


def sanitize_public_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    """Reject unexpected nested fields; never pass private service objects here."""
    try:
        result = _PublicCapabilities.model_validate(value).model_dump(by_alias=True)
        baseline = public_capabilities()
        for key in PUBLIC_CAPABILITY_KEYS:
            if key != "sources" and result[key] != baseline[key]:
                raise ValueError("constant mismatch")
        if len(result["sources"]) != len(SOURCE_CATALOG):
            raise ValueError("source count")
        codes = {"CONFIGURED_DISABLED", "NOT_IMPLEMENTED", "POLICY_EXPIRED", "POLICY_HOLD", "POLICY_NOT_EVALUATED", "AUTH_REQUIRED", "CREDENTIAL_NOT_EVALUATED", "FRESHNESS_STALE", "FRESHNESS_NOT_EVALUATED", "SNAPSHOT_NOT_EVALUATED", "SUCCESS_NOT_OBSERVED"}
        codes.update(field.removesuffix("_state").upper() + "_" + state for field, states in _STATES.items() if field != "credential_state" for state in states)
        for source, expected in zip(result["sources"], baseline["sources"]):
            if any(source[key] != expected[key] for key in ("id", "label", "order", "enabled", "configured_enabled", "collector")):
                raise ValueError("source identity")
            if any(code not in codes for code in source["blocking_reasons"]):
                raise ValueError("unrecognized code")
            revision = source["snapshot_revision"]
            if revision is not None and not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision):
                raise ValueError("revision")
            for field in ("last_attempt_at", "last_success_at"):
                if source[field] is not None:
                    parsed = datetime.fromisoformat(source[field].replace("Z", "+00:00"))
                    if stamp(parsed) != source[field]:
                        raise ValueError("timestamp")
        return result
    except (ValueError, TypeError, KeyError) as exc:
        # Pydantic errors can carry rejected values. Expose a fixed error only.
        raise Hold("PUBLIC_CAPABILITIES_CONTRACT") from None
