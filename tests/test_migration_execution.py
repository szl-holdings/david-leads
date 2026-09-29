"""Execute the checked-in migration Python against a disposable PostgreSQL DB.

Only connection routing changes: validated Neon-shaped test URLs are mapped to
local test sockets. All schema, grants, constraints and verification SQL is real.
"""
import contextlib
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
import yaml

from tests.postgres_support import admin_connection, admin_dsn, bootstrap_test_database, ROLE, PASSWORD

ROOT = Path(__file__).resolve().parents[1]


class MigrationExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bootstrap_test_database()
        workflow = yaml.safe_load((ROOT / ".github/workflows/migrate-neon-persistence.yml").read_text())
        step = next(s for s in workflow["jobs"]["migrate"]["steps"] if s["name"] == "Apply versioned schema in one transaction")
        cls.program = step["run"].split("python3 - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
        compile(cls.program, "checked-in-migration", "exec")

    def setUp(self):
        self.dbname = "david_migration_test_" + uuid4().hex[:16]
        with admin_connection() as connection:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(self.dbname)))
        self.addCleanup(self.drop_database)
        fields = conninfo_to_dict(admin_dsn())
        fields["dbname"] = self.dbname
        self.admin = make_conninfo(**fields)
        fields.update(user=ROLE, password=PASSWORD)
        self.runtime = make_conninfo(**fields)

    def drop_database(self):
        with admin_connection() as connection:
            connection.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(self.dbname)))

    def run_program(self, *, fail_schema=False, wrong_runtime=False):
        real_connect = psycopg.connect
        real_read = Path.read_text
        def connect(dsn, **kwargs):
            local = self.admin if "migration_admin@" in dsn else self.runtime
            if wrong_runtime:
                local = self.admin
            return real_connect(local, **kwargs)
        def read(path, *args, **kwargs):
            value = real_read(path, *args, **kwargs)
            if fail_schema and path.name == "evidence_schema.sql":
                value += "\nSELECT 1 / 0;\n"
            return value
        env = {"DAVID_DATABASE_ADMIN_URL": "postgresql://migration_admin@synthetic.neon.tech/neondb?sslmode=require",
               "DAVID_DATABASE_URL": f"postgresql://{ROLE}@synthetic.neon.tech/neondb?sslmode=require"}
        output = io.StringIO()
        with patch.dict(os.environ, env), patch("psycopg.connect", connect), patch.object(Path, "read_text", read), contextlib.redirect_stdout(output):
            exec(compile(self.program, "checked-in-migration", "exec"), {"__name__": "__main__"})
        return output.getvalue()

    def test_checked_in_migration_applies_real_schema_and_runtime_role(self):
        output = self.run_program()
        self.assertIn('"migration": "VERIFIED"', output)
        from app.domain.david_postgres import verify_runtime_contract
        with psycopg.connect(self.runtime) as connection:
            self.assertEqual(verify_runtime_contract(connection)["schema_version"], 2)

    def test_sql_error_rolls_back_the_whole_migration(self):
        with self.assertRaises(SystemExit):
            self.run_program(fail_schema=True)
        with psycopg.connect(self.admin) as connection:
            self.assertEqual(connection.execute("SELECT to_regclass('public.evidence_nodes'),to_regclass('public.david_dealdesk_schema')").fetchone(), (None, None))

    def test_runtime_admin_login_cannot_pass_readback(self):
        with self.assertRaises(SystemExit):
            self.run_program(wrong_runtime=True)


if __name__ == "__main__":
    unittest.main()
