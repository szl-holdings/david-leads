"""SZL David Leads reference invariants, version 2026-09-11.

This is executable reference/test code, NOT the production David application.
It has no network collector, authentication server, contact sender or deployer.
SQLite demonstrates persistence in tests only. Production must use the existing
Postgres service, authorization boundary, migrations and release controls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

UTC = timezone.utc
SCHEMA = "szl.david.reference/1"
OPERATIONS = frozenset({"collect", "research", "public_display", "redistribute", "train"})
EXCLUDED_FIELDS = frozenset({
    "ssn", "ein", "phone", "email", "personal_address", "officer_name", "donor_name",
    "beneficiary_name", "tax_return", "income_personal", "net_worth_personal",
    "medical_history", "bank_account", "commission", "broker_name", "policy_number",
})


class Hold(ValueError):
    """A required fact or permission was not established; never silently allow."""


class Verdict(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REVIEW = "REVIEW"


def aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise Hold("timezone-aware timestamp required")
    return value.astimezone(UTC)


def stamp(value: datetime) -> str:
    return aware(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_stamp(value: str) -> datetime:
    return aware(datetime.fromisoformat(value.replace("Z", "+00:00")))


def canonical(value: Any) -> str:
    """Local canonical JSON; not a claim of RFC 8785/JCS conformance."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def nonempty(value: str, name: str, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise Hold(f"invalid {name}")
    return value


@dataclass(frozen=True)
class Grant:
    """Construct ONLY from a reviewed, server-owned source policy registry."""
    source_id: str
    policy_revision: str
    review_reference: str
    expires_at: datetime
    rights: Mapping[str, Verdict]
    allowed_fields: frozenset[str]

    def require(self, operation: str, now: datetime) -> None:
        nonempty(self.source_id, "source_id")
        nonempty(self.policy_revision, "policy_revision")
        nonempty(self.review_reference, "review_reference", 2048)
        if operation not in OPERATIONS:
            raise Hold("unknown operation")
        if aware(now) >= aware(self.expires_at):
            raise Hold("policy review expired")
        if self.rights.get(operation) != Verdict.ALLOW:
            raise Hold(f"source permission not affirmative: {operation}")
        if self.allowed_fields & EXCLUDED_FIELDS:
            raise Hold("source policy contains a prohibited David field")


def minimize(record: Mapping[str, Any], grant: Grant, operation: str,
             now: datetime, *, organization_admission: str) -> dict[str, Any]:
    """Projection is NOT semantic privacy review or proof an entity is a business.

    organization_admission must come from the protected entity-admission service,
    never an LLM inference, legal-name suffix alone, or a browser-supplied flag.
    Unselected raw values are neither copied into receipts nor logged here.
    """
    grant.require(operation, now)
    if organization_admission != "VERIFIED_LEGAL_ORGANIZATION":
        raise Hold("organization classification requires review")
    selected: dict[str, Any] = {}
    for key in sorted(grant.allowed_fields):
        if key not in record:
            continue
        value = record[key]
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise Hold("nested values need an explicit schema")
        if isinstance(value, str) and len(value) > 2048:
            raise Hold("oversized field")
        if isinstance(value, float) and not math.isfinite(value):
            raise Hold("non-finite numeric value")
        selected[key] = value
    if not selected:
        raise Hold("no permitted fields")
    return selected


