# Public Revenue Frontier — Publication Readiness

> Status: **PUBLIC · PRODUCTION PATH OPERATIONAL · READY WITH EXPLICIT EXCEPTION**
>
> Scope: `szl-holdings/david-leads` is the revenue-adjacent insurance
> frontier in the nine-repository portfolio.

## Operational evidence

The credential remediation, governed broker desk, and durable persistence path
were observed on 2026-07-28. This evidence is specific to `david-leads`; it is
not an estate-wide claim.

- Protected migration run `30403410802` succeeded for exact protected source
  `41b322c9070886836e7dbdf0a1c371798851a641`.
- Exact-source Hugging Face deployment run `30403452519` succeeded for that
  revision. Its deployment job published the Docker-derived file set, bound the
  protected source revision, attested the running bytes and smoke routes, and
  verified the live source identity.
- The live `/healthz` and `/readyz` probes returned HTTP 200 with
  `authentication=CONFIGURED`, `deal_desk_persistence=POSTGRES_READY`, and
  `persistence_diagnostic=OK`.
- The live `/api/build-info` probe reported the same protected revision, runtime
  bundle digest
  `38cf3d53e219fd7cf35a9b24f0f4fab74330f3ba16c0d0fd05165ba9b7cf86c8`,
  and 51 copied files. The endpoint itself remains
  `github_huggingface_alignment=UNVERIFIED`; the successful exact-source deploy
  attestation is the separate alignment evidence.
- Owner-approved protected rotation run `30403607270` succeeded for the same
  exact protected source. Its secret-free schema-v2 result reported replacement
  login and logout verified, PostgreSQL persistence ready, and
  `credential_values_recorded=false`.
- The repository environment `david-space-credential-rotation` is restricted
  to `main`, has an owner-approval rule, and stores the application,
  runtime-database, and migration-admin credentials as environment secrets.
  Repository secret metadata contains only the scoped Hugging Face publisher.
- The machine-readable evidence record is
  `ops/evidence/david-production-verification-2026-07-28.json`.

This readiness record is itself part of the Docker-copied governance bundle.
A merge that changes a Docker-copied input (`requirements.txt`, `app/**`,
`PUBLICATION_READINESS.md`, `PUBLIC_DATA_OPERATING_MODEL.md`, or
`SPACE_PROVENANCE.json`), the `Dockerfile`, or the deployment workflow must
complete a fresh exact-source deployment and live probe. Other repository
changes do not trigger this deployment and are not covered by its runtime
source-identity evidence. The machine-readable evidence record is deliberately
outside that COPY set so the final exact deployed revision can be recorded
without creating a self-referential deployment loop.

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
- Chicago business-license research is Illinois-only and remains unavailable
  until both reuse approval and a Socrata app token are configured. SAM.gov
  remains explicitly key-required. FCC ULS remains unavailable until a durable
  baseline/delta ingestion lane exists; its large mixed-person archives are
  never downloaded on the request path.
- Social-profile scraping, personal/free-mail enrichment, purchased people
  data, automated voice, robotext, and autodialing are outside this release.

## Credential authority

The historical credential triplet remains permanently revoked because it was
published in tracked handoff/demo artifacts. Removing values from the current
tree cannot revoke external copies.

Current repository secret metadata lists only the scoped Hugging Face
deployment token. Application, runtime-database, and migration-admin
credentials are stored in the owner-approved, `main`-only
`david-space-credential-rotation` environment. The protected migration and
rotation workflows have both completed successfully with owner approval.
Credential values were not emitted into committed evidence or workflow result
records. Local administrator-vault custody remains an operator responsibility
and is not asserted by this repository.

If any current factor may have been disclosed, pause the Space, replace all
application and database values from the approved vault, verify health,
replacement login/logout, exact-source deployment, and drift, then revoke the
administrator session used for rotation.

## Durable broker contract

The following fail-closed contract is deployed and backed by the measured
PostgreSQL-ready runtime above:

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

## Release receipt boundary

The last measured baseline above reported `receipt_minted=false`. Releases
containing the current deployment workflow add a second, cryptographic step:
after the reusable deployer verifies exact running bytes, GitHub OIDC signs the
exact `hf-deploy-manifest.json` and stores the attestation in GitHub. The
workflow then writes only the non-secret attestation reference to Hugging Face
and waits for the restarted runtime to expose the matching source revision,
manifest digest, attestation ID, and URL.

The live `/api/build-info` result remains authoritative:
`receipt_minted=true` means the reference matches the exact running revision;
otherwise the receipt is `UNAVAILABLE`. A green deployment or HTTP 200 alone
does not imply that a release receipt was minted.

## Operational caution

Public visibility is not fully reversible because external readers can retain
copies. If a post-publication issue is found, contain the affected surface,
rotate any exposed credential through the approved local authority, and publish
a correction record. No ruleset, branch-protection, required-review,
required-check, bypass-actor, or governance-workflow weakening is part of this
release.
