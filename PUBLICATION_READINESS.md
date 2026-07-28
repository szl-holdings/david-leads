# Public Revenue Frontier — Publication Readiness

> Status: **PUBLIC · CREDENTIAL ROTATION REQUIRED**
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
- Runtime credentials and signing material must be read from the approved
  secret store and excluded from the repository. The application now revokes
  the known legacy public credential fingerprint and fails closed until the
  Hugging Face Space secrets are rotated.

## Pre-publication evidence and correction

The original preflight was run against default-branch head
`0fa3430671a54f14c3fdb5597127340f47993473` on 2026-07-27:

- GitHub secret scanning reported zero open alerts.
- The tracked tree contained no environment files, private keys, or
  credential files.
- Current-tree and full-history scans found no private-key, GitHub-token,
  cloud-key, or provider-secret signatures.
- The original record claimed the embedded access-tour document and tracked
  handoff artifacts contained no credential assignments.
- All 24 unit tests passed.
- Python syntax compilation passed for `app/` and `ops/`.
- GitHub Actions workflows use read-only repository permissions; deployment
  credentials remain in the secret store.

That credential claim was disproved on 2026-07-28. A complete legacy login
triplet was present in multiple tracked handoff/demo artifacts and still
authenticated successfully against the live Space. Current-tree remediation:

- removed the triplet and historical token from text artifacts;
- regenerated the DOCX without credentials;
- sanitized the portable HTML and converted it to an explicitly unauthenticated
  offline preview;
- added a repository regression test that rejects the exposed markers;
- added a fail-closed fingerprint revocation in the application.

The repository history and external copies must be treated as permanently
exposed. Publication readiness cannot return to `READY` until the Hugging Face
Space secrets are rotated and the deployed fingerprint revocation is observed.

## Operational caution

Changing a repository from private to public is not fully reversible because
external readers can retain copies. If a post-publication issue is found,
restore private visibility immediately, rotate any affected credential, and
publish a correction record. No ruleset, branch-protection, required-review,
required-check, bypass-actor, or governance-workflow change is part of this
release.
