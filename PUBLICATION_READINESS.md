# Public Revenue Frontier — Publication Readiness

> Status: **READY FOR PUBLIC VISIBILITY**
>
> Scope: `szl-holdings/david-leads` is the revenue-adjacent insurance
> frontier in the nine-repository portfolio.

## Public boundary

- The repository is licensed under Apache-2.0.
- Lead intelligence is limited to public records and explicitly consented
  submissions.
- Scores are advisory work-order signals, not probabilities, insurance
  quotes, underwriting decisions, consumer reports, or permission to
  contact.
- Missing evidence remains `NOT_EVALUATED`; offline examples remain
  `EXAMPLE`; unavailable signatures remain `UNSIGNED`.
- Runtime credentials and signing material are read from the approved secret
  store and are excluded from the repository.

## Pre-publication evidence

The preflight was run against default-branch head
`0fa3430671a54f14c3fdb5597127340f47993473` on 2026-07-27:

- GitHub secret scanning reported zero open alerts.
- The tracked tree contained no environment files, private keys, or
  credential files.
- Current-tree and full-history scans found no private-key, GitHub-token,
  cloud-key, or provider-secret signatures.
- The embedded access-tour document contained no credential assignments,
  secret signatures, email addresses, or phone numbers.
- All 24 unit tests passed.
- Python syntax compilation passed for `app/` and `ops/`.
- GitHub Actions workflows use read-only repository permissions; deployment
  credentials remain in the secret store.

## Operational caution

Changing a repository from private to public is not fully reversible because
external readers can retain copies. If a post-publication issue is found,
restore private visibility immediately, rotate any affected credential, and
publish a correction record. No ruleset, branch-protection, required-review,
required-check, bypass-actor, or governance-workflow change is part of this
release.
