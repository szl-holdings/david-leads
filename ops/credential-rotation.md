# David Leads credential rotation

The public repository previously contained a complete David Leads login triplet. Those historical
values are permanently revoked. Removing them from the current tree does not remediate deployed
secrets.

Use an approved local vault to generate and retain replacements for:

- `DAVID_USER`
- `DAVID_PASS`
- `DAVID_ACCESS_KEY`

Before this workflow may be merged or run, a repository administrator must create the protected
GitHub environment `david-space-credential-rotation` with all of these controls:

- deployment branches restricted to the protected `main` branch only;
- a required owner approval before the job can start; and
- `HF_TOKEN`, `DAVID_USER`, `DAVID_PASS`, and `DAVID_ACCESS_KEY` stored as environment secrets.

Delete repository-scoped copies of those four secrets after moving them into the environment. A
branch-selectable workflow can read repository secrets without entering this protected job, so
leaving repository-scoped copies in place defeats the environment boundary.

Copy the replacements directly from the approved vault into those encrypted environment secrets.
Never put the values in a commit, workflow input, issue, pull request, model card, log, or chat.
Keep this pull request in draft until an administrator verifies the environment, branch restriction,
approval rule, environment-secret names, and removal of the repository-scoped copies.

Run the `Rotate David Space credentials` workflow manually from current protected `main`. It uses
the environment-scoped `HF_TOKEN` publisher secret to update all three Hugging Face Space secrets,
restarts the Space, waits until the replacement triplet itself logs in, proves logout, and emits only
the secret names and boolean verification results.

After rotation, run the pinned `Deploy to HuggingFace Space` and `HF Module Drift Check` workflows
from current protected `main`. Production remediation requires all of the following:

1. the rotation workflow succeeds;
2. the live health endpoint reports `CONFIGURED`;
3. the exact-main deployment succeeds;
4. the live build revision matches protected `main`; and
5. the independent GitHub/Hugging Face drift check succeeds.

`receipt_minted=false` remains an explicit exception; source identity and byte-parity checks are not
cryptographic release receipts.
