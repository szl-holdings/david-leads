# David Leads credential rotation

The public repository previously contained a complete David Leads login triplet. Those historical
values are permanently revoked. Removing them from the current tree does not remediate deployed
secrets.

Use an approved local vault to generate and retain replacements for:

- `DAVID_USER`
- `DAVID_PASS`
- `DAVID_ACCESS_KEY`
- `DAVID_DATABASE_URL`

Copy the replacements directly from that vault into encrypted GitHub repository secrets. Never put
the values in a commit, workflow input, issue, pull request, model card, log, or chat.

Run the `Rotate David Space credentials` workflow manually. It uses the existing `HF_TOKEN`
publisher secret to update all four Hugging Face Space secrets, restarts the Space, waits for
`/healthz` to report `authentication=CONFIGURED` and
`deal_desk_persistence=POSTGRES_READY`, proves a replacement login and logout, and emits only the
secret names and boolean verification results.

After rotation, run the pinned `Deploy to HuggingFace Space` and `HF Module Drift Check` workflows
from current protected `main`. Production remediation requires all of the following:

1. the rotation workflow succeeds;
2. the live health endpoint reports `CONFIGURED`;
3. the exact-main deployment succeeds;
4. the live build revision matches protected `main`; and
5. the independent GitHub/Hugging Face drift check succeeds.

`receipt_minted=false` remains an explicit exception; source identity and byte-parity checks are not
cryptographic release receipts.
