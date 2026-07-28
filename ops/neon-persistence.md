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
5. The migration grants only schema usage plus the table-specific select/insert/update privileges
   required by the runtime role.
6. Run `Verify David Neon persistence` from protected `main` with the least-privilege
   `DAVID_DATABASE_URL`.
7. Confirm live health independently reports `POSTGRES_READY`.

The runtime performs read-only schema-contract checks. It fails closed on a missing or mismatched
schema and never attempts `CREATE TABLE`, `CREATE INDEX`, or another privileged migration.
