"""Real runtime-role PostgreSQL source health; no fake database or SQLite."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest
import uuid
import psycopg
from app.domain.david_postgres import connect_postgres_ledger
from app.domain.david_reference import Hold
from app.domain.source_health_store import SourceHealthStore
from app.domain.source_policy import SourceHealthRecord
from tests.postgres_support import bootstrap_test_database


class SourceHealthPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = bootstrap_test_database()

    def setUp(self):
        self.tenant = "source-health-synthetic-" + uuid.uuid4().hex
        self.ledger = connect_postgres_ledger(self.dsn)
        self.addCleanup(self.ledger.close)
        self.store = SourceHealthStore(self.ledger)
        self.now = datetime.now(timezone.utc)
        self.success = SourceHealthRecord(
            "dol-form5500-benefit-timing", credential_state="NOT_REQUIRED",
            transport_state="SUCCESS", schema_state="SUPPORTED", integrity_state="VERIFIED_SIGNATURE",
            completeness_state="COMPLETE", last_attempt_at=self.now, snapshot_revision="a" * 40,
            snapshot_observed_at=self.now - timedelta(hours=1), snapshot_expires_at=self.now + timedelta(days=1))

    def test_actual_runtime_role_persists_across_new_connection(self):
        self.store.record_attempt(self.tenant, self.success)
        other = connect_postgres_ledger(self.dsn)
        try:
            value = SourceHealthStore(other).read(self.tenant, self.success.source_id)
            self.assertEqual(value.last_success_at, self.now)
            self.assertEqual(value.snapshot_revision, "a" * 40)
            with other.transaction(self.tenant) as cursor:
                cursor.execute("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user")
                self.assertEqual(cursor.fetchone(), (False, False))
        finally:
            other.close()

    def test_failure_preserves_success_and_snapshot_but_stores_failure(self):
        self.store.record_attempt(self.tenant, self.success)
        failed = SourceHealthRecord(self.success.source_id, transport_state="UNAVAILABLE", last_attempt_at=self.now + timedelta(minutes=1))
        result = self.store.record_attempt(self.tenant, failed)
        self.assertEqual(result, self.store.read(self.tenant, self.success.source_id))
        self.assertEqual(result.last_success_at, self.now)
        self.assertEqual(result.last_attempt_at, failed.last_attempt_at)
        self.assertEqual(result.transport_state, "UNAVAILABLE")
        self.assertEqual(result.snapshot_revision, "a" * 40)

    def test_rls_withholds_other_tenant_even_without_application_filter(self):
        self.store.record_attempt(self.tenant, self.success)
        with self.ledger.transaction(self.tenant + "-other") as cursor:
            cursor.execute("SELECT record FROM source_health WHERE tenant=%s", (self.tenant,))
            self.assertEqual(cursor.fetchall(), [])
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            with self.ledger.transaction(self.tenant + "-other") as cursor:
                cursor.execute("INSERT INTO source_health(tenant,source_id,revision,record) VALUES(%s,'foreign',0,'{}')", (self.tenant,))

    def test_old_attempt_cannot_overwrite_new_success(self):
        self.store.record_attempt(self.tenant, self.success)
        with self.assertRaisesRegex(Hold, "SOURCE_ATTEMPT_ORDER"):
            self.store.record_attempt(self.tenant, replace(self.success, last_attempt_at=self.now - timedelta(seconds=1)))
        self.assertEqual(self.store.read(self.tenant, self.success.source_id).last_success_at, self.now)