@dataclass(frozen=True, order=True)
class Identifier:
    kind: str
    namespace: str
    jurisdiction: str
    value: str

    def key(self) -> tuple[str, str, str, str]:
        for label, value in (("kind", self.kind), ("namespace", self.namespace),
                             ("jurisdiction", self.jurisdiction), ("value", self.value)):
            nonempty(value, label)
        if self.namespace == "SEC_CIK":
            if self.kind != "organization" or self.jurisdiction != "US":
                raise Hold("CIK scope mismatch")
            if not re.fullmatch(r"[0-9]{1,10}", self.value) or int(self.value) == 0:
                raise Hold("invalid CIK")
            value = str(int(self.value)).zfill(10)
        elif self.namespace == "UEI":
            if self.kind != "organization" or self.jurisdiction != "US":
                raise Hold("UEI scope mismatch")
            value = self.value.upper()
            if not re.fullmatch(r"[A-Z0-9]{12}", value):
                raise Hold("invalid UEI shape")
        elif self.namespace in {"PARCEL", "EPA_FRS", "USDOT"}:
            expected = {"PARCEL": "parcel", "EPA_FRS": "facility", "USDOT": "carrier"}
            if self.kind != expected[self.namespace]:
                raise Hold("identifier entity-type mismatch")
            value = self.value
        else:
            raise Hold("identifier namespace not admitted in reference policy")
        return self.kind, self.namespace, self.jurisdiction, value


def name_candidate(name: str, state: str, postal: str) -> tuple[str, str, str]:
    normalized = unicodedata.normalize("NFKC", name).casefold()
    normalized = "".join(ch for ch in normalized if ch.isalnum())
    if len(normalized) < 5 or not re.fullmatch(r"[A-Z]{2}", state):
        raise Hold("insufficient organization candidate key")
    if not re.fullmatch(r"[0-9]{5}", postal):
        raise Hold("invalid candidate postal code")
    return normalized, state, postal


def relationship(left: Sequence[Identifier], right: Sequence[Identifier],
                 *, same_name_state_postal: bool = False) -> str:
    """Never union candidate identity into a verified canonical organization."""
    a, b = {item.key() for item in left}, {item.key() for item in right}
    shared = a & b
    # A shared ID cannot override a contradictory ID in another matching scope.
    for scope in {k[:3] for k in a} & {k[:3] for k in b}:
        av, bv = {k[3] for k in a if k[:3] == scope}, {k[3] for k in b if k[:3] == scope}
        if av != bv and (shared or same_name_state_postal):
            return "CONFLICT_REVIEW"
    if any(k[0] == "organization" for k in shared):
        return "SAME_ORGANIZATION_ID"
    if shared:
        return "SAME_NON_ORGANIZATION_RECORD"
    return "CANDIDATE_REVIEW" if same_name_state_postal else "UNRESOLVED"


@dataclass(frozen=True)
class Observation:
    source_id: str
    source_record_id: str
    revision: str
    published_at: datetime
    observed_at: datetime
    expires_at: datetime
    fields: Mapping[str, Any]

    def body(self, grant: Grant, now: datetime) -> dict[str, Any]:
        grant.require("research", now)
        if self.source_id != grant.source_id:
            raise Hold("source policy mismatch")
        for label, val in (("source_record_id", self.source_record_id), ("revision", self.revision)):
            nonempty(val, label)
        published, observed = aware(self.published_at), aware(self.observed_at)
        if published > observed or observed > aware(now):
            raise Hold("invalid publication/observation time ordering")
        if aware(self.expires_at) <= aware(now):
            raise Hold("stale observation")
        # A policy renewal or a fetch cannot silently refresh the source event.
        if aware(self.expires_at) > aware(grant.expires_at):
            raise Hold("observation outlives source policy review")
        if not self.fields or not set(self.fields) <= grant.allowed_fields:
            raise Hold("unapproved normalized fields")
        for value in self.fields.values():
            if value is not None and not isinstance(value, (str, int, float, bool)):
                raise Hold("nested normalized field")
            if isinstance(value, str) and len(value) > 2048:
                raise Hold("oversized normalized field")
        result = {
            "schema": SCHEMA, "source_id": self.source_id,
            "source_record_id": self.source_record_id, "revision": self.revision,
            "published_at": stamp(published), "observed_at": stamp(observed),
            "expires_at": stamp(self.expires_at), "policy_revision": grant.policy_revision,
            "review_reference": grant.review_reference, "fields": dict(self.fields),
            "use": "RESEARCH_ONLY", "not_for_underwriting": True,
        }
        canonical(result)  # reject NaN or values outside the serialization contract
        return result


