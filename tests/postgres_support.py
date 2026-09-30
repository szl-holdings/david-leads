"""Disposable PostgreSQL test setup. Migration and runtime use separate logins."""

from __future__ import annotations
import os
from pathlib import Path
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from app.domain.david_postgres import (
    EVIDENCE_TABLES,
    RUNTIME_TABLE_PRIVILEGES,
    apply_evidence_schema,
)

ROOT = Path(__file__).resolve().parents[1]
ROLE = "david_evidence_test_runtime"
PASSWORD = "disposable-test-runtime-only"


def admin_dsn():
    value = os.environ.get("DAVID_EVIDENCE_TEST_DSN", "")
    if not value:
        raise RuntimeError(
            "DAVID_EVIDENCE_TEST_DSN is required for real PostgreSQL tests"
        )
    config = conninfo_to_dict(value)
    if config.get("host") not in {"localhost", "127.0.0.1", "::1", "postgres"}:
        raise RuntimeError(
            "Tests require an explicitly disposable local PostgreSQL service"
        )
    return value


def admin_connection():
    return psycopg.connect(admin_dsn(), autocommit=True, connect_timeout=8)


def runtime_dsn():
    config = conninfo_to_dict(admin_dsn())
    config.update(user=ROLE, password=PASSWORD)
    return make_conninfo(**config)


def bootstrap_test_database():
    """Return runtime DSN after complete SQL programs run under migration login."""
    with admin_connection() as connection:
        with connection.transaction(), connection.cursor() as cursor:
            cursor.execute(
                (ROOT / "app/dealdesk_schema.sql").read_text(), prepare=False
            )
            apply_evidence_schema(connection)
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (ROLE,))
            if not cursor.fetchone():
                cursor.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT"
                    ).format(sql.Identifier(ROLE), sql.Literal(PASSWORD))
                )
            cursor.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            cursor.execute(
                sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                    sql.Identifier(ROLE)
                )
            )
            cursor.execute(
                sql.SQL("GRANT SELECT ON david_dealdesk_schema TO {}").format(
                    sql.Identifier(ROLE)
                )
            )
            for table in EVIDENCE_TABLES:
                cursor.execute(
                    sql.SQL("REVOKE ALL ON {} FROM {}").format(
                        sql.Identifier(table), sql.Identifier(ROLE)
                    )
                )
                cursor.execute(
                    sql.SQL("GRANT {} ON {} TO {}").format(
                        sql.SQL(",").join(
                            map(sql.SQL, RUNTIME_TABLE_PRIVILEGES[table])
                        ),
                        sql.Identifier(table),
                        sql.Identifier(ROLE),
                    )
                )
    return runtime_dsn()


def truncate_evidence():
    with admin_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("TRUNCATE {} CASCADE").format(
                sql.SQL(",").join(map(sql.Identifier, EVIDENCE_TABLES))
            )
        )
