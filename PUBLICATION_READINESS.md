# Public Revenue Frontier — Publication Readiness

> Status: **PUBLIC · cf596 SOURCE ALIGNMENT MEASURED · SUCCESSOR NOT READY**
>
> Scope: `szl-holdings/david-leads` is the revenue-adjacent insurance
> frontier in the nine-repository portfolio.

## Operational evidence

The credential-remediation and governed broker-desk release was observed on
2026-07-28. The evidence below is specific; it is not an estate-wide claim.

- Protected deployment run `30389823219` completed successfully for source
  `cf59692307de7747cfa2c32401b5dda7ff21d0dd`.
- Independent drift-check run `30389999202` succeeded for that exact revision.
- The unauthenticated `/healthz` and `/readyz` probes returned HTTP 200 with
  `authentication=CONFIGURED`, `deal_desk_persistence=POSTGRES_READY`, and
  `persistence_diagnostic=OK`.
- The live `/api/build-info` probe reported the exact protected revision,
  runtime bundle digest
  `ec6f20d49e4b7c9c15befb1bb0128e5d2cdd9e51ab7ebf4628950fe540f4932b`,
  and 50 copied files. The endpoint still reports
  `github_huggingface_alignment=UNVERIFIED`; the independent drift run is the
  separate measured alignment evidence.
- Earlier source `1e27921013f6f92419170b41cd4646aee38b64fc` passed CI in run
  `30388869705`, deployed in run `30388870254`, and passed drift run
  `30389219959`. Those runs are historical evidence, not proof for the current
  revision.
- Neon preflight run `30388377093` succeeded on earlier source
  `b35bbfa7db2de64dd8307d86747bc5626f084547`; it is not exact-source proof for
  `1e27921013f6f92419170b41cd4646aee38b64fc`. The repository had no GitHub
  environments when audited, so this run was not protected-environment proof.
- Replacement production login, protected Frontier Radar access, logout, and
  administrator-vault custody are `UNVERIFIED` here because no exact
  non-secret evidence record was available.
- Repository secret metadata listed only `HF_TOKEN`, but the required protected
  environment did not exist. Environment-bound migration, verification, and
  rotation therefore remain unavailable until a repository administrator
  creates and protects it.

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

Repository secret metadata lists only the scoped Hugging Face deployment token.
The proposed successor moves application, runtime-database, and migration-admin
credentials into an owner-approved, protected-main-only GitHub environment so
only the explicitly bound rotation, migration, and verification jobs can use
them. That environment was absent at the audit snapshot, so its protection,
secret placement, and local administrator-vault custody are not yet proved.
The successor must remain draft until those controls exist.

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
