# David Neon persistence

The application credential `DAVID_DATABASE_URL` is a least-privilege runtime login. The checked-in
migration creates a non-login `david_dealdesk_runtime` group with only the table permissions the
application needs. The login in `DAVID_DATABASE_URL` must be a member of that group; it must not own
the database or have permission to create or alter schema objects.

Schema creation is a separate owner-approved local administrator operation:

1. Obtain a migration-only Neon session through Neon OAuth or an approved local vault. Never store
   its connection string in a GitHub secret, Hugging Face Space secret, log, clipboard, or chat.
2. Verify `app/dealdesk_schema.sql` is the reviewed file from current protected `main`.
3. Apply that exact file in one transaction using the migration-only session.
4. Create or select a dedicated application login, grant it membership in
   `david_dealdesk_runtime`, and verify it has no superuser, create-role, or create-database
   attributes. Do not grant it the owner role.
5. Using the application login, verify the `dealdesk` schema version is `1`; verify transactional
   state/event writes and rollback without printing the connection string.
6. Revoke the migration session and retain only the schema file hash and bounded verification
   result.
7. Confirm live health independently reports `POSTGRES_READY`.

The runtime performs read-only schema-contract checks. It fails closed on a missing or mismatched
schema and never attempts `CREATE TABLE`, `CREATE INDEX`, or another privileged migration.
