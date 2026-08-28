# SPDX-License-Identifier: Apache-2.0
"""Proof-first organization resolution and evidence clocks.

This module is deliberately deterministic and dependency-free.  It never turns
an organization event into contact permission, purchase intent, underwriting
evidence, or a person-level profile.  Cross-source links require either a shared
authoritative organization identifier or an exact normalized name/state/ZIP
candidate that remains explicitly review-required.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any


SCHEMA_VERSION = "david.evidence-constellation.v1"
POLICY_VERSION = "organization-events-2026-08-28"

_LEGAL_SUFFIX = re.compile(
    r"(?:\bL\.?L\.?C\.?|\bINC(?:ORPORATED)?\.?|\bCORP(?:ORATION)?\.?|"
    r"\bCO(?:MPANY)?\.?|\bLTD\.?|\bLIMITED(?:\s+PARTNERSHIP)?|"
    r"\bL\.?L\.?P\.?|\bL\.?P\.?|\bP\.?L\.?L\.?C\.?|\bP\.?C\.?)\s*$",
    re.IGNORECASE,
)
_IDENTIFIER_ALIASES = {
    "UEI": "UEI",
    "SAM UEI": "UEI",
    "UNIQUE ENTITY ID": "UEI",
    "USDOT": "USDOT",
    "DOT": "USDOT",
    "EPA FRS": "EPA_FRS",
    "FRS ID": "EPA_FRS",
    "CIK": "SEC_CIK",
    "SEC CIK": "SEC_CIK",
}
_IDENTIFIER_VALUE_PATTERNS = {
    "UEI": re.compile(r"[A-Z0-9]{12}"),
    "USDOT": re.compile(r"[0-9]{1,8}"),
    "EPA_FRS": re.compile(r"[0-9]{12}"),
    "SEC_CIK": re.compile(r"[0-9]{1,10}"),
}
_EVENT_IDENTIFIERS = ("AWARD", "ACK", "FILING", "LICENSE")
_LIFETIME_DAYS = {
    "BENEFIT_PLAN_TIMING": 120,
    "FMCSA": 90,
    "FEDERAL_CONTRACT": 45,
    "EPA_ECHO": 90,
    "FCC_ULS": 180,
    "CHICAGO_BUSINESS_LICENSE": 90,
    "SAM_ENTITY": 90,
}


def _now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    return current if current.tzinfo else current.replace(tzinfo=timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _normalized_name(value: Any) -> str:
    name = _LEGAL_SUFFIX.sub("", str(value or "").upper().strip())
    return re.sub(r"[^A-Z0-9]+", "", name)


def _postal(value: Any) -> str:
    return re.sub(r"[^0-9]", "", str(value or ""))[:5]


def _stable_identifiers(record: dict[str, Any]) -> tuple[str, ...]:
    keys: set[str] = set()
    for item in record.get("authoritative_entity_ids") or []:
        if not isinstance(item, dict):
            continue
        raw_system = str(item.get("system") or "").upper().strip()
        value = re.sub(r"[^A-Z0-9]", "", str(item.get("value") or "").upper())
        if not raw_system or not value or any(token in raw_system for token in _EVENT_IDENTIFIERS):
            continue
        system = _IDENTIFIER_ALIASES.get(raw_system)
        pattern = _IDENTIFIER_VALUE_PATTERNS.get(system or "")
        if (
            pattern is None
            or pattern.fullmatch(value) is None
            or not value.strip("0")
        ):
            continue
        keys.add(f"{system}:{value}")
    return tuple(sorted(keys))


def _candidate_key(record: dict[str, Any]) -> str:
    name = _normalized_name(record.get("name"))
    state = str(record.get("state") or "").upper().strip()
    postal = _postal(record.get("zip"))
    if len(name) < 5 or len(state) != 2 or len(postal) != 5:
        return ""
    return f"NAME_STATE_ZIP:{state}:{postal}:{name}"


class _UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def resolve_entities(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Create conservative organization groups and explain every cross-source link."""
    resolved = [dict(record) for record in records]
    union = _UnionFind(len(resolved))
    identifier_members: dict[str, list[int]] = defaultdict(list)
    candidate_members: dict[str, list[int]] = defaultdict(list)

    for index, record in enumerate(resolved):
        for key in _stable_identifiers(record):
            identifier_members[key].append(index)
        candidate = _candidate_key(record)
        if candidate:
            candidate_members[candidate].append(index)

    identifier_links: set[tuple[int, int]] = set()
    candidate_links: set[tuple[int, int]] = set()
    for members in identifier_members.values():
        for member in members[1:]:
            union.union(members[0], member)
            identifier_links.add(tuple(sorted((members[0], member))))
    for members in candidate_members.values():
        sources = {str(resolved[index].get("source_frontier") or "") for index in members}
        if len(members) < 2 or len(sources) < 2:
            continue
        for member in members[1:]:
            if union.find(members[0]) == union.find(member):
                continue
            union.union(members[0], member)
            candidate_links.add(tuple(sorted((members[0], member))))

    groups: dict[int, list[int]] = defaultdict(list)
    for index in range(len(resolved)):
        groups[union.find(index)].append(index)

    counts = Counter()
    multi_source_entities = 0
    for members in groups.values():
        sources = sorted({
            str(resolved[index].get("source_frontier") or "")
            for index in members
            if resolved[index].get("source_frontier")
        })
        shared_identifier = any(
            pair in identifier_links
            for position, left in enumerate(members)
            for pair in (tuple(sorted((left, right))) for right in members[position + 1 :])
        )
        exact_candidate = any(
            pair in candidate_links
            for position, left in enumerate(members)
            for pair in (tuple(sorted((left, right))) for right in members[position + 1 :])
        )
        if len(sources) > 1:
            multi_source_entities += 1
        if shared_identifier and exact_candidate:
            status = "MIXED_IDENTIFIER_AND_EXACT_CANDIDATE"
            review_required = True
            basis = [
                "shared authoritative organization identifier",
                "exact normalized legal name, state, and ZIP candidate",
            ]
        elif shared_identifier:
            status = "DETERMINISTIC_IDENTIFIER"
            review_required = False
            basis = ["shared authoritative organization identifier"]
        elif exact_candidate:
            status = "EXACT_NAME_STATE_ZIP_CANDIDATE"
            review_required = True
            basis = ["exact normalized legal name, state, and ZIP"]
        elif any(_stable_identifiers(resolved[index]) for index in members):
            status = "SOURCE_IDENTIFIER_ONLY"
            review_required = False
            basis = ["source-specific authoritative identifier; no cross-source link"]
        else:
            status = "UNRESOLVED"
            review_required = True
            basis = ["no approved authoritative organization identifier"]
        counts[status] += 1

        identifier_fingerprint = sorted({
            key for index in members for key in _stable_identifiers(resolved[index])
        })
        candidate_fingerprint = sorted({
            key for index in members if (key := _candidate_key(resolved[index]))
        })
        if identifier_fingerprint:
            fingerprint = "IDENTIFIER|" + "|".join(identifier_fingerprint)
        elif exact_candidate and candidate_fingerprint:
            fingerprint = "CANDIDATE|" + "|".join(candidate_fingerprint)
        else:
            provenance_parts = sorted(
                "|".join(
                    str(resolved[index].get(key) or "")
                    for key in (
                        "source_frontier",
                        "source_record_id",
                        "normalized_record_sha256",
                        "receipt_id",
                    )
                )
                for index in members
            )
            fingerprint = "PROVENANCE|" + "|".join(provenance_parts)
        group_id = "org_" + hashlib.sha256(fingerprint.encode()).hexdigest()[:16]
        signals = [{
            "source_frontier": resolved[index].get("source_frontier"),
            "observed_trigger": resolved[index].get("observed_trigger"),
            "observed_date": (
                resolved[index].get("trigger_date")
                or resolved[index].get("license_or_issue_date")
                or resolved[index].get("observed_at")
            ),
            "citation": resolved[index].get("citation"),
        } for index in members]

        for index in members:
            record = resolved[index]
            record["entity_resolution"] = {
                "schema_version": SCHEMA_VERSION,
                "group_id": group_id,
                "status": status,
                "basis": basis,
                "review_required": review_required,
                "record_count": len(members),
                "source_count": len(sources),
                "official_sources": sources,
            }
            evidence = dict(record.get("evidence") or {})
            evidence.update({
                "source_count": len(sources),
                "official_sources": sources,
                "triangulation_state": "MULTI_SOURCE" if len(sources) > 1 else "SINGLE_SOURCE",
            })
            record["evidence"] = evidence
            record["corroborating_signals"] = signals

    return resolved, {
        "entity_groups": len(groups),
        "multi_source_entities": multi_source_entities,
        "resolution_counts": dict(sorted(counts.items())),
        "review_required_groups": (
            counts["EXACT_NAME_STATE_ZIP_CANDIDATE"]
            + counts["MIXED_IDENTIFIER_AND_EXACT_CANDIDATE"]
            + counts["UNRESOLVED"]
        ),
    }


