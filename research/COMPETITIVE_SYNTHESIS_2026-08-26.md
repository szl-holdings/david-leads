# Competitive synthesis — Evidence Constellation

**Observed:** 2026-08-26

**Scope:** organization-level, official-public-data insurance opportunity research
**Implementation rule:** clean-room synthesis only; no competitor source code, proprietary data,
copy, screenshots, brand assets, contact databases, or private-person enrichment.

## Product position

David Leads is not another purchased lead list. It is an evidence-backed B2B insurance
opportunity system: official organization events, conservative entity resolution, a visible
evidence clock, counter-evidence, human permission, and a replayable receipt.

The retired `research/LEADERS_RECON.md` contains person-level concepts that are outside the
current operating model. Obituaries, family events, named donors or executives, personal
property, wealth proxies, social profiles, phone/email enrichment, and private-contact scraping
must not return.

## Current functional benchmarks

These are product-pattern benchmarks, not an audited market-share ranking. Scale and performance
claims on vendor pages remain vendor claims.

| Benchmark | Publicly described strength | Clean-room David Leads adaptation |
|---|---|---|
| [Zywave miEdge](https://www.zywave.com/products/miedge/) | Insurance-specific filters, employer profiles, timing intelligence, cross-source research | Build deeper official-source organization dossiers; exclude purchased contacts, household data, and opaque insurance profiles |
| [LeO](https://www.meetleo.com/pricing?lp=homepage) | Insurance search, Form 5500 coverage, X-dates, action-oriented research | Use an official-event clock; label a Form 5500 anniversary as a timing hypothesis, never a renewal |
| [AgencyZoom Smart Cycle](https://support.agencyzoom.com/en/articles/12481686-use-smart-cycle-to-automatically-recycle-leads) | Evidence/date-aware lead recycling with history and ownership | Resurface an organization only after a documented recheck or genuinely new official event |
| [Apollo Prospect & Enrich](https://www.apollo.io/product/prospect-and-enrich) | Dense filters, saved searches, configurable scoring, enrichment workflows | Organization-only watchlists and transparent rules; no proprietary contact or behavioral-intent data |
| [Clay Signals](https://www.clay.com/signals) | Multi-signal account workflows | Approved official-source bundles with source terms, field allowlists, refresh intervals, and retention visible |
| [Attio Workflows](https://attio.com/help/reference/attio-101/introduction-to-workflows) | Trigger-to-step workflows over flexible records | Versioned, previewable workflow plans with actor, filters, source revisions, and output hashes |
| [Affinity Sourcing](https://www.affinity.co/press-release/affinity-sourcing-to-transform-deal-discovery-for-investors) | Deal sourcing, growth signals, relationship context | Separate deliberately recorded first-party relationship facts from official public evidence; never mine private networks silently |

The synthesis is: insurance timing breadth, evidence-aware resurfacing, strong filtering, signal
composition, durable workflows, and deal context—rebuilt around official sources and a Boolean
permission gate.

## Original capability: Evidence Constellation

```text
official observations
  -> normalized event hashes
  -> deterministic-first organization resolution
  -> corroboration and counter-evidence
  -> proof grade plus evidence clock
  -> fail-closed permission state
  -> human action
  -> replayable signed or honestly unsigned packet
```

### Deterministic-first organization graph

Shared authoritative identifiers such as UEI, CIK, USDOT, and EPA FRS ID may create a
deterministic cross-source link. Exact normalized legal name + state + ZIP may create only a
review-required candidate. Fuzzy/probabilistic resolution is not enabled until a labeled company
matching benchmark exists; any future probabilistic link must remain advisory and explain its
evidence.

### Four dimensions stay separate

- **Offering fit:** a documented research hypothesis, not underwriting or guaranteed need.
- **Moment:** event age, recheck time, expiry, and stale state.
- **Proof:** authority, freshness, corroboration, integrity, and identity basis.
- **Permission:** `PUBLIC_RESEARCH_ONLY`, `BLOCKED`, `RESEARCH`, or time-limited `CLEARED`.

The UI must answer why now, why this organization, why the link may be wrong, when the evidence
must be rechecked, what would reverse the recommendation, and whether action is permitted.

### Bounded evidence-agent roles

- Scout reads only approved official adapters and proposes organization events.
- Resolver proposes entity links and exposes the matching basis.
- Skeptic searches approved sources for stale, conflicting, withdrawn, or duplicate observations.
- Policy evaluates purpose, jurisdiction, licensing, suppression, and channel clearance.
- Brief writes from accepted evidence and citations only.
- Auditor recomputes hashes, rules, expiry, and receipt state.

Agents cannot create people, unlock contact, send messages, dial, change suppression state, or
sign a receipt without the deterministic policy gate.

## Permissive technical references

No code from these projects is incorporated by this change. They are documented candidates for
future, separately reviewed work.

| Project | License | Potential use |
|---|---|---|
| [Splink](https://github.com/moj-analytical-services/splink) | MIT | Explainable probabilistic organization resolution after deterministic identifiers |
| [Dedupe](https://github.com/dedupeio/dedupe) | MIT | Alternative trainable linkage engine; choose one after benchmarking |
| [DuckDB](https://github.com/duckdb/duckdb) | MIT | Local scans/joins over official bulk CSV, JSON, and Parquet |
| [OpenLineage](https://github.com/OpenLineage/OpenLineage) | Apache-2.0 | Dataset, job, and run lineage concepts |
| [Great Expectations](https://github.com/great-expectations/great_expectations) | Apache-2.0 | Offline ingestion contracts and data-quality assertions |
| [Atomic CRM](https://github.com/marmelab/atomic-crm) | MIT | Attributed CRM component patterns after asset/dependency review |
| [Apache ECharts](https://github.com/apache/echarts) | Apache-2.0 | Self-hosted evidence timelines and graphs |
| [Sigstore Cosign](https://github.com/sigstore/cosign) | Apache-2.0 | Continue exact-source deployment attestation |
| [USAspending API](https://github.com/fedspendingtransparency/usaspending-api) | CC0-1.0 | Public-domain endpoint contracts and fixtures |

[Twenty CRM](https://github.com/twentyhq/twenty/blob/main/LICENSE) is AGPL-3.0, not permissive.
Study of its public behavior does not authorize incorporating its source into this Apache-2.0
hosted service.

## Demo acceptance contract

1. Show current official-source health and fetch timestamps.
2. Open a real organization event with its source URL, normalized hash, and receipt.
3. Show authoritative identifiers or a review-required exact-match explanation.
4. Show proof grade, why-now, counter-evidence, recheck date, and expiry.
5. Demonstrate that public records do not unlock contact.
6. Independently replay the proof packet.
7. Force a source unavailable or an event stale and show the honest state.
8. Show the exact GitHub revision, Hugging Face revision, byte parity, and release attestation.

## Source and licence discipline

Code licence and source-data permission are separate. Every new adapter needs a stable official
endpoint or bulk path, field allowlist, permitted purpose, retention rule, refresh interval, and
failure state. MIT and Apache code require their notices; Apache modifications must be marked;
CC0 may be reused broadly but should still be cited. Proprietary data and incompatible code stay
out.
