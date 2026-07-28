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
- **Decision Trace** opens the complete operator-readable path from source to action.
- **Call Brief** gives a concise opening line and next step for human review.
- **Proof & Sources** exposes the exact evidence record behind a recommendation.
- **Results** records meeting, sale, and no-sale outcomes without presenting modeled results as facts.
- **More tools** contains territory, wealth, workforce-event, opt-in, export, routing, and CRM actions.

## Data and safety boundaries

- Public records and explicitly consented submissions only.
- No private data source is presented as part of the lead signal set.
- Contact restrictions can block a lead even when its priority score is high.
- Premium values are illustrative and never quotes.
- Existing coverage must be confirmed with the person before a recommendation.
- Proof records are signed only when a real signing key is configured; otherwise they remain honestly unsigned.
- Social-profile scraping and consumer-data enrichment are prohibited by default. See
  [`PUBLIC_DATA_OPERATING_MODEL.md`](PUBLIC_DATA_OPERATING_MODEL.md).
- Modeled lead segments are not named prospects and cannot be advanced to the broker queue.

## Access configuration

Configure these values in the approved secret store for the deployment:

- `DAVID_USER`
- `DAVID_PASS`
- `DAVID_ACCESS_KEY`
- `SZL_COSIGN_PRIVATE_PEM` and `SZL_COSIGN_PUBLIC_PEM` for signed proof records
- `CENSUS_API_KEY` for optional higher-capacity Census access

Do not commit credentials or paste them into issues, pull requests, chat, or model cards.

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
workflow performs the external GitHub-to-Hugging-Face attestation.

© 2026 SZL Holdings · Apache-2.0
