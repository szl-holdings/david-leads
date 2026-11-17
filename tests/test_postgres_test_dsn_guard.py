"""Prevent synthetic SQL test setup and TRUNCATE from targeting live databases.

No test in this file connects to a database or starts a migration.
"""
import pytest

from tests import postgres_support as support
from tests import test_david_postgres as legacy


@pytest.mark.parametrize("dsn", [
    "postgresql://postgres:test@127.0.0.1:5432/david_evidence_test",
    "host=localhost port=55432 user=postgres dbname=david_evidence_test",
    "host=postgres user=postgres dbname=david_evidence_test",
])
def test_disposable_local_database_is_only_admissible_target(monkeypatch, dsn):
    monkeypatch.delenv("PGHOSTADDR", raising=False)
    monkeypatch.delenv("PGSERVICE", raising=False)
    monkeypatch.setenv("DAVID_EVIDENCE_TEST_DSN", dsn)
    assert support.admin_dsn() == dsn


@pytest.mark.parametrize("dsn", [
    "postgresql://postgres:password@127.0.0.1:5432/neondb",
    "postgresql://postgres:password@localhost:5432/david_leads_production",
    "postgresql://postgres:password@prod.neon.tech:5432/david_evidence_test",
    "host=localhost hostaddr=203.0.113.11 dbname=david_evidence_test",
    "host=localhost hostaddr=203.0.113.11 dbname=neondb",
    "host=localhost dbname=david_evidence_test service=production",
    "dbname=david_evidence_test",
])
def test_foreign_or_ambiguous_dsn_is_rejected_before_connect(monkeypatch, dsn):
    monkeypatch.delenv("PGHOSTADDR", raising=False)
    monkeypatch.delenv("PGSERVICE", raising=False)
    monkeypatch.setenv("DAVID_EVIDENCE_TEST_DSN", dsn)
    with pytest.raises(RuntimeError):
        support.admin_dsn()


def test_environment_hostaddr_override_is_rejected(monkeypatch):
    monkeypatch.setenv("DAVID_EVIDENCE_TEST_DSN", "host=localhost dbname=david_evidence_test")
    monkeypatch.setenv("PGHOSTADDR", "203.0.113.11")
    with pytest.raises(RuntimeError, match="PGHOSTADDR"):
        support.admin_dsn()


def test_environment_service_override_is_rejected(monkeypatch):
    monkeypatch.setenv("DAVID_EVIDENCE_TEST_DSN", "host=localhost dbname=david_evidence_test")
    monkeypatch.setenv("PGSERVICE", "prod")
    with pytest.raises(RuntimeError, match="service"):
        support.admin_dsn()


def test_legacy_destructive_sql_setup_is_guarded_without_network(monkeypatch):
    bad = "postgresql://postgres:secret@127.0.0.1/neondb"
    monkeypatch.setattr(legacy, "DSN", bad)
    monkeypatch.setenv("DAVID_EVIDENCE_TEST_DSN", bad)
    called = []
    monkeypatch.setattr(support.psycopg, "connect", lambda *args, **kwargs: called.append(args))
    with pytest.raises(RuntimeError, match="david_evidence_test"):
        legacy._connect()
    assert not called


def test_disposable_database_sentinel_does_not_grant_execution(monkeypatch):
    monkeypatch.setenv("DAVID_EVIDENCE_TEST_DSN", "host=localhost dbname=david_evidence_test")
    assert support.admin_dsn()
    # The guard decides only whether a destructive test *may* open the
    # disposable host; it does not connect or prove production readiness.
