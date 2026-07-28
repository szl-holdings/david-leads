# Public Revenue Frontier — Publication Readiness

> Status: **PUBLIC · CURRENT LIVE SOURCE OBSERVED · c28fe DEPLOYMENT WITHHELD**
>
> Readiness gate: **WITHHELD**. Protected source
> `c28fe240dba336eb4d0279a9d2d70f668472ac4a` has local and migration
> evidence, but it is not the live Hugging Face revision. Current
> administrator-login, credential-custody, and exact-source deployment evidence
> remain `UNVERIFIED`. These are blocking evidence gaps, not operational
> exceptions.
>
> Scope: `szl-holdings/david-leads` is the revenue-adjacent insurance
> frontier in the nine-repository portfolio.

## Current and historical evidence

The evidence below was observed on 2026-07-28. It is source-specific and is not
an estate-wide claim.

- Protected main `c28fe240dba336eb4d0279a9d2d70f668472ac4a`
  completed the operational-safety workflow in run `30398321189`.
- Protected standalone migration run `30398626193` completed successfully for
  that exact source. It applied and verified schema version 2, the separate
  least-privilege runtime role, service-table ownership, schema/table
  privileges, and the governed legacy-suppression boundary without recording
  credential values.
- Push deployment run `30398321778` failed twice before deployment. Its
  reusable migration job did not receive the environment-scoped database
  secrets, even though the standalone protected-environment migration
  succeeded. The live Space was not changed by those failed attempts.
- Unauthenticated `/api/build-info` currently reports live revision
  `0b4eab46ce524501d92e3def5ddc47bcfbe541da`, bundle digest
  `7adfe53b91461fd16454c439e135ce398278432a633dc4b9c35fea60b7fbbaea`,
  50 copied files, and `receipt_minted=false`. It does not report `c28fe`.
- The unauthenticated `/healthz` and `/readyz` probes returned HTTP 200 with
  `authentication=CONFIGURED`, `deal_desk_persistence=POSTGRES_READY`, and
  `persistence_diagnostic=OK` for the older live source. HTTP health is not
  exact-source proof for `c28fe`.
- Earlier protected deployment run `30389823219` and drift-check run
  `30389999202` succeeded for source
  `cf59692307de7747cfa2c32401b5dda7ff21d0dd`. Those runs are historical
  evidence, not proof for current main or the current live revision.
- Replacement production login, protected Frontier Radar access, logout, and
  administrator-vault custody are `UNVERIFIED` here because no exact
  non-secret evidence record was available.

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
an owner-review rule and a protected-main branch policy, and exact-source
migration run `30398626193` proved that the two database credentials were
available to a directly dispatched protected-environment job.

The failed push deployment proves that the former reusable-workflow call did
not receive those environment secrets. This successor therefore runs the
shared checked-in migration script from a normal protected-environment job
before invoking the pinned deployer. This source correction is not production
proof until it is reviewed, merged normally, and completes an exact-source
migration, deployment, live probe, and independent drift check. Current
application-credential scope, effective Hugging Face token scope, and local
administrator-vault custody remain `UNVERIFIED`.

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
