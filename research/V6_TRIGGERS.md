# V6 — Outside-the-Box Life-Insurance Triggers (NY Metro)

**Audience:** New York Life advisor prospecting the NY metro for the *next* family to protect — before any competitor.
**Mission of this doc:** New, free, real-time-or-frequently-refreshed public data feeds that signal a life-insurance / financial-planning need, mapped to NYL products, with verified endpoints we can wire into the existing FastAPI app.
**Scope rule:** Research only — no app-code edits. Prefer keyless Socrata JSON (data.ny.gov / *.cityofnewyork.us). All endpoints below were hit live and verified on **Sun, June 28, 2026** unless explicitly flagged otherwise.

> **Note on Socrata query syntax:** every dataset is reachable at `https://<domain>/resource/<id>.json` and supports SoQL params: `$limit`, `$where`, `$select`, `$group`, `$order`, `$offset`. No API key needed for our volumes (an app token only raises throttling headroom). New-issuance filtering uses the per-row issue/admit/cert date column called out for each source.

---

## TL;DR — Wire These 4 First

Ranked by **signal strength × freshness × free-wireability**. Each is a keyless Socrata JSON feed, refreshed daily, with a per-row date column that lets us isolate *brand-new* records (the high-value "money in motion" moment).

| # | Source | Socrata ID | Why first |
|---|--------|-----------|-----------|
| **1** | **NYS Attorney Registrations** (newly-admitted lawyers) | `data.ny.gov / eqw2-r5nb` | Refreshed **daily**; `year_admitted` isolates new admits (4,613 in 2026, ~1,802 in NYC-area ZIPs). Names + firm + full mailing address. High future income, zero competitors mining it. |
| **2** | **NY Active Real Estate Salespersons & Brokers** | `data.ny.gov / yg7h-zjbf` | Refreshed **daily**; new agents = first commission income + heavy referral network. Name, brokerage, business address. (Use license-number prefixes + appearance dates as new-agent proxy.) |
| **3** | **NYC DCWP License Applications** (new small-business owners) | `data.cityofnewyork.us / ptev-4hud` | Refreshed **weekly**; `application_type = New License` + `submission_date` flags brand-new business owners (key-person + buy-sell + family-protection need). |
| **4** | **NY Professional License NEW-issuance proxies** — DOS Appearance/Barber (`y3u4-jbgh`), DOL Elevator (`cxfs-ya8e`), Real-Estate Appraisers (`3nr4-s9yt`), SLA Liquor (`9s3h-dpkz`) | data.ny.gov | Each carries a true **issue/cert/original-issue date** so we can filter "licensed in the last 90 days." Bundles a wide net of newly-earning tradespeople and new bar/restaurant owners. |

**Rationale:** All four are keyless, daily/weekly, carry name + NY-metro address, and pinpoint the *new-income / new-business* moment — the cleanest life-insurance entry point and the most under-served by competitors. They slot into the same Socrata-ingestion pattern the app already uses for ACRIS and DOB NOW.

---

## Master Ranked Table

Score legend (1–5): **Sig** = signal strength for an LI need · **Fresh** = update cadence · **Wire** = free + easy to ingest (keyless JSON = 5). **Total** = product of the three, normalized. PII/gated sources scored lower on Wire.

