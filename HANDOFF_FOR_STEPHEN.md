# David Leads - release and demo handoff

**Audience:** Stephen and anyone presenting David Leads to David Abraham, a
broker, a manager, or an investor.

**Active product:** Evidence-Backed Broker Research, an organization-only public
research workspace backed by official-source observations.

This handoff describes the current product. For the operating boundary, read
[`README.md`](README.md) and [`FOR_DAVID.md`](FOR_DAVID.md). Historical person-level
scoring concepts are retired and must not be used in a demo.

## What is real

- The public workspace opens without a login in `public_readonly` mode.
- Every displayed item is an organization or facility observation from an
  official source. The live path never substitutes a sample record.
- Each source reports `LIVE`, `UNAVAILABLE`, or `NOT_APPLICABLE`; an outage is
  visible and is not converted into a zero-demand claim.
- Evidence Constellation keeps authority, freshness, corroboration,
  source-receipt integrity, identity, the evidence clock, and counter-evidence
  separate.
- Proof grades describe evidence quality. They are not conversion probabilities,
  intent scores, quotes, eligibility decisions, or underwriting scores.
- Public evidence grants permission to research only. Call-ready remains zero
  until an authenticated human completes the protected clearance workflow.

## What is not claimed

David Leads does not identify people who are ready to buy. It does not infer a
family event, wealth, health, insurability, an existing coverage gap, a renewal,
or consent to contact. It does not promise appointments, premium, revenue, or a
conversion rate. It does not scrape social profiles or expose hidden contact
details.

## Before the meeting

1. Open <https://szlholdings-david-leads.hf.space/> and allow the Space to wake.
2. Verify `/api/build-info` reports the exact GitHub revision intended for the
   demo and a matching release-attestation reference. A merge or HTTP 200 alone
   is not deployment proof.
3. Verify `/healthz` and `/readyz`. Do not describe an unavailable dependency as
   ready.
4. Open **Market coverage** and note which source lanes are live for this pull.
5. Open at least one official citation and one source-receipt verification before
   the meeting. Record counts and source states can change between pulls.
6. Keep [`FOR_DAVID.md`](FOR_DAVID.md) available as the plain-language operating
   guide.

No credentials belong in this repository, a slide, a chat, or a demo recording.
Operator-only actions use credentials from the approved secret store.

## Two-minute demo

### 0:00-0:20 - Set the boundary

Open the public workspace and say:

> David Leads organizes current official organization records into a research
> queue. It tells you what changed, why the timing may deserve attention, what
> evidence supports the card, and what still blocks contact.

Point to the public-data boundary and call-ready count. Explain that public
visibility never creates permission to call, email, market, quote, or underwrite.

### 0:20-0:45 - Show current source health

Open **Market coverage**. Read the current `LIVE`, `UNAVAILABLE`, and
`NOT_APPLICABLE` states from the screen. Do not quote an older record count or
source state from a document.

### 0:45-1:15 - Open one organization

Open a current record and walk through:

1. the source-verified business moment;
2. the timing or recheck window;
3. likely fit as a research hypothesis;
4. the proof grade and its separate dimensions;
5. counter-evidence and limitations; and
6. the `PUBLIC_RESEARCH_ONLY` permission state.

Open the official citation. If it does not confirm the displayed organization
and event, stop and do not use the record.

### 1:15-1:40 - Verify the source receipt

Select **Verify source receipt** and narrate exactly what the response says:

- signature state;
- payload-integrity state;
- predecessor-chain state;
- claim scope; and
- witness state, mode, and durability.

A source receipt binds the normalized source-record reference for the current
runtime session. It does not cover later organization resolution, proof grade,
clock, counter-evidence, or a durable historical archive.

### 1:40-2:00 - Close on the operating workflow

Open **Investor view** and show the release identity, source health, proof-grade
distribution, evidence clock, identity-review count, and session-verifiable
source-reference count. Close with:

> Use David Leads to decide what to research first. Use the official record to
> verify why. Use the protected clearance process to decide whether contact is
> permitted.

## If the live pull is slow or unavailable

- The shell opens after public access is confirmed; source retrieval can finish
  afterward.
- Wait for the current pull or use the visible retry control.
- Never use `David_Leads_PORTABLE.html` as fallback data. It is a retained,
  retired historical artifact and is labeled **DO NOT USE**.
- Never present cached, sample, or historical records as the current pull.

## Diligence links

- Runtime: <https://szlholdings-david-leads.hf.space/>
- Source: <https://github.com/szl-holdings/david-leads>
- Publication contract: [`PUBLICATION_READINESS.md`](PUBLICATION_READINESS.md)
- Data boundary: [`PUBLIC_DATA_OPERATING_MODEL.md`](PUBLIC_DATA_OPERATING_MODEL.md)
- Third-party notices: [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)

Copyright 2026 SZL Holdings. Apache-2.0.
