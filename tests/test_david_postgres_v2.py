"""Real PostgreSQL role, concurrency, crash recovery and disposable restore proofs.

All records and role credentials in this module are synthetic test fixtures.
Thread ordering uses synchronization events plus observed PostgreSQL lock waits.
"""

from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from app.domain.david_postgres import (
    PostgresLedger,
    connect_postgres_ledger,
    verify_runtime_contract,
    apply_evidence_schema,
    SCHEMA_PATH,
)
from app.domain.david_reference import (
    Grant,
    Observation,
    Verdict,
    Hold,
    SCHEMA,
    canonical,
    digest,
    stamp,
)
from tests.postgres_support import (
    bootstrap_test_database,
    admin_connection,
    admin_dsn,
    ROLE,
    ROOT,
)

NOW = datetime(2026, 9, 19, 12, tzinfo=timezone.utc)
EXPIRY = NOW + timedelta(days=1)


def seed(ledger, tenant, scope="work"):
    source = ledger.append(
        tenant, "source", {"synthetic": True}, [], EXPIRY, NOW, scope_id=scope
    )
    brief = ledger.append(
        tenant, "brief", {"synthetic": True}, [source], EXPIRY, NOW, scope_id=scope
    )
    clearance = ledger.append(
        tenant,
        "clearance",
        {
            "action": "MANUAL_RESEARCH_TASK",
            "named_operator": "synthetic-operator",
            "operator_policy_digest": "synthetic-policy",
        },
        [brief],
        EXPIRY,
        NOW,
        scope_id=scope,
    )
    body = {
        "operator": "synthetic-operator",
        "operator_policy_digest": "synthetic-policy",
        "task_type": "VERIFY_SOURCE",
        "contact_permission": "NOT_GRANTED",
    }
    return source, brief, clearance, body


def fixture_grant():
    return Grant(
        "synthetic-source",
        "review-1",
        "SYNTHETIC_TEST_ONLY",
        EXPIRY,
        {"collect": Verdict.ALLOW, "research": Verdict.ALLOW},
        frozenset({"organization_name"}),
    )


def fixture_observation(grant):
    return Observation(
        grant.source_id,
        "synthetic-record",
        "revision-1",
        NOW,
        NOW,
        EXPIRY,
        {"organization_name": "SYNTHETIC Organization"},
    ).body(grant, NOW)


