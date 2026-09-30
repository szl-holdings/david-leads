# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — david-leads vertical
"""Pydantic records for the david-leads v0 vertical.

Doctrine wiring (SZL CANON):
- Truth states VERIFIED / UNKNOWN / UNAVAILABLE everywhere; INCOMPLETE is the
  Law-4 verdict when evidence is missing (missing evidence => INCOMPLETE,
  never PASS, enforced in the scorer rather than in prose).
- Organization-only: the public research path admits organization and facility
  records, never person-level data (see PUBLIC_DATA_OPERATING_MODEL.md).
- Zero-Bandaid: no field silently defaults into a claim. Optional fields stay
  None until evidence populates them; a score without evidence is None, not 0.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TruthState(str, Enum):
    """Declared truth state of a claim, an axis, an adapter, or a response."""

    VERIFIED = "VERIFIED"        # evidence present and provenance checks passed
    UNKNOWN = "UNKNOWN"          # audited state: claim lacks sufficient evidence
    UNAVAILABLE = "UNAVAILABLE"  # source/dependency cannot be reached or is not licensed
    INCOMPLETE = "INCOMPLETE"    # Law 4: required evidence missing; never report PASS


class SourceClass(str, Enum):
    """Evidence provenance class. The scoring policy is Default DENY: any class
    not explicitly permitted for the request is excluded and disclosed."""

    PUBLIC = "PUBLIC"
    FIRST_PARTY_CONSENT = "FIRST_PARTY_CONSENT"
    INTERNAL_OPERATIONAL = "INTERNAL_OPERATIONAL"
    LICENSED_THIRD_PARTY = "LICENSED_THIRD_PARTY"  # denied unless a license is configured
    SYNTHETIC_DEMO = "SYNTHETIC_DEMO"              # permitted only on records labeled synthetic


class Signal(BaseModel):
    """One evidence-backed observation about an organization.

    A signal without an evidence_ref is not evidence. The scorer refuses to
    admit it (Default DENY) and discloses it under denied_signals.
    """

    source: str = Field(description="adapter/source identifier, e.g. 'usaspending' or 'demo_synthetic'")
    source_class: SourceClass
    signal: str = Field(description="human-readable statement of what the record shows")
    observed_at: datetime = Field(description="when the underlying public record is dated")
    retrieved_at: datetime = Field(description="when the adapter retrieved/generated the record")
    evidence_ref: Optional[str] = Field(
        default=None, description="URL or record identifier an auditor can follow; None => not evidence"
    )
    authority_tier: int = Field(default=3, ge=1, le=3, description="1 federal, 2 state, 3 other public record")
    event_id: Optional[str] = Field(
        default=None, description="links signals that describe the same underlying event"
    )


class LeadRecord(BaseModel):
    """Organization-level lead record. Person-level records are out of scope by contract."""

    entity_type: str = Field(default="organization", pattern="^organization$")
    id: str
    legal_name: str
    state: Optional[str] = None
    naics: Optional[str] = None
    synthetic: bool = Field(
        default=False,
        description="true only for clearly-labeled synthetic demonstration records",
    )
    provenance_note: str = ""
    signals: list[Signal] = Field(default_factory=list)


class ScoreRequest(BaseModel):
    """Score a stored demo lead by id, or an inline caller-supplied lead record."""

    lead_id: Optional[str] = None
    lead: Optional[LeadRecord] = None


class AxisResult(BaseModel):
    """One scoring axis. value is None when the axis has no evidence — an honest
    hole, never a fabricated zero presented as knowledge (Zero-Bandaid)."""

    value: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    weight: float
    truth_state: TruthState
    detail: str
    evidence_refs: list[str] = Field(default_factory=list)


class Receipt(BaseModel):
    """Tamper-evident receipt for one scoring decision.

    signed=false with signature_status 'UNSIGNED (hash-chained, honest)' is a
    first-class state, not an error: no key is configured, and this service
    never fabricates a signature (Law 5: signature != truth).
    """

    receipt_id: str
    payload_type: str
    payload: dict
    payload_sha256: str
    signed: bool
    signature: Optional[dict] = None
    signature_status: str
    truth_state: TruthState
    prev_receipt_hash: str
    durability: str = Field(
        default="PROCESS_MEMORY",
        description="receipt chain lives in process memory; not a durable archive (local != remote)",
    )


class ScoreResponse(BaseModel):
    lead_id: str
    legal_name: str
    score: Optional[float] = Field(
        default=None,
        description="0-100 advisory work-order signal; None when evidence is INCOMPLETE",
    )
    bucket: Optional[str] = None
    truth_state: TruthState
    synthetic: bool
    axes: dict[str, AxisResult]
    admitted_signals: int
    denied_signals: list[dict] = Field(default_factory=list)
    disclaimers: list[str] = Field(default_factory=list)
    receipt: Receipt


class AdapterStatus(BaseModel):
    """Honest state of one ingestion adapter. UNAVAILABLE is an audited answer,
    not a failure to hide."""

    name: str
    kind: str  # DEMO | PUBLIC | LICENSED
    truth_state: TruthState
    detail: str
    requires: list[str] = Field(default_factory=list)
    records_available: Optional[int] = None


class VerifyRequest(BaseModel):
    receipt: dict
    previous_receipt: Optional[dict] = None


class VerifyResponse(BaseModel):
    receipt_id: str
    verdict: str
    # A verification outcome is a check verdict, not a claim truth state, so
    # this field is a plain string: VERIFIED or FAILED.
    integrity_state: str
    signature_state: str
    chain_state: str
    checks: list[dict]
    note: str = (
        "A valid signature proves integrity of the receipt, not correctness of "
        "the score it carries (Law 5: signature != truth)."
    )
