# V7 — Multi-State Open Data Expansion (East Coast)

**Prepared:** Sunday, June 28, 2026. **For:** David Abraham (New York Life) lead-intelligence app, currently NY-only.
**Goal:** Find FREE, no-key, machine-readable open-data feeds in East Coast states that match the NY categories the app already ingests — (1) business entity registrations, (2) professional license issuances, (3) property sales / deeds / assessments, (4) building permits.
**Method:** Probed each state's open-data portal via the Socrata Discovery API (`api.us.socrata.com`), CKAN package APIs, and ArcGIS Hub DCAT feeds. **Endpoints below were hit live on 2026-06-28** unless flagged otherwise. **Research only — no app code changed.**

> **Reusable patterns the app already knows.** Three keyless API shapes cover almost everything found:
> 1. **Socrata SODA** — `https://<domain>/resource/<id>.json?$where=…&$order=…&$limit=…` (same as NY's `data.ny.gov` / `data.cityofnewyork.us`). No key needed at our volumes; an app token only raises throttling headroom.
> 2. **ArcGIS REST FeatureServer** — `https://<host>/arcgis/rest/services/<svc>/FeatureServer/<layer>/query?where=1=1&outFields=*&f=json` (used by DC and most VA/FL counties). Keyless. Supports `resultRecordCount`, `resultOffset`, `orderByFields`, `returnCountOnly`.
> 3. **Bulk file pull** — fixed-width / CSV files over public HTTPS or SFTP (FL Sunbiz, NJ license roster). Needs a parse step, not a live query.

---

## 1. Executive Ranking — States by Free Data Richness

Scored 0–4 by how many of the four categories are available as a **free, keyless, machine-readable, reasonably fresh** feed with **named/address-level records** (aggregate-only or stale sources don't count toward the score).

| Rank | State | Score | Portal type | One-line verdict |
|------|-------|-------|-------------|------------------|
| **1** | **Connecticut** | **4 / 4** | Socrata `data.ct.gov` | **Best in class.** Daily business formations + a single license table with real-estate agents/brokers/contractors/attorneys + statewide sales + parcel/CAMA. Wire this first. |
| **2** | **Delaware** | **3.5 / 4** | Socrata `data.delaware.gov` | Daily business licenses, daily individual professional/occupational licenses, trade-name filings. Weak on a clean property-sales feed. Small state but very clean. |
| **3** | **DC** | **3.5 / 4** | ArcGIS Hub `opendata.dc.gov` | Daily "Business License in Last 30 Days," construction/building/occupancy permits, full tax-assessment extract. ArcGIS not Socrata — slightly different query syntax. |
| **4** | **Pennsylvania** | **2 / 4** | Socrata `data.pa.gov` | Strong named **business registrations** (statewide, monthly). Professional licenses are **aggregate counts only**; no property/permit feed. |
| **5** | **Maryland** | **2 / 4** | Socrata `opendata.maryland.gov` | Outstanding **statewide real-property assessments** (2.4M parcels, addresses). No individual business-entity or license feed (only portal metrics / aggregates). |
| **6** | **Virginia** | **2 / 4** | CKAN harvest `data.virginia.gov` → city Socrata/ArcGIS | No statewide feeds; the state portal **federates city/county portals**. Norfolk (Socrata), Virginia Beach (ArcGIS) give business licenses, property sales, permits — but **city-by-city**, not statewide. |
| **7** | **Florida** | **1.5 / 4** | SFTP bulk (Sunbiz) + county ArcGIS | **Business data is gold but not a live API** — Sunbiz free public SFTP, daily fixed-width files (needs parsing). Property via per-county ArcGIS appraisers. No statewide license/permit API. |
| **8** | **New Jersey** | **1 / 4** | Socrata `data.nj.gov` (thin) + bulk roster | Socrata portal is sparse: only a Construction Permit dataset is usable. Business entity = portal-only (paid abstracts). Pro licenses = free bulk **roster download** (not an API). |
| **9** | **Rhode Island** | **0.5 / 4** | Socrata `data.providenceri.gov` (Providence only) | **No state portal.** Providence city Socrata exists but is **stale** (business licenses last updated 2021, permits end 2018). Only property tax rolls are maintained (annual). |
| **10** | **Massachusetts** | **0 / 4 (API)** | "Data Hub" (Next.js) + gated licensing API | **No keyless bulk API for our categories.** data.mass.gov is a download portal, not Socrata/CKAN. The pro-licensing API needs an **API key** and only does single-license lookups. Flag as a gap. |
| **11** | **New Hampshire** | **0 / 4** | None | **No open-data portal / no API.** Secretary of State business search and license lookups are HTML-only. Flag as a gap. |

**Bottom line:** Wire **CT → DE → DC → PA → MD** first (all clean, keyless, fresh). Treat **VA** as a city-by-city add-on (start Norfolk + Virginia Beach). **FL** is high-value but needs a Sunbiz file ingester. **NJ, RI, MA, NH** have no clean statewide free API for these categories today.

---

## 2. State-by-State Detail (exact endpoints, key status, freshness)

Legend: **Key?** = does it need an API key. **Fresh** = update cadence (verified live where noted). All Socrata endpoints support `$where`/`$order`/`$limit` for new-issuance filtering.

### ★ Connecticut — `data.ct.gov` (Socrata) — RICHEST

| Cat | Dataset | Endpoint | Key? | Fresh | Notes (verified 6/28) |
|-----|---------|----------|------|-------|------------------------|
| **Business** | **Business Filing History** `ah3s-bes7` | `https://data.ct.gov/resource/ah3s-bes7.json?$where=type='Business Formation'&$order=filing_date DESC&$limit=50` | **No** | **Daily** | `filing_date`, `filing_type` (Certificate of Organization, etc.). Max `filing_date` = **2026-06-27**; **4,323 Business Formations in the last 30 days.** |
| **Business** | **Business Registry – Master** `n7gp-d28j` | `https://data.ct.gov/resource/n7gp-d28j.json?$order=create_dt DESC&$limit=50` | No | Daily | Entity name, status, mailing address, woman/veteran/minority-owned flags. Join on `accountnumber` to Principals `ka36-64k6` & Agents `qh2m-n44y`. |
| **Licenses** | **State Licenses and Credentials** `ngch-56tr` | `https://data.ct.gov/resource/ngch-56tr.json?$where=issuedate>'2026-01-01'&$order=issuedate DESC&$limit=50` | **No** | **Daily** | **The single most valuable license table on the East Coast.** Full name, address, city/zip, `issuedate`, `status`. Filter `credential` for `REAL ESTATE SALESPERSON` (96,851), `REAL ESTATE BROKER` (21,728), `HOME IMPROVEMENT CONTRACTOR` (134,331), `NEW HOME CONSTRUCTION CONTRACTOR` (15,863), and 100+ professions. **913 new RE salespersons issued in 2026 YTD.** |
| **Property sales** | **Real Estate Sales 2001–2023 GL** `5mzw-sjtu` | `https://data.ct.gov/resource/5mzw-sjtu.json?$order=daterecorded DESC&$limit=50` | No | Annual ⚠️ | Town, address, `saleamount`, `assessedvalue`, sales ratio, property type, lat/long. **Max `daterecorded` = 2024-09-30** — lags ~1.5 yrs (annual grand-list cycle), so it's a comp/affordability layer, not a fresh-trigger feed. |
| **Property assess** | **2025 CT Parcel & CAMA Data** `rny9-6ak2` | `https://data.ct.gov/resource/rny9-6ak2.json?$limit=50` | No | Annual | Statewide parcel + assessment (CAMA). Companion years `pqrn-qghw` (2024), `ezgm-i4uu` (2023). |
| **Permits** | Monthly Building Permits by Units `5vjm-esav` | `https://data.ct.gov/resource/5vjm-esav.json` | No | Monthly (Census-sourced) ⚠️ | **Aggregate counts** by units-in-structure, not individual permits. CT has no individual statewide permit feed — use town portals for named permits. |

**CT recommendation (wire 1–2 first):** **`ah3s-bes7` (daily new business formations)** + **`ngch-56tr` (daily license issuances — new real-estate agents, contractors, attorneys, etc.).** These two alone replicate the NY business-formation + attorney/RE-license feeds with *better* coverage in one portal.

---

### ★ Delaware — `data.delaware.gov` (Socrata)

| Cat | Dataset | Endpoint | Key? | Fresh | Notes |
|-----|---------|----------|------|-------|-------|
| **Business** | **Delaware Business Licenses** `5zy2-grhr` | `https://data.delaware.gov/resource/5zy2-grhr.json?$order=current_license_valid_from DESC&$limit=50` | **No** | **Daily** (updatedAt 2026-06-28) | Business name, trade name, category, `current_license_valid_from/to`, address, lat/long, license number. ⚠️ Some `valid_from` values have data-entry artifacts (future years) — sanity-filter on a sane date range. |
| **Business** | **Trade, Business & Fictitious Names** `i7m4-42sn` | `https://data.delaware.gov/resource/i7m4-42sn.json?$limit=50` | No | Daily | DBA / fictitious-name registrations (new-business proxy). |
| **Licenses** | **Professional and Occupational Licensing** `pjnv-eaih` | `https://data.delaware.gov/resource/pjnv-eaih.json?$where=issue_date>'2026-01-01'&$order=issue_date DESC&$limit=50` | **No** | **Daily** | **Individual** licensees: last/first name, `license_type` (Physician, etc.), city/state/zip, `issue_date`, `license_status`. Real-estate/contractor types present. ⚠️ Some `issue_date` data-entry artifacts (future years) — range-filter. Disciplinary actions in companion `dz6p-akeq`. |
| **Contractors** | Water Well Contractors `2dnk-irgr`, Public Works Prequalified `g7vn-fpb4` | `https://data.delaware.gov/resource/2dnk-irgr.json` | No | Daily | Niche named contractor lists. |
| **Property** | — | — | — | — | **Gap:** no statewide property-sales/deeds dataset on the portal (DE counties handle assessments off-portal). Permits are niche (Well/Septic only). |

**DE recommendation:** **`5zy2-grhr` (Business Licenses, daily)** + **`pjnv-eaih` (Professional/Occupational Licensing, daily)**. Clean keyless mirror of the NY business + professional-license pattern.

---

### ★ District of Columbia — `opendata.dc.gov` (ArcGIS Hub)

ArcGIS REST, not Socrata. Query pattern: `…/FeatureServer/<layer>/query?where=1=1&outFields=*&orderByFields=<datefield> DESC&resultRecordCount=50&f=json`.

| Cat | Dataset | Endpoint (FeatureServer) | Key? | Fresh | Notes |
|-----|---------|--------------------------|------|-------|-------|
| **Business** | **Basic Business License in Last 30 Days** | `https://maps2.dcgis.dc.gov/dcgis/rest/services/FEEDS/DCRA/FeatureServer/1/query?where=1=1&outFields=*&f=json` | **No** | **Daily** (updatedAt 2026-06-26) | 42 fields incl. `ENTITYNAME`, `ENTITYTRADENAME`, `LICENSETYPE`, `LICENSESTARTDATE`, `INITIALISSUEDATE`, `PREMISEADDRESS`. Full-history version = `FeatureServer/0`. |
| **Permits** | **Construction Permits in 2026** | `https://maps2.dcgis.dc.gov/dcgis/rest/services/FEEDS/DDOT/FeatureServer/48/query?where=1=1&outFields=*&f=json` | No | **Daily** | **14,342 permits in 2026** (verified count). "Last 30 Days" = `FeatureServer/12`. Building Permits 2025 = `FEEDS/DCRA/FeatureServer/17`. |
| **Permits** | **Occupancy Permits in 2026 / Last 30 Days** | `https://maps2.dcgis.dc.gov/dcgis/rest/services/FEEDS/DDOT/FeatureServer/49/query?where=1=1&outFields=*&f=json` | No | Daily | New-occupancy = new tenant/owner signal. |
| **Property** | **Integrated Tax System Public Extract (Vacant Property)** | `https://services.arcgis.com/neT9SoYxizqTHZPH/arcgis/rest/services/ITSPE_VACANT_PROPERTY_view/FeatureServer/0/query?where=1=1&outFields=*&f=json` | No | ~Daily (2026-06-26) | Tax-assessment / property extract. DC also exposes full real-property tables in DCGIS. |

**DC recommendation:** **DCRA Business License – Last 30 Days (`FEEDS/DCRA/FeatureServer/1`)** + **Construction Permits 2026 (`FEEDS/DDOT/FeatureServer/48`)**. Note: ArcGIS query syntax differs from Socrata — add a small ArcGIS adapter to the ingester.

---

### Pennsylvania — `data.pa.gov` (Socrata)

| Cat | Dataset | Endpoint | Key? | Fresh | Notes |
|-----|---------|----------|------|-------|-------|
| **Business** | **Registered Businesses in PA – Current by County (Dept. of State)** `xvd7-5r2c` | `https://data.pa.gov/resource/xvd7-5r2c.json?$where=creationdate>'2026-03-01'&$order=creationdate DESC&$limit=50` | **No** | **Monthly** | **Individual** records: `business_name`, `filing_number`, address, `creationdate`, `typeofbusinessregistration`, organizer `first_name`/`last_name`, lat/long. **43,449 new registrations in last ~90 days.** Max `creationdate` = 2026-06-01 (monthly refresh). |
| **Licenses** | **Pennsylvania Professional Licensee Data** `fwj2-whnj` | `https://data.pa.gov/resource/fwj2-whnj.json` | No | ~Annual | ⚠️ **Aggregate counts only** — `active_count` by board/profession/county. **No individual names.** Not usable as a named-lead feed. |
| **Licenses** | Tobacco Tax Licenses `ut72-sft8`; Sales/Use Tax Licenses `ugeq-ckxd` | `https://data.pa.gov/resource/ut72-sft8.json` | No | Daily / Monthly | Business-license proxies (retail/hospitality), county-level, current. |
| Property / Permits | — | — | — | — | **Gap:** no statewide property-sales/deeds or building-permit dataset on the portal. PA property is county-level (e.g., Allegheny/Philadelphia have their own portals). |

**PA recommendation:** **`xvd7-5r2c` (Registered Businesses, individual records with names + creation dates).** Best PA feed by far; a clean mirror of NY business formations. Skip the aggregate license table.

---

### Maryland — `opendata.maryland.gov` (Socrata)

| Cat | Dataset | Endpoint | Key? | Fresh | Notes |
|-----|---------|----------|------|-------|-------|
| **Property assess** | **Maryland Real Property Assessments** `ed4q-f8tm` | `https://opendata.maryland.gov/resource/ed4q-f8tm.json?$limit=50` | **No** | Refreshed 2026-06-04 | **2,438,889 parcels statewide.** Account ID, jurisdiction, lat/long, SDAT detail link, FinderOnline link, assessment fields. Field reference = `w8th-47fz`. **Owner names are hidden** in the open version. Best statewide assessment layer found anywhere on the East Coast. |
| **Property** | Parcel Points `x8a5-h2sy` | `https://opendata.maryland.gov/resource/x8a5-h2sy.json` | No | 2026-06-09 | Geospatial parcels. |
| **Business** | Central Business Licensing System Report `kype-d7gy` | — | No | Monthly | ⚠️ **Portal usage metrics, NOT business records** (visitors, registrations submitted/approved). Number of Businesses `ftgf-3uby` is an **aggregate count**. **No individual business-entity feed** (MD entity data is via SDAT search, not bulk open data). |
| **Licenses / Permits** | — | — | — | — | **Gap:** no statewide individual professional-license or building-permit dataset. (City of Frederick permits `xrz3-9xhj` exist but last updated 2019.) |

**MD recommendation:** **`ed4q-f8tm` (Real Property Assessments).** Use as a property/assessment enrichment + affordability layer (no owner name, so pair with deed/recorder data when needed). MD's business and license categories are effectively a gap on the open portal.

---

### Virginia — `data.virginia.gov` (CKAN harvesting catalog → city portals)

The state portal is a **CKAN catalog that federates city/county open-data portals**; there are no statewide business/license/property JSON feeds. Go directly to the underlying city portals, which are keyless.

| Cat | Source (city) | Endpoint | Key? | Fresh | Notes |
|-----|---------------|----------|------|-------|-------|
| **Business** | **Norfolk – Business Licenses** (Socrata `data.norfolk.gov`) `dpi6-sct5` | `https://data.norfolk.gov/resource/dpi6-sct5.json?$order=business_opened_date DESC&$limit=50` | **No** | Current | `trading_as_name`, `primary_owner`, NAICS, address, `business_opened_date`, lat/long. **Max opened date = 2026-07-03** (very fresh). |
| **Property sales** | **Virginia Beach – Property Sales** (ArcGIS `data.virginiabeach.gov`) | `https://services2.arcgis.com/CyVvlIiUfRBmMQuu/arcgis/rest/services/Property_Sales_/FeatureServer/0/query?where=1=1&outFields=*&f=json` | No | Updated 2026-06-28 | GPIN, street address, city/state, sale fields. Also CSV/JSON via `data.virginiabeach.gov/api/download/...`. |
| **Permits** | **Virginia Beach – Building Permits Applications** (ArcGIS) | `https://services2.arcgis.com/CyVvlIiUfRBmMQuu/arcgis/rest/services/Building_Permits_Applications_view/FeatureServer/0/query?where=1=1&outFields=*&f=json` | No | Updated 2026-06-28 | Permit applications, geocoded. |
| **Property assess** | Dumfries – Real Estate Assessments (Socrata) `rdxq-jfzf` | `https://data.dumfriesva.gov/resource/rdxq-jfzf.json` | No | 2026-06-12 | Town-level assessments. |

**Discovery trick:** browse VA's catalog to find more cities: `https://data.virginia.gov/api/3/action/package_search?q=<business|permits|property+sales>&rows=20` → each result's `package_show` lists the underlying city Socrata/ArcGIS resource URL.

**VA recommendation:** Start with **Norfolk Business Licenses (`dpi6-sct5`)** + **Virginia Beach Property Sales & Permits (ArcGIS)**. Add Richmond/Arlington/Alexandria portals as the territory expands. **No statewide coverage — city-by-city only.**

---

### Florida — Sunbiz (business) + county property appraisers (no statewide JSON API)

| Cat | Source | Endpoint / Access | Key? | Fresh | Notes |
|-----|--------|-------------------|------|-------|-------|
| **Business** | **FL Division of Corporations (Sunbiz) Data Downloads** | Public SFTP `sftp://sftp.floridados.gov` — user `Public`, pass `PubAccess1845!`. Daily files (work-day additions) + quarterly full snapshots. | **No** (public creds) | **Daily** | Corporate/LLC, fictitious-name, and partnership filings with officers, registered agents, addresses. ⚠️ **Fixed-width text files, no headers** — needs a parser using the published file definitions. Verified the SFTP host accepts connections (password prompt). 12M+ entities total. ([Sunbiz Data Downloads](https://dos.fl.gov/sunbiz/other-services/data-downloads/)) |
| **Property** | **County Property Appraisers (ArcGIS REST)** | e.g. Lake County `https://gis.lakecountyfl.gov/lakegis/rest/services/OpenData/OpenData1/MapServer/12/query?where=1=1&outFields=*&f=json` (returns OwnerName, OwnerAddress, ParcelNumber, DeedAcreage) | No | Per-county (varies) | Each of FL's 67 counties runs its own appraiser GIS. Many expose keyless ArcGIS query endpoints with owner + sale data (Orange, Lake, Pasco, etc.). No single statewide feed. |
| **Licenses** | FL DBPR / DOH | — | — | — | FL license data is via DBPR/DOH lookup sites; **no statewide keyless bulk JSON API** in scope. |
| **Permits** | County/city ArcGIS | — | No | Varies | Permit feeds are per-jurisdiction (ArcGIS), like property. |

**FL recommendation:** **Sunbiz daily corporate file ingester** (highest-value FL feed — every new LLC/corp statewide, daily) is the priority but requires a scheduled SFTP-pull + fixed-width parser, not a live API call. Layer in **county property-appraiser ArcGIS** for the target metros (e.g., Orange/Lake for Orlando, Miami-Dade, Hillsborough). **No live license/permit API** statewide.

---

### New Jersey — `data.nj.gov` (Socrata, thin) + bulk roster

| Cat | Source | Endpoint / Access | Key? | Fresh | Notes |
|-----|--------|-------------------|------|-------|-------|
| **Permits** | **NJ Construction Permit Data** `w9se-dmra` | `https://data.nj.gov/resource/w9se-dmra.json?$order=permitdate DESC&$limit=50` (sanity-filter dates) | **No** | Monthly (updatedAt 2026-06-10) | Statewide DCA construction permits: muni, county, block/lot, `permitdate`, `certdate`, permit type, fees, `constcost`. ⚠️ Sample dates lag (2017–2021) and a `max(permitdate)` artifact ("2925") shows data-quality noise — filter to a sane recent window. The **only** broadly usable NJ open-data feed for our categories. |
| **Licenses** | **NJ Division of Consumer Affairs – License Roster (bulk)** | "Download the Roster" / bulk verification at `https://newjersey.mylicense.com/Verification_Bulk/` (person + business) | **No** | Daily-updated DB | ~600k licensed professionals (incl. real-estate via NJ REC, contractors, healthcare). **Bulk file download, not a JSON API** — needs a scheduled pull + parse. The free, machine-readable path for NJ licenses. ([NJ DCA license verification](https://newjersey.mylicense.com/verification/)) |
| **Business** | NJ DORES Business Records | `https://www.njportal.com/dor/businessrecords/` | n/a | — | ⚠️ **No free bulk/JSON API.** Search portal only; downloadable lists/abstracts are **paid**. Business-entity data is effectively a gap for free automated ingestion. |
| **Property** | — | — | — | — | **Gap:** no statewide property-sales/deeds open dataset (`data.nj.gov` has none usable; NJ MOD-IV assessment data exists as bulk files via NJ Treasury, off-portal). |

**NJ recommendation:** **NJ Construction Permit `w9se-dmra`** (only live keyless feed; date-filter carefully) and, if a bulk ingester is acceptable, the **DCA license roster** for new real-estate/contractor licensees. Business-entity registration has **no free API** — flag. Despite the task's expectation, **`data.nj.gov` does not carry a clean business-registration dataset.**

---

### Rhode Island — no state portal; Providence city Socrata is stale

| Cat | Source | Endpoint | Key? | Fresh | Notes |
|-----|--------|----------|------|-------|-------|
| **Business** | Providence – Active Business Licenses `ui7z-kv69` | `https://data.providenceri.gov/resource/ui7z-kv69.json` | No | ⚠️ **Stale (last 2021-12-18)** | Not maintained. |
| **Property** | Providence – Property Tax Rolls (e.g., 2022 `c3q4-f95q`) | `https://data.providenceri.gov/resource/c3q4-f95q.json` | No | Annual (refreshed 2026-06-17) | Assessment rolls only — **no sale transactions**. |
| **Permits** | Providence – DIS Permits `ufmm-rbej` | — | No | ⚠️ **Ends 2018** | Not maintained. |

**RI verdict:** **Largely a gap.** No statewide open-data portal (`data.ri.gov` / `data.rhode-island.gov` don't exist as Socrata). Providence is the only city portal and its business/permit feeds are stale; only property tax rolls are current (annual, no sales). **Flag RI as low/no usable free trigger feed.**

---

### Massachusetts — NO keyless bulk API for our categories (FLAG)

- **data.mass.gov** is a **Next.js "Massachusetts Data Hub"**, *not* a Socrata or CKAN API — `api/3/action/*` and Socrata catalog calls both fail. It's a human-facing download/report portal.
- The **MA Professional Licensing API** (`licensing.api.secure.digital.mass.gov`) **requires an API key** (`X-API-Key`, issued to municipalities/vendors) and only does **single license-number lookups** for permit validation (building/plumbing/electric/hoisting/sheet-metal) — **not a bulk lead feed**. ([MA Professional Licensing API](https://www.mass.gov/info-details/ma-professional-licensing-api))
- MA business-entity, property, and permit data live in agency download pages, MassGIS ArcGIS layers, and the Secretary of the Commonwealth's corporate search (HTML), none of which is a clean keyless bulk JSON API in scope.

**MA verdict:** **Flag as a gap.** No free, no-key, machine-readable feed matching our four categories. (Possible future path: MassGIS ArcGIS parcel layers for property, and per-municipality permit portals — out of scope for a quick wire-in.)

---

### New Hampshire — NO open-data API (FLAG)

- No state open-data portal (`data.nh.gov` doesn't exist; `nh.gov/data` returns 403/no API).
- Business entities = **NH Secretary of State QuickStart business search** (HTML only). Professional/real-estate licenses = HTML lookup sites. No bulk download or JSON API found.

**NH verdict:** **Flag as a gap** — no usable free machine-readable feed for any of the four categories.

---

## 3. "Wire These First" — Cross-State Priority Queue

Ranked by (data richness × freshness × ease of wiring into the existing Socrata-style ingester). All keyless.

| Rank | State | Feed(s) to wire | Why first | Effort |
|------|-------|-----------------|-----------|--------|
| **1** | **CT** | `ah3s-bes7` (daily new business formations) + `ngch-56tr` (daily license issuances: RE agents/brokers, contractors, attorneys) | Two feeds replicate NY's business-formation **and** professional-license categories with broader coverage; both daily, named, addressed. Identical Socrata pattern to the app's NY feeds. | **Very low** |
| **2** | **DE** | `5zy2-grhr` (Business Licenses) + `pjnv-eaih` (Professional/Occupational Licensing) | Daily, individual records, clean Socrata. Add a date sanity-filter for the future-date artifacts. | **Low** |
| **3** | **DC** | `FEEDS/DCRA/FeatureServer/1` (Business License last 30 days) + `FEEDS/DDOT/FeatureServer/48` (Construction Permits 2026) | Daily, named/addressed; covers business + permits. Needs a small **ArcGIS query adapter** (different syntax from Socrata). | **Low–Med** |
| **4** | **PA** | `xvd7-5r2c` (Registered Businesses, individual) | Statewide named business registrations w/ creation dates + lat/long; clean Socrata. Monthly cadence. | **Low** |
| **5** | **MD** | `ed4q-f8tm` (Real Property Assessments, 2.4M parcels) | Best statewide property/assessment layer; great enrichment/affordability data. (Owner name hidden — comp/value layer, not a named trigger.) | **Low** |
| **6** | **VA** | Norfolk `dpi6-sct5` (Business Licenses) + Virginia Beach ArcGIS (Property Sales, Permits) | City-by-city; start with two metros, expand via the CKAN catalog. | **Med** (per-city) |
| **7** | **FL** | Sunbiz daily corporate file (SFTP) + target-county appraiser ArcGIS | Highest business value statewide, but **batch SFTP + fixed-width parser**, not a live API. | **Med–High** |

---

## 4. Gaps / No-Usable-Free-API Flags

| State | Category gap | Detail |
|-------|--------------|--------|
| **NJ** | Business entity registration | No free bulk/JSON API; DORES portal is search-only, downloads are paid. (`data.nj.gov` has **no** business-registration dataset.) |
| **NJ** | Property sales/deeds | No statewide open dataset (MOD-IV is off-portal bulk). |
| **PA** | Professional licenses (individual) | Only **aggregate** counts (`fwj2-whnj`); no named licensees. |
| **PA** | Property & permits | No statewide dataset (county-level only). |
| **MD** | Business entity + individual licenses | Only portal metrics / aggregates; entity data via SDAT search. |
| **MD** | Building permits | No statewide dataset. |
| **VA** | All categories statewide | State portal only federates cities; **no statewide feed** — must wire city-by-city. |
| **FL** | Live API for business/license/permit | Sunbiz is SFTP bulk (no API); licenses/permits are per-agency/county. |
| **RI** | Business, licenses, permits | No state portal; Providence city feeds **stale** (2021/2018). Only annual property tax rolls current. |
| **MA** | All four (keyless bulk) | Data Hub is download portal; licensing API is **key-gated, single-lookup only**. **Flag.** |
| **NH** | All four | **No open-data portal / API at all. Flag.** |

---

## 5. Verification Log (hit live 2026-06-28)

- **CT** `ah3s-bes7`: max `filing_date` 2026-06-27; 4,323 Business Formations in last 30 days. ✅
- **CT** `ngch-56tr`: returns named licensees w/ address + `issuedate`; 913 new RE salespersons in 2026; credential mix incl. RE broker/salesperson, home-improvement & new-home-construction contractors. ✅
- **CT** `5mzw-sjtu`: returns sales w/ amount + lat/long; max `daterecorded` 2024-09-30 (annual lag). ✅⚠️
- **CT** `n7gp-d28j`: returns entity master w/ ownership flags. ✅
- **PA** `xvd7-5r2c`: individual business records w/ creationdate + names; 43,449 in last ~90 days; max creationdate 2026-06-01. ✅
- **PA** `fwj2-whnj`: aggregate `active_count` only — no individuals. ✅⚠️
- **MD** `ed4q-f8tm`: 2,438,889 parcels; addresses + SDAT links; owner names hidden. ✅
- **DE** `5zy2-grhr` & `pjnv-eaih`: live, daily, individual records; some future-date artifacts in date fields. ✅⚠️
- **DC** `FEEDS/DCRA/FeatureServer/1`: 42 fields incl. ENTITYNAME/PREMISEADDRESS/issue dates. `FEEDS/DDOT/FeatureServer/48`: 14,342 permits in 2026. ✅
- **VA** Norfolk `dpi6-sct5`: business licenses, max opened 2026-07-03. ✅ Virginia Beach ArcGIS Property_Sales_ & Building_Permits: live, updated 2026-06-28. ✅
- **FL** Sunbiz SFTP `sftp.floridados.gov`: host reachable, accepts `Public` user (password prompt); documented daily fixed-width files. ✅⚠️ FL county appraiser ArcGIS (Lake `MapServer/12`): returns OwnerName/parcel. ✅
- **NJ** `w9se-dmra`: live; date fields noisy (artifact "2925"), updatedAt 2026-06-10. ✅⚠️
- **RI** Providence `c3q4-f95q` (tax roll) current; business/permit feeds stale. ⚠️
- **MA** data.mass.gov: not Socrata/CKAN; licensing API key-gated. ❌
- **NH**: no portal/API found. ❌

---

## 6. Implementation Notes for the App

- **Socrata states (CT, DE, PA, MD, + VA cities Norfolk/Dumfries, RI Providence):** reuse the existing NY ingester verbatim — just swap `<domain>` and `<resource-id>`. Add `$where=<datefield> > '<cutoff>'` for new-issuance filtering exactly as done for NY.
- **DC + VA-Beach + FL counties (ArcGIS):** add one small adapter — `…/FeatureServer/<n>/query?where=1=1&outFields=*&orderByFields=<date> DESC&resultRecordCount=N&resultOffset=M&f=json`. Paginate via `resultOffset`; get totals with `returnCountOnly=true`.
- **Bulk-file states (FL Sunbiz SFTP, NJ DCA roster):** schedule a daily/weekly pull + parser (fixed-width for Sunbiz per its file definitions; CSV/roster for NJ). Not live queries.
- **Date hygiene:** DE and NJ have out-of-range date artifacts — clamp to a sane window (e.g., 2015 ≤ date ≤ today) before computing "new in last N days."
- **PII/compliance:** CT/DE/DC license + business records contain names + addresses (public record). MD assessments hide owner names. Apply the same NYL permissible-use / FCRA-adjacent handling already used for NY ACRIS/DOB owner data.
