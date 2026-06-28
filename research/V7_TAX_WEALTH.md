# V7 — Tax & Wealth Public Data Sources

**For:** David Abraham (New York Life agent) — lead-intelligence app, East Coast affluent prospecting & money-in-motion
**Scope:** FREE, machine-readable, clean public tax/wealth datasets with exact endpoints. Verified live where possible (HTTP 200 checks performed June 28, 2026).
**Rule:** Research only — no app code changes.

All endpoints below were probed live during research. Status column reflects the actual HTTP response observed.

---

## 1. Ranked Master Table

Ranking score = Signal strength (how directly it identifies a wealthy individual or money-in-motion event) × Freshness (update cadence + recency) × Free-wireability (no key, clean format, stable URL). Scores are 1–5 per axis; **Rank** is the composite priority for this app.

| Rank | Source | Wealth/Tax Signal | Signal | Fresh | Wireable | Key? | Format | Update freq |
|------|--------|-------------------|:------:|:-----:|:--------:|:----:|--------|-------------|
| **1** | **IRS SOI — Income by ZIP** | AGI brackets per ZIP incl. $200k+ tier; counts of high-income returns, dividends, interest, cap gains by neighborhood | 5 | 4 | 5 | No | CSV | Annual |
| **2** | **ProPublica Nonprofit Explorer (990)** | Named nonprofit executives + their compensation = high-income individuals; org assets | 5 | 4 | 5 | No | JSON API | Continuous |
| **3** | **IRS SOI County-to-County Migration** | Who moved in/out + the AGI they brought = "money-in-motion" relocation events | 5 | 4 | 5 | No | CSV | Annual |
| **4** | **SEC EDGAR Form 4 (insider trades)** | Named executives selling/buying stock = real-time liquidity events (estate/annuity timing) | 5 | 5 | 4 | No | JSON/XML API | Real-time |
| 5 | **FEC OpenFEC Schedule A** | Named individuals giving ≥$X with employer/occupation/ZIP = disposable-wealth proxy | 4 | 5 | 4 | Free key | JSON API | ~Daily |
| 6 | **Zillow ZHVI (home values)** | Median home value by ZIP/neighborhood = affluent-area screening + equity proxy | 4 | 5 | 5 | No | CSV | Monthly |
| 7 | **HMDA Mortgage (CFPB)** | High-value loan originations (jumbo) by tract/lender = HNW home buyers, refis | 4 | 3 | 4 | No | CSV/JSON API | Annual |
| 8 | **BEA Personal Income by County** | Per-capita personal income by county = market sizing / territory prioritization | 3 | 4 | 4 | Free key | JSON API | Annual/Qtr |
| 9 | **Opportunity Zones (CDFI/HUD)** | Designated wealth-geography tracts = capital-gains/QOF investor mapping | 3 | 2 | 4 | No | XLSX / ArcGIS | Static (2018) |
| 10 | **Property Tax Assessments (county/state)** | Parcel-level assessed/market home values = direct high-value-home targeting | 5 | 4 | 2 | Varies | CSV/API | Varies by county |

> **Wireability caveat on #10:** property tax data is the single richest signal (parcel-level home values + owner names) but is fragmented across thousands of county assessors with no national standard — low wireability. Best free statewide portals are listed in §2.10.

---

## 2. Exact Endpoints, Columns & NYL Product Mapping

