# Public Revenue Frontier — Publication Readiness

> Status: **PUBLIC · 593a SOURCE-BOUND · RUNTIME HEALTHY · PRODUCTION READINESS WITHHELD**
>
> Readiness gate: **WITHHELD**. Protected source
> `593a90b9b3621b6d31c4078d5e09dc566b21fc32` is source-bound to the live
> Hugging Face Space. `/healthz` and `/readyz` now report `POSTGRES_READY` with
> `persistence_diagnostic=OK`, and independent drift verification succeeded.
> Replacement login/logout, administrator-vault custody, and an exact-source
> deployment of this unmerged successor remain unproved. These are blocking
> evidence gaps, not operational exceptions.
>
> Scope: `szl-holdings/david-leads` is the revenue-adjacent insurance
> frontier in the nine-repository portfolio.

## Current and historical evidence

The evidence below was observed on 2026-07-28. It is source-specific and is not
an estate-wide claim.

- Protected main `593a90b9b3621b6d31c4078d5e09dc566b21fc32`
  completed the operational-safety workflow in run `30400860826`.
- Protected migration run `30400860735` completed successfully for that exact
  source. It applied and verified schema version 2, the separate
  least-privilege runtime role, service-table ownership, schema/table
  privileges, and the governed legacy-suppression boundary without recording
  credential values.
- Push deployment run `30398321778` failed twice before deployment. Its
  reusable migration job did not receive the environment-scoped database
  secrets, even though the standalone protected-environment migration
  succeeded. Protected main `a177` replaced that broken transport with a
  migration-success `workflow_run` handoff that does not move database secrets
  into the deployer.
- Exact-source deployment run `30400902083` completed successfully. It
  published and verified 53 files, resolved 51 Docker `COPY`-bound files,
  observed Hugging Face commit
  `3d4e61eda1e6df1877c7ac8c0d48e48cb6b1981e`, and matched the source-binding
  variable and runtime probe to exact protected source
  `593a90b9b3621b6d31c4078d5e09dc566b21fc32`.
- Unauthenticated `/api/build-info` currently reports live revision
  `593a90b9b3621b6d31c4078d5e09dc566b21fc32`, bundle digest
  `732bf49c9c24e7fb65d2f42bb7c29bab99050910008ae4938878f0d8fc0fc4a5`,
  51 copied files, and `receipt_minted=false`.
- The unauthenticated `/healthz` and `/readyz` probes return HTTP 200 with
  `status=ready`, `authentication=CONFIGURED`,
  `deal_desk_persistence=POSTGRES_READY`, and
  `persistence_diagnostic=OK`.
- Independent manual HF Module Drift Check run `30401085226` completed
  successfully for exact source
  `593a90b9b3621b6d31c4078d5e09dc566b21fc32`.
- Protected credential-rotation run `30399789320` was dispatched for exact
  `a177`, was externally approved, and remains in progress at this evidence
  snapshot.
  Replacement production login, protected Frontier Radar access, logout, and
  administrator-vault custody therefore remain `UNVERIFIED`.
- This successor's checked-in migration script and narrowed workflow are still
  unmerged and have not been deployed. The successful `593a` runtime is
  evidence for current protected main, not for this successor head.

This readiness record is itself part of the Docker-copied governance bundle.
A merge that changes a Docker-copied input (`requirements.txt`, `app/**`,
`PUBLICATION_READINESS.md`, `PUBLIC_DATA_OPERATING_MODEL.md`, or
`SPACE_PROVENANCE.json`), the `Dockerfile`, or the deployment workflow must
complete a fresh exact-source deployment and live probe. Other repository
changes do not trigger this deployment and are not covered by its runtime
source-identity evidence.

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

Repository secret metadata was inspected and lists only `HF_TOKEN`.
Environment-secret metadata for the protected
`david-space-credential-rotation` environment lists `DAVID_USER`,
`DAVID_PASS`, `DAVID_ACCESS_KEY`, `DAVID_DATABASE_URL`, and
`DAVID_DATABASE_ADMIN_URL`. No value was read or recorded. The environment has
an owner-review rule and a protected-main branch policy. Exact-source migration
run `30400860735` proved that the two database credentials were available to
the protected-environment job at source `593a`.

The failed push deployment proves that the former reusable-workflow call did
not receive those environment secrets. Protected main now runs migration
directly on protected-main push and invokes the pinned deployer only from that
exact successful migration event. This successor extracts the unchanged
migration implementation into one checked-in script and removes the unused
`workflow_call` entry point so the environment-only boundary cannot silently
regress.

The current Space is source-bound and reports healthy Postgres readiness, but
that is not complete production proof. Protected rotation run `30399789320`
submitted updates for the four named Space secrets without API error but timed
out without a replacement login/logout receipt. The live Space subsequently
reported `RUNNING`, exact
source `593a90b9b3621b6d31c4078d5e09dc566b21fc32`, authentication
`CONFIGURED`, and `POSTGRES_READY`; those observations do not prove that the
replacement triplet authenticates. This successor adds a non-causal,
secret-free failure receipt for the required rerun and has not been merged or
deployed.
Application-credential replacement, effective Hugging Face token scope, and
local administrator-vault custody remain `UNVERIFIED`.

If any current factor may have been disclosed, pause the Space, replace all
application and database values from the approved vault, verify health,
replacement login/logout, exact-source deployment, and drift, then revoke the
administrator session used for rotation.

## Successor durable broker contract

The following is the fail-closed source contract in this successor. It is not
live production evidence until the protected migration, exact-source
deployment, live probes, and independent drift check succeed for the exact
merged revision.

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
