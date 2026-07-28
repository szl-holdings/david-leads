# David Leads credential rotation

The public repository previously contained a complete David Leads login triplet. Those historical
values are permanently revoked. Removing them from the current tree does not remediate deployed
secrets.

Use an approved local vault to generate and retain replacements for:

- `DAVID_USER`
- `DAVID_PASS`
- `DAVID_ACCESS_KEY`
- `DAVID_DATABASE_URL`

Keep the replacements out of GitHub repository secrets and GitHub Actions. Never put the values in
a commit, workflow input, issue, pull request, model card, log, terminal output, clipboard, or chat.
Transfer them only through the approved vault's non-displaying administrator flow.

Credential rotation is a local administrator operation:

1. pause the Hugging Face Space before changing any value;
2. update all four Space secrets from the approved vault using a least-privilege administrator
   session;
3. if any update fails, keep the Space paused and repeat the complete update;
4. restart only after the complete set has been confirmed;
5. verify `/healthz` reports `authentication=CONFIGURED` and
   `deal_desk_persistence=POSTGRES_READY`;
6. verify one replacement login and logout without recording or displaying any factor; and
7. revoke the administrator session used for rotation.

After rotation, push an exact-source deployment from current protected `main`. Production
remediation requires all of the following:

1. the live health endpoint reports `CONFIGURED`;
2. the exact-main deployment succeeds;
3. the live build revision matches protected `main`;
4. the independent GitHub/Hugging Face drift check succeeds; and
5. no GitHub workflow can read or mutate the application or database credentials.

`receipt_minted=false` remains an explicit exception; source identity and byte-parity checks are not
cryptographic release receipts.
