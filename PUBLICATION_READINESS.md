# Public Revenue Frontier — Publication Readiness

> Status: **PUBLIC · a177 SOURCE-BOUND · PRODUCTION READINESS WITHHELD**
>
> Readiness gate: **WITHHELD**. Protected source
> `a1774f38d61a255d9dd64ed4d8716d27b3d3aaf7` is source-bound to the live
> Hugging Face Space, but `/healthz` and `/readyz` fail closed with
> `SCHEMA_INCOMPATIBLE`. Replacement login/logout, credential custody, runtime
> database convergence, and an exact-source successful deploy remain
> `UNVERIFIED`. These are blocking evidence gaps, not operational exceptions.
>
> Scope: `szl-holdings/david-leads` is the revenue-adjacent insurance
> frontier in the nine-repository portfolio.

## Current and historical evidence

The evidence below was observed on 2026-07-28. It is source-specific and is not
an estate-wide claim.

- Protected main `a1774f38d61a255d9dd64ed4d8716d27b3d3aaf7`
  completed the operational-safety workflow in run `30399398550`.
- Protected migration run `30399398519` completed successfully for that exact
  source. It applied and verified schema version 2, the separate
  least-privilege runtime role, service-table ownership, schema/table
  privileges, and the governed legacy-suppression boundary without recording
  credential values. Earlier direct migration run `30398626193` also succeeded
  at source `c28fe240dba336eb4d0279a9d2d70f668472ac4a`.
- Push deployment run `30398321778` failed twice before deployment. Its
  reusable migration job did not receive the environment-scoped database
  secrets, even though the standalone protected-environment migration
  succeeded. Protected main `a177` replaced that broken transport with a
  migration-success `workflow_run` handoff that does not move database secrets
  into the deployer.
- Exact-source deployment run `30399449769` published 53 verified files and
  bound source `a1774f38d61a255d9dd64ed4d8716d27b3d3aaf7`, but its attestation
  failed because `/healthz` and `/readyz` returned HTTP 503. The run is
  `FAILURE`, not a successful production deployment.
- Unauthenticated `/api/build-info` currently reports live revision
  `a1774f38d61a255d9dd64ed4d8716d27b3d3aaf7`, bundle digest
  `1d4ec5859e0ad9e2fe373ec49f04e6870aa597cc5c25f5a13dd3c8c274e22b6f`,
  51 copied files, and `receipt_minted=false`.
- The unauthenticated `/healthz` and `/readyz` probes return HTTP 503 with
  `authentication=CONFIGURED`, `deal_desk_persistence=POSTGRES_UNAVAILABLE`,
  and `persistence_diagnostic=SCHEMA_INCOMPATIBLE`. The surface is source-bound
  but is not production-ready.
- Earlier protected deployment run `30389823219` and drift-check run
  `30389999202` succeeded for source
  `cf59692307de7747cfa2c32401b5dda7ff21d0dd`. Those runs are historical
  evidence, not proof for current main or the current live revision.
- Protected credential-rotation run `30399789320` was dispatched for exact
  `a177` and remains pending the environment gate at this evidence snapshot.
  Replacement production login, protected Frontier Radar access, logout, and
  administrator-vault custody therefore remain `UNVERIFIED`.

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
runs `30398626193` and `30399398519` proved that the two database credentials
were available to directly dispatched protected-environment jobs.

The failed push deployment proves that the former reusable-workflow call did
not receive those environment secrets. Protected main now runs migration
directly on protected-main push and invokes the pinned deployer only from that
exact successful migration event. This successor extracts the unchanged
migration implementation into one checked-in script and removes the unused
`workflow_call` entry point so the environment-only boundary cannot silently
regress.

That source correction is not production proof. The current Space reports
`SCHEMA_INCOMPATIBLE`, and protected rotation run `30399789320` has not yet
produced a secret-free login/logout receipt. Application-credential scope,
effective Hugging Face token scope, and local administrator-vault custody
remain `UNVERIFIED`.

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
