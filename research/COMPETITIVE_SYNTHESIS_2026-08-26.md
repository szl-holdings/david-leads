# Competitive synthesis — Evidence Constellation

**Observed:** 2026-08-28

**Scope:** organization-level, official-public-data insurance opportunity research
**Implementation rule:** clean-room synthesis only; no competitor source code, proprietary data,
copy, screenshots, brand assets, contact databases, or private-person enrichment.

## Product position

David Leads is not another purchased lead list. It is an evidence-backed B2B insurance
opportunity system: official organization events, conservative entity resolution, a visible
evidence clock, counter-evidence, human permission, and a session-verifiable receipt. Current
receipt storage is bounded process memory: `SESSION_VERIFIABLE_REFERENCE`, `PROCESS_MEMORY`, and
`historical_replay=false`. Durable independent replay remains a future capability until an
immutable receipt store is implemented and witnessed across restart.

The retired `research/LEADERS_RECON.md` contains person-level concepts that are outside the
current operating model. Obituaries, family events, named donors or executives, personal
property, wealth proxies, social profiles, phone/email enrichment, and private-contact scraping
must not return.

## Current functional benchmarks

This is a current primary-source product-pattern benchmark, not an audited market-share ranking.
Product capabilities, scale, accuracy, and performance remain vendor claims. The adaptation column
describes clean-room product lessons, not authorization to copy code, copy, design, data, models,
screenshots, or brand assets.

