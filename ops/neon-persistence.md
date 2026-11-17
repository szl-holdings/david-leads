# David Neon persistence

The application credential `DAVID_DATABASE_URL` is a least-privilege runtime secret. It must be able
to select, insert, and update the versioned deal-desk tables, but it does not need permission to
create or alter schema objects.

Schema creation is a separate owner-approved operation:

1. Store a migration-only Neon connection string as the protected environment secret
   `DAVID_DATABASE_ADMIN_URL`. Never store it as a repository secret or a Hugging Face Space secret.
2. Store the least-privilege runtime connection string as the protected environment secret
   `DAVID_DATABASE_URL` so the migration can grant its exact database role access without exposing
   a role name in source or logs.
3. Restrict `david-space-credential-rotation` to protected `main` and require owner approval.
4. Approve the migration job for the exact protected-main deployment. The deploy job cannot start
   until that migration succeeds.
5. The migration fails if a legacy do-not-call row lacks a durable business identity. Complete a
   governed identity backfill before retrying; never infer one from a changed trigger date or URL.
6. The migration transfers service-table ownership to the administrator, revokes schema creation
   and prior broad table grants from the runtime role and `PUBLIC`, grants only schema usage plus
   the table-specific privileges required by the runtime, and validates the effective result.
7. Run `Verify David Neon persistence` from protected `main` with the least-privilege
   `DAVID_DATABASE_URL`.
8. Confirm live health independently reports `POSTGRES_READY`.

**Destructive test boundary:** PostgreSQL tests apply synthetic schemas and call
`TRUNCATE ... CASCADE`. `tests/postgres_support.py` and the legacy test adapter
reject any test DSN that does not name exactly `david_evidence_test` on the
explicit local PostgreSQL service. Remote hosts, remote `hostaddr`, and libpq
service-based routing are refused *before* opening a connection. A local
forwarding proxy could still disguise a remote service, so run these tests only
against the ephemeral CI `postgres:16-alpine` service or an independently
verified disposable instance. Never use a production Neon URL for `DAVID_EVIDENCE_TEST_DSN`.
The production `DAVID_DATABASE_URL` is a different credential and is never
accepted as a test DSN. This preflight is a safety restriction, not an
independent database identity attestation.

Evidence-kernel tables (`source_grants`, `observations`, `identity_candidates`,
`evidence_nodes`, `evidence_edges`, `derivations`, `clearances`, `suppressions`,
`outcomes`, `outbox`) are an expand-only addition in `app/evidence_schema.sql`.
They do not replace `david_dealdesk_state` or `david_dealdesk_events`. The
runtime still performs read-only schema-contract checks. It fails closed on a
missing or mismatched schema and never attempts `CREATE TABLE`, `CREATE INDEX`,
or another privileged migration. Integrity for evidence nodes remains
`LOCAL_SHA256_UNSIGNED` until the existing Cosign/receipts path binds it.