| Rank | Source | Endpoint (verified) | Update freq | LI signal | NYL product map | Sig | Fresh | Wire | Reliability note |
|------|--------|---------------------|-------------|-----------|-----------------|-----|-------|------|------------------|
| 1 | **NYS Attorney Registrations** | `https://data.ny.gov/resource/eqw2-r5nb.json` (filter `year_admitted=2026`) | Daily ✅ verified 6/28/26 | New lawyer → high future income, just started earning | Term + Whole Life, DI, retirement/IRA, eventually estate | 5 | 5 | 5 | Gold standard. 432k rows; `year_admitted`, `status`, full address, law school, firm. NYC-metro filter via ZIP `10*`/`11*` or `county`. Name+address PII — public record, use compliantly. |
| 2 | **NY Real Estate Salespersons & Brokers (Active)** | `https://data.ny.gov/resource/yg7h-zjbf.json` | Daily ✅ | New agent → variable commission income + referral hub | Term + DI (income volatility), family protection, SEP/solo-401k | 5 | 5 | 5 | Daily refresh. Has name, brokerage, business address, license_type, expiration. **No issue-date column** — new-agent detection via license-number prefix patterns or diffing daily snapshots. Companion sets: Brokers `9twf-9yig`, Salespersons `i8hd-gucs`, Offices `nsde-gcv2`. |
| 3 | **NYC DCWP License Applications** | `https://data.cityofnewyork.us/resource/ptev-4hud.json` (filter `application_type='New License'`) | Weekly ✅ | New small-business owner | Key-person, buy-sell funding, business-overhead, family protection | 5 | 4 | 5 | `submission_date`, `status`, `business_category`, city/state/zip. Pair with **Issued Licenses** `w7w3-xahh` (`license_creation_date`, full lat/long + BBL) to confirm the license actually issued. |
| 4 | **NYC DCWP Issued Licenses** | `https://data.cityofnewyork.us/resource/w7w3-xahh.json` | ~Daily ✅ (6/26/26) | Newly-licensed business at a confirmed NYC address | Key-person, buy-sell, family | 5 | 4 | 5 | `license_creation_date` enables new-issuance filter; geocoded (lat/long, BBL, council district) for territory routing. |
| 5 | **NY DOL Elevator/Trade Individual Licenses** | `https://data.ny.gov/resource/cxfs-ya8e.json` (filter `issued_date>'2026-01-01'`) | Frequent ✅ | Newly-licensed skilled tradesperson → steady union income | Term, DI, mortgage protection, family | 4 | 4 | 5 | True `issued_date` (1,214 issued YTD 2026). Companion: Mold Individual `h6jr-vxqt`, Elevator Contractor `jrac-r9vc`. Statewide; filter to metro by name/employer. |
| 6 | **NY Real Estate Appraisers (Currently Licensed)** | `https://data.ny.gov/resource/3nr4-s9yt.json` (filter `org_date>'2026-01-01'`) | Daily ✅ | New appraiser → professional income; ties into homebuyer ecosystem | Term, DI, retirement | 4 | 5 | 5 | `org_date` (original) + `cert_date` + business address/county. 146 newly originated YTD 2026. |
| 7 | **NY SLA Liquor — Active Licenses** | `https://data.ny.gov/resource/9s3h-dpkz.json` (filter `originalissuedate`) | Frequent ✅ | New bar/restaurant owner → new business + personal risk | Key-person, buy-sell, business-overhead, family | 4 | 4 | 5 | `originalissuedate`, premises county, geocoded. Companion: Pending `f8i8-k2gm` (catches owners *before* opening), Inactive `6dg3-2z7i`. Strong NYC-metro density. |
| 8 | **NYC TLC New Driver Applications** | `https://data.cityofnewyork.us/resource/dpec-ucu7.json` | Daily ✅ (`lastupdate` 6/28/26) | New for-hire driver → first/changed income stream | Term, DI, final-expense, family | 3 | 5 | 5 | `app_date`, `status`, `lastupdate`. No name (app number only) — aggregate/volume signal + funnels to DCWP/credential cross-refs. |
| 9 | **Urban Institute Education Data API (IPEDS Completions)** | `https://educationdata.urban.org/api/v1/college-university/ipeds/completions-cip-2/{year}/?fips=36` | Annual (NCES) ⚠️ | New graduates by school + field (NY = fips 36) | Term, student-loan/DI, Roth IRA, first-policy | 4 | 2 | 5 | Free, **keyless**, fully programmatic JSON; 233k+ NY rows/yr. Annual cadence (lagging) = cohort sizing & geo-targeting, not real-time individuals. Degree level + CIP field → income proxy. |
| 10 | **SUNY / CUNY Degrees Granted** | SUNY `pn4n-h5wp`, `xnq9-9igi`; CUNY `ybg5-afvs` | Annual ⚠️ | New-graduate cohort volumes by campus | First-policy, DI, Roth | 3 | 2 | 5 | Aggregate counts by degree type/year — campaign sizing, not individuals. Keyless Socrata. |
| 11 | **DOL OFLC Disclosure — LCA (H-1B/E-3) + PERM** | `https://www.dol.gov/agencies/eta/foreign-labor/performance` (quarterly XLSX) | Quarterly ⚠️ | New high-income immigrant hires (new employment), employer-sponsored green cards | Term + Whole Life, DI, college/retirement, estate later | 4 | 3 | 3 | Free public domain, no key, but **bulk XLSX (70–140 MB/qtr)** not JSON — needs a parse step. LCA fields flag "new employment" + offered wage + worksite (filter NY). PERM = green-card sponsorship (settling-down signal). Latest: FY2026 Q2 (Oct 2025–Mar 2026). |
| 12 | **NYC DOB / DOB NOW Permits (residential alterations)** | NYC Open Data permit sets (e.g., DOB NOW Build Job Filings) | Daily | Home renovation/expansion → growing family / rising net worth | Family protection, increased coverage, LTC | 3 | 5 | 5 | Already partially wired (DOB NOW new buildings). *Alteration* permits beyond new-builds add a "nesting/expanding family" layer. Geocoded. |
| 13 | **NYS DOS Business Filings (monthly)** | `https://data.ny.gov/resource/m7i3-tv6j.json` | Monthly ✅ | New LLC/Corp formation volume statewide | Key-person, buy-sell, business | 3 | 3 | 5 | **Aggregate monthly counts** by entity type — not individual filers. Good macro trend; pair with NYC DCWP for named leads. |
| 14 | **NYC Surrogate's Court — WebSurrogate (probate/estate)** | `https://websurrogates.nycourts.gov/` | Continuous ⚠️ | Probate filing → estate & annuity money in motion; surviving spouse/heirs | Annuities, estate planning, LTC, beneficiary review | 5 | 4 | 2 | Free 24/7 public search across 47 NY counties incl. Queens & Richmond; records 2014–present. **No public JSON API** — HTML search only, would require structured collection. PII-sensitive (decedent + heirs). High value, higher effort. |
| 15 | **Obituary feeds (Legacy.com network)** | Legacy.com / local funeral-home & newspaper feeds | Continuous ⚠️ | Death in family → surviving-spouse & adult-child planning | Final-expense, surviving-spouse annuity, beneficiary/estate review | 4 | 5 | 2 | Legacy covers ~95% of US obits with structured data **but API/data access is licensed/paid**; raw newspaper feeds are free but messy. **Grief-sensitive — compliance-first (CAN-SPAM/TCPA), no PII in ads.** Treat as supervised, opt-in outreach only. |
| 16 | **NYC Historical Vital Records — Marriage Index** | `https://data.cityofnewyork.us/resource/d8dr-nyhw.json` | Historical only ❌ | Marriage = beneficiary-add / new-household trigger | New family protection, beneficiary review | 4 | 1 | 4 | **GAP:** keyless JSON exists but covers **historical** marriages only (index, not current). Current NYC marriage licenses are via City Clerk (`cityclerk.nyc.gov`) — **not an open API**, request-based. ReclaimTheRecords (`nycmarriageindex.com`) offers free bulk historical CSV/SQL. No real-time marriage feed found. |

