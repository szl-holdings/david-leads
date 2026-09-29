"""Server-owned DOL admission; a parsed filing alone is never an organization."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import os
import hashlib
from pathlib import Path
import re
from .david_reference import Grant, Hold, Observation, OPERATIONS, Verdict, aware, minimize, parse_stamp
from .source_policy import SourceHealthRecord
from ..federal_refresh_store import DolSnapshotBundle, _strict_json, load_dol_snapshot

SOURCE_ID = "dol-form5500-benefit-timing"
FIELDS = frozenset({"organization_name", "state", "form_year", "plan_year_begin", "plan_year_end", "amended_filing", "participant_count", "reported_life_benefit", "source_url"})

@dataclass(frozen=True)
class AdmissionPolicy:
    grant: Grant
    snapshot_revision: str
    jurisdictions: frozenset[str]
    classifications: dict

@dataclass(frozen=True)
class AdmittedObservation:
    grant: Grant
    observation: Observation
    entity_type: str
    classification_evidence: dict
    snapshot_revision: str
    signing_key_fingerprint: str


def _private_file(variable: str, maximum: int) -> bytes:
    name = os.environ.get(variable, "")
    if not name:
        secret_name = {"DAVID_DOL_POLICY_PATH": "DAVID_DOL_POLICY_JSON",
                       "DAVID_DOL_SIGNING_KEY_FILE": "DAVID_DOL_SIGNING_KEY"}.get(variable)
        value = os.environ.get(secret_name, "").encode("utf-8") if secret_name else b""
        if value and len(value) <= maximum:
            return value
        raise Hold("DATA_ADMISSION_NOT_CONFIGURED")
    path = Path(name)
    if not name or not path.is_absolute() or path.is_symlink():
        raise Hold("DATA_ADMISSION_NOT_CONFIGURED")
    try:
        with path.open("rb") as stream:
            value = stream.read(maximum + 1)
    except OSError:
        raise Hold("DATA_ADMISSION_NOT_CONFIGURED") from None
    if len(value) > maximum:
        raise Hold("DATA_ADMISSION_POLICY_INVALID")
    return value


def load_admission_policy(now: datetime, *, operation: str = "research") -> AdmissionPolicy:
    """No default grant. The policy is a reviewed deployment input, not an API body."""
    now = aware(now)
    policy = _strict_json(_private_file("DAVID_DOL_POLICY_PATH", 1024 * 1024))
    try:
        if (not isinstance(policy, dict) or set(policy) != {"schema", "source_id", "policy_revision", "review_reference", "expires_at", "rights", "allowed_fields", "purpose", "jurisdictions", "snapshot_revision", "classifications"}
                or policy["schema"] != "szl.david.dol-admission/v1" or policy["source_id"] != SOURCE_ID
                or policy["purpose"] != "organization_research"
                or not re.fullmatch(r"[0-9a-f]{40}", policy["snapshot_revision"])
                or not isinstance(policy["rights"], dict) or set(policy["rights"]) != OPERATIONS
                or not isinstance(policy["allowed_fields"], list) or not set(policy["allowed_fields"]) <= FIELDS
                or len(set(policy["allowed_fields"])) != len(policy["allowed_fields"])
                or not isinstance(policy["classifications"], dict) or len(policy["classifications"]) > 2000
                or not isinstance(policy["jurisdictions"], list) or not policy["jurisdictions"]
                or any(not isinstance(v, str) or not re.fullmatch(r"[A-Z]{2}", v) for v in policy["jurisdictions"])):
            raise Hold("DATA_ADMISSION_POLICY_INVALID")
        grant = Grant(SOURCE_ID, policy["policy_revision"], policy["review_reference"], parse_stamp(policy["expires_at"]),
                      {op: Verdict(value) for op, value in policy["rights"].items()}, frozenset(policy["allowed_fields"]))
        grant.require(operation, now)
    except Hold:
        raise
    except (TypeError, ValueError, KeyError, AttributeError):
        raise Hold("DATA_ADMISSION_POLICY_INVALID") from None
    return AdmissionPolicy(grant, policy["snapshot_revision"], frozenset(policy["jurisdictions"]), policy["classifications"])


def _bundle(policy: AdmissionPolicy, revision: str, now: datetime, *, allow_stale=False) -> DolSnapshotBundle:
    if revision != policy.snapshot_revision:
        raise Hold("SNAPSHOT_REVISION_NOT_ADMITTED")
    key = _private_file("DAVID_DOL_SIGNING_KEY_FILE", 4096)
    return load_dol_snapshot(revision, signing_key=key, now=now, allow_stale=allow_stale)


def _admit_record(policy: AdmissionPolicy, bundle: DolSnapshotBundle, record: dict, now: datetime,
                  operation: str) -> AdmittedObservation:
    review = policy.classifications.get(record["source_record_id"])
    if (not isinstance(review, dict) or set(review) != {"classification", "review_reference", "record_hash", "expires_at"}
            or review.get("classification") != "VERIFIED_LEGAL_ORGANIZATION"
            or review.get("record_hash") != record["normalized_record_hash"]
            or not isinstance(review.get("review_reference"), str) or not 1 <= len(review["review_reference"]) <= 2048):
        raise Hold("ORGANIZATION_CLASSIFICATION_REVIEW_REQUIRED")
    try:
        classification_expiry = parse_stamp(review["expires_at"])
    except (ValueError, AttributeError, TypeError):
        raise Hold("ORGANIZATION_CLASSIFICATION_REVIEW_REQUIRED") from None
    if classification_expiry <= now or record["state"] not in policy.jurisdictions:
        raise Hold("ORGANIZATION_CLASSIFICATION_REVIEW_REQUIRED")
    fields = {"organization_name": record["org_name"], "state": record["state"], **record["raw"],
              "source_url": "https://www.dol.gov/agencies/ebsa/about-ebsa/our-activities/public-disclosure/foia/form-5500-datasets"}
    selected = minimize(fields, policy.grant, operation, now, organization_admission=review["classification"])
    observation = Observation(SOURCE_ID, record["source_record_id"], bundle.revision, bundle.observed_at,
                              bundle.observed_at, min(bundle.expires_at, policy.grant.expires_at, classification_expiry), selected)
    if operation == "research":
        observation.body(policy.grant, now)
    return AdmittedObservation(policy.grant, observation, "organization", dict(review), bundle.revision, bundle.signing_key_fingerprint)


def get_admitted_observation(source_id: str, record_id: str, snapshot_revision: str, now: datetime) -> AdmittedObservation:
    now = aware(now)
    if source_id != SOURCE_ID:
        raise Hold("SOURCE_NOT_ADMITTED")
    policy = load_admission_policy(now)
    bundle = _bundle(policy, snapshot_revision, now)
    record = next((item for item in bundle.records if item["source_record_id"] == record_id), None)
    if record is None:
        raise Hold("SOURCE_RECORD_NOT_FOUND")
    return _admit_record(policy, bundle, record, now, "research")


def validate_stored_admission(body: dict, now: datetime) -> None:
    """Recheck current reviewed rights/classification on every protected use.

    Immutable provenance preserves history; it does not preserve revoked rights.
    No download is needed because the admitted record hash is bound in the DAG.
    """
    policy = load_admission_policy(now)
    current_key = hashlib.sha256(_private_file("DAVID_DOL_SIGNING_KEY_FILE", 4096)).hexdigest()
    if body.get("signing_key_fingerprint") != current_key:
        raise Hold("CURRENT_SOURCE_SIGNING_KEY_REQUIRED")
    if (body.get("source_id") != SOURCE_ID
            or body.get("policy_revision") != policy.grant.policy_revision
            or body.get("snapshot_revision") != policy.snapshot_revision
            or not set(body.get("fields", {})) <= policy.grant.allowed_fields):
        raise Hold("CURRENT_SOURCE_GRANT_REQUIRED")
    current = policy.classifications.get(body.get("source_record_id"))
    previous = body.get("classification_evidence")
    if (not isinstance(current, dict) or not isinstance(previous, dict)
            or current != previous or current.get("classification") != "VERIFIED_LEGAL_ORGANIZATION"
            or body.get("entity_type") != "organization"
            or body.get("fields", {}).get("state") not in policy.jurisdictions):
        raise Hold("CURRENT_ORGANIZATION_CLASSIFICATION_REQUIRED")
    try:
        if parse_stamp(current["expires_at"]) <= aware(now):
            raise Hold("CURRENT_ORGANIZATION_CLASSIFICATION_REQUIRED")
    except (ValueError, TypeError, KeyError, AttributeError):
        raise Hold("CURRENT_ORGANIZATION_CLASSIFICATION_REQUIRED") from None


def public_dol_records(states: list[str], limit: int, now: datetime) -> tuple[list[dict], str]:
    """Reads only the minimized published snapshot after separate display approval."""
    policy = load_admission_policy(now, operation="public_display")
    bundle = _bundle(policy, policy.snapshot_revision, now)
    results = []
    for record in bundle.records:
        if record["state"] not in states:
            continue
        try:
            admitted = _admit_record(policy, bundle, record, now, "public_display")
        except Hold:
            continue
        fields = dict(admitted.observation.fields)
        if "organization_name" not in fields or "state" not in fields:
            continue
        results.append({"name": fields["organization_name"], "state": fields["state"], "source_frontier": SOURCE_ID,
                        "source_record_id": record["source_record_id"], "fields": fields,
                        "observed_at": bundle.observed_at.isoformat(), "expires_at": admitted.observation.expires_at.isoformat(),
                        "snapshot_created_at": bundle.observed_at.isoformat(), "filing_published_at": None,
                        "signal_summary": "Reported organization filing; plan anniversaries are unconfirmed research hypotheses.",
                        "hypothesis_status": "UNCONFIRMED", "contact_permission": "NOT_GRANTED", "not_for_underwriting": True,
                        "citation": {"label": "DOL Form 5500", "url": fields.get("source_url", "")}})
        if len(results) >= max(1, min(limit, 100)):
            break
    return results, bundle.revision


def evaluate_source_health(snapshot_revision: str, now: datetime) -> SourceHealthRecord:
    """Observe real source inputs. Store via SourceHealthStore to retain history."""
    from dataclasses import replace
    now = aware(now)
    attempt = SourceHealthRecord(SOURCE_ID, credential_state="NOT_REQUIRED", last_attempt_at=now)
    try:
        policy = load_admission_policy(now)
        attempt = replace(attempt, grant=policy.grant)
        bundle = _bundle(policy, snapshot_revision, now, allow_stale=True)
        return replace(attempt, transport_state="SUCCESS", schema_state="SUPPORTED", integrity_state="VERIFIED_SIGNATURE",
                       completeness_state="COMPLETE", snapshot_revision=bundle.revision,
                       snapshot_observed_at=bundle.observed_at, snapshot_expires_at=bundle.expires_at)
    except Hold as exc:
        code = str(exc)
        if code in {"SOURCE_TRANSPORT_UNAVAILABLE", "SOURCE_BYTE_BUDGET"}:
            return replace(attempt, transport_state="UNAVAILABLE")
        if code in {"SOURCE_INTEGRITY_FAILED", "SOURCE_SIGNATURE_INVALID", "SOURCE_RECEIPT_BINDING_FAILED", "SOURCE_POINTER_HASHES"}:
            return replace(attempt, transport_state="SUCCESS", integrity_state="INTEGRITY_FAILED")
        if code in {"SOURCE_PARTIAL", "SOURCE_COMPLETENESS_FAILED"}:
            return replace(attempt, transport_state="SUCCESS", schema_state="SUPPORTED", completeness_state="PARTIAL")
        if code in {"SOURCE_SCHEMA_CHANGED", "SOURCE_POINTER_SCHEMA", "SOURCE_MINIMIZATION_FAILED", "SOURCE_POINTER_SCOPE"}:
            return replace(attempt, transport_state="SUCCESS", schema_state="SCHEMA_CHANGED")
        return attempt
