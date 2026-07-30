# Frontier product research — July 30, 2026

## Product patterns worth adopting

This upgrade uses interaction patterns from current sales-intelligence and
broker-workflow leaders without copying their proprietary interfaces:

- [AgencyZoom](https://www.agencyzoom.com/) emphasizes an insurance-specific
  customer journey, pipeline visibility, and automatic resurfacing around
  timing events.
- [Attio Workflows](https://attio.com/platform/workflows) combines flexible
  organization records with lists, workflows, and relationship context.
- [Apollo Prospect & Enrich](https://www.apollo.io/product/prospect-and-enrich)
  makes dense search and prioritization understandable through filters and
  scoring.

The resulting David Leads pattern is one primary evidence-ranked queue with
deal-moment lanes, timing, likely fit, source strength, and a focused record
drawer. Timing and product fit remain separate from contact permission.

## David-specific fit

David Abraham's [official New York Life profile](https://www.newyorklife.com/agent/dabraham02)
lists life insurance, long-term care, and annuities. The first new public-data
frontier therefore uses only the life-benefit indicator from DOL Schedule A for
product fit. Medical, dental, vision, and other reported categories may appear
as source context but never as products David is assumed to offer.

## Implemented lawful frontier

### DOL Form 5500 employer life-plan timing

The [U.S. Department of Labor Form 5500 datasets](https://www.dol.gov/agencies/ebsa/about-ebsa/our-activities/public-disclosure/foia/form-5500-datasets)
are official monthly bulk disclosures covering employee-benefit plans.

The adapter:

- joins the main Form 5500 filing with Schedule A by public acknowledgement ID;
- keeps organization, city/state/ZIP, participant count, plan/policy period,
  reported life-benefit indicator, benefit categories, and relevant carriers;
- calculates the next anniversary of the previously reported period;
- labels the result as a timing hypothesis, never a guaranteed renewal;
- prioritizes 25-500 participant employers, then 501-2,500 participant
  employers, and caps the lane at 5,000 participants;
- collapses duplicate sponsor filings;
- excludes EINs, administrators, signers, preparers, phone numbers,
  person-level addresses, broker identities, and commissions.

## Triangulation

Every official record now receives an organization/state identity key. When
independent sources observe the same organization, the account displays a
multi-source evidence state and the corroborating event chain. A single source
remains explicitly `SINGLE_SOURCE`; the application never invents a second
observation.

## Next official-data frontiers

These are useful only after their licensing, reuse, and operating controls are
configured:

1. [SAM.gov Contract Opportunities API](https://open.gsa.gov/api/get-opportunities-public-api/)
   for documented pre-award organization intent. It requires a SAM API key and
   should remain `UNAVAILABLE` without one.
2. [DOL foreign labor disclosure data](https://www.dol.gov/agencies/eta/foreign-labor/performance)
   for organization-level workforce expansion. It needs a durable quarterly
   file-ingestion lane and industry-purpose review.
3. Official state WARN feeds for organization contraction events. These should
   be used for continuity and workforce research only, never employee
   targeting.
4. Official state corporation and license feeds for new organization events,
   subject to documented reuse terms and stable bulk/API access.

## Rejected frontiers

The production lead path does not use:

- social-profile scraping;
- personal emails or phone enrichment;
- named nonprofit executives or compensation as wealth leads;
- SEC insiders or transactions as personal liquidity leads;
- political donors, obituaries, property owners, family events, or other
  person-level proxies;
- aggregate tax-return affluence or migration as person-targeting signals.

Public availability alone is not a sufficient purpose, license, or contact
permission.