### 1. IRS SOI — Individual Income Tax by ZIP Code ⭐ PRIORITY
The flagship wealth-targeting dataset: income by ZIP, broken into AGI brackets, including a **$200,000+** tier. ([IRS ZIP Code data page](https://www.irs.gov/statistics/soi-tax-stats-individual-income-tax-statistics-zip-code-data-soi))

**Download URL pattern** (files live at `https://www.irs.gov/pub/irs-soi/`):
- All-states, with AGI brackets: `https://www.irs.gov/pub/irs-soi/YYzpallagi.csv` (YY = 2-digit tax year)
- All-states, no AGI brackets (totals only): `https://www.irs.gov/pub/irs-soi/YYzpallnoagi.csv`
- Documentation guide: `https://www.irs.gov/pub/irs-soi/YYzpdoc.docx`

**Verified live (HTTP 200):**
- `https://www.irs.gov/pub/irs-soi/22zpallagi.csv` — **Tax Year 2022, latest available** (last-modified Feb 14, 2025)
- `https://www.irs.gov/pub/irs-soi/22zpallnoagi.csv` — 200
- `https://www.irs.gov/pub/irs-soi/21zpallagi.csv` — 200 (TY2021)
- `https://www.irs.gov/pub/irs-soi/20zpallagi.csv` — 200 (TY2020)
- `https://www.irs.gov/pub/irs-soi/22zpdoc.docx` — 200 (column documentation)

> **Note:** TY2023 ZIP data is scheduled for release **August 27, 2026** per the IRS "What's New" page — set a refresh reminder.

**Key columns (verified from the live CSV header):**
| Column | Meaning | Wealth use |
|--------|---------|-----------|
| `STATEFIPS`, `STATE`, `zipcode` | Geography | Join key for East Coast ZIP filtering |
| `agi_stub` | AGI bracket code **1–6** (verified values present) | **The wealth dial** — filter to 5 & 6 |
| `N1` | Number of returns (≈ households) | Count of households in each bracket |
| `N2` | Number of individuals (exemptions ≈ population) | Population sizing |
| `A00100` | **Total Adjusted Gross Income** (in $000s) | Aggregate wealth per ZIP/bracket |
| `A00200` | Wages & salaries amount | Earned-income mass |
| `A00300` / `A00600` | Taxable interest / Ordinary dividends amount | **Investment-income signal → annuity/estate** |
| `A00650` | Qualified dividends | Investor concentration |
| `A01000` | Net capital gains amount | **Liquidity / money-in-motion proxy** |
| `A02650` | Total income amount | Top-line income mass |
| `A18500` / `A18450` | Real-estate / state-and-local taxes paid | High-value homeowners |
| `N02300` `A02300` | Unemployment comp (low in affluent ZIPs) | Negative filter |
| `A11900`/`A11902` | Tax due / overpayment refunded | — |

**agi_stub legend (standard SOI):** 1 = \$1–25k · 2 = \$25–50k · 3 = \$50–75k · 4 = \$75–100k · 5 = **\$100–200k** · 6 = **\$200k+**. Money amounts are in **thousands of dollars**.

**Per-state Excel files** also exist inside the annual ZIP archive (linked from the IRS page), but the all-states CSV above is the clean machine-readable path.

**NYL product mapping:** Filter East Coast ZIPs by share of `agi_stub` 5–6 returns and high `A00600`/`A01000` → rank neighborhoods for **estate planning** and **premium-finance (HNW)** prospecting; high dividend/interest mass flags **annuity** rollover candidates; concentration of `A18500` (RE taxes) flags high-value homeowners for **LTC / estate** outreach.

---

### 2. ProPublica Nonprofit Explorer API (IRS Form 990) ⭐ PRIORITY
Nonprofit executives are reliably high-income individuals; 990s disclose their names, titles, and compensation, plus org financials. **Free, no API key.** ([ProPublica Nonprofit Explorer API v2](https://projects.propublica.org/nonprofits/api))

**Base URL:** `https://projects.propublica.org/nonprofits/api/v2`

**Endpoints (verified live, HTTP 200, no key):**
- **Search:** `GET /search.json` — params: `q`, `state[id]` (2-letter, URL-encode brackets as `state%5Bid%5D=NY`), `ntee[id]` (1–10), `c_code[id]` (e.g. `3` for 501(c)(3)), `page` (0-indexed, 25/page).
  - Verified: `https://projects.propublica.org/nonprofits/api/v2/search.json?state%5Bid%5D=NY&c_code%5Bid%5D=3` → returned `total_results` with NY 501(c)(3) orgs (e.g., NYU, Healthfirst).
- **Organization detail:** `GET /organizations/{EIN}.json` — full profile + filings.
  - Verified: `https://projects.propublica.org/nonprofits/api/v2/organizations/142007220.json` → returned org profile incl. `asset_amount`, address, subsection code.

**Key response fields:**
- Org object: `ein`, `name`, `city`, `state`, `zipcode`, `subseccd`, `ntee_code`, `asset_amount`, `income_amount`, `guidestar_url`.
- Filing object: `totrevenue`, `totfuncexpns`, `totassetsend`, `totliabend`, `pct_compnsatncurrofcr` (% of expenses = officer compensation), plus 40–120 additional IRS element-name fields per form type (990 / 990-EZ / 990-PF). Executive comp detail (officer names + salaries) is in the full filing/990 Part VII.

**Bulk alternative (no key, deeper):**
- IRS 990 raw e-file XML on AWS: index at `https://www.irs.gov/charities-non-profits/form-990-series-downloads`; bulk XML historically via `https://apps.irs.gov/pub/epostcard/990/xml/` and the AWS open-data bucket. ProPublica's `pdf_url` per filing also serves the original 990.
- IRS Exempt Org Business Master File (EO BMF): `https://www.irs.gov/charities-non-profits/exempt-organizations-business-master-file-extract-eo-bmf` (CSV by region, refreshed ~monthly).

**Update frequency:** Continuous as IRS releases extracts (last major data updates ongoing).

**NYL product mapping:** Pull NY/NJ/CT/MA/FL 501(c)(3) and 990-PF (private foundation) orgs; extract officers/trustees with high reported comp → target list of **HNW individuals for estate planning, premium-finance, and key-person/deferred-comp** conversations. Foundation trustees are prime **estate & charitable-planning** leads.

---

### 3. IRS SOI County-to-County Migration (Money-in-Motion)
Who moved in/out of a county and the **AGI they carried** — the cleanest free "wealthy people relocating" signal. ([IRS Migration data page](https://www.irs.gov/statistics/soi-tax-stats-migration-data))

**Download URL pattern** (`https://www.irs.gov/pub/irs-soi/`):
- County inflow: `countyinflowYYZZ.csv` · County outflow: `countyoutflowYYZZ.csv`
- State inflow: `stateinflowYYZZ.csv` · State outflow: `stateoutflowYYZZ.csv`
- (YYZZ = year pair, e.g. `2223` for 2022→2023)

**Verified live (HTTP 200):**
- `https://www.irs.gov/pub/irs-soi/countyinflow2223.csv` — **latest, 2022→2023**
- `https://www.irs.gov/pub/irs-soi/countyoutflow2223.csv` — 200
- `https://www.irs.gov/pub/irs-soi/stateinflow2223.csv` — 200
- `https://www.irs.gov/pub/irs-soi/countyinflow2122.csv` / `countyoutflow2122.csv` / `stateinflow2122.csv` — 200 (prior year)
- Users guide: `https://www.irs.gov/pub/irs-soi/2223inpublicmigdoc.pdf`

**Key columns (verified from live header):**
`y2_statefips`, `y2_countyfips` (destination), `y1_statefips`, `y1_countyfips`, `y1_state`, `y1_countyname` (origin), **`n1`** (# returns/households moved), **`n2`** (# individuals), **`agi`** (aggregate AGI of movers, $000s).

Sample verified row: `01,001,96,000,AL,"Autauga County Total Migration-US and Foreign",2148,4413,138794`.

**Update frequency:** Annual.

**NYL product mapping:** Compute **average AGI per migrating return** (`agi / n1`) into each East Coast county. High-AGI inflows = affluent newcomers needing local advisors → **relocation-triggered estate review, annuity rollovers, and new-policy** outreach. Sort target counties by net high-AGI inflow.

---

### 4. SEC EDGAR Form 4 — Insider Transactions (Liquidity Events)
Executives, directors, and 10% owners report stock buys/sells on Form 4 — selling = a **liquidity event** ripe for wealth-deployment conversations. **Free, official, no key.**

**Full-text search API (verified live, HTTP 200):**
- `https://efts.sec.gov/LATEST/search-index?forms=4&startdt=YYYY-MM-DD&enddt=YYYY-MM-DD&q=KEYWORD`
- Verified: `https://efts.sec.gov/LATEST/search-index?forms=4&startdt=2026-06-20&enddt=2026-06-27` → **2,915 Form 4 filings** in one week, each with `display_names` (insider name + CIK) and the XML filing path.
- Requires a descriptive `User-Agent` header (SEC policy), e.g. `User-Agent: DavidLeads research@yourdomain.com`. (Tested and accepted.)

**Other free official paths:**
- Browse-EDGAR (Atom/HTML): `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=4&owner=include&count=10&output=atom` — verified 200.
- Full-index daily/quarterly: `https://www.sec.gov/Archives/edgar/full-index/2026/QTR2/` — verified 200 (lists every filing incl. Form 4 with accession paths).
- Each Form 4 XML (parse for transaction code, shares, price, A/D flag) is under `https://www.sec.gov/Archives/edgar/data/{CIK}/...`.

**Key fields (from Form 4 XML):** insider name + CIK, issuer + ticker, `transactionCode` (P=purchase, S=sale, M=option exercise), shares, price per share, shares owned after, direct/indirect ownership, `periodOfReport`.

**Update frequency:** Real-time (filings indexed within minutes of acceptance).

**NYL product mapping:** Screen for **S-code (sale)** transactions by officers/directors at NY-area issuers, especially large dollar sales and 10b5-1 plan sales → newly-liquid HNW individuals for **annuity, estate planning, and premium-finance** outreach. Cross-reference insider home ZIP (from proxy/SC 13D) with SOI high-AGI ZIPs.

---

### 5. FEC OpenFEC — Large Individual Donors (Wealth Proxy)
Itemized individual contributions (≥$200 are itemized) disclose **donor name, employer, occupation, city, ZIP, and amount** — large or frequent donors are a strong disposable-wealth proxy.

**Endpoint (verified live, HTTP 200):**
- `https://api.open.fec.gov/v1/schedules/schedule_a/`
- Verified query: `?api_key=DEMO_KEY&min_amount=10000&contributor_state=NY&two_year_transaction_period=2024&sort=-contribution_receipt_amount` → returned **14,647 NY contributions ≥$10,000** in the 2024 cycle (with full pagination).
- **Required:** at least one of `two_year_transaction_period`, `committee_id`, `contributor_name`, `contributor_city`, `contributor_zip`, `contributor_employer`, `contributor_occupation`, or `image_number` (confirmed from API's own 400 error message).
- **API key:** free from `https://api.data.gov/signup/` (7,200 calls/hour). `DEMO_KEY` works for testing.

**Key fields:** `contributor_name`, `contributor_employer`, `contributor_occupation`, `contributor_city`, `contributor_state`, `contributor_zip`, `contribution_receipt_amount`, `contribution_receipt_date`, `committee`.

**Update frequency:** Roughly daily as committees file.

**NYL product mapping:** Filter East Coast donors with high cumulative giving + high-end occupations/employers → affluent prospect list. ZIP joins back to SOI #1 for neighborhood corroboration. Useful for **estate planning, charitable-giving riders, and premium-finance** segmentation.

---

### 6. Zillow ZHVI — Home Values (Affluent-Area Screening)
Median home value by ZIP/neighborhood = clean affluent-area screen and homeowner-equity proxy. **Free CSV, no key.** ([Zillow Research Data](https://www.zillow.com/research/data/))

**Verified live (HTTP 200, ~122 MB):**
- ZIP-level ZHVI (all homes, smoothed, seasonally adj.): `https://files.zillowstatic.com/research/public_csvs/zhvi/Zip_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv`
- Other geographies follow the same path pattern with prefix `Metro_`, `State_`, `County_`, `City_`, `Neighborhood_` instead of `Zip_`.

**Structure:** one row per region; columns `RegionID, SizeRank, RegionName (ZIP), RegionType, StateName, State, City, Metro, CountyName`, then one column per month (`YYYY-MM-DD`) of the ZHVI value. ([ZHVI User Guide](https://www.zillow.com/research/zhvi-user-guide/))

**Update frequency:** Monthly.

**NYL product mapping:** Rank East Coast ZIPs by ZHVI to define **affluent territories**; high home values → home-equity wealth for **premium-finance, estate, and LTC** conversations. Pair with SOI AGI for a two-factor affluence score.

---

### 7. HMDA Mortgage Data (CFPB) — High-Value / Jumbo Loans
Loan-level mortgage originations with loan amount by census tract and lender — filter to **jumbo/high-value loans** to find HNW home buyers and cash-out refis. **Free, no key.** ([HMDA Data Browser API](https://ffiec.cfpb.gov/documentation/api/data-browser/))

**Endpoints (verified live):**
- Filtered CSV download: `https://ffiec.cfpb.gov/v2/data-browser-api/view/csv?years=2023&states=NY&loan_amount_min=1000000` → **302→200** (redirects to a generated CSV at `files.ffiec.cfpb.gov`, verified final 200).
- Aggregations (JSON/gzip): `https://ffiec.cfpb.gov/v2/data-browser-api/view/aggregations?years=2023&states=NY&loan_amount_min=1000000` — verified 200 (gzip).
- Filters supported: `years`, `states`, `counties`, `loan_amount_min`/`max`, `actions`, `loan_purposes`, etc.

**Key fields:** loan amount, loan purpose, action taken, property value, income, census tract, lender (LEI), occupancy, loan type.

**Update frequency:** Annual (2024 data released; historical back-files at `https://www.consumerfinance.gov/data-research/hmda/historic-data/`).

**NYL product mapping:** High loan-amount + high income in East Coast tracts = HNW homebuyers → **premium-finance, mortgage-protection, estate** outreach. Cash-out refis flag liquidity events.

---

### 8. BEA — Personal Income / Per-Capita Income by County
County per-capita personal income for market sizing and territory prioritization. ([BEA Personal Income by County](https://www.bea.gov/data/income-saving/personal-income-by-county))

**Endpoint (structure verified live — returns BEAAPI response; needs free UserID):**
- `https://apps.bea.gov/api/data?UserID={KEY}&method=GetData&datasetname=Regional&TableName=CAINC1&LineCode=3&GeoFips=COUNTY&Year=2024&ResultFormat=JSON`
- `CAINC1` LineCode `3` = **per-capita personal income (dollars)**; LineCode `1` = total personal income. Tables `CAINC4`/`CAINC5` give detailed/per-capita breakouts.
- Free UserID registration: `https://apps.bea.gov/API/signup/` (verified 200).

**Update frequency:** Annual county estimates (2024 released; 2025 due Dec 2, 2026), some series quarterly.

**NYL product mapping:** Rank East Coast counties by per-capita income to **prioritize territory and quota allocation**; macro layer beneath the ZIP/parcel targeting.

---

### 9. Opportunity Zones — Wealth Geography (Capital-Gains Investors)
Treasury/IRS-designated census tracts where investors park capital gains via Qualified Opportunity Funds — maps where capital-gains wealth is being deployed. **Free.**

**Verified live (HTTP 200):**
- Official designated-QOZ list (Treasury CDFI Fund, all states): `https://www.cdfifund.gov/sites/cdfi/files/documents/designated-qozs.12.14.18.xlsx` (301 → resolves to `https://www.cdfifund.gov/system/files/documents/designated-qozs.12.14.18.xlsx`, verified 200, XLSX, ~277 KB). Lists every designated tract GEOID by state/county.
- Spatial layer (shapefile/GeoJSON/CSV): HUD ArcGIS **`Opportunity_Zones`** FeatureServer exists in the HUD services directory (`https://services.arcgis.com/VTyQ9soqVukalItT/arcgis/rest/services` — confirmed the layer is published); download via the HUD Open Data / data.gov "Opportunity Zones" dataset page. ([data.gov Opportunity Zones](https://catalog.data.gov/dataset/opportunity-zones-16322), [Treasury QOZ page](https://home.treasury.gov/policy-issues/tax-policy/data-transparency/qualified-opportunity-zones))

**Key fields:** census tract GEOID (11-digit), state, county, tract type (low-income community vs. contiguous).

**Update frequency:** Static — designations finalized 2018, fixed for the program term.

**NYL product mapping:** Lower priority for direct prospecting; useful to identify **capital-gains investors and QOF participants** (often HNW) for estate/tax-aware planning, and to flag tracts where local investors may have deferred gains.

---

### 10. Property Tax Assessments — High-Value-Home Data (County/State)
Parcel-level assessed/market values + owner names — the **richest single affluence signal**, but fragmented across county assessors (low wireability; no single national free API). Best free machine-readable statewide East Coast portals:

- **New York** — NYS parcel/assessment data via NY Open Data (Socrata): `https://data.ny.gov` (search "Property Assessment Data from Local Assessment Rolls"); SODA API + CSV.
- **NYC** — Dept. of Finance assessment + ACRIS via NYC Open Data: `https://data.cityofnewyork.us` (datasets: "Property Valuation and Assessment Data", "Annualized Sales").
- **Massachusetts** — MassGIS standardized statewide parcel/assessor data: `https://www.mass.gov/info-details/massgis-data-property-tax-parcels` (downloadable, includes assessed value + owner).
- **Maryland** — SDAT real-property data via Maryland Open Data / `https://opendata.maryland.gov`.
- **Connecticut / NJ / FL** — mostly per-county assessor portals; FL counties (e.g. Miami-Dade, Palm Beach) publish free parcel CSV/APIs.
- National aggregators (free tiers / open): data.gov parcel datasets; many counties expose ArcGIS REST parcel layers.

**Key fields (typical):** parcel ID, owner name, situs address, assessed value, market/full value, land use code, year built, sale price/date.

**Update frequency:** Varies (annual assessment rolls; some real-time sales).

**NYL product mapping:** Highest-value homes + owner names = the most direct **HNW estate-planning, premium-finance, and LTC** target list. Best wired state-by-state, starting with NY (David's home market) where the statewide roll is free and machine-readable.

---

## 3. WIRE THESE 4 FIRST

These four are the highest signal-per-effort, all **free, no-friction, verified-200**, and directly map to NYL HNW products:

1. **IRS SOI Income-by-ZIP** — `https://www.irs.gov/pub/irs-soi/22zpallagi.csv`
   *Why first:* the foundational affluence map. One CSV gives every East Coast ZIP's $200k+ household counts, dividend/interest/cap-gains mass. No key, annual. Filter `agi_stub` 5–6.

2. **ProPublica Nonprofit Explorer 990 API** — `https://projects.propublica.org/nonprofits/api/v2/search.json?state%5Bid%5D=NY&c_code%5Bid%5D=3`
   *Why first:* named high-income executives & foundation trustees with compensation. No key, JSON, continuously updated. Iterate `/organizations/{EIN}.json` for officer comp.

3. **IRS SOI County-to-County Migration** — `https://www.irs.gov/pub/irs-soi/countyinflow2223.csv`
   *Why first:* the money-in-motion signal. `agi / n1` = average wealth of movers into each county → relocation-triggered outreach. No key, annual.

4. **SEC EDGAR Form 4 insider trades** — `https://efts.sec.gov/LATEST/search-index?forms=4&startdt=YYYY-MM-DD&enddt=YYYY-MM-DD`
   *Why first:* the only real-time liquidity-event feed — named executives selling stock today. No key (just a descriptive User-Agent). Filter S-code sales at NY-area issuers.

**Sequencing note:** #1 and #2 are the stated priorities and are nailed above with working URLs + full column/field layouts. Add #3 and #4 in the same sprint since they share the IRS/federal no-key pattern. FEC (#5), Zillow (#6), and HMDA (#7) are strong fast-follows. Property tax (#10) is the richest but should be wired state-by-state starting with NY.

---

## 4. Verification Log (probed June 28, 2026)

| Endpoint | Result |
|----------|--------|
| `irs.gov/pub/irs-soi/22zpallagi.csv` | 200, text/csv, mod Feb-2025 |
| `irs.gov/pub/irs-soi/22zpallnoagi.csv` | 200 |
| `irs.gov/pub/irs-soi/22zpdoc.docx` | 200 |
| `irs.gov/pub/irs-soi/countyinflow2223.csv` | 200, header + sample row confirmed |
| `irs.gov/pub/irs-soi/countyoutflow2223.csv` | 200 |
| `irs.gov/pub/irs-soi/stateinflow2223.csv` | 200 |
| ProPublica `/v2/search.json?state[id]=NY&c_code[id]=3` | 200, NY 501c3 orgs returned |
| ProPublica `/v2/organizations/142007220.json` | 200, org profile returned |
| `efts.sec.gov/LATEST/search-index?forms=4` | 200, 2,915 Form 4 hits/week, insider names |
| `sec.gov/cgi-bin/browse-edgar?type=4&output=atom` | 200 |
| `sec.gov/Archives/edgar/full-index/2026/QTR2/` | 200 |
| OpenFEC `schedule_a` (DEMO_KEY, NY, ≥$10k, 2024) | 200, 14,647 records |
| Zillow ZIP ZHVI CSV | 200, ~122 MB |
| HMDA filtered CSV (NY, ≥$1M, 2023) | 302→200 |
| HMDA aggregations (NY, ≥$1M) | 200 (gzip) |
| BEA `api/data` GetData CAINC1 | 200 (BEAAPI response; needs free UserID) |
| CDFI designated-QOZ XLSX | 200, ~277 KB |
| HUD ArcGIS `Opportunity_Zones` FeatureServer | layer confirmed published in services directory |
