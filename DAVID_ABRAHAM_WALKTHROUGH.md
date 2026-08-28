# David Leads - current client walkthrough

This walkthrough is for the current Evidence-Backed Broker Research workspace at
<https://szlholdings-david-leads.hf.space/>. It is an organization-only public
research demo. It is not a person-level prospect list, buying-intent model, or
permission-to-contact system.

Before presenting, verify the exact running release and current source states as
described in [`HANDOFF_FOR_STEPHEN.md`](HANDOFF_FOR_STEPHEN.md). Counts below are
deliberately not fixed because every source pull can change.

## One-sentence takeaway

> David Leads turns official organization records into an evidence-backed
> research queue: what changed, why the timing may matter, what proves it, what
> contradicts it, and what a licensed human must clear before outreach.

## 1. Open the public research workspace

Open the live URL. The public research view does not require a username,
password, or access key. It exposes sanitized organization and facility records
only. Saved notes, channels, clearances, dispositions, exports, and other
operator actions remain protected.

Say:

> Public access lets us inspect official evidence. It never creates consent or
> permission to contact anyone.

## 2. Read the release and data state

Point to the release stamp and the data-state indicator.

- The release stamp identifies the running source revision.
- The data-state indicator reports how many source lanes answered live in this
  pull.
- `UNAVAILABLE` is a real state, not a hidden failure and not a zero-demand
  claim.

Do not say the current release is aligned with GitHub unless `/api/build-info`
and the deployment evidence bind the same exact revision.

## 3. Choose a market

Choose **All East**, a region, or one state. A state selection narrows the query
and can return a different record set. Explain that the interface shows current
official-source observations; it does not fill gaps with sample prospects.

## 4. Show source health

Open **Market coverage**. For each source, read the state shown on screen:

- `LIVE`: the adapter completed a current observation, which may contain zero or
  more records;
- `UNAVAILABLE`: the adapter could not complete and returned no substitute; or
- `NOT_APPLICABLE`: the source does not cover the selected territory.

Use an available official citation to demonstrate that records remain
independently checkable.

## 5. Open an organization record

Choose a current record and explain these fields in order:

1. **Source-verified business moment** - the organization-level fact returned by
   the official source.
2. **Timing** - an observation or recheck window, not proof of a renewal,
   dissatisfaction, purchase, or insurance need.
3. **Likely fit** - a research question, not a recommendation, eligibility
   decision, or quote.
4. **Proof grade** - evidence quality only, never sales probability.
5. **Evidence clock** - `CURRENT`, `RECHECK_DUE`, `STALE`, or `UNKNOWN`.
6. **Counter-evidence** - missing corroboration, identity-review needs, stale
   evidence, source limitations, and other facts that can weaken the case.
7. **Permission** - `PUBLIC_RESEARCH_ONLY` until the protected human-clearance
   process is complete.

Open the source link. Confirm the organization, source-record identifier, date,
and displayed event before using the card in any decision.

## 6. Show Evidence Constellation

Open **Investor view** and point out that Evidence Constellation does not collapse
different questions into one score:

- identity links can be deterministic, review-required, or unresolved;
- corroboration can be single-source or multi-source;
- authority, freshness, source-receipt integrity, and identity remain separate;
- the clock states when evidence must be checked again; and
- counter-evidence is visible on every organization event.

If the current pull contains no deterministic multi-source organization, say so.
Zero is an observed result, not a reason to imply corroboration.

## 7. Verify a source receipt

Select **Verify source receipt**. Read the returned fields rather than reducing
them to one green badge:

- **Signature** says whether the configured public key verifies the receipt.
- **Payload integrity** says whether the bound receipt payload re-derives.
- **Predecessor chain** distinguishes a verified predecessor, declared genesis,
  an unverified predecessor, and failure.
- **Claim scope** states exactly what the verification covers.
- **Witness** reports threshold state, signing mode, and durability.

The current public receipt cache is process memory. A session-verifiable source
reference is not a durable historical archive, and the receipt does not cover
later identity resolution, grade, clock, or counter-evidence.

## 8. Show the contact gate

Return to the record and point to the permission state. The protected broker
workflow requires a first-party business channel, a named operator, license and
jurisdiction scope, talk-track version, suppression and rules checks, and an
unexpired clearance receipt. If any required check is absent, contact remains
blocked.

## 9. Close

Say:

> This is useful because it preserves the difference between evidence and
> action. David sees the official observation, its limits, and its proof before
> deciding what to research. Outreach remains a separate, accountable human
> decision.

## Claims to avoid

- Do not call an organization record a person who is ready to buy.
- Do not promise appointments, conversion, premium, revenue, or pipeline.
- Do not infer wealth, health, family status, insurability, or a coverage gap.
- Do not call a source live when the current source panel says unavailable.
- Do not say every receipt is signed; unsigned is the correct state when no real
  signing key is configured.
- Do not say the predecessor chain or witness is durable when the response says
  process-ephemeral or unverified.
- Do not present the retired portable HTML, historic V8 artifacts, or old
  person-level walkthroughs as the current product.

The short operating guide is [`FOR_DAVID.md`](FOR_DAVID.md).
