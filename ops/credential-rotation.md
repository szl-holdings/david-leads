# David Leads credential rotation

The public repository previously contained a complete David Leads login triplet. Those historical
values are permanently revoked. Removing them from the current tree does not remediate deployed
secrets.

Use an approved local vault to generate and retain replacements for:

- `DAVID_USER`
- `DAVID_PASS`
- `DAVID_ACCESS_KEY`
- `DAVID_DATABASE_URL`

The protected GitHub environment `david-space-credential-rotation` is configured with these
controls:

- deployment branches restricted to the protected `main` branch only;
- a required owner approval before a bound job can start; and
- `DAVID_USER`, `DAVID_PASS`, `DAVID_ACCESS_KEY`, `DAVID_DATABASE_URL`, and
  `DAVID_DATABASE_ADMIN_URL` are stored as
  environment secrets.

Repository secret metadata contains only the narrowly scoped `HF_TOKEN` used by the
protected-main deployment and the owner-approved rotation workflow. No `DAVID_*` value is stored at
repository scope. Copy replacements directly from the approved vault into the encrypted environment
secrets. Never put values in a commit, workflow input, issue, pull request, model card, log, or chat.

Run the `Rotate David Space credentials` workflow manually from current protected `main`. It uses
the scoped publisher to update all four Hugging Face Space secrets, waits until the replacement
triplet itself logs in, proves logout, and emits only secret names and boolean verification results.
Database readiness is reported separately: a database outage cannot invalidate a successful
authentication rotation, and successful rotation does not prove persistence readiness.

Protected run `30403607270` completed this procedure successfully on
`41b322c9070886836e7dbdf0a1c371798851a641`. Its schema-v2 result recorded replacement login and
logout verified, PostgreSQL ready, and `credential_values_recorded=false`.

Production remediation requires all of the following:

1. the rotation workflow succeeds;
2. the live health endpoint reports authentication `CONFIGURED`;
3. live health independently reports `deal_desk_persistence=POSTGRES_READY`;
4. the exact-main deployment succeeds;
5. the live build revision matches protected `main`; and
6. the independent GitHub/Hugging Face drift check succeeds.

`receipt_minted=false` remains an explicit exception; source identity and byte-parity checks are not
cryptographic release receipts.