def _deal_clock(record: dict[str, Any], current: datetime) -> dict[str, Any]:
    source = str(record.get("source_frontier") or "")
    event_at = _parse_datetime(
        record.get("trigger_date")
        or record.get("license_or_issue_date")
        or record.get("observed_at")
    )
    anniversary = _parse_datetime((record.get("timing") or {}).get("next_anniversary"))
    if source == "BENEFIT_PLAN_TIMING" and anniversary:
        expires_at = anniversary + timedelta(days=30)
        recheck_at = anniversary - timedelta(days=90)
        basis = "reported plan or policy period anniversary hypothesis"
    elif event_at:
        lifetime = _LIFETIME_DAYS.get(source, 90)
        expires_at = event_at + timedelta(days=lifetime)
        recheck_at = event_at + timedelta(days=max(7, lifetime * 2 // 3))
        basis = f"{lifetime}-day documented evidence lifetime"
    else:
        return {
            "state": "UNKNOWN",
            "event_at": None,
            "recheck_at": None,
            "expires_at": None,
            "days_until_expiry": None,
            "basis": "source did not provide a usable event date",
        }

    if current > expires_at:
        state = "STALE"
    elif current >= recheck_at:
        state = "RECHECK_DUE"
    else:
        state = "CURRENT"
    return {
        "state": state,
        "event_at": event_at.isoformat() if event_at else None,
        "recheck_at": recheck_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "days_until_expiry": (expires_at.date() - current.date()).days,
        "basis": basis,
    }


def _signed_source_receipt(record: dict[str, Any]) -> bool:
    """Require a coherent signed receipt reference over the normalized source record."""
    digest = str(record.get("normalized_record_sha256") or "")
    return bool(
        str(record.get("receipt_id") or "").strip()
        and record.get("receipt_signed") is True
        and str(record.get("receipt_state") or "").upper() == "SIGNED"
        and re.fullmatch(r"[0-9a-f]{64}", digest)
    )


def _proof(record: dict[str, Any], clock: dict[str, Any]) -> dict[str, Any]:
    citation = record.get("citation") or {}
    authority = (
        "OFFICIAL_CITED"
        if str(citation.get("url") or "").startswith("https://")
        and str(record.get("source_class") or "").startswith("OFFICIAL")
        else "PARTIAL"
    )
    integrity = (
        "SIGNED_SOURCE_RECEIPT"
        if _signed_source_receipt(record)
        else ("REFERENCE_ONLY" if record.get("receipt_id") else "UNAVAILABLE")
    )
    resolution = record.get("entity_resolution") or {}
    source_count = int((record.get("evidence") or {}).get("source_count") or 0)
    if clock["state"] == "STALE" or authority != "OFFICIAL_CITED":
        grade = "D"
    elif integrity == "SIGNED_SOURCE_RECEIPT" and source_count > 1 and resolution.get("status") == "DETERMINISTIC_IDENTIFIER":
        grade = "A"
    elif integrity == "SIGNED_SOURCE_RECEIPT" and clock["state"] in {"CURRENT", "RECHECK_DUE"}:
        grade = "B"
    else:
        grade = "C"
    return {
        "grade": grade,
        "not_a_sales_probability": True,
        "dimensions": {
            "authority": authority,
            "freshness": clock["state"],
            "corroboration": "MULTI_SOURCE" if source_count > 1 else "SINGLE_SOURCE",
            "integrity": integrity,
            "identity": resolution.get("status", "UNRESOLVED"),
            "receipt_claim_scope": "NORMALIZED_SOURCE_RECORD_ONLY",
        },
    }


def _counter_evidence(record: dict[str, Any], clock: dict[str, Any]) -> list[str]:
    items: list[str] = []
    resolution = record.get("entity_resolution") or {}
    if int((record.get("evidence") or {}).get("source_count") or 0) <= 1:
        items.append("No independent official source corroborates this organization event in the current pull.")
    if resolution.get("review_required"):
        items.append("The organization link requires human review before records may be treated as one entity.")
    if clock["state"] in {"RECHECK_DUE", "STALE", "UNKNOWN"}:
        items.append("The evidence clock requires a fresh official-source check before prioritization.")
    if (
        str(record.get("receipt_state") or "").upper() == "SIGNED"
        and not _signed_source_receipt(record)
    ):
        items.append("The declared signed receipt is incomplete or inconsistent and is treated as unverified.")
    for limitation in record.get("limitations") or []:
        text = str(limitation).strip()
        if text and text not in items:
            items.append(text)
        if len(items) >= 5:
            break
    items.append("The observation does not establish buying intent, insurability, revenue, or permission to contact.")
    return items[:6]


def annotate_constellation(
    records: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Resolve organizations and attach session-verifiable source-receipt references."""
    current = _now(now)
    resolved, resolution_summary = resolve_entities(records)
    grade_counts: Counter[str] = Counter()
    clock_counts: Counter[str] = Counter()
    session_verifiable = 0
    signed_source_receipts = 0
    for record in resolved:
        clock = _deal_clock(record, current)
        proof = _proof(record, clock)
        packet_state = (
            "SESSION_VERIFIABLE_REFERENCE"
            if record.get("normalized_record_sha256")
            and record.get("parser_version")
            and record.get("source_record_id")
            and _signed_source_receipt(record)
            else "PARTIAL"
        )
        packet = {
            "schema_version": SCHEMA_VERSION,
            "state": packet_state,
            "durability": "PROCESS_MEMORY",
            "historical_replay": False,
            "claim_scope": "NORMALIZED_SOURCE_RECORD_RECEIPT_REFERENCE",
            "normalized_record_sha256": record.get("normalized_record_sha256"),
            "parser_version": record.get("parser_version"),
            "source_record_id": record.get("source_record_id"),
            "receipt_id": record.get("receipt_id"),
            "entity_group_id": (record.get("entity_resolution") or {}).get("group_id"),
        }
        record["evidence_constellation"] = {
            "schema_version": SCHEMA_VERSION,
            "policy_version": POLICY_VERSION,
            "proof": proof,
            "deal_clock": clock,
            "counter_evidence": _counter_evidence(record, clock),
            "decision_dimensions": {
                "offering_fit": "SUPPORTED_HYPOTHESIS" if record.get("product_fit") else "REVIEW_REQUIRED",
                "moment": clock["state"],
                "proof": proof["grade"],
                "permission": "PUBLIC_RESEARCH_ONLY",
            },
            "proof_packet": packet,
        }
        grade_counts[proof["grade"]] += 1
        clock_counts[clock["state"]] += 1
        session_verifiable += int(packet_state == "SESSION_VERIFIABLE_REFERENCE")
        signed_source_receipts += int(proof["dimensions"]["integrity"] == "SIGNED_SOURCE_RECEIPT")

    return resolved, {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "generated_at": current.isoformat(),
        "events_total": len(resolved),
        **resolution_summary,
        "proof_grades": {grade: grade_counts.get(grade, 0) for grade in ("A", "B", "C", "D")},
        "deal_clock": {
            state: clock_counts.get(state, 0)
            for state in ("CURRENT", "RECHECK_DUE", "STALE", "UNKNOWN")
        },
        "session_verifiable_references": session_verifiable,
        "signed_source_receipts": signed_source_receipts,
        "proof_reference_durability": "PROCESS_MEMORY",
        "historical_replay": False,
        "permission_state": "PUBLIC_RESEARCH_ONLY",
        "doctrine": (
            "Proof quality is not a sales probability. Organization events remain research-only; "
            "contact requires authenticated human clearance."
        ),
    }
