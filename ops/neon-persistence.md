# David Neon persistence

The application credential `DAVID_DATABASE_URL` is a least-privilege runtime secret. It must be able
to select, insert, and update the versioned deal-desk tables, but it does not need permission to
create or alter schema objects.

Schema creation is a separate owner-approved local administrator operation:

1. Obtain a migration-only Neon session through Neon OAuth or an approved local vault. Never store
   its connection string in a GitHub secret, Hugging Face Space secret, log, clipboard, or chat.
2. Verify `app/dealdesk_schema.sql` is the reviewed file from current protected `main`.
3. Apply that exact file in one transaction using the migration-only session.
4. Verify the `dealdesk` schema version is `1`, revoke the migration session, and retain only the
   schema file hash and bounded verification result.
5. Confirm live health independently reports `POSTGRES_READY`.

The runtime performs read-only schema-contract checks. It fails closed on a missing or mismatched
schema and never attempts `CREATE TABLE`, `CREATE INDEX`, or another privileged migration.
