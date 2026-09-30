"""Postgres evidence adapter for the David kernel.

Implements the same Hold / revoke / verify contracts as the SQLite reference
Ledger. SQLite remains test-only. Integrity stays LOCAL_SHA256_UNSIGNED until
the existing Cosign/receipts path binds it. This adapter never creates schema
objects at runtime.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from .david_reference import (
    SCHEMA,
    Grant,
    Hold,
    Identifier,
    aware,
    canonical,
    digest,
    nonempty,
    Observation,
    parse_stamp,
    relationship,
    stamp,
)

try:
    import psycopg
except Exception:  # pragma: no cover - exercised when psycopg is absent locally
    psycopg = None

EVIDENCE_TABLES = (
    "source_grants",
    "observations",
    "identity_candidates",
    "evidence_nodes",
    "evidence_edges",
    "derivations",
    "clearances",
    "suppressions",
    "outcomes",
    "outbox",
    "decision_scopes",
    "manual_tasks",
    "source_grant_authorities",
    "source_health",
)
RUNTIME_TABLE_PRIVILEGES = {
    table: ("SELECT", "INSERT")
    if table == "evidence_edges"
    else ("SELECT", "INSERT", "UPDATE")
    for table in EVIDENCE_TABLES
}
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "evidence_schema.sql"
DEALDESK_TABLES = ("david_dealdesk_state", "david_dealdesk_events")
CANDIDATE_RELATIONSHIPS = frozenset(
    {"CANDIDATE_REVIEW", "UNRESOLVED", "CONFLICT_REVIEW"}
)


def apply_evidence_schema(connection: Any) -> None:
    """Apply the expand-only evidence SQL. Never drops deal-desk tables."""
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    if any(
        f"DROP TABLE {name}" in sql or f"DROP TABLE IF EXISTS {name}" in sql
        for name in DEALDESK_TABLES
    ):
        raise Hold("evidence schema must not drop deal-desk tables")
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute(sql, prepare=False)


class PostgresLedger:
    """Production-equivalent durable DAG. Tenant values are service-context only."""

    def __init__(self, connection: Any):
        if connection is None:
            raise Hold("postgres connection required")
        self.conn = connection
        try:
            self.conn.autocommit = True
        except Exception:
            pass

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def transaction(self, tenant: str) -> Iterator[Any]:
        nonempty(tenant, "tenant")
        with self.conn.transaction():
            with self.conn.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('david.tenant', %s, true)",
                    (tenant,),
                )
                yield cursor

    def _lock_scope(self, cursor, tenant, scope_id, expected_epoch=None):
        nonempty(scope_id, "scope_id")
        cursor.execute(
            "INSERT INTO decision_scopes (tenant,scope_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
            (tenant, scope_id),
        )
        cursor.execute(
            "SELECT decision_epoch,suppressed FROM decision_scopes WHERE tenant=%s AND scope_id=%s FOR UPDATE",
            (tenant, scope_id),
        )
        epoch, suppressed = cursor.fetchone()
        if expected_epoch is not None and (
            type(expected_epoch) is not int or expected_epoch != epoch
        ):
            raise Hold("DECISION_EPOCH_CONFLICT")
        return epoch, suppressed

    def decision_epoch(self, tenant, scope_id):
        with self.transaction(tenant) as cursor:
            return self._lock_scope(cursor, tenant, scope_id)[0]

    @contextmanager
    def scope_read(self, tenant, scope_id):
        """One coherent graph read; writers take this same scope lock first."""
        with self.transaction(tenant) as cursor:
            self._lock_scope(cursor, tenant, scope_id)
            yield

    def _node_scope(self, cursor, tenant, node):
        cursor.execute(
            "SELECT scope_id FROM evidence_nodes WHERE tenant=%s AND id=%s",
            (tenant, node),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def state(self, tenant: str, node: str, now: datetime) -> str:
        with self.transaction(tenant) as cursor:
            scope = self._node_scope(cursor, tenant, node)
            if scope is None:
                return "MISSING"
            self._lock_scope(cursor, tenant, scope)
            return self._state_unlocked(cursor, tenant, node, now)

    def get_node(self, tenant, node, now, *, scope_id=None):
        with self.transaction(tenant) as cursor:
            if scope_id is None:
                scope = self._node_scope(cursor, tenant, node)
            else:
                # The caller may already hold its own scope lock. Reject an
                # unrelated identifier before taking any second scope lock.
                cursor.execute(
                    "SELECT scope_id FROM evidence_nodes WHERE tenant=%s AND id=%s AND scope_id=%s",
                    (tenant, node, scope_id),
                )
                row = cursor.fetchone()
                scope = row[0] if row else None
            if scope is None:
                return None
            epoch, _ = self._lock_scope(cursor, tenant, scope)
            cursor.execute(
                "SELECT envelope,decision_epoch FROM evidence_nodes WHERE tenant=%s AND id=%s",
                (tenant, node),
            )
            row = cursor.fetchone()
            envelope = json.loads(row[0])
            return {
                "id": node,
                "kind": envelope["kind"],
                "body": envelope["body"],
                "parents": envelope["parents"],
                "expires_at": envelope["expires_at"],
                "scope_id": scope,
                "decision_epoch": row[1],
                "current_epoch": epoch,
                "state": self._state_unlocked(cursor, tenant, node, now),
            }

    def append(
        self,
        tenant: str,
        kind: str,
        body: Mapping[str, Any],
        parents: Sequence[str],
        expires_at: datetime,
        now: datetime,
        *,
        scope_id: str = "legacy",
        expected_epoch: int | None = None,
    ) -> str:
        nonempty(tenant, "tenant")
        nonempty(kind, "kind")
        parent_ids = sorted(set(parents))
        if len(parent_ids) != len(parents):
            raise Hold("duplicate dependency")
        if aware(expires_at) <= aware(now):
            raise Hold("node already expired")
        self._reject_canonical_inheritance(kind, body)
        with self.transaction(tenant) as cursor:
            if kind == "grant":
                self._lock_grant(
                    cursor, tenant, body.get("source_id"), body.get("policy_revision")
                )
            epoch, suppressed = self._lock_scope(
                cursor, tenant, scope_id, expected_epoch
            )
            if suppressed:
                raise Hold("SCOPE_SUPPRESSED")
            return self._append_locked(
                cursor, tenant, scope_id, epoch, kind, body, parent_ids, expires_at, now
            )

    def _append_locked(
        self, cursor, tenant, scope_id, epoch, kind, body, parent_ids, expires_at, now
    ):
        envelope = {
            "schema": SCHEMA,
            "tenant": tenant,
            "kind": kind,
            "body": dict(body),
            "parents": parent_ids,
            "expires_at": stamp(expires_at),
            "integrity": "LOCAL_SHA256_UNSIGNED",
            "scope_id": scope_id,
        }
        # A content retry is resolved before an epoch change. The immutable hash
        # binds the scope, while the separately checked SQL epoch binds admission.
        serialized, node = canonical(envelope), digest(envelope)
        # An upgrade must not manufacture a second identity for the exact V1
        # content. Old envelopes remain byte-for-byte intact and verifiable.
        if scope_id == "legacy":
            old_envelope = {
                key: value for key, value in envelope.items() if key != "scope_id"
            }
            old_node = digest(old_envelope)
            cursor.execute(
                "SELECT envelope FROM evidence_nodes WHERE tenant=%s AND id=%s",
                (tenant, old_node),
            )
            old = cursor.fetchone()
            if old:
                if (
                    old[0] != canonical(old_envelope)
                    or self._state_unlocked(cursor, tenant, old_node, now) != "VALID"
                ):
                    raise Hold("idempotent retry cannot revive invalid evidence")
                return old_node
        cursor.execute(
            "SELECT envelope FROM evidence_nodes WHERE tenant=%s AND id=%s",
            (tenant, node),
        )
        existing = cursor.fetchone()
        if existing:
            if existing[0] != serialized:
                raise Hold("content identity collision")
            if self._state_unlocked(cursor, tenant, node, now) != "VALID":
                raise Hold("idempotent retry cannot revive invalid evidence")
            return node
        for parent in parent_ids:
            if self._node_scope(cursor, tenant, parent) != scope_id:
                raise Hold("CROSS_SCOPE_DEPENDENCY_DENIED")
            if self._state_unlocked(cursor, tenant, parent, now) != "VALID":
                raise Hold("missing, stale or revoked dependency")
            cursor.execute(
                "SELECT expires_at FROM evidence_nodes WHERE tenant=%s AND id=%s",
                (tenant, parent),
            )
            parent_expiry = cursor.fetchone()[0]
            if aware(expires_at) > parse_stamp(parent_expiry):
                raise Hold("derivation outlives a dependency")
        if kind in {
            "grant",
            "source",
            "observation",
            "identity",
            "permission",
            "suppression",
            "organization_review",
            "brief_review",
            "counter_evidence",
        }:
            cursor.execute(
                "UPDATE decision_scopes SET decision_epoch=decision_epoch+1 WHERE tenant=%s AND scope_id=%s RETURNING decision_epoch",
                (tenant, scope_id),
            )
            epoch = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO evidence_nodes (tenant,id,kind,envelope,expires_at,state,scope_id,decision_epoch) VALUES (%s,%s,%s,%s,%s,'VALID',%s,%s)",
            (tenant, node, kind, serialized, stamp(expires_at), scope_id, epoch),
        )
        if parent_ids:
            cursor.executemany(
                "INSERT INTO evidence_edges VALUES (%s,%s,%s)",
                [(tenant, parent, node) for parent in parent_ids],
            )
        self._project(cursor, tenant, kind, node, body, expires_at, serialized)
        self._outbox(
            cursor,
            tenant,
            node,
            "EVIDENCE_APPENDED",
            {"kind": kind, "integrity": "LOCAL_SHA256_UNSIGNED"},
            now,
        )
        return node

    def revoke(
        self,
        tenant: str,
        node: str,
        reason: str,
        now: datetime,
        *,
        scope_id=None,
        expected_epoch=None,
    ) -> int:
        nonempty(reason, "reason", 128)
        with self.transaction(tenant) as cursor:
            actual_scope = self._node_scope(cursor, tenant, node)
            if actual_scope is None or (
                scope_id is not None and scope_id != actual_scope
            ):
                raise Hold("EVIDENCE_NOT_FOUND_IN_SCOPE")
            self._lock_scope(cursor, tenant, actual_scope, expected_epoch)
            cursor.execute(
                "UPDATE decision_scopes SET decision_epoch=decision_epoch+1 WHERE tenant=%s AND scope_id=%s",
                (tenant, actual_scope),
            )
            cursor.execute(
                "SELECT 1 FROM evidence_nodes WHERE tenant=%s AND id=%s FOR UPDATE",
                (tenant, node),
            )
            if cursor.fetchone() is None:
                raise Hold("unknown node in tenant")
            cursor.execute(
                """
                WITH RECURSIVE d(id) AS (
                    SELECT %s
                    UNION
                    SELECT e.child FROM evidence_edges e JOIN d ON e.parent=d.id
                    WHERE e.tenant=%s
                )
                SELECT n.id, n.kind FROM evidence_nodes n JOIN d ON n.id=d.id
                WHERE n.tenant=%s AND n.state='VALID'
                """,
                (node, tenant, tenant),
            )
            descendants = cursor.fetchall()
            for item, kind in descendants:
                cursor.execute(
                    "UPDATE evidence_nodes SET state='REVOKED' "
                    "WHERE tenant=%s AND id=%s",
                    (tenant, item),
                )
                self._revoke_projections(cursor, tenant, item, kind, now)
                self._outbox(
                    cursor,
                    tenant,
                    item,
                    "EVIDENCE_REVOKED",
                    {"reason": reason, "kind": kind},
                    now,
                )
        return len(descendants)

    def correct(
        self,
        tenant: str,
        node: str,
        reason: str,
        now: datetime,
        *,
        scope_id=None,
        expected_epoch=None,
    ) -> int:
        """Correction revokes the node and every descendant, including brief/clearance/CRM."""
        return self.revoke(
            tenant,
            node,
            reason or "SOURCE_CORRECTED",
            now,
            scope_id=scope_id,
            expected_epoch=expected_epoch,
        )

    def verify(self, tenant: str, node: str) -> bool:
        with self.transaction(tenant) as cursor:
            scope = self._node_scope(cursor, tenant, node)
            if scope is None:
                return False
            self._lock_scope(cursor, tenant, scope)
            return self._verify_unlocked(cursor, tenant, node)

    def put_grant(
        self,
        tenant: str,
        grant: Grant,
        now: datetime,
        *,
        scope_id="legacy",
        expected_epoch=None,
    ) -> str:
        grant.require("research", now)
        body = {
            "source_id": grant.source_id,
            "policy_revision": grant.policy_revision,
            "review_reference": grant.review_reference,
            "rights": {key: value.value for key, value in grant.rights.items()},
            "allowed_fields": sorted(grant.allowed_fields),
        }
        with self.transaction(tenant) as cursor:
            self._lock_grant(cursor, tenant, grant.source_id, grant.policy_revision)
            return self.append(
                tenant,
                "grant",
                body,
                (),
                grant.expires_at,
                now,
                scope_id=scope_id,
                expected_epoch=expected_epoch,
            )

    def _lock_grant(self, cursor, tenant, source_id, revision, *, allow_revoked=False):
        nonempty(source_id, "source_id")
        nonempty(revision, "policy_revision")
        cursor.execute(
            "INSERT INTO source_grant_authorities (tenant,source_id,policy_revision) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
            (tenant, source_id, revision),
        )
        cursor.execute(
            "SELECT revoked FROM source_grant_authorities WHERE tenant=%s AND source_id=%s AND policy_revision=%s FOR UPDATE",
            (tenant, source_id, revision),
        )
        if cursor.fetchone()[0] and not allow_revoked:
            raise Hold("SOURCE_GRANT_REVOKED")

    def admit_observation(
        self, tenant, scope_id, grant, body, expires_at, now, expected_epoch=None,
        *, authorize=None
    ):
        """Trusted admission: grant lock precedes the scope lock in every path.

        A permanent grant tombstone also protects previously unseen scopes.
        No browser-supplied rights or classification belong in this interface.
        """
        with self.transaction(tenant) as cursor:
            self._lock_grant(cursor, tenant, grant.source_id, grant.policy_revision)
            self._lock_scope(cursor, tenant, scope_id, expected_epoch)
            # Production authority and wall time must be refreshed after both
            # potentially blocking locks, before any durable evidence write.
            if authorize is not None:
                if not callable(authorize):
                    raise Hold("ADMISSION_AUTHORIZATION_REQUIRED")
                now = aware(authorize())
            grant.require("collect", now)
            grant.require("research", now)
            observation = Observation(
                grant.source_id,
                body["source_record_id"],
                body["revision"],
                parse_stamp(body["published_at"]),
                parse_stamp(body["observed_at"]),
                expires_at,
                body["fields"],
            )
            checked = observation.body(grant, now)
            for key in (
                "entity_type",
                "organization_admission",
                "classification_reference",
                "classification_evidence",
                "signing_key_fingerprint",
                "snapshot_revision",
            ):
                if key in body:
                    checked[key] = body[key]
            grant_node = self.put_grant(tenant, grant, now, scope_id=scope_id)
            return self.append(
                tenant,
                "observation",
                checked,
                [grant_node],
                expires_at,
                now,
                scope_id=scope_id,
            )

    def revoke_grant(self, tenant, source_id, policy_revision, reason, now):
        nonempty(reason, "reason", 128)
        with self.transaction(tenant) as cursor:
            self._lock_grant(
                cursor, tenant, source_id, policy_revision, allow_revoked=True
            )
            cursor.execute(
                "UPDATE source_grant_authorities SET revoked=true WHERE tenant=%s AND source_id=%s AND policy_revision=%s",
                (tenant, source_id, policy_revision),
            )
            cursor.execute(
                "SELECT scope_id,node_id FROM source_grants WHERE tenant=%s AND source_id=%s AND policy_revision=%s ORDER BY scope_id,node_id",
                (tenant, source_id, policy_revision),
            )
            rows = cursor.fetchall()
            for scope in sorted({row[0] for row in rows}):
                self._lock_scope(cursor, tenant, scope)
            return sum(
                self.revoke(tenant, node, reason, now, scope_id=scope)
                for scope, node in rows
            )

    def suppress(self, tenant, scope_id, reason, now, *, expected_epoch=None):
        nonempty(reason, "reason", 128)
        with self.transaction(tenant) as cursor:
            epoch, already = self._lock_scope(cursor, tenant, scope_id, expected_epoch)
            if already:
                return 0
            cursor.execute(
                "UPDATE decision_scopes SET suppressed=true,decision_epoch=decision_epoch+1 WHERE tenant=%s AND scope_id=%s",
                (tenant, scope_id),
            )
            cursor.execute(
                "SELECT id,kind FROM evidence_nodes WHERE tenant=%s AND scope_id=%s AND state='VALID'",
                (tenant, scope_id),
            )
            rows = cursor.fetchall()
            for node, kind in rows:
                cursor.execute(
                    "UPDATE evidence_nodes SET state='REVOKED' WHERE tenant=%s AND id=%s",
                    (tenant, node),
                )
                self._revoke_projections(cursor, tenant, node, kind, now)
                self._outbox(
                    cursor,
                    tenant,
                    node,
                    "SCOPE_SUPPRESSED",
                    {"reason": reason, "scope_id": scope_id},
                    now,
                )
            suppression_id = digest(
                {
                    "tenant": tenant,
                    "scope": scope_id,
                    "epoch": epoch + 1,
                    "reason": reason,
                }
            )
            cursor.execute(
                "INSERT INTO suppressions (tenant,id,subject_key,reason,recorded_at,node_id,active,envelope) VALUES (%s,%s,%s,%s,%s,NULL,true,%s)",
                (
                    tenant,
                    suppression_id,
                    scope_id,
                    reason,
                    stamp(now),
                    canonical(
                        {"scope_id": scope_id, "reason": reason, "epoch": epoch + 1}
                    ),
                ),
            )
            return len(rows)

    def create_manual_task(
        self,
        tenant,
        scope_id,
        clearance_node,
        body,
        idempotency_key,
        expected_epoch,
        expires_at,
        now,
    ):
        nonempty(idempotency_key, "idempotency_key", 128)
        request_digest = digest(
            {"scope": scope_id, "clearance": clearance_node, "body": dict(body)}
        )
        with self.transaction(tenant) as cursor:
            epoch, suppressed = self._lock_scope(
                cursor, tenant, scope_id, expected_epoch
            )
            if suppressed:
                raise Hold("SCOPE_SUPPRESSED")
            cursor.execute(
                "SELECT id,request_digest FROM manual_tasks WHERE tenant=%s AND scope_id=%s AND idempotency_key=%s",
                (tenant, scope_id, idempotency_key),
            )
            existing = cursor.fetchone()
            if existing:
                if existing[1] != request_digest:
                    raise Hold("IDEMPOTENCY_KEY_CONFLICT")
                if self._state_unlocked(cursor, tenant, existing[0], now) != "VALID":
                    raise Hold("TASK_NO_LONGER_VALID")
                return existing[0]
            cursor.execute(
                "SELECT kind,scope_id,envelope FROM evidence_nodes WHERE tenant=%s AND id=%s",
                (tenant, clearance_node),
            )
            row = cursor.fetchone()
            if (
                not row
                or row[:2] != ("clearance", scope_id)
                or self._state_unlocked(cursor, tenant, clearance_node, now) != "VALID"
            ):
                raise Hold("CLEARANCE_NO_LONGER_VALID")
            clearance = json.loads(row[2])["body"]
            if (
                clearance.get("action") != "MANUAL_RESEARCH_TASK"
                or clearance.get("named_operator") != body.get("operator")
                or clearance.get("operator_policy_digest")
                != body.get("operator_policy_digest")
            ):
                raise Hold("CLEARANCE_AUTHORITY_MISMATCH")
            if aware(expires_at) <= aware(now):
                raise Hold("TASK_EXPIRED")
            task = self._append_locked(
                cursor,
                tenant,
                scope_id,
                epoch,
                "manual_task",
                {**body, "idempotency_key": idempotency_key},
                [clearance_node],
                expires_at,
                now,
            )
            cursor.execute(
                "INSERT INTO manual_tasks (tenant,id,scope_id,decision_epoch,clearance_node,idempotency_key,request_digest,body,state) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'PENDING')",
                (
                    tenant,
                    task,
                    scope_id,
                    epoch,
                    clearance_node,
                    idempotency_key,
                    request_digest,
                    canonical(dict(body)),
                ),
            )
            self._outbox(
                cursor,
                tenant,
                task,
                "MANUAL_TASK_READY",
                {
                    "scope_id": scope_id,
                    "decision_epoch": epoch,
                    "request_digest": request_digest,
                },
                now,
            )
            return task

    def claim_outbox(self, tenant, worker, now, lease_seconds=30):
        nonempty(worker, "worker", 128)
        if type(lease_seconds) is not int or not 1 <= lease_seconds <= 300:
            raise Hold("INVALID_LEASE")
        with self.transaction(tenant) as cursor:
            cursor.execute(
                "SELECT o.id,o.node_id,n.scope_id FROM outbox o JOIN evidence_nodes n ON n.tenant=o.tenant AND n.id=o.node_id WHERE o.tenant=%s AND o.event_type='MANUAL_TASK_READY' AND (o.status='PENDING' OR (o.status IN ('LEASED','DISPATCHING') AND o.lease_until<=%s)) ORDER BY n.scope_id,o.created_at,o.id LIMIT 100",
                (tenant, aware(now)),
            )
            candidates = cursor.fetchall()
            for item, node, scope in candidates:
                self._lock_scope(cursor, tenant, scope)
                cursor.execute(
                    "SELECT status,fencing_token,lease_until,payload FROM outbox WHERE tenant=%s AND id=%s FOR UPDATE SKIP LOCKED",
                    (tenant, item),
                )
                row = cursor.fetchone()
                if (
                    not row
                    or row[0] not in {"PENDING", "LEASED", "DISPATCHING"}
                    or (row[0] != "PENDING" and row[2] > aware(now))
                ):
                    continue
                if row[0] == "DISPATCHING":
                    cursor.execute(
                        "UPDATE outbox SET status='DELIVERY_UNKNOWN' WHERE tenant=%s AND id=%s",
                        (tenant, item),
                    )
                    continue
                if self._state_unlocked(cursor, tenant, node, now) != "VALID":
                    cursor.execute(
                        "UPDATE outbox SET status='CANCELLED' WHERE tenant=%s AND id=%s",
                        (tenant, item),
                    )
                    continue
                token = row[1] + 1
                cursor.execute(
                    "UPDATE outbox SET status='LEASED',fencing_token=%s,lease_until=%s,worker=%s WHERE tenant=%s AND id=%s",
                    (
                        token,
                        aware(now) + timedelta(seconds=lease_seconds),
                        worker,
                        tenant,
                        item,
                    ),
                )
                return {
                    "id": item,
                    "node_id": node,
                    "fencing_token": token,
                    "payload": json.loads(row[3]),
                    "status": "LEASED",
                }
            return None

    def begin_outbox_dispatch(
        self, tenant, item_id, fencing_token, now, authorization_check
    ):
        """Recheck a current server-owned policy immediately before external I/O.

        The callback receives the immutable task body. A crash after this commit
        cannot be retried automatically: the outcome is DELIVERY_UNKNOWN.
        """
        return self._transition_outbox(
            tenant, item_id, fencing_token, now, "DISPATCHING", authorization_check
        )

    def finalize_outbox(self, tenant, item_id, fencing_token, now, delivery_state):
        if delivery_state not in {"PUBLISHED", "DELIVERY_UNKNOWN"}:
            raise Hold("INVALID_DELIVERY_STATE")
        return self._transition_outbox(
            tenant, item_id, fencing_token, now, delivery_state, None
        )

    def _transition_outbox(self, tenant, item, token, now, target, authorization_check):
        with self.transaction(tenant) as cursor:
            cursor.execute(
                "SELECT n.scope_id,o.node_id FROM outbox o JOIN evidence_nodes n ON n.tenant=o.tenant AND n.id=o.node_id WHERE o.tenant=%s AND o.id=%s AND o.event_type='MANUAL_TASK_READY'",
                (tenant, item),
            )
            binding = cursor.fetchone()
            if not binding:
                raise Hold("OUTBOX_ITEM_NOT_FOUND")
            self._lock_scope(cursor, tenant, binding[0])
            cursor.execute(
                "SELECT status,fencing_token,lease_until FROM outbox WHERE tenant=%s AND id=%s FOR UPDATE",
                (tenant, item),
            )
            status, fence, until = cursor.fetchone()
            required = "LEASED" if target == "DISPATCHING" else "DISPATCHING"
            if (
                type(token) is not int
                or token != fence
                or status != required
                or until is None
                or until <= aware(now)
            ):
                raise Hold("OUTBOX_LEASE_CONFLICT")
            valid = self._state_unlocked(cursor, tenant, binding[1], now) == "VALID"
            if target == "DISPATCHING":
                cursor.execute(
                    "SELECT body FROM manual_tasks WHERE tenant=%s AND id=%s",
                    (tenant, binding[1]),
                )
                body = json.loads(cursor.fetchone()[0])
                if (
                    not valid
                    or not callable(authorization_check)
                    or authorization_check(body) is not True
                ):
                    raise Hold("DISPATCH_AUTHORIZATION_DENIED")
            elif not valid:
                target = "DELIVERY_UNKNOWN"
            cursor.execute(
                "UPDATE outbox SET status=%s,published_at=%s WHERE tenant=%s AND id=%s",
                (target, stamp(now) if target == "PUBLISHED" else None, tenant, item),
            )
            return target

    def remember_identity(
        self,
        tenant: str,
        left: Sequence[Identifier],
        right: Sequence[Identifier],
        *,
        same_name_state_postal: bool,
        parents: Sequence[str],
        expires_at: datetime,
        now: datetime,
    ) -> str:
        """Persist a candidate or verified-id relationship. Never inherit canonical identity."""
        rel = relationship(
            left,
            right,
            same_name_state_postal=same_name_state_postal,
        )
        left_key = left[0].key() if left else ("", "", "", "")
        body = {
            "kind": left_key[0],
            "namespace": left_key[1],
            "jurisdiction": left_key[2],
            "value_normalized": left_key[3],
            "relationship": rel,
            "canonical_organization_id": None,
            "same_name_state_postal": same_name_state_postal,
        }
        return self.append(tenant, "identity", body, parents, expires_at, now)

    def _state_unlocked(
        self,
        cursor: Any,
        tenant: str,
        node: str,
        now: datetime,
    ) -> str:
        cursor.execute(
            "SELECT state FROM evidence_nodes WHERE tenant=%s AND id=%s",
            (tenant, node),
        )
        row = cursor.fetchone()
        if row is None:
            return "MISSING"
        if row[0] == "REVOKED":
            return "REVOKED"
        cursor.execute(
            """
            WITH RECURSIVE a(id) AS (
                SELECT %s
                UNION
                SELECT e.parent FROM evidence_edges e JOIN a ON e.child=a.id
                WHERE e.tenant=%s
            )
            SELECT n.id, n.state, n.expires_at
            FROM evidence_nodes n JOIN a ON n.id=a.id
            WHERE n.tenant=%s
            """,
            (node, tenant, tenant),
        )
        ancestors = cursor.fetchall()
        if any(
            not self._verify_unlocked(cursor, tenant, item[0]) for item in ancestors
        ):
            return "INTEGRITY_FAILED"
        if any(item[1] != "VALID" for item in ancestors):
            return "REVOKED"
        if any(parse_stamp(item[2]) <= aware(now) for item in ancestors):
            return "STALE"
        cursor.execute(
            "SELECT n.kind,n.decision_epoch,s.decision_epoch,s.suppressed FROM evidence_nodes n JOIN decision_scopes s ON n.tenant=s.tenant AND n.scope_id=s.scope_id WHERE n.tenant=%s AND n.id=%s",
            (tenant, node),
        )
        kind, bound, current, suppressed = cursor.fetchone()
        if suppressed:
            return "REVOKED"
        if kind in {"clearance", "crm_task", "manual_task"} and bound != current:
            return "STALE"
        return "VALID"

    def _verify_unlocked(self, cursor: Any, tenant: str, node: str) -> bool:
        cursor.execute(
            "SELECT envelope, kind, expires_at, scope_id FROM evidence_nodes "
            "WHERE tenant=%s AND id=%s",
            (tenant, node),
        )
        row = cursor.fetchone()
        if row is None:
            return False
        try:
            obj = json.loads(row[0])
            cursor.execute(
                "SELECT parent FROM evidence_edges WHERE tenant=%s AND child=%s",
                (tenant, node),
            )
            edges = sorted(item[0] for item in cursor.fetchall())
            return (
                digest(obj) == node
                and obj["tenant"] == tenant
                and obj["kind"] == row[1]
                and obj["expires_at"] == row[2]
                and obj.get("scope_id", "legacy") == row[3]
                and edges == obj["parents"]
            )
        except (ValueError, TypeError, KeyError):
            return False

    def _reject_canonical_inheritance(self, kind: str, body: Mapping[str, Any]) -> None:
        if kind != "identity":
            return
        relationship_value = str(body.get("relationship") or "")
        canonical_id = body.get("canonical_organization_id")
        if relationship_value in CANDIDATE_RELATIONSHIPS and canonical_id:
            raise Hold("candidates never inherit canonical identity")
        if canonical_id:
            raise Hold("canonical identity is not assigned by this adapter")

    def _project(
        self,
        cursor: Any,
        tenant: str,
        kind: str,
        node: str,
        body: Mapping[str, Any],
        expires_at: datetime,
        envelope: str,
    ) -> None:
        expiry = stamp(expires_at)
        payload = canonical(dict(body))
        if kind == "grant":
            cursor.execute(
                "INSERT INTO source_grants (tenant,source_id,policy_revision,review_reference,expires_at,rights,allowed_fields,envelope,node_id,state,scope_id) VALUES "
                "(%s,%s,%s,%s,%s,%s,%s,%s,%s,'VALID',%s)",
                (
                    tenant,
                    nonempty(str(body.get("source_id") or node), "source_id"),
                    nonempty(
                        str(body.get("policy_revision") or "unknown"), "policy_revision"
                    ),
                    nonempty(
                        str(body.get("review_reference") or "unknown"),
                        "review_reference",
                        2048,
                    ),
                    expiry,
                    canonical(body.get("rights") or {}),
                    canonical(body.get("allowed_fields") or []),
                    envelope,
                    node,
                    self._node_scope(cursor, tenant, node),
                ),
            )
        elif kind in {"source", "observation"}:
            cursor.execute(
                "INSERT INTO observations (tenant,id,source_id,source_record_id,revision,published_at,observed_at,expires_at,fields,envelope,state,scope_id) VALUES "
                "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'VALID',%s)",
                (
                    tenant,
                    node,
                    str(body.get("source_id") or "unknown"),
                    str(body.get("source_record_id") or node),
                    str(body.get("revision") or "r1"),
                    str(body.get("published_at") or expiry),
                    str(body.get("observed_at") or expiry),
                    expiry,
                    canonical(body.get("fields") or body),
                    envelope,
                    self._node_scope(cursor, tenant, node),
                ),
            )
        elif kind == "identity":
            cursor.execute(
                "INSERT INTO identity_candidates VALUES "
                "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'VALID')",
                (
                    tenant,
                    node,
                    str(body.get("kind") or "organization"),
                    str(body.get("namespace") or "UNKNOWN"),
                    str(body.get("jurisdiction") or "US"),
                    str(body.get("value_normalized") or node),
                    body.get("name_key"),
                    body.get("state_code"),
                    body.get("postal"),
                    str(body.get("relationship") or "UNRESOLVED"),
                    None,
                    body.get("observation_id"),
                    envelope,
                ),
            )
        elif kind in {"brief", "score"}:
            cursor.execute(
                "INSERT INTO derivations VALUES (%s,%s,%s,%s,%s,%s,'VALID')",
                (tenant, node, kind, node, payload, expiry),
            )
        elif kind == "clearance":
            cursor.execute(
                "INSERT INTO clearances VALUES (%s,%s,%s,%s,%s,%s,'VALID')",
                (
                    tenant,
                    node,
                    node,
                    nonempty(
                        str(body.get("named_operator") or "unknown"), "named_operator"
                    ),
                    payload,
                    expiry,
                ),
            )
        elif kind == "suppression":
            cursor.execute(
                "INSERT INTO suppressions VALUES (%s,%s,%s,%s,%s,%s,true,%s)",
                (
                    tenant,
                    node,
                    nonempty(str(body.get("subject_key") or node), "subject_key"),
                    nonempty(str(body.get("reason") or "SUPPRESSED"), "reason", 128),
                    expiry,
                    node,
                    envelope,
                ),
            )
        elif kind in {"crm_task", "outcome", "disposition"}:
            cursor.execute(
                "INSERT INTO outcomes VALUES (%s,%s,%s,%s,%s,%s,'VALID')",
                (tenant, node, kind, node, payload, expiry),
            )

    def _revoke_projections(
        self,
        cursor: Any,
        tenant: str,
        node: str,
        kind: str,
        now: datetime,
    ) -> None:
        cursor.execute(
            "UPDATE source_grants SET state='REVOKED' WHERE tenant=%s AND node_id=%s",
            (tenant, node),
        )
        cursor.execute(
            "UPDATE observations SET state='REVOKED' WHERE tenant=%s AND id=%s",
            (tenant, node),
        )
        cursor.execute(
            "UPDATE identity_candidates SET state='REVOKED' WHERE tenant=%s AND id=%s",
            (tenant, node),
        )
        cursor.execute(
            "UPDATE derivations SET state='REVOKED' WHERE tenant=%s AND node_id=%s",
            (tenant, node),
        )
        cursor.execute(
            "UPDATE clearances SET state='REVOKED' WHERE tenant=%s AND node_id=%s",
            (tenant, node),
        )
        cursor.execute(
            "UPDATE outcomes SET state='REVOKED' WHERE tenant=%s AND node_id=%s",
            (tenant, node),
        )
        cursor.execute(
            "UPDATE suppressions SET active=false WHERE tenant=%s AND node_id=%s",
            (tenant, node),
        )
        cursor.execute(
            "UPDATE manual_tasks SET state='REVOKED' WHERE tenant=%s AND id=%s",
            (tenant, node),
        )
        cursor.execute(
            "UPDATE outbox SET status=CASE WHEN status='DISPATCHING' THEN 'DELIVERY_UNKNOWN' ELSE 'CANCELLED' END WHERE tenant=%s AND node_id=%s AND event_type='MANUAL_TASK_READY' AND status IN ('PENDING','LEASED','DISPATCHING')",
            (tenant, node),
        )
        del kind, now

    def _outbox(
        self,
        cursor: Any,
        tenant: str,
        node: str,
        event_type: str,
        payload: Mapping[str, Any],
        now: datetime,
    ) -> None:
        body = {
            "schema": SCHEMA,
            "tenant": tenant,
            "node": node,
            "event_type": event_type,
            "payload": dict(payload),
            "created_at": stamp(now),
            "integrity": "LOCAL_SHA256_UNSIGNED",
        }
        cursor.execute(
            "INSERT INTO outbox (tenant,id,node_id,event_type,payload,created_at,published_at) VALUES (%s,%s,%s,%s,%s,%s,NULL) "
            "ON CONFLICT (tenant, id) DO NOTHING",
            (
                tenant,
                digest(body),
                node,
                event_type,
                canonical(body),
                stamp(now),
            ),
        )


def connect_postgres_ledger(dsn: str) -> PostgresLedger:
    if psycopg is None:
        raise Hold("psycopg is required for the postgres evidence adapter")
    nonempty(dsn, "dsn", 4096)
    connection = psycopg.connect(dsn, connect_timeout=8)
    try:
        verify_runtime_contract(connection)
    except Exception:
        connection.close()
        raise
    return PostgresLedger(connection)


def verify_runtime_contract(connection):
    """Fail admission for privileged roles, incomplete migrations or weakened RLS."""
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT r.rolsuper,r.rolbypassrls,r.rolcreaterole,r.rolcreatedb,r.rolreplication,current_user=session_user FROM pg_roles r WHERE r.rolname=current_user"
            )
            role = cursor.fetchone()
            if not role or any(role[:5]) or not role[5]:
                raise Hold("RUNTIME_ROLE_PRIVILEGED")
            cursor.execute(
                "SELECT 1 FROM pg_roles WHERE pg_has_role(current_user,oid,'MEMBER') AND (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication) LIMIT 1"
            )
            if cursor.fetchone():
                raise Hold("RUNTIME_ROLE_PRIVILEGED_MEMBERSHIP")
            cursor.execute(
                "SELECT has_schema_privilege(current_user,'public','CREATE')"
            )
            if cursor.fetchone()[0]:
                raise Hold("RUNTIME_SCHEMA_CREATE_DENIED")
            cursor.execute(
                "SELECT schema_version FROM david_dealdesk_schema WHERE schema_name='evidence'"
            )
            if cursor.fetchone() != (2,):
                raise Hold("EVIDENCE_SCHEMA_VERSION_MISMATCH")
            for table in EVIDENCE_TABLES:
                cursor.execute(
                    "SELECT c.relrowsecurity,pg_has_role(current_user,c.relowner,'MEMBER'),has_table_privilege(current_user,c.oid,'SELECT'),has_table_privilege(current_user,c.oid,'INSERT'),has_table_privilege(current_user,c.oid,'UPDATE'),has_table_privilege(current_user,c.oid,'TRUNCATE') FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname=%s AND c.relkind='r'",
                    (table,),
                )
                contract = cursor.fetchone()
                if contract != (
                    True,
                    False,
                    True,
                    True,
                    "UPDATE" in RUNTIME_TABLE_PRIVILEGES[table],
                    False,
                ):
                    raise Hold("EVIDENCE_TABLE_PRIVILEGE_MISMATCH")
                for privilege in (
                    "DELETE",
                    "REFERENCES",
                    "TRIGGER",
                    "SELECT WITH GRANT OPTION",
                    "INSERT WITH GRANT OPTION",
                    "UPDATE WITH GRANT OPTION",
                ):
                    cursor.execute(
                        "SELECT has_table_privilege(current_user,to_regclass(%s),%s)",
                        (f"public.{table}", privilege),
                    )
                    if cursor.fetchone()[0]:
                        raise Hold("EVIDENCE_TABLE_EXCESS_PRIVILEGE")
                cursor.execute(
                    "SELECT polcmd,polpermissive,polroles,pg_get_expr(polqual,polrelid),pg_get_expr(polwithcheck,polrelid) FROM pg_policy WHERE polrelid=to_regclass(%s)",
                    (f"public.{table}",),
                )
                policies = cursor.fetchall()
                expected = "(tenant = current_setting('david.tenant'::text, true))"
                if len(policies) != 1 or policies[0] != (
                    "*",
                    True,
                    [0],
                    expected,
                    expected,
                ):
                    raise Hold("EVIDENCE_RLS_POLICY_MISMATCH")
            required = {
                "evidence_nodes": {"scope_id", "decision_epoch"},
                "outbox": {"status", "fencing_token", "lease_until", "worker"},
                "manual_tasks": {"idempotency_key", "request_digest"},
                "source_health": {"record", "revision"},
            }
            for table, columns in required.items():
                cursor.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",
                    (table,),
                )
                if not columns <= {row[0] for row in cursor.fetchall()}:
                    raise Hold("EVIDENCE_SCHEMA_INCOMPLETE")
            cursor.execute(
                "SELECT pg_get_constraintdef(oid),convalidated FROM pg_constraint WHERE conrelid='identity_candidates'::regclass AND conname='identity_candidates_candidates_are_not_canonical'"
            )
            constraint = cursor.fetchone()
            if (
                not constraint
                or not constraint[1]
                or "SAME_ORGANIZATION_ID" not in constraint[0]
                or "kind = 'organization'" not in constraint[0]
                or "SAME_NON_ORGANIZATION_RECORD" in constraint[0]
            ):
                raise Hold("IDENTITY_CONSTRAINT_MISMATCH")
            cursor.execute(
                "SELECT convalidated FROM pg_constraint WHERE conrelid='identity_candidates'::regclass AND conname='identity_candidates_typed_namespace'"
            )
            if cursor.fetchone() != (True,):
                raise Hold("IDENTITY_NAMESPACE_CONSTRAINT_MISSING")
    return {
        "schema_version": 2,
        "runtime_role": "NONOWNER_NONBYPASS",
        "tables_checked": len(EVIDENCE_TABLES),
    }
