"""Versioned protected workflow endpoints. The existing app supplies authentication."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .domain.david_reference import Hold
from .domain.david_workflow import Workflow


class VersionedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_epoch: int = Field(ge=0)


class SourceSelection(VersionedRequest):
    source_ids: list[str] = Field(min_length=1, max_length=20)

    @field_validator("source_ids")
    @classmethod
    def unique_source_ids(cls, values):
        if len(set(values)) != len(values) or any(len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value) for value in values):
            raise ValueError("unique evidence SHA-256 identifiers required")
        return values


class IdentityReview(SourceSelection):
    decision: Literal["ORGANIZATION_CONFIRMED", "NEEDS_REVIEW", "REJECTED"]


class AdmissionRequest(VersionedRequest):
    source_id: Literal["dol-form5500-benefit-timing"]
    record_id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9_.:-]+$")
    snapshot_revision: str = Field(pattern=r"^[0-9a-f]{40}$")


class SourceRefreshRequest(VersionedRequest):
    snapshot_revision: str = Field(pattern=r"^[0-9a-f]{40}$")


class BriefRequest(SourceSelection):
    identity_review_id: str = Field(pattern=r"^[0-9a-f]{64}$")


class BriefReview(VersionedRequest):
    brief_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved: bool


class ClearanceRequest(VersionedRequest):
    review_id: str = Field(pattern=r"^[0-9a-f]{64}$")


class TaskRequest(VersionedRequest):
    clearance_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    task_type: Literal["VERIFY_SOURCE", "RESOLVE_IDENTITY", "REVIEW_CHANGE", "REVIEW_COUNTER_EVIDENCE"]
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")


class CorrectionRequest(VersionedRequest):
    node_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: Literal["SOURCE_CORRECTED", "SOURCE_WITHDRAWN", "IDENTITY_MISMATCH", "PERMISSION_REVOKED", "INTEGRITY_FAILED"]


class OutcomeRequest(VersionedRequest):
    task_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcome: Literal["WRONG_ENTITY", "SOURCE_STALE", "NOT_RELEVANT", "FURTHER_VERIFICATION_NEEDED", "PERMISSION_DECLINED", "RESEARCH_COMPLETED"]


class CounterEvidenceRequest(SourceSelection):
    reason: Literal["CONTRADICTORY_SOURCE", "IDENTITY_CONFLICT", "STALE_EVENT", "MISSING_EXPECTED_EVIDENCE"]


def make_router(context_provider, ledger_provider):
    router = APIRouter(prefix="/api/v1/operator", tags=["Protected organization research"])

    def execute(authorization, action):
        now = datetime.now(timezone.utc)
        ledger = None
        try:
            context = context_provider(authorization, now)
            ledger = ledger_provider()
            return action(Workflow(ledger, context, now))
        except HTTPException:
            raise
        except Hold as exc:
            raw = str(exc)
            code = raw if raw and len(raw) < 100 and all(c.isupper() or c.isdigit() or c == "_" for c in raw) else "EVIDENCE_CONFLICT"
            status = 403 if any(part in code for part in ("POLICY", "GRANT", "DENIED", "APPROVAL_REQUIRED")) else 409
            if "NOT_FOUND" in code:
                status = 404
            if "NOT_CONFIGURED" in code or "UNAVAILABLE" in code:
                status = 503
            raise HTTPException(status, {"code": code, "state": "HOLD", "contact_permission": "NOT_GRANTED"}) from None
        except Exception:
            raise HTTPException(503, {"code": "WORKFLOW_PERSISTENCE_UNAVAILABLE", "state": "UNAVAILABLE"}) from None
        finally:
            if ledger is not None:
                ledger.close()

    @router.get("/workspaces/{scope}")
    def workspace(scope: str, authorization: str | None = Header(default=None)):
        return execute(authorization, lambda flow: flow.workspace(scope))

    @router.get("/workspaces/{scope}/nodes/{node_id}")
    def node(scope: str, node_id: str, authorization: str | None = Header(default=None)):
        return execute(authorization, lambda flow: flow.view_node(scope, node_id))

    @router.post("/workspaces/{scope}/identity-reviews")
    def identity_review(scope: str, req: IdentityReview, authorization: str | None = Header(default=None)):
        return execute(authorization, lambda f: f.review_identity(scope, req.expected_epoch, req.source_ids, req.decision))

    @router.post("/workspaces/{scope}/admissions")
    def admission(scope: str, req: AdmissionRequest, authorization: str | None = Header(default=None)):
        return execute(authorization, lambda f: f.admit(scope, req.expected_epoch,
            req.source_id, req.record_id, req.snapshot_revision))

    @router.post("/workspaces/{scope}/source-refreshes")
    def refresh_source(scope: str, req: SourceRefreshRequest, authorization: str | None = Header(default=None)):
        return execute(authorization, lambda f: f.refresh_source(scope, req.expected_epoch, req.snapshot_revision))

    @router.post("/workspaces/{scope}/briefs")
    def brief(scope: str, req: BriefRequest, authorization: str | None = Header(default=None)):
        return execute(authorization, lambda f: f.brief(scope, req.expected_epoch, req.source_ids, req.identity_review_id))

    @router.post("/workspaces/{scope}/brief-reviews")
    def review_brief(scope: str, req: BriefReview, authorization: str | None = Header(default=None)):
        return execute(authorization, lambda f: f.review_brief(scope, req.expected_epoch, req.brief_id, req.approved))

    @router.post("/workspaces/{scope}/clearances")
    def clearance(scope: str, req: ClearanceRequest, authorization: str | None = Header(default=None)):
        return execute(authorization, lambda f: f.clearance(scope, req.expected_epoch, req.review_id))

    @router.post("/workspaces/{scope}/tasks")
    def task(scope: str, req: TaskRequest, authorization: str | None = Header(default=None)):
        return execute(authorization, lambda f: f.manual_task(scope, req.expected_epoch, req.clearance_id, req.task_type, req.idempotency_key))

    @router.post("/workspaces/{scope}/corrections")
    def correction(scope: str, req: CorrectionRequest, authorization: str | None = Header(default=None)):
        return execute(authorization, lambda f: f.correct(scope, req.expected_epoch, req.node_id, req.reason))

    @router.post("/workspaces/{scope}/suppressions")
    def suppression(scope: str, req: VersionedRequest, authorization: str | None = Header(default=None)):
        return execute(authorization, lambda f: f.suppress(scope, req.expected_epoch))

    @router.post("/workspaces/{scope}/outcomes")
    def outcome(scope: str, req: OutcomeRequest, authorization: str | None = Header(default=None)):
        return execute(authorization, lambda f: f.outcome(scope, req.expected_epoch, req.task_id, req.outcome))

    @router.post("/workspaces/{scope}/counter-evidence")
    def counter_evidence(scope: str, req: CounterEvidenceRequest, authorization: str | None = Header(default=None)):
        return execute(authorization, lambda f: f.counter_evidence(scope, req.expected_epoch, req.source_ids, req.reason))

    @router.get("/workspaces/{scope}/decision-diff")
    def decision_diff(scope: str, before: str, after: str, authorization: str | None = Header(default=None)):
        return execute(authorization, lambda f: f.decision_diff(scope, before, after))

    return router