---

## Category Findings & Gaps

### 1. New graduates / young adults entering the workforce
- **Best wireable:** **Urban Institute Education Data API** (IPEDS completions) — keyless JSON, NY = `fips=36`, by school (`unitid`), degree level, and CIP field of study. Annual cadence, so it's a **cohort-sizing / geo-targeting** tool, not an individual-lead feed. Endpoint verified returning 233k+ NY rows.
- **SUNY/CUNY degree counts** on data.ny.gov are aggregate-only (campaign sizing).
- **Individual new grads** are not publicly listed anywhere free in real time (FERPA-protected). The closest *individual* proxies are the **NEW professional-license / bar-admission feeds** below (a new lawyer/agent/appraiser is, by definition, a recent grad entering high income).
- **OPT/H-1B new employment:** DOL OFLC LCA disclosure flags "new employment" + worksite + offered wage (free, quarterly XLSX). USCIS H-1B Employer Data Hub is **aggregate counts only** (no individuals).

### 2. Newly-licensed professionals (the headline win)
- **NYS Attorney Registrations `eqw2-r5nb`** is the standout: daily refresh, `year_admitted` isolates new admits, full name + firm + NY-metro address. **This is the single best new-high-income-professional feed in the catalog.** Verified: 4,613 admitted in 2026, ~1,802 in NYC-area ZIPs.
- **Real estate agents** (`yg7h-zjbf`) and **appraisers** (`3nr4-s9yt`, with `org_date`) — daily, named, addressed.
- **Tradespeople** via DOL individual-license sets (Elevator `cxfs-ya8e`, Mold `h6jr-vxqt`) carry real `issued_date`.
- **Doctors / nurses / CPAs / dentists / PEs (NYSED Office of the Professions):** the authoritative registry (1.5M licensees, daily updates, includes *date of original license*) is **search-by-record-only — no bulk download or open API** (`op.nysed.gov`). This is a notable gap for the highest-income medical/CPA segment; only per-name verification is free. Third-party paid APIs exist (flag: paid/PII).

### 3. Marriage & divorce (beneficiary changes)
- **GAP / mostly unavailable free in real time.** NYC marriage *index* on Open Data is **historical only**. Current marriage licenses go through the City Clerk and are **request-based, not an API**. ReclaimTheRecords publishes free bulk **historical** CSV/SQL. Divorce records in NY are sealed for 100 years — effectively unavailable. **Recommendation:** do not rely on a live marriage feed; infer household formation from co-located ACRIS deed purchases + new-mover signals instead.

### 4. Probate / estate / obituary
- **WebSurrogate** (`websurrogates.nycourts.gov`) — free, 24/7, 47 counties incl. Queens & Staten Island, 2014–present. **No JSON API** (HTML search), PII-sensitive. Highest signal for annuity/estate money-in-motion; needs structured collection effort.
- **Obituaries (Legacy.com)** — best coverage but **licensed/paid** API; grief-sensitive, compliance-first.
- **SSA Death Master File** — the public ("DMF") version is **gated/fee-based** via NTIS and excludes state-protected records; flag paid.

