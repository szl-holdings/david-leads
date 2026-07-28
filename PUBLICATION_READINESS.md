# Public Revenue Frontier — Publication Readiness

> Status: **PUBLIC · OPERATIONAL WITH EXPLICIT EVIDENCE EXCEPTIONS**
>
> Exceptions: `receipt_minted=false`; administrator-login evidence remains
> `UNVERIFIED`; current vault/Hugging Face credential-policy conformance and the
> current GitHub Actions secret inventory remain `UNVERIFIED`.
>
> Scope: `szl-holdings/david-leads` is the revenue-adjacent insurance
> frontier in the nine-repository portfolio.

## Operational evidence

The credential-remediation and governed broker-desk release was observed on
2026-07-28. The evidence below is specific; it is not an estate-wide claim.

- Protected source revision
  `1e27921013f6f92419170b41cd4646aee38b64fc` passed CI in run
  `30388869705`.
- Protected deployment run `30388870254` completed successfully and bound the
  live Hugging Face Space to that exact GitHub revision.
- Independent drift-check run `30389219959` reported
  `Source in sync with the live HF Space`.
- The unauthenticated `/healthz` and `/readyz` probes returned HTTP 200 with
  `authentication=CONFIGURED`, `deal_desk_persistence=POSTGRES_READY`, and
  `persistence_diagnostic=OK`.
- The live `/api/build-info` probe reported the exact protected revision,
  runtime bundle digest
  `a6de59cf79530ab693f71e13428df718ddf1687f27f2c304a50fe3db75e0ce62`,
  and 50 copied files.
- Protected Neon preflight run `30388377093` verified the encrypted connection,
  schema read, transactional writes, and rollback without recording the
  database credential.
- A non-displaying administrator-vault flow was reported to have verified
  replacement production login, protected Frontier Radar access, and logout.
  No secret-free immutable receipt is referenced by this record, so that
  administrator-login evidence remains `UNVERIFIED`; no credential factor is
  included here.

This readiness record is itself part of the Docker-copied governance bundle.
Every later merge must complete a fresh exact-source deployment and live probe;
the revision reported by `/api/build-info` is the current source identity.

## Public boundary

- The repository is licensed under Apache-2.0.
- Lead intelligence is limited to organization/entity-level public records and
  explicitly consented submissions.
- Public records create research tasks; they never create contact permission.
- Only a current clearance bound to a first-party business channel, named
  operator, business purpose, jurisdiction, license scope, required suppression
  checks, and expiry can unlock a call sheet.
- Scores are advisory evidence-completeness priorities, not probabilities,
  insurance quotes, underwriting decisions, consumer reports, or permission to
  contact.
- Missing evidence remains `NOT_EVALUATED`; offline demonstrations remain
  `EXAMPLE`; unavailable sources remain `UNAVAILABLE`.
- EPA ECHO data is limited to neutral facility identity and
  compliance-monitoring activity. No violation, penalty, demographic,
  individual, risk, or underwriting label is exposed.
- Social-profile scraping, personal/free-mail enrichment, purchased people
  data, automated voice, robotext, and autodialing are outside this release.

## Credential authority

The historical credential triplet remains permanently revoked because it was
published in tracked handoff/demo artifacts. Removing values from the current
tree cannot revoke external copies.

The intended credential-authority policy governs production application and
database values through the approved local administrator vault and write-only
Hugging Face Space secret interfaces. Current conformance to that policy remains
`UNVERIFIED` because this record did not inspect the current GitHub Actions
secret inventory or capture immutable evidence of the current vault and Space
secret state.
Historical Neon preflight run `30388377093` read `DAVID_DATABASE_URL` from a
scoped GitHub Actions secret to verify schema reads, transactional writes, and
rollback; the credential value was not included in its evidence.
The current deployment workflow receives only the scoped Hugging Face token, and
the former GitHub workflow that rotated application and database values has been
removed. This record does not claim that every present or future Actions
workflow can never read a separately scoped credential. The intended local,
non-displaying administrator rotation policy is documented in
`ops/credential-rotation.md`; current conformance remains `UNVERIFIED`.

If any current factor may have been disclosed, pause the Space, replace all
application and database values from the approved vault, verify health,
replacement login/logout, exact-source deployment, and drift, then revoke the
administrator session used for rotation.

## Durable broker workflow

- Opportunity snapshots are persisted in `david_dealdesk_state`.
- Immutable research, clearance, stage, and disposition events are persisted in
  `david_dealdesk_events`.
- A transient Postgres startup failure is retried on a bounded, thread-safe
  interval; readiness remains fail-closed until the database is usable.
- CSV export is formula-injection safe and reveals a business channel only while
  its clearance is current.
- `DO_NOT_CALL` immediately revokes the clearance and blocks the opportunity.
- CRM webhooks require an explicit HTTPS hostname allowlist and pin connections
  to validated public addresses.

## Explicit exception

`receipt_minted=false` remains the truthful release-receipt state. Exact GitHub
revision, runtime byte manifest, protected deployment, live probes, and
independent drift evidence prove source alignment; they are not a cryptographic
release receipt.

## Operational caution

Public visibility is not fully reversible because external readers can retain
copies. If a post-publication issue is found, contain the affected surface,
rotate any exposed credential through the approved local authority, and publish
a correction record. No ruleset, branch-protection, required-review,
required-check, bypass-actor, or governance-workflow weakening is part of this
release.
