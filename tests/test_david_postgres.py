"""Postgres evidence-adapter contracts. SQLite is not used here."""
from __future__ import annotations

import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.domain.david_postgres import (
    DEALDESK_TABLES,
    EVIDENCE_TABLES,
    PostgresLedger,
    SCHEMA_PATH,
    apply_evidence_schema,
)
from app.domain.david_reference import Grant, Hold, Identifier, Verdict, aware

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 11, 12, tzinfo=timezone.utc)
DAY = timedelta(days=1)
DSN = os.environ.get("DAVID_EVIDENCE_TEST_DSN")


def _require_dsn() -> str:
    if DSN:
        return DSN
    if os.environ.get("CI"):
        raise RuntimeError("DAVID_EVIDENCE_TEST_DSN is required in CI")
    raise unittest.SkipTest("DAVID_EVIDENCE_TEST_DSN is not configured")


def _connect():
    import psycopg

    connection = psycopg.connect(_require_dsn(), connect_timeout=8)
    connection.autocommit = True
    return connection


def _apply_expand(connection) -> None:
    dealdesk = (ROOT / "app" / "dealdesk_schema.sql").read_text(encoding="utf-8")
    statements = [part.strip() for part in dealdesk.split(";") if part.strip()]
    with connection.transaction():
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
    apply_evidence_schema(connection)


def _truncate(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "TRUNCATE "
            + ", ".join(EVIDENCE_TABLES)
            + " RESTART IDENTITY CASCADE"
        )


class EvidenceSchemaExpandTests(unittest.TestCase):
    def test_sql_is_expand_only_and_keeps_dealdesk_tables(self):
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        dealdesk_sql = (ROOT / "app" / "dealdesk_schema.sql").read_text(encoding="utf-8")
        for table in EVIDENCE_TABLES:
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", sql)
        for table in DEALDESK_TABLES:
            self.assertNotIn(f"DROP TABLE {table}", sql)
            self.assertNotIn(f"DROP TABLE IF EXISTS {table}", sql)
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", dealdesk_sql)
        self.assertNotIn("DROP TABLE david_dealdesk_state", sql)
        self.assertNotIn("DROP TABLE david_dealdesk_events", sql)
        self.assertIn("VALUES ('evidence', 1)", sql)
        self.assertIn("VALUES ('dealdesk', 2)", dealdesk_sql)
        self.assertIn("identity_candidates_candidates_are_not_canonical", sql)
        self.assertIn("ENABLE ROW LEVEL SECURITY", sql)

    def test_runtime_adapter_does_not_migrate(self):
        source = (ROOT / "app" / "domain" / "david_postgres.py").read_text(encoding="utf-8")
        self.assertNotIn("CREATE TABLE", source.split("apply_evidence_schema", 1)[0])
        self.assertIn("never creates schema", source)