class PostgresV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = bootstrap_test_database()

    def setUp(self):
        self.tenant = "synthetic-v2-" + uuid4().hex
        self.ledger = connect_postgres_ledger(self.dsn)
        self.addCleanup(self.ledger.close)

    def second(self):
        ledger = connect_postgres_ledger(self.dsn)
        self.addCleanup(ledger.close)
        return ledger

    def task(self):
        source, brief, clearance, body = seed(self.ledger, self.tenant)
        epoch = self.ledger.decision_epoch(self.tenant, "work")
        task = self.ledger.create_manual_task(
            self.tenant, "work", clearance, body, "task-key", epoch, EXPIRY, NOW
        )
        return source, brief, clearance, body, task, epoch

    def wait_for_blocked(self, pid):
        deadline = time.monotonic() + 5
        with admin_connection() as connection:
            while time.monotonic() < deadline:
                row = connection.execute(
                    "SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s", (pid,)
                ).fetchone()
                if row and row[0] == "Lock":
                    return
                threading.Event().wait(0.01)
        self.fail("The competing connection never reached a PostgreSQL lock wait")

    def interleave(
        self,
        first,
        second,
        first_operation,
        second_operation,
        lock_method="_lock_scope",
    ):
        locked = threading.Event()
        release = threading.Event()
        original = getattr(first, lock_method)
        once = False

        def hold(*args, **kwargs):
            nonlocal once
            value = original(*args, **kwargs)
            if not once:
                once = True
                locked.set()
                if not release.wait(8):
                    raise RuntimeError("Test synchronization timed out")
            return value

        setattr(first, lock_method, hold)
        with ThreadPoolExecutor(max_workers=2) as workers:
            one = workers.submit(first_operation)
            self.assertTrue(locked.wait(5))
            two = workers.submit(second_operation)
            try:
                self.wait_for_blocked(second.conn.info.backend_pid)
            finally:
                release.set()
            result = one.result(timeout=8)
            try:
                other = two.result(timeout=8)
            except Hold as exc:
                other = str(exc)
        setattr(first, lock_method, original)
        return result, other

    def test_actual_runtime_is_nonowner_and_tenant_context_resets(self):
        self.assertEqual(
            verify_runtime_contract(self.ledger.conn)["runtime_role"],
            "NONOWNER_NONBYPASS",
        )
        source, *_ = seed(self.ledger, self.tenant)
        with self.ledger.conn.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM evidence_nodes")
            self.assertEqual(cursor.fetchone()[0], 0)
        with self.ledger.transaction(self.tenant) as cursor:
            cursor.execute("SELECT count(*) FROM evidence_nodes WHERE id=%s", (source,))
            self.assertEqual(cursor.fetchone()[0], 1)
        with self.ledger.transaction("other-" + self.tenant) as cursor:
            cursor.execute("SELECT count(*) FROM evidence_nodes")
            self.assertEqual(cursor.fetchone()[0], 0)
            cursor.execute(
                "UPDATE evidence_nodes SET state='REVOKED' WHERE id=%s", (source,)
            )
            self.assertEqual(cursor.rowcount, 0)
        self.assertEqual(self.ledger.state(self.tenant, source, NOW), "VALID")

    def test_scope_filtered_read_rejects_foreign_node_before_second_scope_lock(self):
        foreign, *_ = seed(self.ledger, self.tenant, "foreign-work")
        reader = self.second()
        with ThreadPoolExecutor(max_workers=1) as workers:
            with self.ledger.scope_read(self.tenant, "foreign-work"):
                pending = workers.submit(reader.get_node, self.tenant, foreign, NOW, scope_id="work")
                self.assertIsNone(pending.result(timeout=3))

    def test_missing_tenant_insert_and_cross_tenant_write_denied_by_sql(self):
        source, *_ = seed(self.ledger, self.tenant)
        for tenant in (None, "other-" + self.tenant):
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with (
                    self.ledger.conn.transaction(),
                    self.ledger.conn.cursor() as cursor,
                ):
                    if tenant:
                        cursor.execute(
                            "SELECT set_config('david.tenant',%s,true)", (tenant,)
                        )
                    cursor.execute(
                        "INSERT INTO decision_scopes (tenant,scope_id) VALUES (%s,'forged')",
                        (self.tenant,),
                    )
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            with self.ledger.transaction("other-" + self.tenant) as cursor:
                cursor.execute(
                    "INSERT INTO evidence_edges (tenant,parent,child) VALUES (%s,%s,%s)",
                    ("other-" + self.tenant, source, source),
                )

    def test_admin_connection_is_rejected(self):
        with self.assertRaisesRegex(Hold, "RUNTIME_ROLE_PRIVILEGED"):
            connect_postgres_ledger(admin_dsn())

    def test_wrong_grants_and_schema_version_are_rejected(self):
        with admin_connection() as admin:
            admin.execute(
                sql.SQL("GRANT DELETE ON evidence_nodes TO {}").format(
                    sql.Identifier(ROLE)
                )
            )
            try:
                with self.assertRaisesRegex(Hold, "EXCESS_PRIVILEGE"):
                    connect_postgres_ledger(self.dsn)
            finally:
                admin.execute(
                    sql.SQL("REVOKE DELETE ON evidence_nodes FROM {}").format(
                        sql.Identifier(ROLE)
                    )
                )
            admin.execute(
                "UPDATE david_dealdesk_schema SET schema_version=99 WHERE schema_name='evidence'"
            )
            try:
                with self.assertRaisesRegex(Hold, "VERSION_MISMATCH"):
                    connect_postgres_ledger(self.dsn)
            finally:
                admin.execute(
                    "UPDATE david_dealdesk_schema SET schema_version=2 WHERE schema_name='evidence'"
                )

    def test_sql_nonorganization_identifier_cannot_populate_canonical_organization(
        self,
    ):
        for kind, namespace in (
            ("parcel", "PARCEL"),
            ("facility", "EPA_FRS"),
            ("carrier", "USDOT"),
            ("organization", "PARCEL"),
        ):
            with (
                self.subTest(kind=kind, namespace=namespace),
                self.assertRaises(psycopg.errors.CheckViolation),
            ):
                with self.ledger.transaction(self.tenant) as cursor:
                    cursor.execute(
                        "INSERT INTO identity_candidates (tenant,id,kind,namespace,jurisdiction,value_normalized,relationship,canonical_organization_id,envelope,state) VALUES (%s,%s,%s,%s,'US','synthetic','SAME_ORGANIZATION_ID','forged-org','{}','VALID')",
                        (self.tenant, uuid4().hex, kind, namespace),
                    )

    def test_correction_blocks_later_derivation_on_second_connection(self):
        source, *_ = seed(self.ledger, self.tenant)
        second = self.second()
        epoch = self.ledger.decision_epoch(self.tenant, "work")
        _, other = self.interleave(
            self.ledger,
            second,
            lambda: self.ledger.correct(self.tenant, source, "SOURCE_CORRECTED", NOW),
            lambda: second.append(
                self.tenant,
                "brief",
                {"later": True},
                [source],
                EXPIRY,
                NOW,
                scope_id="work",
                expected_epoch=epoch,
            ),
        )
        self.assertEqual(other, "DECISION_EPOCH_CONFLICT")

    def test_committed_derivation_is_included_in_concurrent_correction(self):
        source, *_ = seed(self.ledger, self.tenant)
        second = self.second()
        child, count = self.interleave(
            self.ledger,
            second,
            lambda: self.ledger.append(
                self.tenant,
                "brief",
                {"racing": True},
                [source],
                EXPIRY,
                NOW,
                scope_id="work",
            ),
            lambda: second.correct(self.tenant, source, "SOURCE_CORRECTED", NOW),
        )
        self.assertGreaterEqual(count, 4)
        self.assertEqual(second.state(self.tenant, child, NOW), "REVOKED")

    def test_correction_blocks_racing_task_creation(self):
        source, brief, clearance, body = seed(self.ledger, self.tenant)
        epoch = self.ledger.decision_epoch(self.tenant, "work")
        second = self.second()
        _, other = self.interleave(
            self.ledger,
            second,
            lambda: self.ledger.correct(self.tenant, source, "SOURCE_CORRECTED", NOW),
            lambda: second.create_manual_task(
                self.tenant, "work", clearance, body, "race", epoch, EXPIRY, NOW
            ),
        )
        self.assertEqual(other, "DECISION_EPOCH_CONFLICT")

    def test_new_evidence_stales_action_but_unrelated_scope_does_not(self):
        _, _, clearance, _, task, epoch = self.task()
        self.ledger.append(
            self.tenant,
            "source",
            {"other": True},
            [],
            EXPIRY,
            NOW,
            scope_id="unrelated",
        )
        self.assertEqual(self.ledger.state(self.tenant, task, NOW), "VALID")
        self.ledger.append(
            self.tenant, "source", {"new": True}, [], EXPIRY, NOW, scope_id="work"
        )
        self.assertEqual(self.ledger.state(self.tenant, clearance, NOW), "STALE")
        self.assertEqual(self.ledger.state(self.tenant, task, NOW), "STALE")
        self.assertIsNone(
            self.ledger.claim_outbox(self.tenant, "synthetic-worker", NOW)
        )

    def test_task_idempotency_atomic_outbox_and_key_conflict(self):
        _, _, clearance, body, task, epoch = self.task()
        self.assertEqual(
            task,
            self.ledger.create_manual_task(
                self.tenant, "work", clearance, body, "task-key", epoch, EXPIRY, NOW
            ),
        )
        with self.assertRaisesRegex(Hold, "IDEMPOTENCY_KEY_CONFLICT"):
            self.ledger.create_manual_task(
                self.tenant,
                "work",
                clearance,
                {**body, "task_type": "different"},
                "task-key",
                epoch,
                EXPIRY,
                NOW,
            )
        with self.ledger.transaction(self.tenant) as cursor:
            cursor.execute(
                "SELECT count(*) FROM outbox WHERE event_type='MANUAL_TASK_READY'"
            )
            self.assertEqual(cursor.fetchone()[0], 1)

    def test_outbox_insert_failure_rolls_back_task_and_evidence(self):
        _, _, clearance, body = seed(self.ledger, self.tenant)
        epoch = self.ledger.decision_epoch(self.tenant, "work")
        original = self.ledger._outbox

        def fail(cursor, tenant, node, event, *args):
            if event == "MANUAL_TASK_READY":
                raise RuntimeError("synthetic interrupted transaction")
            return original(cursor, tenant, node, event, *args)

        self.ledger._outbox = fail
        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            self.ledger.create_manual_task(
                self.tenant, "work", clearance, body, "failed", epoch, EXPIRY, NOW
            )
        with self.ledger.transaction(self.tenant) as cursor:
            cursor.execute("SELECT count(*) FROM manual_tasks")
            self.assertEqual(cursor.fetchone()[0], 0)
            cursor.execute(
                "SELECT count(*) FROM evidence_nodes WHERE kind='manual_task'"
            )
            self.assertEqual(cursor.fetchone()[0], 0)

    def test_two_workers_one_claim_and_fencing_rejects_stale_holder(self):
        self.task()
        second = self.second()
        one, two = self.interleave(
            self.ledger,
            second,
            lambda: self.ledger.claim_outbox(self.tenant, "worker-one", NOW, 1),
            lambda: second.claim_outbox(self.tenant, "worker-two", NOW, 1),
        )
        self.assertIsNotNone(one)
        self.assertIsNone(two)
        replacement = second.claim_outbox(
            self.tenant, "worker-two", NOW + timedelta(seconds=2)
        )
        self.assertEqual(replacement["fencing_token"], one["fencing_token"] + 1)
        with self.assertRaisesRegex(Hold, "LEASE_CONFLICT"):
            self.ledger.begin_outbox_dispatch(
                self.tenant,
                one["id"],
                one["fencing_token"],
                NOW + timedelta(seconds=2),
                lambda body: True,
            )

    def test_current_policy_rechecked_before_dispatch_and_unknown_not_retried(self):
        self.task()
        item = self.ledger.claim_outbox(self.tenant, "worker", NOW, 1)
        with self.assertRaisesRegex(Hold, "AUTHORIZATION_DENIED"):
            self.ledger.begin_outbox_dispatch(
                self.tenant, item["id"], item["fencing_token"], NOW, lambda body: False
            )
        self.assertEqual(
            self.ledger.begin_outbox_dispatch(
                self.tenant, item["id"], item["fencing_token"], NOW, lambda body: True
            ),
            "DISPATCHING",
        )
        self.assertIsNone(
            self.ledger.claim_outbox(
                self.tenant, "replacement", NOW + timedelta(seconds=2)
            )
        )
        with self.ledger.transaction(self.tenant) as cursor:
            cursor.execute("SELECT status FROM outbox WHERE id=%s", (item["id"],))
            self.assertEqual(cursor.fetchone()[0], "DELIVERY_UNKNOWN")

    def test_correction_before_dispatch_cancels_lease(self):
        source, *_ = self.task()
        item = self.ledger.claim_outbox(self.tenant, "worker", NOW)
        self.ledger.correct(self.tenant, source, "SOURCE_CORRECTED", NOW)
        with self.assertRaisesRegex(Hold, "LEASE_CONFLICT"):
            self.ledger.begin_outbox_dispatch(
                self.tenant, item["id"], item["fencing_token"], NOW, lambda body: True
            )
        with self.ledger.transaction(self.tenant) as cursor:
            cursor.execute("SELECT status FROM outbox WHERE id=%s", (item["id"],))
            self.assertEqual(cursor.fetchone()[0], "CANCELLED")

    def test_correction_during_dispatch_records_unknown(self):
        source, *_ = self.task()
        item = self.ledger.claim_outbox(self.tenant, "worker", NOW)
        self.ledger.begin_outbox_dispatch(
            self.tenant, item["id"], item["fencing_token"], NOW, lambda body: True
        )
        self.ledger.correct(self.tenant, source, "SOURCE_CORRECTED", NOW)
        with self.ledger.transaction(self.tenant) as cursor:
            cursor.execute("SELECT status FROM outbox WHERE id=%s", (item["id"],))
            self.assertEqual(cursor.fetchone()[0], "DELIVERY_UNKNOWN")

    def test_grant_revoke_covers_existing_and_previously_unseen_scopes(self):
        grant = fixture_grant()
        body = fixture_observation(grant)
        a = self.ledger.admit_observation(self.tenant, "a", grant, body, EXPIRY, NOW)
        b = self.ledger.admit_observation(self.tenant, "b", grant, body, EXPIRY, NOW)
        second = self.second()
        _, other = self.interleave(
            self.ledger,
            second,
            lambda: self.ledger.revoke_grant(
                self.tenant,
                grant.source_id,
                grant.policy_revision,
                "GRANT_WITHDRAWN",
                NOW,
            ),
            lambda: second.admit_observation(
                self.tenant, "never-before-seen", grant, body, EXPIRY, NOW
            ),
            "_lock_grant",
        )
        self.assertEqual(other, "SOURCE_GRANT_REVOKED")
        for node in (a, b):
            self.assertEqual(second.state(self.tenant, node, NOW), "REVOKED")
        with self.assertRaisesRegex(Hold, "SOURCE_GRANT_REVOKED"):
            second.put_grant(self.tenant, grant, NOW, scope_id="another-new")

    def test_suppression_is_durable_and_prevents_new_action(self):
        _, _, clearance, body, task, epoch = self.task()
        self.ledger.suppress(
            self.tenant, "work", "OPERATOR_SUPPRESSION", NOW, expected_epoch=epoch
        )
        second = self.second()
        self.assertEqual(second.state(self.tenant, task, NOW), "REVOKED")
        with self.assertRaisesRegex(Hold, "SCOPE_SUPPRESSED"):
            second.append(
                self.tenant, "source", {"later": True}, [], EXPIRY, NOW, scope_id="work"
            )

    def test_migration_failure_rolls_back_and_reapply_preserves_envelope(self):
        source, *_ = seed(self.ledger, self.tenant)
        before = self.ledger.get_node(self.tenant, source, NOW)
        with admin_connection() as admin:
            with self.assertRaises(psycopg.errors.DivisionByZero):
                with admin.transaction():
                    admin.execute(
                        "UPDATE david_dealdesk_schema SET schema_version=999 WHERE schema_name='evidence'; SELECT 1/0",
                        prepare=False,
                    )
            self.assertEqual(
                admin.execute(
                    "SELECT schema_version FROM david_dealdesk_schema WHERE schema_name='evidence'"
                ).fetchone(),
                (2,),
            )
            apply_evidence_schema(admin)
        self.assertEqual(before, self.ledger.get_node(self.tenant, source, NOW))

    def test_v1_envelope_remains_verifiable_and_exact_retry_keeps_old_hash(self):
        # V1 writer inserts only the original columns. V2 schema defaults are
        # compatible, and the old serialized content is never rewritten.
        old = {
            "schema": SCHEMA,
            "tenant": self.tenant,
            "kind": "source",
            "body": {"synthetic": "v1"},
            "parents": [],
            "expires_at": stamp(EXPIRY),
            "integrity": "LOCAL_SHA256_UNSIGNED",
        }
        node = digest(old)
        with self.ledger.transaction(self.tenant) as cursor:
            cursor.execute(
                "INSERT INTO evidence_nodes (tenant,id,kind,envelope,expires_at,state) VALUES (%s,%s,'source',%s,%s,'VALID')",
                (self.tenant, node, canonical(old), stamp(EXPIRY)),
            )
        self.assertTrue(self.ledger.verify(self.tenant, node))
        self.assertEqual(
            self.ledger.append(self.tenant, "source", old["body"], [], EXPIRY, NOW),
            node,
        )
        with self.ledger.transaction(self.tenant) as cursor:
            cursor.execute(
                "SELECT envelope FROM evidence_nodes WHERE tenant=%s AND id=%s",
                (self.tenant, node),
            )
            self.assertEqual(cursor.fetchone()[0], canonical(old))

    def test_migration_refuses_future_version_without_downgrade(self):
        with admin_connection() as admin:
            # Uncommitted setup is invisible to other tests. The error aborts
            # this entire transaction, retaining the current deployed marker.
            with self.assertRaisesRegex(
                psycopg.errors.RaiseException, "VERSION_MISMATCH"
            ):
                with admin.transaction():
                    admin.execute(
                        "UPDATE david_dealdesk_schema SET schema_version=99 WHERE schema_name='evidence'"
                    )
                    apply_evidence_schema(admin)
            self.assertEqual(
                admin.execute(
                    "SELECT schema_version FROM david_dealdesk_schema WHERE schema_name='evidence'"
                ).fetchone(),
                (2,),
            )

    def test_fresh_process_crash_preserves_evidence_outbox_and_suppression(self):
        env = {**os.environ, "TEST_RUNTIME_DSN": self.dsn, "TEST_TENANT": self.tenant}
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / "restart.json"
            env["TEST_RECORD"] = str(record)
            writer = """import os,json
from pathlib import Path
from tests.test_david_postgres_v2 import seed,NOW,EXPIRY
from app.domain.david_postgres import connect_postgres_ledger
l=connect_postgres_ledger(os.environ['TEST_RUNTIME_DSN']); t=os.environ['TEST_TENANT']
s,b,c,body=seed(l,t); e=l.decision_epoch(t,'work')
task=l.create_manual_task(t,'work',c,body,'restart',e,EXPIRY,NOW)
seed(l,t,'suppressed'); l.suppress(t,'suppressed','SYNTHETIC_SUPPRESSION',NOW)
Path(os.environ['TEST_RECORD']).write_text(json.dumps({'pid':os.getpid(),'source':s,'task':task}))
os._exit(0)
"""
            subprocess.run(
                [sys.executable, "-c", writer],
                env=env,
                cwd=ROOT,
                check=True,
                timeout=30,
                capture_output=True,
            )
            first = json.loads(record.read_text())
            reader = """import os,json
from pathlib import Path
from tests.test_david_postgres_v2 import NOW
from app.domain.david_postgres import connect_postgres_ledger
l=connect_postgres_ledger(os.environ['TEST_RUNTIME_DSN']); t=os.environ['TEST_TENANT']; r=json.loads(Path(os.environ['TEST_RECORD']).read_text())
assert l.state(t,r['task'],NOW)=='VALID'
item=l.claim_outbox(t,'replacement-after-crash',NOW); assert item and item['node_id']==r['task']
assert l.claim_outbox(t,'second-worker',NOW) is None
with l.transaction(t) as c:
 c.execute("SELECT suppressed FROM decision_scopes WHERE tenant=%s AND scope_id='suppressed'",(t,)); assert c.fetchone()==(True,)
l.correct(t,r['source'],'SOURCE_CORRECTED',NOW)
assert l.state(t,r['task'],NOW)=='REVOKED'
print(json.dumps({'pid':os.getpid(),'writer_pid':r['pid'],'state':'REVOKED','pending_outbox_recovered':True}))
"""
            result = subprocess.run(
                [sys.executable, "-c", reader],
                env=env,
                cwd=ROOT,
                check=True,
                timeout=30,
                capture_output=True,
                text=True,
            )
            proof = json.loads(result.stdout)
            self.assertNotEqual(first["pid"], proof["pid"])
            self.assertTrue(proof["pending_outbox_recovered"])

    def test_disposable_backup_restore_preserves_tasks_suppression_and_tombstone(self):
        source, _, _, _, task, _ = self.task()
        seed(self.ledger, self.tenant, "suppressed")
        self.ledger.suppress(self.tenant, "suppressed", "SYNTHETIC_SUPPRESSION", NOW)
        self.ledger.revoke_grant(
            self.tenant, "synthetic-withdrawn", "v1", "SYNTHETIC_WITHDRAWAL", NOW
        )
        binary_dir = os.environ.get("DAVID_PG_BIN", "")
        suffix = ".exe" if os.name == "nt" else ""

        def binary(name):
            candidate = Path(binary_dir) / (name + suffix)
            result = (
                str(candidate)
                if binary_dir and candidate.is_file()
                else shutil.which(name)
            )
            if not result:
                self.fail(
                    f"{name} is required for the mandatory disposable restore proof"
                )
            return result

        config = conninfo_to_dict(admin_dsn())
        target = "david_restore_" + uuid4().hex[:16]
        control = make_conninfo(**{**config, "dbname": "postgres"})
        env = {**os.environ, "PGPASSWORD": config.get("password", "")}
        args = [
            "-h",
            config["host"],
            "-p",
            config.get("port", "5432"),
            "-U",
            config.get("user", "postgres"),
        ]
        with (
            psycopg.connect(control, autocommit=True) as admin,
            tempfile.TemporaryDirectory() as tmp,
        ):
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target)))
            try:
                archive = Path(tmp) / "synthetic.dump"
                subprocess.run(
                    [
                        binary("pg_dump"),
                        *args,
                        "-Fc",
                        "-f",
                        str(archive),
                        config["dbname"],
                    ],
                    env=env,
                    check=True,
                    capture_output=True,
                    timeout=60,
                )
                subprocess.run(
                    [
                        binary("pg_restore"),
                        *args,
                        "--exit-on-error",
                        "-d",
                        target,
                        str(archive),
                    ],
                    env=env,
                    check=True,
                    capture_output=True,
                    timeout=60,
                )
                restored = connect_postgres_ledger(
                    make_conninfo(**{**conninfo_to_dict(self.dsn), "dbname": target})
                )
                try:
                    self.assertEqual(restored.state(self.tenant, task, NOW), "VALID")
                    with restored.transaction(self.tenant) as cursor:
                        cursor.execute(
                            "SELECT suppressed FROM decision_scopes WHERE tenant=%s AND scope_id='suppressed'",
                            (self.tenant,),
                        )
                        self.assertEqual(cursor.fetchone(), (True,))
                        cursor.execute(
                            "SELECT revoked FROM source_grant_authorities WHERE tenant=%s AND source_id='synthetic-withdrawn'",
                            (self.tenant,),
                        )
                        self.assertEqual(cursor.fetchone(), (True,))
                    restored.correct(self.tenant, source, "RESTORED_CORRECTION", NOW)
                    self.assertEqual(restored.state(self.tenant, task, NOW), "REVOKED")
                finally:
                    restored.close()
            finally:
                admin.execute(
                    sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                        sql.Identifier(target)
                    )
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
