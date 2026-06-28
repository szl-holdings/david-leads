# David Leads V3 — Recon Refresh + Buildable Wire-In Spec

**Project:** David Leads (AI lead-intelligence app for David Abraham, NYL financial professional)
**Author:** Opus Agent 1
**Date:** 2026-06-28
**Scope:** (1) Refresh of competitive recon since the last pass; (2) concrete, buildable spec of FREE public data sources to wire into the FastAPI server, each with exact endpoint, key status, life-insurance lead signal, and product mapping; plus non-data integrations. Research only — no app code touched.

> **Read this first.** Everything below is verified against the live endpoints on 2026-06-28 (curl tests run against FRED, Treasury FiscalData, BLS, Census, IRS, and data.ny.gov). Where a source turned out to be gated or paywalled, that is called out explicitly so we do not waste a sprint wiring something that won't respond from a server. The crown-jewel discovery is at the very bottom.

---

## PART 1 — COMPETITIVE RECON REFRESH (what's NEW since LEADERS_RECON.md)

The strategic picture from the last pass holds: every leader still sells an opaque score to carriers/marketing teams, not to an individual agent. But four things moved in 2026, and all of them *reinforce* our wedge.

### 1.1 Verisk → Anthropic Claude MCP connectors (May 5, 2026) — the biggest move
Verisk launched **Model Context Protocol (MCP) connectors that put its analytics directly inside Anthropic's Claude** ([GlobeNewswire, May 5 2026](https://www.globenewswire.com/news-release/2026/05/05/3288003/0/en/verisk-brings-its-trusted-analytics-and-generative-ai-capabilities-directly-into-anthropic-s-claude.html); [Verisk AI page](https://www.verisk.com/company/ai/)). Two connectors shipped: **Verisk Underwriting Intelligence (ISO Indications)** for loss-cost trends/filing signals, and **XactRestore** for claims-repair estimating ([BriefGlance summary](https://briefglance.com/companies/verisk-analytics-inc/pulses/10526)).