@unittest.skipUnless(DSN or os.environ.get("CI"), "postgres DSN not configured")
class PostgresLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = _connect()
        _apply_expand(cls.conn)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def setUp(self):
        _truncate(self.conn)
        self.ledger = PostgresLedger(self.conn)

    def add(self, kind="source", parents=(), body=None, tenant="test-tenant", expiry=None):
        return self.ledger.append(
            tenant,
            kind,
            body or {"synthetic": True},
            parents,
            expiry or NOW + DAY,
            NOW,
        )

    def test_idempotent_ingestion(self):
        self.assertEqual(self.add(), self.add())
        with self.conn.cursor() as cursor:
            cursor.execute("SELECT set_config('david.tenant', %s, true)", ("test-tenant",))
            cursor.execute("SELECT COUNT(*) FROM evidence_nodes")
            self.assertEqual(cursor.fetchone()[0], 1)

    def test_restart_preserves_evidence(self):
        node = self.add()
        restarted = PostgresLedger(self.conn)
        self.assertEqual(restarted.state("test-tenant", node, NOW), "VALID")
        self.assertTrue(restarted.verify("test-tenant", node))

    def test_cross_tenant_dependency_denied(self):
        node = self.add()
        with self.assertRaises(Hold):
            self.add("brief", (node,), tenant="other-tenant")
        self.assertEqual(self.ledger.state("other-tenant", node, NOW), "MISSING")

    def test_unknown_dependency_rolls_back(self):
        with self.assertRaises(Hold):
            self.add("brief", ("missing",))
        with self.conn.cursor() as cursor:
            cursor.execute("SELECT set_config('david.tenant', %s, true)", ("test-tenant",))
            cursor.execute("SELECT COUNT(*) FROM evidence_nodes")
            self.assertEqual(cursor.fetchone()[0], 0)

    def test_correction_revokes_brief_clearance_and_crm_task(self):
        source = self.add()
        identity = self.add("identity", (source,), body={
            "relationship": "CANDIDATE_REVIEW",
            "canonical_organization_id": None,
            "kind": "organization",
            "namespace": "SEC_CIK",
            "jurisdiction": "US",
            "value_normalized": "0000000123",
        })
        brief = self.add("brief", (identity,))
        clearance = self.add("clearance", (brief,), body={"named_operator": "David"})
        crm = self.add("crm_task", (clearance,), body={"task": "follow-up"})
        self.assertEqual(
            self.ledger.correct("test-tenant", source, "SOURCE_CORRECTED", NOW),
            5,
        )
        for node in (source, identity, brief, clearance, crm):
            self.assertEqual(self.ledger.state("test-tenant", node, NOW), "REVOKED")
        with self.conn.cursor() as cursor:
            cursor.execute("SELECT set_config('david.tenant', %s, true)", ("test-tenant",))
            cursor.execute("SELECT state FROM derivations WHERE id=%s", (brief,))
            self.assertEqual(cursor.fetchone()[0], "REVOKED")
            cursor.execute("SELECT state FROM clearances WHERE id=%s", (clearance,))
            self.assertEqual(cursor.fetchone()[0], "REVOKED")
            cursor.execute("SELECT state FROM outcomes WHERE id=%s", (crm,))
            self.assertEqual(cursor.fetchone()[0], "REVOKED")
            cursor.execute(
                "SELECT published_at FROM outbox WHERE node_id=%s AND event_type=%s",
                (source, "EVIDENCE_REVOKED"),
            )
            self.assertIsNone(cursor.fetchone()[0])
        self.assertEqual(
            self.ledger.revoke("test-tenant", source, "RETRY", NOW),
            0,
        )

    def test_candidates_never_inherit_canonical_identity(self):
        source = self.add()
        with self.assertRaises(Hold):
            self.add(
                "identity",
                (source,),
                body={
                    "relationship": "CANDIDATE_REVIEW",
                    "canonical_organization_id": "org-canonical",
                    "kind": "organization",
                    "namespace": "SEC_CIK",
                    "jurisdiction": "US",
                    "value_normalized": "0000000123",
                },
            )
        left = [Identifier("organization", "SEC_CIK", "US", "123")]
        node = self.ledger.remember_identity(
            "test-tenant",
            left,
            [],
            same_name_state_postal=True,
            parents=(source,),
            expires_at=NOW + DAY,
            now=NOW,
        )
        with self.conn.cursor() as cursor:
            cursor.execute("SELECT set_config('david.tenant', %s, true)", ("test-tenant",))
            cursor.execute(
                "SELECT relationship, canonical_organization_id FROM identity_candidates "
                "WHERE id=%s",
                (node,),
            )
            relationship_value, canonical_id = cursor.fetchone()
        self.assertEqual(relationship_value, "CANDIDATE_REVIEW")
        self.assertIsNone(canonical_id)

    def test_naive_timestamp_denied(self):
        with self.assertRaises(Hold):
            aware(datetime(2026, 9, 11))
        with self.assertRaises(Hold):
            self.ledger.append(
                "test-tenant",
                "source",
                {"synthetic": True},
                (),
                datetime(2026, 9, 12),
                NOW,
            )

    def test_child_cannot_outlive_parent(self):
        parent = self.add()
        with self.assertRaises(Hold):
            self.add("brief", (parent,), expiry=NOW + 2 * DAY)

    def test_tampered_content_fails_integrity(self):
        node = self.add()
        with self.conn.cursor() as cursor:
            cursor.execute("SELECT set_config('david.tenant', %s, true)", ("test-tenant",))
            cursor.execute(
                "UPDATE evidence_nodes SET envelope=%s WHERE id=%s",
                ("{}", node),
            )
        self.assertFalse(self.ledger.verify("test-tenant", node))
        self.assertEqual(
            self.ledger.state("test-tenant", node, NOW),
            "INTEGRITY_FAILED",
        )

    def test_unsigned_status_not_confused_with_signature(self):
        node = self.add()
        with self.conn.cursor() as cursor:
            cursor.execute("SELECT set_config('david.tenant', %s, true)", ("test-tenant",))
            cursor.execute(
                "SELECT envelope FROM evidence_nodes WHERE id=%s",
                (node,),
            )
            envelope = json.loads(cursor.fetchone()[0])
        self.assertEqual(envelope["integrity"], "LOCAL_SHA256_UNSIGNED")

    def test_put_grant_and_observation_time_order(self):
        grant = Grant(
            "synthetic-source",
            "review-v1",
            "test-review-only",
            NOW + 30 * DAY,
            {
                "collect": Verdict.ALLOW,
                "research": Verdict.ALLOW,
                "public_display": Verdict.REVIEW,
                "redistribute": Verdict.DENY,
                "train": Verdict.DENY,
            },
            frozenset({"organization_name", "state"}),
        )
        node = self.ledger.put_grant("test-tenant", grant, NOW)
        self.assertEqual(self.ledger.state("test-tenant", node, NOW), "VALID")
        with self.conn.cursor() as cursor:
            cursor.execute("SELECT set_config('david.tenant', %s, true)", ("test-tenant",))
            cursor.execute("SELECT source_id FROM source_grants WHERE node_id=%s", (node,))
            self.assertEqual(cursor.fetchone()[0], "synthetic-source")


if __name__ == "__main__":
    unittest.main(verbosity=2)