| Benchmark | Publicly documented product pattern | Clean-room David Leads adaptation |
|---|---|---|
| [ZoomInfo](https://www.sec.gov/Archives/edgar/data/1794515/000179451526000012/zi-20251231.htm) | Its current Form 10-K describes public and proprietary data collection, entity standardization and matching, verification and cleaning, human-in-the-loop review, signals, and CRM-connected products | Use an explicit official observation -> normalized event -> entity candidate -> proof -> workflow pipeline, with analyst review when deterministic matching is unavailable; exclude contacts, proprietary sources, and intent data |
| [D&B Hoovers](https://www.dnb.com/en-us/products/dnb-hoovers.html) | Company research, targeted lists, news/change alerts, corporate linkages, prospect scoring, and integrations | Build official-record organization profiles, deterministic public-ID links, and change watchlists; do not ingest D&B data, D-U-N-S relationships, contacts, intent, or scores without a separate license and admission review |
| [LinkedIn Sales Navigator](https://business.linkedin.com/sell/sales-navigator?src=li-help) | Account IQ, filters, alerts, CRM integration, Relationship Map, and Relationship Explorer | Build an organization-centered evidence workspace and source-dependency graph; do not scrape LinkedIn or recreate named-person, social-activity, or private-relationship graphs |
| [Apollo Prospect & Enrich](https://www.apollo.io/product/prospect-and-enrich) | Dense filters, personas, saved-search alerts, enrichment, and a Data Health Center | Provide transparent filters over approved official-event fields, saved organization watchlists, and source-health status; a proof grade is not a propensity-to-buy score |
| [Zywave miEdge](https://www.zywave.com/products/miedge/) | Insurance-specific search, employer and household profiles, alerts, and a mix of official and proprietary sources, including Form 5500, DOT, and OSHA data | Build line-specific official-source dossiers and timing hypotheses; exclude household and person data, and never claim policy, broker, carrier, premium, or renewal knowledge without permitted authoritative evidence |
| [Applied Epic](https://www1.appliedsystems.com/en-us/solutions/for-agents/agency-management-system/applied-epic) | Prospecting, pipeline management, quoting and submissions, policy and document management, role dashboards, permissions, and insurer connectivity in an AMS | Act as a pre-AMS organization research and qualification layer with a human-cleared handoff; do not present David Leads as an AMS, quote, policy record, coverage determination, or underwriting system |
| [Sayari Graph](https://sayari.com/platform/graph/) | Multi-layer entity/network visualization with source-linked connections and evidence packages carrying primary-source citations | Make every graph edge inspectable through its approved identifier, source URL, retrieval time, hash, resolution basis, and counter-evidence; do not use Sayari's proprietary data, ontology, risk models, copy, or design |

Two narrower workflow references remain useful when accurately bounded. [AgencyZoom Smart
Cycle](https://support.agencyzoom.com/en/articles/12481686-use-smart-cycle-to-automatically-recycle-leads)
documents date/event-triggered recycling with notes and owner continuity; it does not document
evidence-backed revalidation. [Attio Workflows](https://attio.com/help/reference/automations/workflows/create-a-workflow)
documents trigger-to-step workflows, drafts and publishing, access control, run inspection, and
version-pinned in-progress runs. David Leads should resurface an organization only after a
documented recheck or genuinely new official event, and should pin every evidence workflow run to
its published rule and source revisions.

The synthesis is: insurance-specific context, official-event watchlists, strong filtering,
source health, inspectable evidence graphs, versioned workflows, and producer handoff—rebuilt
around approved public sources and a fail-closed permission state machine.

## Original capability: Evidence Constellation

```text
official observations
  -> normalized event hashes
  -> deterministic-first organization resolution
  -> corroboration and counter-evidence
  -> proof grade plus evidence clock
  -> fail-closed permission state
  -> human action
  -> session-verifiable packet with explicit signature and persistence state
```

### Deterministic-first organization graph

Shared authoritative identifiers such as UEI, CIK, USDOT, and EPA FRS ID may create a
deterministic cross-source link. Exact normalized legal name + state + ZIP may create only a
review-required candidate. Fuzzy/probabilistic resolution is not enabled until a labeled company
matching benchmark exists; any future probabilistic link must remain advisory and explain its
evidence.

No deterministic multi-source organization is currently witnessed. At the audited production
observation `2026-08-28T02:41:46Z`, 72 live events formed 70 entity groups and zero multi-source
groups. Counts are drift-prone, but the current namespace limitation is structural: DOL emits a
filing/acknowledgement identifier rather than an organization identifier, FMCSA emits USDOT,
USAspending emits UEI, and EPA ECHO emits EPA FRS. None of those organization-ID namespaces is
currently emitted by a second active lane. The UI must therefore label cross-source deterministic
linking as supported by rule when a shared approved identifier exists, not as a live demonstrated
result. Same-source repeats may form deterministic groups; exact name/state/ZIP remains review-only.

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

This research does not authorize incorporating code, assets, or data from these projects. Any
future use requires a separate exact-revision dependency, source, asset, and license review.
Whether referenced code is already present in the service must be established by a provenance
inventory or SBOM; this research note does not prove its absence.

| Project | Repository code license | Potential use |
|---|---|---|
| [Splink](https://github.com/moj-analytical-services/splink) | MIT | Explainable probabilistic organization resolution after deterministic identifiers |
| [Dedupe](https://github.com/dedupeio/dedupe) | MIT | Alternative trainable linkage engine; choose one after benchmarking |
| [DuckDB](https://github.com/duckdb/duckdb) | MIT | Local scans/joins over official bulk CSV, JSON, and Parquet |
| [OpenLineage](https://github.com/OpenLineage/OpenLineage) | Apache-2.0 | Dataset, job, and run lineage concepts |
| [Great Expectations](https://github.com/fivetran/great_expectations) | Apache-2.0 | Offline ingestion contracts and data-quality assertions |
| [Atomic CRM](https://github.com/marmelab/atomic-crm) | MIT | Attributed CRM component patterns after asset/dependency review |
| [Apache ECharts](https://github.com/apache/echarts) | Apache-2.0 | Self-hosted evidence timelines and graphs |
| [Sigstore Cosign](https://github.com/sigstore/cosign) | Apache-2.0 | Continue exact-source deployment attestation |
| [USAspending API](https://github.com/fedspendingtransparency/usaspending-api) | CC0-1.0 | Review API-code contracts and fixtures; the repository license does not grant blanket permission for every upstream or endpoint-returned dataset |

[Twenty CRM](https://github.com/twentyhq/twenty/blob/main/LICENSE) is mixed-license: its current
license says the project is mostly AGPLv3, enterprise-marked files are commercial, and selected
packages are MIT, with an application exception and no trademark grant. Study of public behavior
does not authorize incorporating its source, enterprise files, or marks into this Apache-2.0
hosted service.

## Demo acceptance contract

1. Show current official-source health and fetch timestamps.
2. Open a real organization event with its source URL, normalized hash, and session receipt.
3. Show authoritative identifiers or a review-required exact-match explanation.
4. Show proof grade, why-now, counter-evidence, recheck date, and expiry.
5. Demonstrate that public records do not unlock contact.
6. Verify the current-session packet, show `PROCESS_MEMORY` and `historical_replay=false`, and
   demonstrate that an unavailable historical receipt fails closed.
7. Force a source unavailable or an event stale and show the honest state.
8. Show the exact GitHub revision, Hugging Face revision, byte parity, and release attestation.

## Source and licence discipline

Code licence and source-data permission are separate. Every new adapter needs a stable official
endpoint or bulk path, field allowlist, permitted purpose, retention rule, refresh interval, and
failure state. MIT and Apache code require their notices; Apache modifications must be marked;
a repository's CC0 code license may permit broad code reuse but does not override the terms,
privacy duties, or upstream provenance of data returned by an endpoint. Proprietary data and
incompatible code stay out.
