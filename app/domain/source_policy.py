"""Honest source and READY-gate policy for the public research surface.

This module does not collect, scrape, or enable held sources. IRS/NYC remain
POLICY_HOLD. Chicago/SAM remain AUTH_REQUIRED. FCC remains NOT_IMPLEMENTED.
DOL Form 5500 is first among four configured federal snapshot lanes. Enabled
describes configuration, not current snapshot availability. Integrity is unsigned.
"""
from __future__ import annotations

from typing import Any, Mapping

from .david_reference import SCHEMA, nonempty

CAPABILITIES_SCHEMA = "szl.david.public-capabilities/v1"
INTEGRITY = "LOCAL_SHA256_UNSIGNED"
PUBLIC_CAPABILITY_KEYS = (
    "schema",
    "integrity",
    "receipt_minted",
    "access",
    "contact_permission",
    "ready_patch",
    "kernel",
    "sources",
    "operations",
    "unsigned_until",
)
SOURCE_CATALOG = (
    {
        "id": "dol-form5500-benefit-timing",
        "label": "DOL Form 5500 benefit-plan filings",
        "status": "ENABLED",
        "order": 1,
        "enabled": True,
        "collector": "VERIFIED_SNAPSHOT_REQUIRED",
    },
    {
        "id": "fmcsa-company-census",
        "label": "FMCSA Company Census",
        "status": "ENABLED",
        "order": 2,
        "enabled": True,
        "collector": "VERIFIED_SNAPSHOT_REQUIRED",
    },
    {
        "id": "usaspending-contract-activity",
        "label": "USAspending federal contract activity",
        "status": "ENABLED",
        "order": 3,
        "enabled": True,
        "collector": "VERIFIED_SNAPSHOT_REQUIRED",
    },
    {
        "id": "epa-echo-monitoring-activity",
        "label": "EPA ECHO facility inspection activity",
        "status": "ENABLED",
        "order": 4,
        "enabled": True,
        "collector": "VERIFIED_SNAPSHOT_REQUIRED",
    },
    {
        "id": "irs-form990",
        "label": "IRS Form 990 organization filings",
        "status": "POLICY_HOLD",
        "order": 5,
        "enabled": False,
        "collector": "NOT_ENABLED",
    },
    {
        "id": "nyc-acris",
        "label": "NYC ACRIS property records",
        "status": "POLICY_HOLD",
        "order": 6,
        "enabled": False,
        "collector": "NOT_ENABLED",
    },
    {
        "id": "chicago-new-business-licenses",
        "label": "Chicago new active business licenses",
        "status": "AUTH_REQUIRED",
        "order": 7,
        "enabled": False,
        "collector": "NOT_ENABLED",
    },
    {
        "id": "sam-active-entity-updates",
        "label": "SAM.gov active entity updates",
        "status": "AUTH_REQUIRED",
        "order": 8,
        "enabled": False,
        "collector": "NOT_ENABLED",
    },
    {
        "id": "fcc-uls-organization-licenses",
        "label": "FCC ULS organization license activity",
        "status": "NOT_IMPLEMENTED",
        "order": 9,
        "enabled": False,
        "collector": "NOT_ENABLED",
    },
)
FRONTIER_HOLDS = {
    "fcc-uls-organization-licenses": ("NOT_IMPLEMENTED", "NOT_IMPLEMENTED"),
    "chicago-new-business-licenses": ("AUTH_REQUIRED", "AUTH_REQUIRED"),
    "sam-active-entity-updates": ("AUTH_REQUIRED", "AUTH_REQUIRED"),
}


def source_status(source_id: str) -> dict[str, Any]:
    nonempty(source_id, "source_id")
    for item in SOURCE_CATALOG:
        if item["id"] == source_id:
            return {
                "id": item["id"],
                "label": item["label"],
                "status": item["status"],
                "order": item["order"],
                "enabled": item["enabled"],
                "collector": item["collector"],
            }
    return {
        "id": source_id,
        "label": source_id,
        "status": "UNKNOWN",
        "order": None,
        "enabled": False,
        "collector": "NOT_ENABLED",
    }


def ready_blockers(
    *,
    principal: str,
    method: str,
    gates_complete: bool = False,
) -> tuple[str, ...]:
    """Named blockers for READY. PATCH and public view never succeed."""
    blockers: list[str] = []
    if str(method or "").upper() == "PATCH":
        blockers.append("BROWSER_PATCH_DENIED")
    if principal != "operator":
        blockers.append("PUBLIC_VIEW")
    if gates_complete is not True:
        blockers.append("GATES_INCOMPLETE")
    blockers.append("READY_REQUIRES_CLEARANCE")
    return tuple(blockers)


def public_capabilities() -> dict[str, Any]:
    """Sanitized public capability card. No secrets, DSNs, or operator state."""
    payload = {
        "schema": CAPABILITIES_SCHEMA,
        "integrity": INTEGRITY,
        "receipt_minted": False,
        "access": "PUBLIC_READONLY",
        "contact_permission": "NOT_EVALUATED",
        "ready_patch": "DENIED",
        "kernel": SCHEMA,
        "sources": [source_status(item["id"]) for item in SOURCE_CATALOG],
        "operations": {
            "collect": "SCHEDULED_FEDERAL_SNAPSHOTS",
            "research": "REVIEW",
            "public_display": "REVIEW",
            "redistribute": "DENY",
            "train": "DENY",
            "patch_ready": "DENY",
        },
        "unsigned_until": "existing Cosign/receipts path binds integrity",
    }
    return {key: payload[key] for key in PUBLIC_CAPABILITY_KEYS}


def sanitize_public_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value[key] for key in PUBLIC_CAPABILITY_KEYS if key in value}