### 5. New movers / relocations (USPS NCOA is paid — free alternatives)
- **Voter-registration address changes:** NY voter file is obtainable but **request-based (not a free open API)** and use is legally restricted to election purposes — **flag gated / not LI-usable.**
- **Best free proxies for "new mover":** **ACRIS deed purchases** (already wired) + **DOB alteration permits** + **new utility/business-license activity at a fresh address**. No clean free utility-hookup feed exists for NYC. **Recommendation:** treat ACRIS + DOB permits as the de-facto mover signal; skip paid NCOA.

### 6. Other creative & free
- **NYC DCWP License Applications/Issued** (new business owners) — wire-ready, weekly/daily.
- **SLA Liquor licenses** (`9s3h-dpkz` active + `f8i8-k2gm` pending) — new bar/restaurant owners, geocoded, `originalissuedate`.
- **NYC TLC New Driver Applications** (`dpec-ucu7`) — new gig-income, updated daily.
- **DMV facilities / driver licenses issued** — mostly aggregate (`a4s2-d9tt` is demographic counts, no names).
- **CDC natality / NYC birth records** — already wired (new-baby trigger).

---

## Reliability & Compliance Flags

- **Keyless & wire-ready (use freely):** `eqw2-r5nb`, `yg7h-zjbf`, `9twf-9yig`, `i8hd-gucs`, `3nr4-s9yt`, `cxfs-ya8e`, `h6jr-vxqt`, `9s3h-dpkz`, `f8i8-k2gm`, `ptev-4hud`, `w7w3-xahh`, `dpec-ucu7`, `m7i3-tv6j` (data.ny.gov / cityofnewyork.us); Urban Institute IPEDS API.
- **Free but bulk-file (needs parse step, not JSON):** DOL OFLC LCA/PERM quarterly XLSX.
- **Free but no API (HTML/manual, higher effort):** WebSurrogate probate.
- **Gated / request-based (not freely wireable):** NY voter file, NYSED Office of the Professions bulk, current NYC marriage licenses.
- **Paid / licensed:** Legacy.com obituary API, SSA Death Master File, USPS NCOA, third-party license-verification APIs.
- **PII / ethics:** All named feeds are public records, but new-lead outreach must follow CAN-SPAM / TCPA and NYL compliance. **Obituary/probate outreach is grief-sensitive — supervised, value-first messaging only.**

---

## Verified Endpoint Quick-Reference (copy/paste)

```
# 1. New attorneys (2026 admits)
https://data.ny.gov/resource/eqw2-r5nb.json?$where=year_admitted=2026&$limit=50000

# 2. Real estate agents (daily snapshot)
https://data.ny.gov/resource/yg7h-zjbf.json?$limit=50000

# 3. New NYC business license applications
https://data.cityofnewyork.us/resource/ptev-4hud.json?$where=application_type='New License'&$order=submission_date DESC

# 4a. New trade licenses (issued in 2026)
https://data.ny.gov/resource/cxfs-ya8e.json?$where=issued_date>'2026-01-01'
# 4b. New appraisers
https://data.ny.gov/resource/3nr4-s9yt.json?$where=org_date>'2026-01-01'
# 4c. New liquor licenses (new bar/restaurant owners)
https://data.ny.gov/resource/9s3h-dpkz.json?$order=originalissuedate DESC

# Supporting
https://data.cityofnewyork.us/resource/w7w3-xahh.json   # issued business licenses (geocoded)
https://data.cityofnewyork.us/resource/dpec-ucu7.json    # TLC new drivers
https://educationdata.urban.org/api/v1/college-university/ipeds/completions-cip-2/2021/?fips=36  # NY grad cohorts
https://www.dol.gov/agencies/eta/foreign-labor/performance  # OFLC LCA/PERM disclosure (XLSX)
https://websurrogates.nycourts.gov/                       # probate (HTML, no API)
```

---

*Sources: NY Open Data catalog & live Socrata JSON resources (data.ny.gov, data.cityofnewyork.us), verified 2026-06-28; NY Dept of State Licensee Search (dos.ny.gov/index-licensees-and-registrants); NYSED Office of the Professions (op.nysed.gov/services/verifications/online-verification-searches); DOL OFLC Performance Data (dol.gov/agencies/eta/foreign-labor/performance); Urban Institute Education Data API (educationdata.urban.org); NY Courts WebSurrogate (websurrogates.nycourts.gov, nycourts.gov/LegacyPDFS/press/pdfs/AV22_02.pdf); LIMRA obituary-data brief; Reclaim The Records / NYC Marriage Index (nycmarriageindex.com); SSA Death Master File (ssa.gov/dataexchange/request_dmf.html).*
