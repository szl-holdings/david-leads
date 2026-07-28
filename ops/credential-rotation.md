# David Leads credential rotation

The public repository previously contained a complete David Leads login triplet. Those historical
values are permanently revoked. Removing them from the current tree does not remediate deployed
secrets.

Use an approved local vault to generate and retain replacements for:

- `DAVID_USER`
- `DAVID_PASS`
- `DAVID_ACCESS_KEY`
- `DAVID_DATABASE_URL`

Before this workflow may be merged or run, a repository administrator must create the protected
GitHub environment `david-space-credential-rotation` with all of these controls:

- deployment branches restricted to the protected `main` branch only;
- a required owner approval before the job can start; and
- `HF_TOKEN`, `DAVID_USER`, `DAVID_PASS`, `DAVID_ACCESS_KEY`, and `DAVID_DATABASE_URL` stored as
  environment secrets.

Delete repository-scoped copies of the four `DAVID_*` values after moving them into the environment.
The narrowly scoped `HF_TOKEN` used by the protected-main push-only deploy workflow is a separate
publisher boundary; no branch-selectable workflow may reference it. Copy replacements directly from
the approved vault into the encrypted environment secrets. Never put values in a commit, workflow
input, issue, pull request, model card, log, or chat. Keep this pull request in draft until an
administrator verifies the environment, branch restriction, approval rule, environment-secret
names, and removal of repository-scoped `DAVID_*` copies.

Run the `Rotate David Space credentials` workflow manually from current protected `main`. It uses
the environment-scoped publisher secret to update all four Hugging Face Space secrets, restarts the
Space, waits until the replacement triplet itself logs in, proves logout, and emits only secret
names and boolean verification results. Database readiness is reported separately: a database
outage cannot invalidate a successful authentication rotation, and successful rotation does not
prove persistence readiness.

Production remediation requires all of the following:

1. the rotation workflow succeeds;
2. the live health endpoint reports authentication `CONFIGURED`;
3. live health independently reports `deal_desk_persistence=POSTGRES_READY`;
4. the exact-main deployment succeeds;
5. the live build revision matches protected `main`; and
6. the independent GitHub/Hugging Face drift check succeeds.

`receipt_minted=false` remains an explicit exception; source identity and byte-parity checks are not
cryptographic release receipts.
