# David Leads market-cockpit design research

## Public interfaces reviewed

- Attio: record tables, saved views, filters, sorting, and one record page that
  keeps context and activity together.
- Apollo: prominent company search with layered filters and plain-language
  discovery.
- HubSpot Sales Workspace: a single seller home focused on the next useful
  action instead of a collection of disconnected tools.
- Convex: a territory-first, map-oriented sales-intelligence experience for
  field teams.
- Pipeline CRM: list and pipeline views with the few metrics needed to act.
- GitHub public projects: Twenty, Frappe CRM, Atomic CRM, WFP PRISM, and
  OpenSearch Dashboards Maps.
- GitLab public projects: Flectra and Dokos.
- Hugging Face public Spaces: GISWQS Geospatial Data Visualization, Solara
  Geospatial, and IBM/NASA Prithvi demos.

## Product decisions

1. One primary workspace replaces the former collection of competing cards.
2. Eastern U.S. territory selection is always visible on desktop and region
   selection is always visible on mobile.
3. Broker view uses a filterable table plus a detail drawer, so David can scan
   quickly and still inspect proof without losing his place.
4. Market coverage makes every Eastern state directly selectable. A zero in the
   latest cross-territory pull is explained, not treated as a lack of coverage.
5. Investor view reports operating evidence, source availability, release
   identity, and governance separately from financial or outcome claims.
6. No runtime CDN, copied proprietary interface, personal-data enrichment, or
   social-profile scraping was introduced.

## Eastern territory

The workspace exposes 27 markets grouped into New England, Mid-Atlantic, Great
Lakes, and Southeast: AL, CT, DC, DE, FL, GA, IL, IN, KY, ME, MD, MA, MI, MS,
NH, NJ, NY, NC, OH, PA, RI, SC, TN, VT, VA, WV, and WI.

The API normalization limit was raised from 12 to 30 after the audit proved the
former cap silently dropped legitimate Eastern-state selections.
