"""Postgres evidence adapter for the David kernel.

Implements the same Hold / revoke / verify contracts as the SQLite reference
Ledger. SQLite remains test-only. Integrity stays LOCAL_SHA256_UNSIGNED until
the existing Cosign/receipts path binds it. This adapter never creates schema
objects at runtime.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime
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
)
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "evidence_schema.sql"
DEALDESK_TABLES = ("david_dealdesk_state", "david_dealdesk_events")
CANDIDATE_RELATIONSHIPS = frozenset(
    {"CANDIDATE_REVIEW", "UNRESOLVED", "CONFLICT_REVIEW"}
)


def apply_evidence_schema(connection: Any) -> None:
    """Apply the expand-only evidence SQL. Never drops deal-desk tables."""
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    if any(f"DROP TABLE {name}" in sql or f"DROP TABLE IF EXISTS {name}" in sql
           for name in DEALDESK_TABLES):
        raise Hold("evidence schema must not drop deal-desk tables")
    statements = [part.strip() for part in sql.split(";") if part.strip()]
    with connection.transaction():
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)


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

    def state(self, tenant: str, node: str, now: datetime) -> str:
        with self.transaction(tenant) as cursor:
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
        if any(not self.verify(tenant, item[0]) for item in ancestors):
            return "INTEGRITY_FAILED"
        if any(item[1] != "VALID" for item in ancestors):
            return "REVOKED"
        if any(parse_stamp(item[2]) <= aware(now) for item in ancestors):
            return "STALE"
        return "VALID"

    def append(
        self,
        tenant: str,
        kind: str,
        body: Mapping[str, Any],
        parents: Sequence[str],
        expires_at: datetime,
        now: datetime,
    ) -> str:
        nonempty(tenant, "tenant")
        nonempty(kind, "kind")
        parent_ids = sorted(set(parents))
        if len(parent_ids) != len(parents):
            raise Hold("duplicate dependency")
        if aware(expires_at) <= aware(now):
            raise Hold("node already expired")
        self._reject_canonical_inheritance(kind, body)
        envelope = {
            "schema": SCHEMA,
            "tenant": tenant,
            "kind": kind,
            "body": dict(body),
            "parents": parent_ids,
            "expires_at": stamp(expires_at),
            "integrity": "LOCAL_SHA256_UNSIGNED",
        }
        serialized, node = canonical(envelope), digest(envelope)
        with self.transaction(tenant) as cursor:
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
                if self._state_unlocked(cursor, tenant, parent, now) != "VALID":
                    raise Hold("missing, stale or revoked dependency")
                cursor.execute(
                    "SELECT expires_at FROM evidence_nodes WHERE tenant=%s AND id=%s",
                    (tenant, parent),
                )
                parent_expiry = cursor.fetchone()[0]
                if aware(expires_at) > parse_stamp(parent_expiry):
                    raise Hold("derivation outlives a dependency")
            cursor.execute(
                "INSERT INTO evidence_nodes VALUES (%s,%s,%s,%s,%s,'VALID')",
                (tenant, node, kind, serialized, stamp(expires_at)),
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

    def revoke(self, tenant: str, node: str, reason: str, now: datetime) -> int:
        nonempty(reason, "reason", 128)
        with self.transaction(tenant) as cursor:
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

    def correct(self, tenant: str, node: str, reason: str, now: datetime) -> int:
        """Correction revokes the node and every descendant, including brief/clearance/CRM."""
        return self.revoke(tenant, node, reason or "SOURCE_CORRECTED", now)

    def verify(self, tenant: str, node: str) -> bool:
        with self.transaction(tenant) as cursor:
            return self._verify_unlocked(cursor, tenant, node)

    def put_grant(self, tenant: str, grant: Grant, now: datetime) -> str:
        grant.require("research", now)
        body = {
            "source_id": grant.source_id,
            "policy_revision": grant.policy_revision,
            "review_reference": grant.review_reference,
            "rights": {key: value.value for key, value in grant.rights.items()},
            "allowed_fields": sorted(grant.allowed_fields),
        }
        return self.append(tenant, "grant", body, (), grant.expires_at, now)

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
        if any(not self._verify_unlocked(cursor, tenant, item[0]) for item in ancestors):
            return "INTEGRITY_FAILED"
        if any(item[1] != "VALID" for item in ancestors):
            return "REVOKED"
        if any(parse_stamp(item[2]) <= aware(now) for item in ancestors):
            return "STALE"
        return "VALID"

    def _verify_unlocked(self, cursor: Any, tenant: str, node: str) -> bool:
        cursor.execute(
            "SELECT envelope, kind, expires_at FROM evidence_nodes "
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
                "INSERT INTO source_grants VALUES "
                "(%s,%s,%s,%s,%s,%s,%s,%s,%s,'VALID')",
                (
                    tenant,
                    nonempty(str(body.get("source_id") or node), "source_id"),
                    nonempty(str(body.get("policy_revision") or "unknown"), "policy_revision"),
                    nonempty(str(body.get("review_reference") or "unknown"), "review_reference", 2048),
                    expiry,
                    canonical(body.get("rights") or {}),
                    canonical(body.get("allowed_fields") or []),
                    envelope,
                    node,
                ),
            )
        elif kind in {"source", "observation"}:
            cursor.execute(
                "INSERT INTO observations VALUES "
                "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'VALID')",
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
                    nonempty(str(body.get("named_operator") or "unknown"), "named_operator"),
                    payload,
                    expiry,
                ),
            )
        elif kind == "suppression":
            cursor.execute(
                "INSERT INTO suppressions VALUES "
                "(%s,%s,%s,%s,%s,%s,true,%s)",
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
            "INSERT INTO outbox VALUES (%s,%s,%s,%s,%s,%s,NULL) "
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
    return PostgresLedger(connection)
