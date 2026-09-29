"""Evidence-bound manual research workflow over the existing PostgreSQL ledger.

No contact sender, browser gate flags, model authority or production fallback.
Mutation linearization is the ledger's scope lock and expected epoch comparison.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .david_reference import Hold, aware, digest, parse_stamp, stamp
from .operator_policy import OperatorContext, PURPOSE

FACT_FIELDS = frozenset({"organization_name", "legal_name", "state", "city", "postal", "participant_count",
    "plan_name", "plan_year", "form_year", "filing_date", "plan_begin_date", "plan_end_date",
    "reported_life_benefit", "source_url", "event_type", "observed_change", "industry",
    "plan_year_begin", "plan_year_end", "amended_filing"})
TASKS = {
    "VERIFY_SOURCE": "Verify the current official source record",
    "RESOLVE_IDENTITY": "Review the organization identity evidence",
    "REVIEW_CHANGE": "Review the observed organization change",
    "REVIEW_COUNTER_EVIDENCE": "Investigate contradictory evidence",
}
OUTCOMES = frozenset({"WRONG_ENTITY", "SOURCE_STALE", "NOT_RELEVANT", "FURTHER_VERIFICATION_NEEDED", "PERMISSION_DECLINED", "RESEARCH_COMPLETED"})
CORRECTIONS = frozenset({"SOURCE_CORRECTED", "SOURCE_WITHDRAWN", "IDENTITY_MISMATCH", "PERMISSION_REVOKED", "INTEGRITY_FAILED"})


class Workflow:
    def __init__(self, ledger, context: OperatorContext, now: datetime):
        self.ledger, self.context, self.now = ledger, context, aware(now)

    def _node(self, scope: str, node_id: str, kinds=None, *, valid=True):
        node = self.ledger.get_node(self.context.tenant, node_id, self.now)
        if not node or node.get("scope_id") != scope:
            raise Hold("EVIDENCE_NOT_FOUND_IN_SCOPE")
        if kinds is not None and node["kind"] not in kinds:
            raise Hold("EVIDENCE_TYPE_MISMATCH")
        if valid and node["state"] != "VALID":
            raise Hold("EVIDENCE_" + node["state"])
        if valid:
            self._current_admissions(scope, node)
        if valid and node["kind"] in {"source", "observation"}:
            grants = [self.ledger.get_node(self.context.tenant, parent, self.now)
                      for parent in node.get("parents", [])]
            if not any(grant and grant["kind"] == "grant" and grant["state"] == "VALID"
                       and grant.get("scope_id") == scope
                       and grant["body"].get("source_id") == node["body"].get("source_id")
                       and grant["body"].get("policy_revision") == node["body"].get("policy_revision")
                       and grant["body"].get("rights", {}).get("research") == "ALLOW"
                       for grant in grants):
                raise Hold("CURRENT_SOURCE_GRANT_REQUIRED")
        return node

    def _current_admissions(self, scope, node):
        from .source_admission import SOURCE_ID, validate_stored_admission
        queue, seen = [node], set()
        while queue:
            current = queue.pop()
            if current["id"] in seen:
                continue
            seen.add(current["id"])
            if len(seen) > 500:
                raise Hold("EVIDENCE_SCOPE_LIMIT_REQUIRES_ARCHIVAL")
            if current["kind"] in {"source", "observation"} and current["body"].get("source_id") == SOURCE_ID:
                validate_stored_admission(current["body"], self.now)
            for parent_id in current.get("parents", []):
                parent = self.ledger.get_node(self.context.tenant, parent_id, self.now)
                if not parent or parent.get("scope_id") != scope or parent["state"] != "VALID":
                    raise Hold("CURRENT_DEPENDENCY_REQUIRED")
                queue.append(parent)

    def _scope_nodes(self, scope: str):
        # The database applies both RLS and an explicit tenant/scope predicate.
        with self.ledger.transaction(self.context.tenant) as cursor:
            cursor.execute("SELECT id FROM evidence_nodes WHERE tenant=%s AND scope_id=%s ORDER BY id LIMIT 501",
                           (self.context.tenant, scope))
            ids = [row[0] for row in cursor.fetchall()]
        if len(ids) > 500:
            raise Hold("EVIDENCE_SCOPE_LIMIT_REQUIRES_ARCHIVAL")
        return [self._node(scope, node, valid=False) for node in ids]

    def _expiry(self, parents, hours=24):
        return min([self.now + timedelta(hours=hours), self.context.expires_at] +
                   [parse_stamp(node["expires_at"]) for node in parents])

    def _evidence_context(self, scope, nodes=None):
        """Bind review to all current source and identity decisions in its scope."""
        material = {"source", "observation", "grant", "identity", "organization_review", "counter_evidence", "permission"}
        nodes = self._scope_nodes(scope) if nodes is None else nodes
        return digest(sorted((node["id"], node["state"]) for node in nodes if node["kind"] in material))

    def _require_current_brief(self, scope, brief):
        if brief["body"].get("evidence_context_digest") != self._evidence_context(scope):
            raise Hold("BRIEF_EVIDENCE_CHANGED_REVIEW_REQUIRED")

    def _require_latest_decision(self, scope, decision, kind, subject_ids):
        decisions = [node for node in self._scope_nodes(scope) if node["kind"] == kind]
        for subject in subject_ids:
            relevant = [node for node in decisions if subject in node.get("parents", [])]
            latest = max(relevant, key=lambda node: node["decision_epoch"], default=None)
            if latest is None or latest["id"] != decision["id"] or latest["state"] != "VALID":
                raise Hold("REVIEW_SUPERSEDED")

    def _append(self, scope, epoch, kind, body, parents, expiry):
        return self.ledger.append(self.context.tenant, kind,
            {**body, "purpose": PURPOSE, "operator": self.context.username,
             "operator_policy_digest": self.context.policy_digest, "created_at": stamp(self.now)},
            [node["id"] for node in parents], expiry, self.now,
            scope_id=scope, expected_epoch=epoch)

    def view_node(self, scope, node_id):
        self.context.require("read", self.now)
        with self.ledger.scope_read(self.context.tenant, scope):
            return self._view_node(scope, node_id)

    def _view_node(self, scope, node_id):
        node = self._node(scope, node_id, valid=False)
        body = node["body"]
        result = {key: node[key] for key in ("id", "kind", "state", "expires_at", "scope_id")}
        result.update(parents=node.get("parents", []), decision_epoch=self.ledger.decision_epoch(self.context.tenant, scope),
                      integrity="LOCAL_SHA256_UNSIGNED", contact_permission="NOT_GRANTED")
        # Invalidated payloads are withheld; references and status remain inspectable.
        if node["state"] == "VALID":
            try:
                self._current_admissions(scope, node)
            except Hold:
                result.update(state="HOLD", blockers=["CURRENT_SOURCE_GRANT_REQUIRED"])
                return result
            if node["kind"] in {"source", "observation"}:
                try:
                    self._node(scope, node_id)
                except Hold:
                    result.update(state="HOLD", blockers=["CURRENT_SOURCE_GRANT_REQUIRED"])
                    return result
                result["facts"] = self._facts(node)
                result["observed_at"] = body.get("observed_at")
                result["published_at"] = body.get("published_at")
                if body.get("source_id") == "dol-form5500-benefit-timing":
                    result["snapshot_published_at"] = result["published_at"]
                    result["published_at"] = None
            else:
                result["detail"] = {key: body[key] for key in
                    ("summary", "limitations", "next_verification", "decision", "reason", "task_type", "outcome", "reviewed_brief_id") if key in body}
                if node["kind"] == "brief":
                    result["detail"]["facts"] = [{
                        "source_node_id": row["source_node_id"],
                        "published_at": row["published_at"], "observed_at": row["observed_at"],
                        "snapshot_published_at": row.get("snapshot_published_at"),
                        "fields": self._facts({"body": {"fields": row["fields"]}}),
                    } for row in body.get("facts", [])]
                    result["detail"]["counter_evidence_ids"] = list(body.get("counter_evidence_ids", []))
        return result

    def workspace(self, scope):
        self.context.require("read", self.now)
        with self.ledger.scope_read(self.context.tenant, scope):
            return self._workspace(scope)

    def _workspace(self, scope):
        nodes = self._scope_nodes(scope)
        from .source_health_store import SourceHealthStore
        from .source_policy import source_status
        health = SourceHealthStore(self.ledger).read(self.context.tenant, "dol-form5500-benefit-timing")
        return {"schema": "szl.david.workspace/v2", "scope_id": scope,
            "decision_epoch": self.ledger.decision_epoch(self.context.tenant, scope),
            "nodes": [self.view_node(scope, node["id"]) for node in nodes],
            "purpose": PURPOSE, "contact_permission": "NOT_GRANTED",
            "empty": not nodes, "available_actions": sorted(self.context.actions),
            "source_health": source_status(health.source_id, health=health, now=self.now)}

    def refresh_source(self, scope, epoch, snapshot_revision):
        self.context.require("admit", self.now)
        from .source_admission import evaluate_source_health
        from .source_health_store import SourceHealthStore
        from .source_policy import source_status
        # Network work precedes the database transaction. Health describes this
        # attempt only and never grants evidence or workflow authority.
        attempt = evaluate_source_health(snapshot_revision, self.now)
        with self.ledger.scope_read(self.context.tenant, scope):
            if self.ledger.decision_epoch(self.context.tenant, scope) != epoch:
                raise Hold("DECISION_EPOCH_CONFLICT")
            record = SourceHealthStore(self.ledger).record_attempt(self.context.tenant, attempt)
        return source_status(record.source_id, health=record, now=self.now)

    @staticmethod
    def _facts(node):
        fields = node["body"].get("fields")
        if type(fields) is not dict or not fields:
            raise Hold("NORMALIZED_OBSERVATION_REQUIRED")
        selected = {}
        for key in FACT_FIELDS & fields.keys():
            value = fields[key]
            if value is not None and type(value) not in (str, int, float, bool):
                raise Hold("NORMALIZED_OBSERVATION_SCHEMA_INVALID")
            if isinstance(value, str) and len(value) > 2048:
                raise Hold("NORMALIZED_OBSERVATION_SCHEMA_INVALID")
            selected[key] = value
        if not selected:
            raise Hold("NO_PERMITTED_ORGANIZATION_FACTS")
        digest(selected)  # Reject nonfinite values before they enter a derivation.
        return selected

    def review_identity(self, scope, epoch, source_ids, decision):
        self.context.require("review", self.now)
        if decision not in {"ORGANIZATION_CONFIRMED", "NEEDS_REVIEW", "REJECTED"}:
            raise Hold("IDENTITY_REVIEW_DECISION_INVALID")
        sources = [self._node(scope, node, {"source", "observation"}) for node in source_ids]
        # This is a reviewed relation, never a parcel/facility-to-canonical-ID union.
        for node in sources:
            self._facts(node)
            if node["body"].get("entity_type") != "organization" or not node["body"].get("classification_evidence"):
                raise Hold("TYPED_ORGANIZATION_RELATION_REQUIRED")
        node_id = self._append(scope, epoch, "organization_review", {
            "decision": decision, "reason": "HUMAN_REVIEW_OF_ORGANIZATION_EVIDENCE",
            "canonical_identity_assigned": False}, sources, self._expiry(sources))
        return self.view_node(scope, node_id)

    def admit(self, scope, epoch, source_id, record_id, snapshot_revision):
        self.context.require("admit", self.now)
        from .source_admission import get_admitted_observation
        admitted = get_admitted_observation(source_id, record_id, snapshot_revision, self.now)
        if admitted.entity_type != "organization" or not admitted.classification_evidence:
            raise Hold("TYPED_ORGANIZATION_RELATION_REQUIRED")
        body = admitted.observation.body(admitted.grant, self.now)
        body.update(entity_type=admitted.entity_type,
                    classification_evidence=admitted.classification_evidence,
                    signing_key_fingerprint=admitted.signing_key_fingerprint,
                    snapshot_revision=admitted.snapshot_revision)
        self._facts({"body": body})
        node_id = self.ledger.admit_observation(self.context.tenant, scope,
            admitted.grant, body, admitted.observation.expires_at, self.now, expected_epoch=epoch)
        return self.view_node(scope, node_id)

    def brief(self, scope, epoch, source_ids, identity_review_id):
        self.context.require("brief", self.now)
        identity = self._node(scope, identity_review_id, {"organization_review"})
        if identity["body"].get("decision") != "ORGANIZATION_CONFIRMED":
            raise Hold("IDENTITY_REVIEW_REQUIRED")
        self._require_latest_decision(scope, identity, "organization_review", source_ids)
        sources = [self._node(scope, node, {"source", "observation"}) for node in source_ids]
        if not set(source_ids) <= set(identity.get("parents", [])):
            raise Hold("IDENTITY_REVIEW_DOES_NOT_COVER_SOURCES")
        scope_nodes = self._scope_nodes(scope)
        contradictions = [n for n in scope_nodes if n["kind"] == "counter_evidence" and n["state"] == "VALID"]
        parents = sources + [identity] + contradictions
        facts = [{"source_node_id": n["id"], "published_at": n["body"].get("published_at"),
                  "observed_at": n["body"].get("observed_at"), "fields": self._facts(n)} for n in sources]
        for row, source in zip(facts, sources):
            if source["body"].get("source_id") == "dol-form5500-benefit-timing":
                row["snapshot_published_at"] = row["published_at"]
                row["published_at"] = None
        body = {"summary": "Review the recorded organization facts against their original sources.",
            "facts": facts, "feature_digest": digest(facts), "as_of": stamp(self.now),
            "identity_review_id": identity_review_id, "counter_evidence_ids": [n["id"] for n in contradictions],
            "evidence_context_digest": self._evidence_context(scope, scope_nodes),
            "limitations": ["Research only; filing anniversaries are not confirmed renewals or buying intent.",
                            "Source agreement is not proof of independent corroboration."],
            "next_verification": TASKS["REVIEW_COUNTER_EVIDENCE" if contradictions else "VERIFY_SOURCE"],
            "inference": "DETERMINISTIC_NO_MODEL", "not_for_underwriting": True}
        node_id = self._append(scope, epoch, "brief", body, parents, self._expiry(parents))
        return self.view_node(scope, node_id)

    def review_brief(self, scope, epoch, brief_id, approved):
        self.context.require("review", self.now)
        brief = self._node(scope, brief_id, {"brief"})
        self._require_current_brief(scope, brief)
        if approved and brief["body"].get("counter_evidence_ids"):
            raise Hold("COUNTER_EVIDENCE_REVIEW_REQUIRED")
        node_id = self._append(scope, epoch, "brief_review", {
            "reviewed_brief_id": brief_id, "decision": "APPROVED" if approved else "REJECTED",
            "reason": "HUMAN_REVIEW_RECORDED"}, [brief], self._expiry([brief]))
        return self.view_node(scope, node_id)

    def clearance(self, scope, epoch, review_id):
        self.context.require("clearance", self.now)
        review = self._node(scope, review_id, {"brief_review"})
        if review["body"].get("decision") != "APPROVED":
            raise Hold("BRIEF_APPROVAL_REQUIRED")
        self._require_latest_decision(scope, review, "brief_review", [review["body"]["reviewed_brief_id"]])
        brief = self._node(scope, review["body"]["reviewed_brief_id"], {"brief"})
        self._require_current_brief(scope, brief)
        if review["body"].get("operator_policy_digest") != self.context.policy_digest:
            raise Hold("OPERATOR_POLICY_CHANGED")
        node_id = self._append(scope, epoch, "clearance", {
            "named_operator": self.context.username, "reviewed_brief_id": brief["id"],
            "action": "MANUAL_RESEARCH_TASK", "contact_permission": "NOT_GRANTED",
            "policy_revision": self.context.policy_revision}, [review, brief], self._expiry([review, brief]))
        return self.view_node(scope, node_id)

    def manual_task(self, scope, epoch, clearance_id, task_type, idempotency_key):
        self.context.require("manual_task", self.now)
        clearance = self._node(scope, clearance_id, {"clearance"})
        body = clearance["body"]
        if body.get("action") != "MANUAL_RESEARCH_TASK" or body.get("named_operator") != self.context.username:
            raise Hold("CLEARANCE_SCOPE_MISMATCH")
        if body.get("operator_policy_digest") != self.context.policy_digest:
            raise Hold("OPERATOR_POLICY_CHANGED")
        if task_type not in TASKS:
            raise Hold("MANUAL_TASK_TYPE_NOT_ALLOWED")
        task_id = self.ledger.create_manual_task(self.context.tenant, scope, clearance_id,
            {"task_type": task_type, "summary": TASKS[task_type], "purpose": PURPOSE,
             "operator": self.context.username, "operator_policy_digest": self.context.policy_digest,
             "contact_permission": "NOT_GRANTED"}, idempotency_key, epoch,
            self._expiry([clearance]), self.now)
        return self.view_node(scope, task_id)

    def correct(self, scope, epoch, node_id, reason):
        self.context.require("correct", self.now)
        if reason not in CORRECTIONS:
            raise Hold("CORRECTION_REASON_NOT_ALLOWED")
        self._node(scope, node_id, valid=False)
        before = {n["id"] for n in self._scope_nodes(scope) if n["state"] == "VALID"}
        count = self.ledger.correct(self.context.tenant, node_id, reason, self.now,
                                    scope_id=scope, expected_epoch=epoch)
        after = self._scope_nodes(scope)
        impacted = [{"id": n["id"], "kind": n["kind"], "state": n["state"]}
                    for n in after if n["id"] in before and n["state"] != "VALID"]
        return {"revoked": count, "impact": impacted,
                "decision_epoch": self.ledger.decision_epoch(self.context.tenant, scope),
                "external_recall_guaranteed": False}

    def decision_diff(self, scope, before_id, after_id):
        self.context.require("read", self.now)
        before = self._node(scope, before_id, {"brief"})
        after = self._node(scope, after_id, {"brief"})
        def facts(node):
            rows = node["body"]["facts"]
            if digest(rows) != node["body"]["feature_digest"]:
                raise Hold("BRIEF_FEATURE_INTEGRITY_FAILED")
            return {row["source_node_id"]: digest(row) for row in rows}
        a, b = facts(before), facts(after)
        return {"before": before_id, "after": after_id, "added": sorted(b.keys()-a.keys()),
                "removed": sorted(a.keys()-b.keys()), "unchanged": sorted(k for k in a.keys() & b.keys() if a[k] == b[k]),
                "known_then": before["body"]["as_of"], "known_later": after["body"]["as_of"],
                "interpretation": "STORED_DETERMINISTIC_FEATURES_NO_LATER_EVIDENCE_INJECTED"}

    def suppress(self, scope, epoch):
        self.context.require("suppress", self.now)
        result = self.ledger.suppress(self.context.tenant, scope, "OPERATOR_SUPPRESSION", self.now,
                                      expected_epoch=epoch)
        return {"state": "SUPPRESSED", "result": result,
                "decision_epoch": self.ledger.decision_epoch(self.context.tenant, scope),
                "external_recall_guaranteed": False}

    def outcome(self, scope, epoch, task_id, outcome):
        self.context.require("outcome", self.now)
        if outcome not in OUTCOMES:
            raise Hold("OUTCOME_NOT_ALLOWED")
        task = self._node(scope, task_id, {"crm_task", "manual_task"})
        node_id = self._append(scope, epoch, "outcome", {"outcome": outcome}, [task], self._expiry([task]))
        return self.view_node(scope, node_id)

    def counter_evidence(self, scope, epoch, source_ids, reason):
        self.context.require("review", self.now)
        if reason not in {"CONTRADICTORY_SOURCE", "IDENTITY_CONFLICT", "STALE_EVENT", "MISSING_EXPECTED_EVIDENCE"}:
            raise Hold("COUNTER_EVIDENCE_REASON_INVALID")
        sources = [self._node(scope, node, {"source", "observation"}) for node in source_ids]
        node_id = self._append(scope, epoch, "counter_evidence", {
            "reason": reason, "decision": "UNRESOLVED", "action_eligibility": "HOLD"},
            sources, self._expiry(sources))
        return self.view_node(scope, node_id)
