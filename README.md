---
thumbnail: https://huggingface.co/spaces/SZLHOLDINGS/david-leads/resolve/main/og-card.png
title: David Leads — Operator Lead Command
emoji: 🛡️
colorFrom: blue
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
short_description: Public-record lead command with transparent decision traces
tags:
  - insurance
  - lead-intelligence
  - public-data
  - receipts
  - governance
  - szl-holdings
---

# David Leads — Operator Lead Command

David Leads helps insurance operators answer five questions quickly:

1. Who should I call first?
2. Why is this lead timely?
3. What should I do next?
4. What public evidence supports the recommendation?
5. What remains uncertain or blocks contact?

The workspace combines public-record signals, a prioritized work list, next-best actions,
territory coverage, best-fit advisor routing, outcomes, and checkable proof records. The
operator view uses plain language; technical scoring details are kept out of the daily workflow.

## The open-box difference

Every ranked lead has a **Decision Trace**. It shows the source path, the reasons that moved the
lead up or down, contact permission, the recommended human action, proof state, confidence range,
and explicit caveats. A missing contradiction check is shown as `NOT_EVALUATED`; an offline example
is shown as `EXAMPLE`; an unavailable signature is shown as `UNSIGNED`.

The priority score is an advisory work-order signal. It is not a probability, insurance quote,
underwriting decision, consumer report, or permission to contact.

## Operator workflow

- **Find Leads** gathers current public records. If an upstream source is unavailable, fallback
  examples remain visibly labeled instead of being presented as live prospects.
- **Opportunity Desk** turns official business and license records into a research queue with
  explicit stages, next actions, source links, and a fail-closed contact gate. Public visibility
  is never treated as permission to contact.
- **Frontier Radar** adds Department of Labor Form 5500 employer life-plan timing, recent FMCSA
  carrier-entity additions, USAspending contract activity, and EPA ECHO facility monitoring
  activity. The Form 5500 lane reads official monthly bulk disclosures, keeps only organization,
  plan-period, participant-count, and benefit-category fields, and treats the next reported
  anniversary as a research hypothesis rather than a renewal claim. A Chicago organization-license lane is implemented
  but remains gated on documented reuse approval and a Socrata app token; SAM.gov remains
  key-gated; FCC ULS remains unavailable until a durable bulk-ingestion lane exists. Every source
  reports its true state, requests only minimized entity/facility fields, never substitutes
  samples, and keeps every signal out of underwriting.
- **Governed Broker Desk** records a business-published channel, issues a hashed 24-hour clearance
  receipt only after all licensing/suppression checks are affirmative, unlocks a manual call sheet,
  and captures factual outcomes including immediate do-not-call suppression.
- **Decision Trace** opens the complete operator-readable path from source to action.
- **Call Brief** gives a concise opening line and next step for human review.
- **Proof & Sources** exposes the exact evidence record behind a recommendation.
- **Results** records meeting, sale, and no-sale outcomes without presenting modeled results as facts.
- **More tools** contains territory, workforce-event, opt-in, export, routing, and CRM actions.

## Data and safety boundaries

- Public records and explicitly consented submissions only.
- No private data source is presented as part of the lead signal set.
- Contact restrictions can block a lead even when its priority score is high.
- Premium values are illustrative and never quotes.
- Existing coverage must be confirmed with the person before a recommendation.
- Proof records are signed only when a real signing key is configured; otherwise they remain honestly unsigned.
- Social-profile scraping and consumer-data enrichment are prohibited by default. See
  [`PUBLIC_DATA_OPERATING_MODEL.md`](PUBLIC_DATA_OPERATING_MODEL.md).
- Frontier adapters do not request phone, email, named officer, crash/safety, compliance status,
  penalties, community demographics, insurance, or policy fields. Every resulting packet is
  `PROSPECTING_ONLY` and `not_for_underwriting=true`.
- The Form 5500 adapter additionally excludes EINs, signers, preparers, administrators, named
  brokers, commissions, and person-level addresses. Only a reported Schedule A life-benefit
  indicator informs the life/business-protection fit shown in the queue.
- A public record cannot enter `READY` through a checkbox or direct stage change. It requires a
  first-party business channel, named operator, license scope, jurisdiction, talk-track version,
  affirmative suppression/rules checks, and an unexpired clearance receipt.
- Modeled lead segments are not named prospects and cannot be advanced to the broker queue.

## Access configuration

The default deployment mode is `DAVID_ACCESS_MODE=public_readonly`. Visitors can
open a sanitized public-record research view without logging in. That view never
reads or returns saved broker notes, owners, channels, clearances, dispositions,
suppression details, exports, opt-in leads, or workflow history, and it cannot
perform mutations. Set `DAVID_ACCESS_MODE=authenticated` to require login for
the entire application.

Operator credentials remain required for broker workflow changes, exports,
outcomes, call sheets, webhook tests, and other protected actions. Configure
these values in the approved secret store:

- `DAVID_USER`
- `DAVID_PASS`
- `DAVID_ACCESS_KEY`
- `DAVID_DATABASE_URL` for restart-durable opportunity state and immutable workflow events
- `SZL_COSIGN_PRIVATE_PEM` and `SZL_COSIGN_PUBLIC_PEM` for signed proof records
- `CENSUS_API_KEY` for optional higher-capacity Census access

Do not commit credentials or paste them into issues, pull requests, chat, or model cards.
The fail-closed rotation procedure is documented in
[`ops/credential-rotation.md`](ops/credential-rotation.md).
Credential values must stay inside the approved vault's non-displaying administrator flow. No
repository script reads credentials into terminal output, logs, chat, screenshots, or clipboard.

## Source and deployment

- GitHub source of record: public Apache-2.0 repository
  [`szl-holdings/david-leads`](https://github.com/szl-holdings/david-leads)
- Hugging Face runtime: [SZLHOLDINGS/david-leads](https://huggingface.co/spaces/SZLHOLDINGS/david-leads)
- Estate command center: [a-11-oy.com](https://a-11-oy.com)
- Hugging Face organization: [SZLHOLDINGS](https://huggingface.co/SZLHOLDINGS)
- GitHub organization: [szl-holdings](https://github.com/szl-holdings)

The publication boundary and its verification record are documented in
[`PUBLICATION_READINESS.md`](PUBLICATION_READINESS.md).

The GitHub workflow derives the deployed file set from the Dockerfile and performs a post-build
content comparison. A GitHub merge is not a live deployment until that deployment and verification
finish successfully.

The runtime exposes `/api/build-info` with an exact bundle digest and a source revision truth
label. It intentionally reports parity as `UNVERIFIED` inside the process; the pinned deployment
workflow performs the external GitHub-to-Hugging-Face comparison. After a successful exact-source
deployment, GitHub OIDC signs the deployment manifest and the workflow publishes only its
non-secret attestation reference to the Space. `receipt_minted=true` is fail-closed and appears
only when that reference matches the exact running source revision.


Last deployment refresh request: 2026-08-08 (for solo end-to-end operational alignment).
© 2026 SZL Holdings · Apache-2.0