class Ledger:
    """Local durable DAG test adapter. No signatures, public routes or production auth.

    Tenant IDs passed here are trusted service-context values, NOT request bodies.
    The production adapter must enforce tenant isolation with Postgres RLS and
    transaction-scoped tenant context as well as application authorization.
    """
    def __init__(self, path: str | Path):
        self.db = sqlite3.connect(str(path), isolation_level=None)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS nodes (
            tenant TEXT NOT NULL, id TEXT NOT NULL, kind TEXT NOT NULL,
            envelope TEXT NOT NULL, expires_at TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('VALID','REVOKED')),
            PRIMARY KEY(tenant,id));
          CREATE TABLE IF NOT EXISTS edges (
            tenant TEXT NOT NULL, parent TEXT NOT NULL, child TEXT NOT NULL,
            PRIMARY KEY(tenant,parent,child),
            FOREIGN KEY(tenant,parent) REFERENCES nodes(tenant,id),
            FOREIGN KEY(tenant,child) REFERENCES nodes(tenant,id));
          CREATE INDEX IF NOT EXISTS edges_child ON edges(tenant,child);
          CREATE TABLE IF NOT EXISTS events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, tenant TEXT NOT NULL,
            node TEXT NOT NULL, reason TEXT NOT NULL, at TEXT NOT NULL,
            FOREIGN KEY(tenant,node) REFERENCES nodes(tenant,id));
        """)

    def close(self) -> None:
        self.db.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        else:
            self.db.execute("COMMIT")

    def state(self, tenant: str, node: str, now: datetime) -> str:
        row = self.db.execute(
            "SELECT state FROM nodes WHERE tenant=? AND id=?", (tenant, node)).fetchone()
        if row is None:
            return "MISSING"
        if row[0] == "REVOKED":
            return "REVOKED"
        # Includes this node and its ancestors; UNION terminates even on corrupt cycles.
        ancestors = self.db.execute("""
          WITH RECURSIVE a(id) AS (
            SELECT ? UNION SELECT e.parent FROM edges e JOIN a ON e.child=a.id
            WHERE e.tenant=?)
          SELECT n.id,n.state,n.expires_at FROM nodes n JOIN a ON n.id=a.id
          WHERE n.tenant=?
        """, (node, tenant, tenant)).fetchall()
        if any(not self.verify(tenant, r[0]) for r in ancestors):
            return "INTEGRITY_FAILED"
        if any(r[1] != "VALID" for r in ancestors):
            return "REVOKED"
        if any(parse_stamp(r[2]) <= aware(now) for r in ancestors):
            return "STALE"
        return "VALID"

    def append(self, tenant: str, kind: str, body: Mapping[str, Any],
               parents: Sequence[str], expires_at: datetime, now: datetime) -> str:
        nonempty(tenant, "tenant")
        nonempty(kind, "kind")
        parent_ids = sorted(set(parents))
        if len(parent_ids) != len(parents):
            raise Hold("duplicate dependency")
        if aware(expires_at) <= aware(now):
            raise Hold("node already expired")
        envelope = {
            "schema": SCHEMA, "tenant": tenant, "kind": kind, "body": dict(body),
            "parents": parent_ids, "expires_at": stamp(expires_at),
            "integrity": "LOCAL_SHA256_UNSIGNED",
        }
        serialized, node = canonical(envelope), digest(envelope)
        with self.transaction():
            existing = self.db.execute(
                "SELECT envelope FROM nodes WHERE tenant=? AND id=?", (tenant, node)).fetchone()
            if existing:
                if existing[0] != serialized:
                    raise Hold("content identity collision")
                if self.state(tenant, node, now) != "VALID":
                    raise Hold("idempotent retry cannot revive invalid evidence")
                return node
            for parent in parent_ids:
                if self.state(tenant, parent, now) != "VALID":
                    raise Hold("missing, stale or revoked dependency")
                parent_expiry = self.db.execute(
                    "SELECT expires_at FROM nodes WHERE tenant=? AND id=?",
                    (tenant, parent)).fetchone()[0]
                if aware(expires_at) > parse_stamp(parent_expiry):
                    raise Hold("derivation outlives a dependency")
            self.db.execute("INSERT INTO nodes VALUES(?,?,?,?,?,'VALID')",
                            (tenant, node, kind, serialized, stamp(expires_at)))
            self.db.executemany("INSERT INTO edges VALUES(?,?,?)",
                                [(tenant, p, node) for p in parent_ids])
        return node

    def revoke(self, tenant: str, node: str, reason: str, now: datetime) -> int:
        nonempty(reason, "reason", 128)
        # reason should be a non-sensitive controlled code, not pasted source text.
        with self.transaction():
            if not self.db.execute("SELECT 1 FROM nodes WHERE tenant=? AND id=?",
                                   (tenant, node)).fetchone():
                raise Hold("unknown node in tenant")
            descendants = self.db.execute("""
              WITH RECURSIVE d(id) AS (
                SELECT ? UNION SELECT e.child FROM edges e JOIN d ON e.parent=d.id
                WHERE e.tenant=?)
              SELECT n.id FROM nodes n JOIN d ON n.id=d.id
              WHERE n.tenant=? AND n.state='VALID'
            """, (node, tenant, tenant)).fetchall()
            for (item,) in descendants:
                self.db.execute("UPDATE nodes SET state='REVOKED' WHERE tenant=? AND id=?",
                                (tenant, item))
                self.db.execute("INSERT INTO events(tenant,node,reason,at) VALUES(?,?,?,?)",
                                (tenant, item, reason, stamp(now)))
        return len(descendants)

    def verify(self, tenant: str, node: str) -> bool:
        """Recompute content and dependencies; does not authenticate a signer."""
        row = self.db.execute(
            "SELECT envelope,kind,expires_at FROM nodes WHERE tenant=? AND id=?",
            (tenant, node)).fetchone()
        if row is None:
            return False
        try:
            obj = json.loads(row[0])
            edges = sorted(r[0] for r in self.db.execute(
                "SELECT parent FROM edges WHERE tenant=? AND child=?", (tenant, node)))
            return (digest(obj) == node and obj["tenant"] == tenant
                    and obj["kind"] == row[1] and obj["expires_at"] == row[2]
                    and edges == obj["parents"])
        except (ValueError, TypeError, KeyError):
            return False


@dataclass(frozen=True)
class ClearanceFacts:
    """Protected service facts; no public API may directly accept this object."""
    named_operator: str
    business_channel_verified: bool
    license_scope_passed: bool
    jurisdiction_passed: bool
    suppression_passed: bool
    purpose_passed: bool
    policy_passed: bool
    human_approved: bool
    checked_at: datetime
    expires_at: datetime
    policy_revision: str
    talk_track_revision: str


def clearance_decision(facts: ClearanceFacts, now: datetime,
                       dependencies_valid: bool) -> tuple[bool, tuple[str, ...]]:
    blockers: list[str] = []
    if not facts.named_operator.strip():
        blockers.append("OPERATOR_REQUIRED")
    for field in ("business_channel_verified", "license_scope_passed", "jurisdiction_passed",
                  "suppression_passed", "purpose_passed", "policy_passed", "human_approved"):
        if getattr(facts, field) is not True:
            blockers.append(field.upper())
    now = aware(now)
    if aware(facts.checked_at) > now or aware(facts.expires_at) <= now:
        blockers.append("CLEARANCE_TIME_INVALID")
    if (aware(facts.expires_at) - aware(facts.checked_at)).total_seconds() > 24 * 3600:
        blockers.append("CLEARANCE_LIFETIME_EXCEEDS_24H")
    if not facts.policy_revision.strip() or not facts.talk_track_revision.strip():
        blockers.append("VERSION_REQUIRED")
    if dependencies_valid is not True:
        blockers.append("DEPENDENCY_INVALID")
    return not blockers, tuple(blockers)


def research_priority(fit: float, event_relevance: float, independent_groups: int,
                      *, evidence_valid: bool, identity_verified: bool,
                      contradiction_unresolved: bool) -> dict[str, Any]:
    """Illustrative versioned work-order heuristic, NOT a learned probability.

    independent_groups are asserted by reviewed source lineage, NOT domain count.
    All numeric weights below require prospective evaluation before production use.
    Permission to contact is deliberately absent from this scoring function.
    """
    for value in (fit, event_relevance):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise Hold("invalid feature")
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise Hold("feature outside [0,1]")
    if isinstance(independent_groups, bool) or not isinstance(independent_groups, int) or independent_groups < 0:
        raise Hold("invalid independent evidence-group count")
    blockers = []
    if evidence_valid is not True:
        blockers.append("EVIDENCE_INVALID")
    if identity_verified is not True:
        blockers.append("IDENTITY_REVIEW")
    if contradiction_unresolved is not False:
        blockers.append("CONTRADICTION_REVIEW")
    components = {"fit": fit, "event_relevance": event_relevance,
                  "corroboration": min(independent_groups, 2) / 2}
    priority = None if blockers else round(100 * (
        0.45 * components["fit"] + 0.40 * components["event_relevance"]
        + 0.15 * components["corroboration"]), 2)
    return {"policy": "reference-work-order-v1-not-validated", "priority": priority,
            "components": components, "blockers": blockers,
            "conversion_probability": None, "contact_permission": "NOT_EVALUATED"}


def inventory_plan(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Read a GitHub-authored public inventory; never mutate GitHub or Hugging Face."""
    if snapshot.get("org") != "SZLHOLDINGS":
        raise Hold("unexpected organization")
    nonempty(snapshot.get("observedAt", ""), "observedAt")
    parse_stamp(snapshot["observedAt"])
    items = snapshot.get("inventory", {}).get("spaces")
    if not isinstance(items, list):
        raise Hold("missing spaces array")
    seen: set[str] = set()
    plan = []
    for item in items:
        if not isinstance(item, dict):
            raise Hold("invalid inventory item")
        repo = item.get("id", "")
        if not re.fullmatch(r"SZLHOLDINGS/[A-Za-z0-9][A-Za-z0-9_.-]*", repo):
            raise Hold("unexpected Space id")
        if repo in seen:
            raise Hold("duplicate Space in snapshot")
        seen.add(repo)
        review = ["RESOLVE_CANONICAL_SOURCE", "READ_CURRENT_RUNTIME", "VERIFY_RELEASE_PARITY"]
        if repo.rsplit("/", 1)[1] in {"terra", "counsel", "lyte"}:
            review.append("PUBLICATION_GUARDRAIL_REVIEW")
        if not item.get("license"):
            review.append("LICENSE_REVIEW")
        plan.append({"space": repo, "runtime": "NOT_OBSERVED_BY_THIS_TOOL",
                     "publication": "NOT_AUTHORIZED_BY_INVENTORY", "required": review})
    declared = snapshot.get("counts", {}).get("spaces")
    if declared is not None and declared != len(plan):
        raise Hold("declared Space count disagrees with snapshot")
    return {"schema": SCHEMA, "observed_at": snapshot["observedAt"],
            "visibility": "SNAPSHOT_SCOPE_ONLY", "count": len(plan), "plan": plan}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("inventory-plan", help="validate a saved inventory; read-only")
    check.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    try:
        if args.snapshot.stat().st_size > 8 * 1024 * 1024:
            raise Hold("snapshot exceeds 8 MiB limit")
        result = inventory_plan(json.loads(args.snapshot.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, f"HOLD: {type(exc).__name__}; validate the local input.\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