- **Critical constraint that protects us:** the connector is **Claude Enterprise only**, requires an **active Verisk/ISOnet subscription with entitlements**, OAuth + MFA, and is **read-only loss-cost/actuarial data** — there is *nothing here for an individual life agent*, and *no lead generation at all* ([Verisk Underwriting Intelligence Connector page](https://www.verisk.com/resources/verisk-underwriting-intelligence/)). It is a carrier-actuary tool with a chat skin.
- **Takeaway:** the state-of-the-art "AI access layer" for insurance data is now *conversational MCP access to a proprietary, subscription-gated dataset*. We can out-class this by giving David **conversational access to FULLY PUBLIC, fully cited data** — same UX paradigm, none of the gate, plus a signed receipt Verisk can never produce.

### 1.2 The 2026 trigger-driven prospecting consensus has crystallized
The market has now openly converged on **trigger-driven qualification replacing passive/general targeting** — which is *exactly* the thesis David Leads is built on, now validated as the mainstream playbook:

- A 2026 HNW-prospecting analysis states HNW prospecting is "moving from passive referral cultivation to **trigger-driven qualification, where specific life events and financial thresholds activate outreach** rather than general wealth signals," with the activating signals named as **property closings, board appointments, and business liquidity events** — explicitly described as **public-data signals** ([Kadence, Jun 10 2026](https://www.startkadence.com/blog/high-net-worth-insurance-prospecting-term-pipeline-scaling)). HNW floor = **$1M investable assets**; premium tier = **$5M liquid / $10M net worth**; only **25% of affluent individuals report a strong risk appetite** (HUB 2026 survey, cited same source).
- A 2026 health-lead case study independently confirms the trigger taxonomy: "**recently married, recently moved, recently self-employed, recently lost employer coverage** — these are the *real* trigger events that put a family in the market," and "buyers are triggered by life events (job change, marriage, baby, self-employment)" ([D1TechCreative, Jun 18 2026](https://www.d1techcreative.com/blog/health-insurance-lead-generation-case-study/)).
- Life-insurance marketing guides now price **life-event search triggers** ("life insurance new baby / after marriage / mortgage") as the highest-intent, lowest-competition keywords at $6–15 ([Bespoken, Jun 4 2026](https://www.bspkn.co/insights/life-insurance-agent-marketing-get-more-clients-2026/)).

**Implication:** our public-data life-event radar is no longer a novel bet — it's the acknowledged winning strategy, but *nobody has packaged the public signals for an individual life agent with provenance.* We are early to the consensus, not betting against it.

### 1.3 The lead-marketplace economics got worse for agents (good for us)
2026 pricing confirms the marketplace treadmill is intensifying: **shared web leads $5–20, exclusive $30–60, live transfers $50–150+, aged leads $0.50–2** ([EBS Media, Jun 26 2026](https://ebsmedia.us/latest/insight/life-insurance-leads/); [Kadence aged-lead economics, Jun 9 2026](https://www.startkadence.com/reports/aged-lead-economics-cost-per-policy)). Aged leads convert at only **0.4%–1.0% over 90 days (≈1 policy per 100–250 leads)** ([Kadence](https://www.startkadence.com/reports/aged-lead-economics-cost-per-policy)). Our near-zero-marginal-cost, exclusive, event-real leads look better by the quarter.

### 1.4 NEW REGULATORY SHIFT — TCPA "one-to-one consent" (must design around)
The **FCC updated TCPA rules to require one-to-one consent**: a lead who checked a box agreeing to be contacted "by insurance companies" is **no longer sufficient — they must have consented specifically to be contacted by you** ([EBS Media, Jun 26 2026](https://ebsmedia.us/latest/insight/life-insurance-leads/)). A2P 10DLC registration is now table stakes for automated SMS ([CUFinder, May 31 2026](https://cufinder.io/blog/lead-generation-industry/insurance/)).
- **Why this is a moat-amplifier:** purchased/shared leads are now a *consent liability*. Our leads are sourced from **public records — outreach is initiated by the agent, not predicated on a resold consent checkbox** — so our compliance card ("public records, non-FCRA, permitted use = outreach only") becomes even more valuable. Keep this front-and-center.

### 1.5 New entrants in the agent-AI layer (mostly CRM/voice, not lead intelligence)
The crowded 2026 "AI tools for agents" field is overwhelmingly **conversational/CRM/claims automation, not public-data lead generation** ([Thunai, Jun 19 2026](https://www.thunai.ai/blog/best-ai-tools-for-insurance-agents)):
- **Thunai AI** — unified "Brain + Agent Studio + Revenue AI," $99/mo unlimited users; Revenue AI scores deal-close likelihood from calls/emails.
- **HubSpot Smart CRM (Breeze AI)** — predictive lead scoring from "past data and buying signs."
- **AI phone agents** (e.g., **Thoughtly**) now trigger an **outbound call or SMS the instant a web form / aggregator / call-in event fires** ([Thoughtly, Jun 10 2026](https://thoughtly.com/blog/best-ai-phone-agents-for-life-insurance-leads-2026)).
- **Zocks / monday.com / Insightly** push **life-event-driven outreach + 5-touch follow-up sequences** as the standard CRM motion ([monday.com, May 28 2026](https://monday.com/blog/crm-and-sales/life-insurance-crm/); [Zocks, Jun 24 2026](https://www.zocks.io/blog/how-life-insurance-agents-use-ai)).
- **LeO** remains commercial-lines-only (x-dates, 5500, DOT) — the **individual-life public-data lane is still wide open.**

**Net of the refresh:** the field is racing toward (a) conversational/MCP access to data and (b) trigger-driven, fast-follow-up outreach. None of them generate **verified, cited, public-data life-event leads for a single life agent.** Our V3 should lean into a conversational query layer + instant-follow-up talk tracks, on top of the provenance moat.

---

## PART 2 — FREE PUBLIC DATA WIRE-INS (verified endpoints, signals, product mapping)

All endpoints below were live-tested on 2026-06-28. Key legend: **🟢 no key** · **🟡 free key (env, sample fallback)** · **🔴 gated/skip**.

Product map shorthand: **FAM** = family/income protection (term/whole), **RET** = retirement/annuity, **LTC** = long-term care, **COL** = college funding.

---

### 2.1 🟡 FRED — Federal Reserve Economic Data (interest/mortgage/CPI/housing)
**Base / JSON shape (verified):**
```
https://api.stlouisfed.org/fred/series/observations?series_id={ID}&api_key={KEY}&file_type=json&sort_order=desc&limit={N}
```
Response: `{"observations":[{"date":"YYYY-MM-DD","value":"6.49"}, ...]}` ([FRED series_observations docs](https://fred.stlouisfed.org/docs/api/fred/series_observations.html)). **Key required** (free, 32-char), read from `env FRED_API_KEY` with sample fallback. No-key call returns HTTP 400 `Variable api_key is not set` (verified). Optional params: `frequency` (d/w/m/q/a), `units` (lin/chg/pch), `observation_start`.

**Confirmed series IDs + live values (2026-06-28):**
| Series ID | What | Latest value | Freq | Lead signal → product |
|---|---|---|---|---|
| `MORTGAGE30US` | 30-Yr Fixed Mortgage Avg (Freddie Mac) | **6.49%** (2026-06-25) | Weekly | Rate environment for new-homeowner term-need + affordability framing → **FAM** |
| `FEDFUNDS` | Effective Fed Funds Rate | monthly | Monthly | Macro rate backdrop; annuity/whole-life crediting context → **RET** |
| `DFF` | Fed Funds (daily) | daily | Daily | Same, intraday-fresh ticker value → **RET** |
| `CPIAUCSL` | CPI All-Urban (inflation) | **333.979** (May 2026) | Monthly | Inflation erosion of coverage → "your $500k policy buys less" nudge → **FAM/RET** |
| `DGS10` / `GS10` | 10-Yr Treasury (daily/monthly) | — | Daily/Mo | Long-rate context for whole-life/annuity → **RET** |
| `HOUST` | Housing Starts (000s units) | monthly | Monthly | Housing-market heat → new-mortgage volume proxy → **FAM** |
| `CSUSHPINSA` | Case-Shiller US National Home Price Index | — | Monthly | Home equity growth → estate/LTC funding capacity → **LTC/RET** |
| `UNRATE` | National Unemployment Rate | — | Monthly | Macro income-security backdrop → **FAM** |
| `UMCSENT` | Consumer Sentiment | — | Monthly | Buying-mood ticker color → all |

(IDs cross-verified across [FRED MORTGAGE30US](https://fred.stlouisfed.org/series/MORTGAGE30US), [FRED CPIAUCSL](https://fred.stlouisfed.org/series/CPIAUCSL), and FRED series-ID compendiums [DEV Community](https://dev.to/0012303/fred-has-a-free-api-800000-us-economic-time-series-at-your-fingertips-46e9), [ApudFlow](https://apudflow.com/docs/Workers/flow/fred_connector/).)

**Build note:** FRED powers the macro ticker AND the needs-calculator math (mortgage rate × balance = monthly obligation the policy must cover). It is the single most reliable, highest-frequency free source.

---

### 2.2 🟢 U.S. Treasury FiscalData — rates, NO KEY (verified live)
**Base:** `https://api.fiscaldata.treasury.gov/services/api/fiscal_service`
**Best endpoint (verified live, no key):**
```
GET /v2/accounting/od/avg_interest_rates?sort=-record_date&page[size]=N
```
Returned `{"data":[{"record_date":"2026-05-31","security_desc":"Treasury Bills","avg_interest_rate_amt":"3.690"},{"...Notes":"3.248"},{"...Bonds":"3.413"}],"meta":{...}}` (verified 2026-06-28). No account needed; returns JSON; standard HTTP codes ([FiscalData API docs](https://fiscaldata.treasury.gov/api-documentation/); endpoint catalog [DataDistillr](https://docs.datadistillr.com/connecting-data/connecting-to-apis-and-external-data/fiscaldata-api/)).
- Other useful endpoints: `/v2/accounting/od/debt_to_penny`, `/v2/accounting/od/interest_expense`.
- **Lead signal → product:** government-backed yield baseline for **annuity/whole-life positioning** ("guaranteed alternatives are yielding X") → **RET**. Value: a *no-key, never-rate-limited* fallback if FRED key is missing — guarantees the rate ticker always renders honest data.

---

### 2.3 🟡 BEA — Regional personal income (free key)
**Base:** `https://apps.bea.gov/api/data/` ([BEA for-developers](https://www.bea.gov/resources/for-developers))
**Pattern:**
```
https://apps.bea.gov/api/data/?&UserID={KEY}&method=GetData&datasetname=Regional&TableName=CAINC1&LineCode=3&GeoFips=COUNTY&Year=LAST5&ResultFormat=JSON
```
- **Key:** free signup (name + email) at https://apps.bea.gov/API/signup/ — read from `env BEA_API_KEY`, sample fallback. (Verified the API responds and validates UserID; an invalid key is rejected gracefully.)
- **Key tables/line codes:** `CAINC1` = County personal income summary — **LineCode 1** = total personal income, **LineCode 2** = population, **LineCode 3** = **per-capita personal income**. `GeoFips=36000` = NY statewide; per-county uses 5-digit county FIPS (e.g. `36119` Westchester).
- **Lead signal → product:** county-level **per-capita income trend** = territory affluence + premium-capacity sizing. Rising per-capita income → upgrade FAM term toward whole-life / fund **COL** and **RET**. ([Personal Income by County](https://www.bea.gov/data/income-saving/personal-income-by-county))

---

### 2.4 🟢/🟡 Census ACS 5-Year — extra variables (David already has Newdave key)
**Pattern (verified group definitions live):**
```
https://api.census.gov/data/2023/acs/acs5?get=NAME,{VARS}&for=county:*&in=state:36&key={KEY}
```
- **Key:** required — no-key call returns **HTTP 302** (verified). David's app already uses the Census/Newdave key, so this is a drop-in extension of an existing wired source, NOT a new credential.
- **Confirmed variable groups + exact labels (pulled live from `/groups/{G}.json`):**

| Variable | Label (verified) | Lead signal → product |
|---|---|---|
| `B25003_001E` / `_002E` / `_003E` | Total / **Owner occupied** / **Renter occupied** (tenure) | Homeownership rate → mortgage-protection density → **FAM** |
| `B15003_022E`…`_025E` | Bachelor's / Master's / Professional / **Doctorate** degree | Educational attainment → income proxy + **COL** funding propensity |
| `B12001_*` | Sex by marital status (Now married / Widowed / Divorced) | Marital composition: **widowed** = bereavement-adjacent need; **married** = beneficiary/income-protection → **FAM** |
| `B11003_002E`…`_006E` | Married-couple families **with own children under 18** (incl. "Under 6," "6 to 17") | **Households with minor children = the #1 family-coverage trigger** → **FAM + COL** |
| `B19013_001E` | Median household income (2023 $) | Premium-capacity + coverage-gap math → all |

(Labels verified from [Census ACS5 2023 variable groups API](https://api.census.gov/data/2023/acs/acs5/groups/B25003.json).)
- **Build note:** `B11003` (families with children under 18) and `B25003` (homeownership) are the two highest-signal additions — they let the Territory Map color counties by *family-coverage opportunity density* rather than raw population.

---

### 2.5 🟢 BLS — local unemployment & wages, NO KEY (verified live)
**Base:** `https://api.bls.gov/publicAPI/v2/timeseries/data/{SERIES_ID}` (GET works no-key; POST for multi-series; registering a free key only raises the daily quota).
**LAUS (Local Area Unemployment Statistics) series-ID construction:**
- **County:** `LAUCN` + `{state2}{county3}` + `0000000` + `{measure}` — measure `03` = unemployment rate.
  - Verified: `LAUCN361190000000003` (Westchester County, NY) → **3.3%** (Apr 2026, preliminary).
- **Statewide:** `LAUST` + `{state2}` + `0000000000` + `{measure}`.
  - Verified: `LAUST360000000000003` (NY) → **4.2%** (May 2026).
- Response: `{"Results":{"series":[{"seriesID":...,"data":[{"year","period","periodName","value","footnotes"}]}]}}` (verified).
- **Lead signal → product:** **rising county unemployment = income-protection urgency** (term, DI conversations) and a softer touch on discretionary RET/COL; **falling unemployment = capacity to fund** RET/COL/LTC → **FAM (primary)**.

---

### 2.6 🟢 IRS SOI County-to-County Migration — bundle a curated NY slice (verified live download)
**This source has NO live API — it is a static bulk CSV we download once and bundle as a curated NY asset (exactly as the brief specifies).**

- **Exact current files (Filing Years 2021→2022, released Jun 2024 — the most recent available):**
  - **County inflow:** `https://www.irs.gov/pub/irs-soi/countyinflow2122.csv` ✅ verified live, **90,499 rows, ~4.28 MB**
  - **County outflow:** `https://www.irs.gov/pub/irs-soi/countyoutflow2122.csv`
  - State inflow/outflow: `stateinflow2122.csv` / `stateoutflow2122.csv`
  - Documentation/users guide: `https://www.irs.gov/pub/irs-soi/2122inpublicmigdoc.pdf`
  - Index page: [SOI Migration data 2021–2022](https://www.irs.gov/statistics/soi-tax-stats-migration-data-2021-2022)
- **Column layout (verified from live header of `countyinflow2122.csv`):**
  ```
  y2_statefips, y2_countyfips, y1_statefips, y1_countyfips, y1_state, y1_countyname, n1, n2, agi
  ```
  - `y2_*` = **destination** (where they moved TO, year 2) · `y1_*` = **origin** (year 1)
  - `n1` = number of returns (≈ households) · `n2` = number of exemptions (≈ individuals) · `agi` = aggregate adjusted gross income (thousands $)
  - Special origin rows use pseudo-FIPS: `97001`=Total Same-State, `97003`=Total Different-State, `96000`=Total US+Foreign, `36xxx`=same-state county; a `Non-migrants` row gives the stayer baseline.
  - **Verified NY sample** (`y2_statefips=36`): `36,1,36,83,NY,Rensselaer County,1588,2477,89790` = 1,588 households (2,477 people, $89.79M AGI) moved INTO Albany County FROM Rensselaer.
- **Curated NY slice to bundle:** `awk -F',' '$1==36'` → all rows where destination is NY. For each NY county, rank top origin counties and sum **inflow AGI** = "new affluent residents arriving."
- **Lead signal → product:** **in-migration = brand-new residents with no local advisor** — the cleanest cold-territory opportunity. High-AGI inflow → affluent newcomers needing **FAM + RET + estate**; family-sized inflow (high n2/n1 ratio) → **FAM + COL**. Pair with property-deed data downstream for an address-level "just moved in" trigger.

---

### 2.7 🟢 NY State Open Data (data.ny.gov) — NEW BUSINESS FORMATIONS, NO KEY (verified live) ⭐
**This is a high-value find the brief didn't list — it replaces the now-paywalled OpenCorporates for NY business signals.**
**Endpoint (Socrata SODA, verified live, no key):**
```
https://data.ny.gov/resource/n9v6-gdp6.json?$limit=N
https://data.ny.gov/resource/n9v6-gdp6.json?county=Westchester&$where=initial_dos_filing_date > '2025-01-01'
https://data.ny.gov/resource/n9v6-gdp6.json?$select=count(dos_id)&county=Westchester&$where=...   (aggregation works)
```
- Dataset: NY DOS **Active Corporations**. Returns JSON: `dos_id, current_entity_name, initial_dos_filing_date, county, jurisdiction, entity_type, dos_process_address_1/city/state/zip` (verified — includes a mailable address). Optional free Socrata app token only raises throughput.
- Verified: filtering Westchester filings since 2025-01-01 returned a live count (19,003 cumulative active in sample query); supports full SoQL (`$select`, `$where`, `count()`, date filters).
- **Lead signal → product:** **a newly-formed business with a NY address and a filing date = a buy-sell / key-person / business-continuation life trigger** (the life-side analog of LeO's commercial x-dates, but free and public) → **FAM (key-person/buy-sell) + RET (owner SEP/retirement) + COL.** Filing date is a true time-anchored event for the X-Date countdown UX.

---

### 2.8 🔴 / ⚠️ Sources to AVOID or down-prioritize (saves a wasted sprint)
- **🔴 HUD Aggregated USPS Vacancy Data** — *restricted to government & non-profit registered users; will NOT respond from David's commercial app* ([HUD USPS datasets](https://www.huduser.gov/portal/datasets/usps.html); [HUD login](https://www.huduser.gov/apps/public/usps/login)). **Skip.**
- **⚠️ USPS PostalPro "Occupancy Trends" County Vacant File** — public-facing but requires an **Occupancy Trends License Agreement + Order Form**, not an open download ([PostalPro Occupancy Trends](https://postalpro.usps.com/ot)). Treat as a manual, licensed bundle at best — not a reliable server wire-in.
- **🟡 HUD-USPS ZIP Crosswalk API** — this one *is* free with a token ([HUD crosswalk API](https://www.huduser.gov/portal/dataset/uspszip-api.html)) but only maps ZIP↔tract/county; it's a geo-utility, not a lead signal. Use only if we need ZIP→county reconciliation.
- **🔴 OpenCorporates API** — now a paid/gated data-licensing product ("get data access to 200M companies"), not a free open endpoint ([api.opencorporates.com](https://api.opencorporates.com)). For NY, **use data.ny.gov (2.7) instead** — free and richer.
- **Data.gov** — is a *catalog* that points to the same primary sources above (IRS, BEA, Treasury); no separate live API worth wiring. Go to primaries.

---

## PART 3 — NON-DATA INTEGRATIONS (which are free/public)
RGA's lesson stands: *timing creates the window, messaging closes it* — so the follow-up layer matters as much as the signal.

| Integration | Free/public? | What it gives David | Notes |
|---|---|---|---|
| **Calendar booking (.ics generation)** | 🟢 Free, no dependency | One-click "Book a review" — generate an RFC-5545 `.ics` file server-side and attach/serve it; opens in any calendar | Pure Python, no API, no key. Best first non-data add. |
| **Google Calendar / Microsoft Graph booking** | 🟡 Free APIs, OAuth | Auto-create a hold on David's real calendar when he acts on a lead | OAuth setup overhead; do after .ics. |
| **CRM export (CSV / vCard)** | 🟢 Free | Export ranked leads + receipts to CSV or vCard for any CRM (AgencyZoom, monday, Insightly all ingest CSV/API) | monday.com/Insightly explicitly ingest "30+ vendors via API or email" ([monday.com](https://monday.com/blog/crm-and-sales/life-insurance-crm/)). Zero-cost interop instead of building a CRM. |
| **Email follow-up (SMTP / templated drafts)** | 🟢 Free (SMTP) | Generate the NYL-compliant talk-track as a ready-to-send email draft per lead | Pair every trigger with messaging (RGA). Keep send manual for compliance. |
| **SMS follow-up pattern** | ⚠️ Free to *draft*, paid+regulated to *send* | Draft the first-touch SMS; do NOT auto-send | **TCPA one-to-one consent now required** + A2P 10DLC registration ([EBS Media](https://ebsmedia.us/latest/insight/life-insurance-leads/), [CUFinder](https://cufinder.io/blog/lead-generation-industry/insurance/)). Generate draft + a consent/compliance reminder; David sends. |
| **5-touch follow-up cadence engine** | 🟢 Free (in-app logic) | Auto-schedule call→text→email sequence with shot-clock nudges (steal AgencyZoom SmartCycle/Shot-Clock UX) | Industry-standard motion in 2026 ([Zocks](https://www.zocks.io/blog/how-life-insurance-agents-use-ai)); pure app state, no external service. |

---

## PART 4 — WIRE THESE 5 FIRST (ranked by lead-signal strength × reliability)

| Rank | Wire-in | Signal strength | Reliability | Why first |
|---|---|---|---|---|
| **1** | **IRS County Migration (NY inflow slice)** — `countyinflow2122.csv` | ★★★★★ | ★★★★★ (static bundle, never fails) | Exclusive "brand-new resident, no advisor" trigger; zero runtime dependency; AGI-ranked affluence built in. Highest signal that cannot break. |
| **2** | **NY Active Corporations** — `data.ny.gov/resource/n9v6-gdp6.json` | ★★★★★ | ★★★★☆ (live, no key, SoQL) | Free business-formation X-Date trigger (buy-sell/key-person) with a mailable address + filing date. The life-side LeO equivalent nobody has packaged. |
| **3** | **Census ACS extras** — `B11003` (kids<18) + `B25003` (homeownership) | ★★★★☆ | ★★★★★ (key already wired) | Turns the Territory Map into a *family-coverage opportunity heatmap*; reuses David's existing key — near-zero integration risk. |
| **4** | **FRED** — `MORTGAGE30US`, `CPIAUCSL`, `FEDFUNDS` | ★★★★☆ | ★★★★☆ (free key, fallback) | Powers the macro ticker AND the needs-calculator math; mortgage rate is the engine of the new-homeowner FAM nudge. |
| **5** | **BLS LAUS county unemployment** — `LAUCN{fips}…03` | ★★★☆☆ | ★★★★★ (no key, verified) | Income-protection urgency dial per county; zero-cost, no-key, instantly reliable. |

(Treasury Fiscalbased 🟢 sits just behind as the no-key *fallback* for the rate ticker so it never renders empty; BEA per-capita income is a fast follow-on after the BEA key is provisioned.)

---

## PART 5 — THE SINGLE MOST IMPRESSIVE NEW CAPABILITY TO OUT-CLASS EVERYONE

### 🏆 "Ask the Territory" — a conversational, citation-grounded query layer over the live public-data radar

In 2026 the entire industry's flagship move was **Verisk putting its data inside Claude via an MCP connector** — but it's **Enterprise-only, subscription-gated, read-only actuarial data with no provenance and nothing for an individual agent** ([Verisk/Claude, May 5 2026](https://www.globenewswire.com/news-release/2026/05/05/3288003/0/en/verisk-brings-its-trusted-analytics-and-generative-ai-capabilities-directly-into-anthropic-s-claude.html); [Verisk connector requirements](https://www.verisk.com/resources/verisk-underwriting-intelligence/)). LeO already proved a **conversational "Siri for prospecting"** UX wins for agents — but only for commercial lines.

**We give David the same conversational paradigm the giants just blessed — but over FULLY PUBLIC, FULLY CITED life-event data, for a single life agent, with a signed receipt on every answer.**

He types or speaks:
> *"Who moved into Westchester this year with the highest income, and which of them just started a business?"*

The app joins **IRS migration inflow (2.6) × NY new-business filings (2.7) × ACS family/homeownership (2.4) × FRED rate context (2.1)**, returns a ranked answer in plain language, and — the part nobody else can do — **every figure in the answer is a clickable signed "Why This Lead" receipt** (source URL + capture date + SHA-256 hash) with a ready-to-send, TCPA-aware NYL talk track attached.

**Why it out-classes the entire field at once:**
- **Verisk's Claude connector** = gated, proprietary, no provenance, no leads → ours = open, cited, lead-generating, agent-grade.
- **LeO's conversational prospecting** = commercial-only → ours = the first conversational life-event query engine for individual life.
- **The marketplaces** = resold low-intent form-fills now burdened by one-to-one consent → ours = exclusive, public-event-real, consent-clean.
- **LexisNexis/Deloitte/RGA** = opaque scores in a whitepaper or a carrier portal → ours = the agent asks a question in English and gets a *cited, defensible* answer he can show the client.

In one line: **"the conversational data layer the giants just standardized on — but public, cited, and pointed at the individual life agent instead of the carrier."** It rides the exact 2026 trend (conversational MCP-style access + trigger-driven prospecting) while keeping the one thing none of them will ever surrender: the receipt.

---

### Endpoint quick-reference (copy-paste tested 2026-06-28)
```
FRED        🟡 https://api.stlouisfed.org/fred/series/observations?series_id=MORTGAGE30US&api_key={KEY}&file_type=json&sort_order=desc&limit=5
Treasury    🟢 https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/avg_interest_rates?sort=-record_date&page[size]=5
BEA         🟡 https://apps.bea.gov/api/data/?&UserID={KEY}&method=GetData&datasetname=Regional&TableName=CAINC1&LineCode=3&GeoFips=36119&Year=LAST5&ResultFormat=JSON
Census ACS  🟡 https://api.census.gov/data/2023/acs/acs5?get=NAME,B11003_002E,B25003_002E,B25003_003E,B19013_001E&for=county:*&in=state:36&key={KEY}
BLS LAUS    🟢 https://api.bls.gov/publicAPI/v2/timeseries/data/LAUCN361190000000003   (county unemployment rate)
IRS migr.   🟢 https://www.irs.gov/pub/irs-soi/countyinflow2122.csv   (bundle NY slice: statefips 36)
NY biz      🟢 https://data.ny.gov/resource/n9v6-gdp6.json?county=Westchester&$where=initial_dos_filing_date>'2025-01-01'
```

*All values, series IDs, and column layouts in this report were verified against live endpoints on 2026-06-28. Sources are cited inline above with full URLs.*
