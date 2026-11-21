"""Offline regression for bounded PostgreSQL evidence-role preflight.

Synthetic mocks only: no network, database, credentials, or operator state.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, call, patch

from app.domain import david_postgres as pg


class RuntimePreflightDeadlineTests(unittest.TestCase):
    def test_statement_timeout_is_first_and_transaction_local(self) -> None:
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.execute.side_effect = [
            None,
            RuntimeError("synthetic role-query failure"),
        ]

        with self.assertRaisesRegex(RuntimeError, "synthetic role-query failure"):
            pg.verify_runtime_contract(connection)

        connection.transaction.assert_called_once_with()
        cursor.execute.assert_has_calls(
            [
                call("SET LOCAL statement_timeout = '4000ms'"),
                call(
                    "SELECT r.rolsuper,r.rolbypassrls,r.rolcreaterole,"
                    "r.rolcreatedb,r.rolreplication,current_user=session_user "
                    "FROM pg_roles r WHERE r.rolname=current_user"
                ),
            ]
        )
        self.assertEqual(cursor.execute.call_count, 2)

    def test_failed_runtime_preflight_never_returns_ledger(self) -> None:
        connection = MagicMock()
        synthetic_dsn = "postgresql://example.invalid/synthetic"

        with (
            patch.object(pg, "psycopg") as driver,
            patch.object(
                pg,
                "verify_runtime_contract",
                side_effect=TimeoutError("synthetic query timeout"),
            ),
        ):
            driver.connect.return_value = connection
            with self.assertRaisesRegex(TimeoutError, "synthetic query timeout"):
                pg.connect_postgres_ledger(synthetic_dsn)
            driver.connect.assert_called_once_with(synthetic_dsn, connect_timeout=8)

        connection.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
