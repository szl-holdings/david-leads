# V5 Fresh Data Feeds — "Act Now" Life-Event Triggers for NYL Agent (David Abraham, NY Metro)

**Prepared:** Sunday, June 28, 2026. **Scope:** FREE public data feeds that respond reliably from a Python/FastAPI server (JSON or easily-parsed CSV), to give David a timing edge on life-event triggers. **Research only — no app code changed.**

All endpoints below were hit live during research on 2026-06-28 unless explicitly flagged. The app already uses (with freshness): NY DOS business formations (daily), SEC EDGAR 8-K (real-time), Treasury rates (daily), BLS wages/unemployment (monthly), CDC natality (annual), Census ACS 5-yr (annual).

---

## 1. Freshness-Ranked Master Table (daily > weekly > monthly)

| # | Source / Dataset | Endpoint (verified pattern) | Key? | Update cadence | Life-insurance signal | NYL product map | Reliability |
|---|---|---|---|---|---|---|---|
| 1 | **NYC ACRIS – Real Property Master** (DEEDs + MTGE) `bnx9-e6tj` | `https://data.cityofnewyork.us/resource/bnx9-e6tj.json?doc_type=DEED&$order=recorded_datetime%20DESC&$limit=50` | **No** (optional app token raises limits) | **Daily** refresh; deeds recorded ~3–4 wks behind closing. Latest deed recorded 2026-05-29 at time of check | **Home purchase = #1 mortgage-protection trigger.** `document_amt` = sale/loan size → coverage need. 3,908 deeds recorded since May 1 | **Family coverage / mortgage protection (term life)** | High. Stable Socrata SODA API, no key needed. Join to `8h5j-fqxa` (Legals) for address, `636b-3b5g` (Parties) for buyer name |
| 2 | **NY DOS Active Corporations** `n9v6-gdp6` (the app's existing "business formations" feed) | `https://data.ny.gov/resource/n9v6-gdp6.json?$order=initial_dos_filing_date%20DESC&$limit=50` | **No** | **Daily** by `initial_dos_filing_date` (docs say monthly extract, but filings appear next-day; latest = 2026-06-27). County rollups available | New business owner = key-person / buy-sell / SEP-IRA need. Last 7 days: Kings 700, Albany 687, NY County 631, Queens 557, Nassau 443 | **Retirement (SEP/solo-401k), key-person, buy-sell** | High. Already in use — recommend adding **county + 7-day delta** queries |
| 3 | **NYC DOB NOW: Build – Job Application Filings** `w9ak-ipjd` | `https://data.cityofnewyork.us/resource/w9ak-ipjd.json?job_type=New%20Building&$order=filing_date%20DESC&$limit=50` | **No** | **Daily** (dataset updatedAt 2026-06-27). `filing_date` is a true timestamp (filterable) | New construction / new home. **1,357 New Building filings since June 1.** Returns `owner_first_name`, `owner_last_name`, `proposed_dwelling_units`, borough | **Family coverage / mortgage protection** | High. Modern dataset, clean timestamps, owner names included — best DOB source |
| 4 | **NYC DOB NOW: Build – Approved Permits** `rbx6-tga4` | `https://data.cityofnewyork.us/resource/rbx6-tga4.json?$limit=50` | **No** | **Daily** (updatedAt 2026-06-28T18:48) | Permit issued = construction underway. Has `owner_name`, `estimated_job_costs`, NB/demolition `work_type` | **Family coverage / mortgage protection** | High refresh, but **no explicit date field** — use as enrichment to #3, not for date filtering |
| 5 | **FEC OpenFEC – Schedule A (individual contributions)** | `https://api.open.fec.gov/v1/schedules/schedule_a/?api_key=KEY&contributor_state=NY&two_year_transaction_period=2026&min_amount=10000&sort=-contribution_receipt_date` | **Free key** (`DEMO_KEY` works for testing; request real key from APIinfo@fec.gov, 7,200 calls/hr) | **Daily** (filings posted continuously; latest NY contribution 2026-06-03 seen). 5,260 NY contributions ≥$10k in 2026 cycle | **High-net-worth signal.** Large political donors → estate planning, premium-finance, wealth transfer. Returns name, employer, occupation, city, amount | **Retirement / estate planning / LTC / large permanent policies** | High. Stable, documented. Requires a free key for production rate limits. PII-sensitive — handle compliantly |
| 6 | **USAspending.gov – Spending by Award** | `POST https://api.usaspending.gov/api/v2/search/spending_by_award/` (JSON body: filter `recipient_locations:[{country:"USA",state:"NY"}]`, `award_type_codes`, `time_period`) | **No** | **Daily/weekly** (federal feeds refresh continuously) | **Liquidity event for local businesses** — new grant/contract = cash infusion → business owner can fund retirement / key-person. Verified returning NY awards by amount | **Retirement (qualified plans), key-person, business succession** | High. POST API, well-documented, no key. Earliest date 2007-10-01 |
| 7 | **Freddie Mac PMMS via FRED – 30-yr mortgage rate** `MORTGAGE30US` | `https://api.stlouisfed.org/fred/series/observations?series_id=MORTGAGE30US&api_key=KEY&file_type=json&sort_order=desc&limit=4` | **Free key** (FRED API key, instant signup) | **Weekly** (Thursdays 12pm ET; latest 2026-06-25 = 6.49%) | Macro mortgage-affordability context; pairs with ACRIS to gauge refinance/purchase waves. Not a per-lead trigger | **Mortgage protection (context layer)** | High. Note: a true **weekly MBA mortgage-applications index is NOT on FRED**; PMMS rate is the weekly proxy |
| 8 | **FRED – Consumer Sentiment** `UMCSENT` | `https://api.stlouisfed.org/fred/series/observations?series_id=UMCSENT&api_key=KEY&file_type=json&sort_order=desc&limit=2` | **Free key** | **Monthly** | Macro mood / income-confidence backdrop for outreach timing | **All products (context)** | High |
| 9 | **Census ACS 1-Year (2023)** — median income/age, NY counties pop 65k+ | `https://api.census.gov/data/2023/acs/acs1?get=NAME,B19013_001E,B01002_001E&for=county:*&in=state:36&key=KEY` | **Free key REQUIRED** (Census now redirects to "Missing Key" without one; app likely already has one for its ACS 5-yr feed) | **Annual** (1-yr is MORE current than the 5-yr already in use) | Up-to-date median household income (`B19013_001E`) and median age (`B01002_001E`) per large county → better affordability/targeting than 5-yr | **All products (targeting layer)** | High once key supplied. 1-yr only covers counties ≥65k pop (covers all NY-metro counties) |
| 10 | **BLS QCEW – county employment & wages** | `https://data.bls.gov/cew/data/api/2025/1/area/36061.csv` (36061 = NY County/Manhattan; 36047 = Kings, 36081 = Queens, 36005 = Bronx, 36085 = Richmond, 36059 = Nassau, 36103 = Suffolk, 36119 = Westchester) | **No** | **Quarterly** (more granular than the monthly state BLS feed already used; 2025 Q1 already available — fresher than expected) | County-level establishment counts, employment levels, avg weekly wage, over-the-year change → local economic-health / employer-growth signal | **Family coverage / retirement (local prospecting)** | High. **CSV not JSON** — parse with `csv`/`pandas`. No key |
| 11 | NY DOS Active Corporations — **county delta query** (same dataset as #2) | `https://data.ny.gov/resource/n9v6-gdp6.json?$select=county,count(*)&$where=initial_dos_filing_date>'2026-06-20T00:00:00'&$group=county&$order=count%20DESC` | **No** | **Daily** | County-level new-business velocity for territory planning | **Retirement / business** | High |

---

## 2. WARN Act Layoff Notices — Important Caveat (your priority #1)

**Finding:** NY's WARN data is **NOT** a Socrata JSON dataset on data.ny.gov (despite the task's expectation). NY moved WARN to a **Tableau dashboard** in April 2025.

- **Current source:** NY DOL WARN Dashboard — `https://dol.ny.gov/warn-dashboard`, backed by a Tableau viz at `https://data.osc.ny.gov` (Comptroller's `DOL-WARNDashboard`). ([NY DOL WARN Dashboard](https://dol.ny.gov/warn-dashboard))
- **Legacy (frozen) data:** `https://dol.ny.gov/legacy-warn-notices` and per-year HTML pages e.g. `https://dol.ny.gov/2023-warn-notices`. **No new notices added after 2025-04-01.** ([NY DOL Legacy WARN](https://dol.ny.gov/legacy-warn-notices))
- **No official structured API.** The Socrata catalog returns no WARN dataset for data.ny.gov or health.data.ny.gov.

**Recommended FastAPI approach for WARN (pick one):**
1. **Tableau export** — Tableau views expose a CSV via `.../views/<view>?:format=csv` or the underlying `tabdata`/`vqlcmdserver` JSON. Fragile (Tableau internal API changes); requires session-token handling. Medium reliability.
2. **HTML extraction of the dashboard table** — parse the rendered WARN notices table. Medium reliability.
3. **Federal cross-check:** US DOL aggregates state WARN; third-party mirrors exist (e.g., Big Local News `newyork_warn_raw`, 4,268 rows). Use only as backup — not authoritative/fresh. ([Big Local News NY WARN](https://biglocal.datasettes.com/COVID_WARN_Notices/newyork_warn_raw))

**Verdict:** WARN is the highest-signal trigger (layoff = income-protection urgency, maps to **family coverage / disability / income protection**) but is the **least reliable to wire** because there is no JSON API. Treat as a scheduled scheduled extractor with manual fallback, not a clean feed. **Flagged as needs-extraction / unreliable.**

---

## 3. Census ACS 1-Year — Exact Working Pattern (your priority #4)

- **Endpoint:** `https://api.census.gov/data/2023/acs/acs1?get=NAME,B19013_001E,B01002_001E&for=county:*&in=state:36&key=YOUR_KEY`
- **Variables:** `B19013_001E` = median household income; `B01002_001E` = median age; add `B01003_001E` for total population.
- **Key status:** **REQUIRED as of now.** Without a key the API 302-redirects to `missing_key.html`. The app almost certainly already holds a Census key for its existing ACS 5-yr feed — reuse it. Free instant signup at the Census site.
- **Coverage:** ACS 1-yr only publishes counties with population ≥65,000 — this covers **all NY-metro counties** (NYC five boroughs, Nassau, Suffolk, Westchester, Rockland, etc.). It is **one year more current** than the 5-yr estimates already in the app.

---

## 4. "Wire These 4 First" — Ranked by (Timeliness × Lead-Signal Strength × Reliability)

| Rank | Feed | Why it wins | Effort |
|------|------|-------------|--------|
| **1** | **NYC ACRIS Real Property Master — DEEDs (`bnx9-e6tj`)** | Daily-refreshed, **no key**, and a home purchase is the single strongest mortgage-protection trigger. `document_amt` directly sizes the coverage need. ~3,900 fresh deeds/month in NYC. Highest signal × reliability. | Low — one SODA GET + join Legals/Parties for address & buyer name |
| **2** | **NYC DOB NOW Job Application Filings — New Buildings (`w9ak-ipjd`)** | Daily, **no key**, clean `filing_date` timestamp, and returns **owner first/last name + dwelling units** out of the box. 1,357 new-building filings since June 1 = a steady, named, geocoded lead stream for new homeowners/developers. | Low — single filtered GET, owner name already present |
| **3** | **USAspending.gov Spending by Award (NY)** | Daily-ish, **no key**, POST JSON. Federal grant/contract to a local business = a clear liquidity event → retirement-plan & key-person opportunity. Distinct signal from the consumer-home feeds above; widens product mix. | Low–Med — POST body with NY filter |
| **4** | **NY DOS Active Corporations — county delta (`n9v6-gdp6`)** | Already in the app but **underused**: add daily **county-level new-business counts and 7-day deltas** to drive territory prospecting (retirement/business products). Daily fresh, no key, trivial query. | Very low — add `$group=county` + date-window queries to existing feed |

**Honorable mentions to wire next:** FEC Schedule A (best HNW signal but needs a free key + PII compliance care) and Census ACS 1-yr 2023 (best targeting layer; reuse existing Census key).

---

## 5. Key-Status & Reliability Flags (quick reference)

- **No key, high reliability (wire freely):** ACRIS (`bnx9-e6tj`, `8h5j-fqxa`, `636b-3b5g`), DOB NOW (`w9ak-ipjd`, `rbx6-tga4`), NY DOS Active Corporations (`n9v6-gdp6`), USAspending, BLS QCEW (CSV).
- **Free key required (easy):** FRED (`MORTGAGE30US`, `UMCSENT`), FEC OpenFEC (`DEMO_KEY` for dev; request production key from APIinfo@fec.gov), Census ACS 1-yr (reuse existing key).
- **No clean JSON API — needs extractor / unreliable:** **NY WARN** (Tableau dashboard only; no Socrata dataset). Highest signal, lowest wireability — build a scheduled extractor with HTML/Tableau-CSV fallback, or defer.
- **Avoid for date-filtering:** Legacy **DOB Permit Issuance (`ipu4-2q9a`)** stores dates as `MM/DD/YYYY` text, so timestamp `$where` filters fail and sample rows lag to 2020–2022. Use DOB NOW datasets instead.
- **PII / compliance note:** ACRIS, DOB owner names, and FEC donor names contain personal data. Confirm permissible-use under NYL compliance and FCRA-adjacent rules before using for outreach.

---

## 6. Verification Log (hit live 2026-06-28)

- ACRIS `bnx9-e6tj`: returned DEED docs, latest `recorded_datetime` 2026-05-29, 3,908 deeds since 2026-05-01. ✅
- DOB NOW `w9ak-ipjd`: 1,357 New Building filings since 2026-06-01, owner names + dwelling units present. ✅
- DOB NOW `rbx6-tga4`: updatedAt 2026-06-28T18:48; no date field. ✅
- NY DOS `n9v6-gdp6`: latest filing 2026-06-27; county deltas returned (Kings 700, etc.). ✅
- USAspending `spending_by_award`: returned NY awards sorted by amount, no key. ✅
- FEC `schedule_a` with `DEMO_KEY`: 5,260 NY contributions ≥$10k in 2026 cycle, latest 2026-06-03. ✅
- FRED `MORTGAGE30US`: latest 2026-06-25 = 6.49% (per Freddie Mac PMMS). ✅ ([Freddie Mac PMMS](https://www.freddiemac.com/pmms))
- Census ACS1 2023: returns "Missing Key" without key → **key required**, otherwise valid. ⚠️
- BLS QCEW CSV `…/2025/1/area/36061.csv`: returns 2025 Q1 NY County data (CSV). ✅
- WARN: no Socrata dataset found; Tableau dashboard only. ⚠️ ([NY DOL WARN Dashboard](https://dol.ny.gov/warn-dashboard))
