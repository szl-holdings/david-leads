# David Neon persistence

The application credential `DAVID_DATABASE_URL` is a least-privilege runtime secret. It must be able
to select, insert, and update the versioned deal-desk tables, but it does not need permission to
create or alter schema objects.

Schema creation is a separate owner-approved operation:

1. Store a migration-only Neon connection string as the protected environment secret
   `DAVID_DATABASE_ADMIN_URL`. Never store it as a repository secret or a Hugging Face Space secret.
2. Restrict `david-space-credential-rotation` to protected `main` and require owner approval.
3. Run `Migrate David Neon persistence` from protected `main`.
4. Run `Verify David Neon persistence` from protected `main` with the least-privilege
   `DAVID_DATABASE_URL`.
5. Confirm live health independently reports `POSTGRES_READY`.

The runtime performs read-only schema-contract checks. It fails closed on a missing or mismatched
schema and never attempts `CREATE TABLE`, `CREATE INDEX`, or another privileged migration.
