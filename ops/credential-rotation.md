# David Leads credential rotation

The public repository previously contained a complete David Leads login triplet. Those historical
values are permanently revoked. Removing them from the current tree does not remediate deployed
secrets.

Use an approved local vault to generate and retain replacements for:

- `DAVID_USER`
- `DAVID_PASS`
- `DAVID_ACCESS_KEY`
- `DAVID_DATABASE_URL`
- `DAVID_DATASET_READ_TOKEN` — a fine-grained Hugging Face token with demonstrated
  read access to `SZLHOLDINGS/david-leads-data`. In the Hugging Face token form,
  configure only read access to that selected repository; the Hub identity API
  proves token type and successful reads, but does not expose every permission
  checkbox for the workflow to independently attest.

The protected GitHub environment `david-space-credential-rotation` is configured with these
controls:

- deployment branches restricted to the protected `main` branch only;
- a required owner approval before a bound job can start; and
- `DAVID_USER`, `DAVID_PASS`, `DAVID_ACCESS_KEY`, `DAVID_DATABASE_URL`,
  `DAVID_DATASET_READ_TOKEN`, and
  `DAVID_DATABASE_ADMIN_URL` are stored as
  environment secrets.

Repository secret metadata contains only the narrowly scoped `HF_TOKEN` used by the
protected-main deployment and the owner-approved rotation workflow. No `DAVID_*` value is stored at
repository scope. Copy replacements directly from the approved vault into the encrypted environment
secrets. Never put values in a commit, workflow input, issue, pull request, model card, log, or chat.

Run the `Rotate David Space credentials` workflow manually from current protected `main`. It first
requires the dataset reader to be fine-grained and reads every canonical lane pointer at one
immutable private-dataset revision. It then uses the separate scoped publisher to update the five
Hugging Face Space secrets, waits until the replacement triplet itself logs in, proves logout, and
requires the restarted Space's live canary to bind all four runtime snapshots back to those exact
pointers and the exact attested GitHub source. A final non-secret, per-run generation digest prevents
a still-serving predecessor process from satisfying the proof. It emits only secret names, revision identifiers,
snapshot identifiers, paths, and boolean verification results—never records or credential values.
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
