# David Leads — Public Data Operating Model

> Reviewed 2026-07-28. Operational guardrail, not legal advice. Public visibility
> is not permission to scrape, profile, resell, or contact.

## Product decision

David Leads is an entity-level B2B opportunity-intelligence system for a broker.
It is not a consumer-profile marketplace, an underwriting engine, a data broker,
or an automated outreach system.

The operating chain is:

```text
official observation
  -> resolved business entity
  -> corroborated event
  -> research-only opportunity
  -> current-source verification
  -> business contact-channel verification
  -> execution-time outreach clearance
  -> human call / meeting
  -> disposition and follow-up
  -> measured conversion
```

The product must never turn a modeled persona, aggregate statistic, or sample row
into a callable person.

## Best first vertical: commercial trucking

Commercial trucking is the strongest expansion wedge because FMCSA exposes
machine-readable official entity, fleet, inspection, authority, and insurance
filing data. A broker can receive an auditable renewal or coverage-event queue
without LinkedIn scraping.

High-value official datasets:

- [FMCSA Company Census](https://data.transportation.gov/Trucking-and-Motorcoaches/Company-Census-File/az4n-8mr2)
- [Motor Carrier Census](https://data.transportation.gov/Trucking-and-Motorcoaches/SMS-Input-Motor-Carrier-Census-Information/kjg3-diqy)
- [Carrier history](https://data.transportation.gov/Trucking-and-Motorcoaches/Carrier-All-With-History/u4i8-4m26)
- [Insurance filing history](https://data.transportation.gov/Trucking-and-Motorcoaches/Motus-Insur-All-With-History/c5y8-a4uz)
- [Vehicle inspections](https://data.transportation.gov/Trucking-and-Motorcoaches/Vehicle-Inspection-File/fx4q-ay7w)

### Implemented now

`Frontier Radar` queries the FMCSA Company Census for recent active entity
additions and selects only legal/DBA name, USDOT identifier, addition date,
carrier class, equipment/driver counts, and physical business location. It does
not request phone, email, named officer, crash, safety-rating, insurance, or
policy fields. Every row is `PROSPECTING_ONLY`, `not_for_underwriting=true`, and
requires a current SAFER check before a broker can record contact clearance.

The second implemented lane queries [USAspending](https://api.usaspending.gov/docs/intro-tutorial)
for recent federal contract activity between $25,000 and $10 million. It retains
the recipient entity name, UEI, business location, agency, award identifier,
amount, dates, and description. The interface explicitly warns that the search
window may reflect a modification to an older award; award amount is never
presented as revenue, cash flow, insurance need, or a newly signed contract.

The third implemented lane uses the documented
[EPA ECHO web service](https://echo.epa.gov/tools/web-services) for small, on-demand
facility research. It selects only facility name/address, FRS identifier, NAICS,
and the last compliance-monitoring date. It deliberately excludes compliance
status, violations, penalties, demographics, and person fields. The interface
describes the result as monitoring activity—not a violation, enforcement
finding, unsafe condition, claim predictor, or underwriting fact. Production-
scale collection must use EPA's weekly bulk exporter instead of robotic UI
queries.

Three additional frontiers now have fail-closed adapters:

- [Chicago Business Licenses](https://data.cityofchicago.org/Community-Economic-Development/Business-Licenses/r5kz-chrr)
  is queried only when Illinois is explicitly selected, data-reuse approval is
  recorded, and a Socrata app token is configured. The adapter selects initial
  active licenses and organization fields only. It never joins the Business
  Owners dataset or emits exact street addresses, personal contacts, or
  geolocation.
- [SAM.gov Entity API](https://open.gsa.gov/api/entity-api/) is implemented with
  the documented query-parameter API key, zero-based paging, public sensitivity,
  and only `entityRegistration,coreData`. Missing credentials produce
  `SAM_GOV_API_KEY_NOT_CONFIGURED`, not zero results. D&B-sourced, D&B-open,
  non-public, person-like, and pre-2022 records fail closed.
- [FCC ULS bulk data](https://data.fcc.gov/download/pub/uls/complete/) is
  deliberately unavailable in the live request path. Its large mixed-person
  archives require a durable baseline/delta parser, transactional watermarks,
  checksums, and applicant-type filtering before the source can become live.

Guardrails:

- Hide full policy identifiers from the broker UI.
- Treat a filing as a time-stamped signal, not present-tense coverage truth.
- Never label a carrier "unsafe" or "uninsured" from a derived signal.
- Re-check the current official record before outreach.
- Use business contact information only.
- Keep the score for prospecting priority, never underwriting or pricing.

## Prioritized source portfolio

| Tier | Official source | Opportunity signal | Boundary |
|---|---|---|---|
| 1 | FMCSA | fleet growth, authority and filing events, operating status | Business entity only; suppress full policy numbers |
| 1 | [SAM.gov Entity API](https://open.gsa.gov/api/entity-api/) | active public registration updates | Key-gated; public sensitivity and entity/core allowlist only; exclude POC, CUI, D&B and pre-2022 records |
| 1 | [USAspending API](https://api.usaspending.gov/docs/endpoints) | award activity and award periods | Activity may be a modification; not financial-health truth |
| 1 | [Chicago Business Licenses](https://data.cityofchicago.org/Community-Economic-Development/Business-Licenses/r5kz-chrr) | newly issued active organization licenses | Illinois only; reuse-approval and app-token gated; never join Business Owners |
| 1 | state Secretary of State open data | formations, status changes, mergers | Registered-agent/service address may not be an operating contact |
| 1 | [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | 8-K events, financing, acquisitions, disclosed changes | Follow SEC fair-access guidance and declared User-Agent |
| 1 | [EPA ECHO](https://echo.epa.gov/tools/web-services) | recent facility compliance-monitoring activity | Live, minimized facility fields; not a violation, risk judgment, or underwriting fact |
| 2 | [OSHA data](https://www.osha.gov/foia/) | inspection and enforcement events | Reported event, not a conclusive risk judgment |
| 2 | [OpenFEMA](https://www.fema.gov/about/reports-and-data/openfema), [NOAA Storm Events](https://www.ncei.noaa.gov/stormevents/ftp.jsp), [USGS](https://earthquake.usgs.gov/ws/) | facility/geographic hazard context | Aggregate/facility context; no household reconstruction |
| 2 | [CMS provider enrollment](https://data.cms.gov/provider-characteristics/medicare-provider-supplier-enrollment) | facility openings, ownership and enrollment changes | Facility only; no PHI or beneficiary data |
| 2 | [IRS tax-exempt bulk data](https://www.irs.gov/charities-non-profits/tax-exempt-organization-search-bulk-data-downloads) and [Form 990 XML](https://www.irs.gov/charities-non-profits/form-990-series-downloads) | nonprofit scale and organizational changes | Do not use home addresses or personal compensation as sales hooks |
| 3 | [Census business APIs](https://www.census.gov/topics/business-economy/small-business/data/api.html) and [BLS QCEW](https://www.bls.gov/cew/downloadable-data-files.htm) | market sizing, industry and employment concentration | Territory context only |
| Verify | [NIPR license verification](https://nipr.com/licensing/verify-existing-licenses) and [NAIC DOI directory](https://content.naic.org/state-insurance-departments) | broker license, line and jurisdiction verification | Verification, not prospect harvesting; contractual access may apply |

## Evaluated next frontiers

| Frontier | Potential signal | Decision |
|---|---|---|
| [SAM.gov Entity API](https://open.gsa.gov/api/entity-api/) | active registration and public entity updates | `ADAPTER_READY_KEY_REQUIRED`; approved key/system-account operations still required |
| [Chicago Business Licenses](https://data.cityofchicago.org/Community-Economic-Development/Business-Licenses/r5kz-chrr) | initial active organization licenses | `ADAPTER_READY_REUSE_APPROVAL_AND_APP_TOKEN_REQUIRED`; Illinois must be explicitly selected |
| [EPA ECHO weekly exporter](https://echo.epa.gov/tools/data-downloads) | restart-safe bulk facility refresh | On-demand adapter is live; bulk automation needs a durable incremental parser |
| [FCC ULS public data](https://opendata.fcc.gov/Wireless/FCC-Universal-Licensing-System-ULS-/x28i-i4z4/data) | new entity radio licenses and infrastructure operations | `FCC_DURABLE_INGEST_NOT_CONFIGURED`; never download large mixed-person archives on the request path |
| [FAA releasable aircraft database](https://www.faa.gov/licenses_certificates/aircraft_certification/aircraft_registry/releasable_aircraft_download) | corporate aircraft registration/transfer | `PRIVACY_REVIEW_REQUIRED`; the bulk file mixes company and individual owners and supports owner-information withholding |
| Company RSS/newsroom/job feeds | expansion, executive, location and hiring events | `ALLOWLIST_REVIEW_REQUIRED`; terms/robots check, low-rate retrieval, normalized fact only |

This backlog is intentionally not a license to ingest everything public. A
frontier moves to `LIVE` only when its fields, allowed purpose, retention,
deletion path, refresh interval, and broker action are documented and tested.

Company websites, government notices, press releases, RSS, and job pages are
allowlisted research sources only after terms and robots review. Store the
normalized fact, canonical URL, observed timestamp, raw hash, parser version,
allowed purpose, and refresh deadline—not a copied page.

## Social media boundary

Do not scrape LinkedIn, Meta, X, Instagram, logged-in pages, private groups, or
search-engine result pages. Do not reuse cookies, create fake accounts, bypass a
CAPTCHA, rotate proxies, or copy member data into CRM enrichment.

Allowed paths are:

- human research performed by the broker,
- approved ads and first-party lead forms,
- user-supplied links used as research hints,
- explicitly licensed APIs used only for their approved purpose.

Primary references:

- [LinkedIn User Agreement](https://www.linkedin.com/legal/user-agreement)
- [LinkedIn Crawling Terms](https://www.linkedin.com/legal/crawling-terms)
- [LinkedIn Marketing API restricted uses](https://learn.microsoft.com/en-us/linkedin/marketing/restricted-use-cases?view=li-lms-2026-04)

## Outreach execution gate

An opportunity becomes `READY` only through the evidence-backed clearance endpoint
after the broker records:

1. current official entity verification,
2. at least one timely, attributable trigger,
3. corroboration or an explicit single-source limitation,
4. a business-published contact channel,
5. broker license/appointment verification for state and product,
6. applicable federal and state DNC/TCPA/email checks,
7. internal and company-specific suppression checks,
8. a truthful human-created call purpose.

The clearance binds the chosen channel, operator, jurisdiction, license scope,
talk-track version, four affirmative checks, issue time, expiry (maximum 24
hours), and a deterministic receipt identifier. `RESEARCH`, `BLOCKED`, `LOST`,
expiry, or a `DO_NOT_CALL` disposition revokes call readiness. The governed CSV
export includes only entity research fields and exposes a business channel only
while its clearance is current; spreadsheet-formula prefixes are escaped.

Automated dialing, texting, prerecorded voice, and AI voice are disabled by
default. First-party consent must retain the exact language, seller, channel,
scope, timestamp, source, revocation state, and receipt.

Primary guidance:

- [47 CFR §64.1200](https://www.ecfr.gov/current/title-47/chapter-I/subchapter-B/part-64/subpart-L/section-64.1200)
- [FTC Telemarketing Sales Rule guide](https://www.ftc.gov/business-guidance/resources/complying-telemarketing-sales-rule)
- [FTC B2B telemarketing amendment](https://www.ftc.gov/news-events/news/press-releases/2024/03/ftc-implements-new-protections-businesses-against-telemarketing-fraud-affirms-protections-against-ai)
- [FTC CAN-SPAM guide](https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business)
- [CFPB FCRA permissible-purpose opinion](https://www.consumerfinance.gov/rules-policy/final-rules/fair-credit-reporting-permissible-purposes-for-furnishing-using-and-obtaining-consumer-reports/)

## Privacy and data-broker boundary

California's DROP obligations begin on 2026-08-01 for qualifying data brokers.
Before commercial launch, counsel must document whether the product or operator
falls within data-broker registration and deletion obligations. The safer design
is single-broker, first-party use; no raw-contact resale; no consumer-profile
marketplace; and working correction, suppression, export, and deletion flows.

- [California data-broker guidance](https://cppa.ca.gov/data_brokers/)
- [DROP regulations](https://cppa.ca.gov/regulations/drop.html)
- [DROP portal](https://privacy.ca.gov/drop/)

Applicant, quote, policyholder, and customer information belongs in a separate
GLBA/state-insurance-controlled system, not in the prospecting lake.

## Broker packet contract

```text
legal_name
dba
authoritative_entity_ids[]
operating_location
industry
observed_trigger
trigger_date
recommended_product_fit
why_now_summary
source_urls[]
source_observed_at[]
source_record_id
normalized_record_sha256
parser_version
receipt_state = SIGNED | HASH_CHAINED_UNSIGNED | UNAVAILABLE
evidence_freshness
confidence_and_limitations
broker_state_line_authority
business_contact_source
outreach_eligibility
suppression_checked_at
suppression_status
purpose = PROSPECTING_ONLY
not_for_underwriting = true
```

## Measured operating metrics

Lead with measured workflow results, not modeled sales claims:

- official opportunities discovered,
- records with fresh corroboration,
- opportunities awaiting research,
- opportunities manually cleared,
- follow-ups due,
- manual attempts and connects,
- meetings booked,
- proposals, wins, and lost reasons,
- premium recorded after sale,
- source freshness and live/cached/example ratio,
- permission and suppression coverage.

Modeled appointment and premium potential may remain secondary and must always be
marked `MODELED` or `ILLUSTRATIVE`.
