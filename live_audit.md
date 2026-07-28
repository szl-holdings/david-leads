# Live + Doctrine Audit — David Leads App
**Audited:** https://szlholdings-david-leads.hf.space  
**Date:** 2026-06-29 (UTC)  
**Auditor:** Read-only HTTP audit via curl/HTTP — no code modified  
**Intended client:** David Abraham, New York Life agent  

---

## Executive Summary

The app is **production-ready for demo use** with two items requiring fixes before sending to a client (P1), two items that should be addressed soon (P2), and several low-priority polish items (P3). No authentication bypasses, no stack-trace leaks, no fabricated signals. Doctrine compliance is strong but incomplete in one specific area: `est_premium` and `kpi.pipeline_premium` carry no machine-readable advisory label at the JSON field level.

---

## 1. COLD START

| Check | Result |
|---|---|
| Space sleeping on first request | **PASS — Space is warm, no cold start** |
| `/healthz` HTTP code | **200** |
| `/healthz` response time | **62 ms** (wall: 71 ms) |
| Response body | `{"status":"ok","service":"david-leads","doctrine":"SZL governed-AI · honest by design"}` |

**Finding:** Space was already warm at audit time. No cold-start delay observed. The HuggingFace `x-proxied-replica: if5aynkx-96csp` header confirms it was served by a live replica. Cold-start behavior on first wake cannot be confirmed from this audit alone (documented as a known HuggingFace Spaces behavior: ~15–30s on free tier).

---

## 2. AUTH / SECURITY

### 2.1 Login endpoint

| Test | Expected | Actual | PASS/FAIL |
|---|---|---|---|
| Correct environment-supplied test credentials | 200 + token | **Historical result: HTTP 200; token redacted. The published legacy triplet is now revoked and requires deployment-secret rotation.** | **REMEDIATION REQUIRED** |
| Wrong password | 401 | **HTTP 401** `{"detail":"Invalid credentials or access key"}` | **PASS** |
| Wrong access_key | 401 | **HTTP 401** `{"detail":"Invalid credentials or access key"}` | **PASS** |
| Wrong username | 401 | **HTTP 401** `{"detail":"Invalid credentials or access key"}` | **PASS** |
| Schema field name | — | Login requires `access_key` (not `api_key`) per OpenAPI schema | Note |

All three wrong-credential cases return identical `401` with a clean, non-leaking message. No stack trace, no username enumeration hint.

### 2.2 Protected endpoints — no token

Every protected endpoint was tested without an `Authorization` header:

| Endpoint | Expected | Actual | PASS/FAIL |
|---|---|---|---|
| `POST /api/run` | 401 | **HTTP 401** `{"detail":"Missing token"}` | **PASS** |
| `GET /api/pulse` | 401 | **HTTP 401** `{"detail":"Missing token"}` | **PASS** |
| `GET /api/model` | 401 | **HTTP 401** `{"detail":"Missing token"}` | **PASS** |
| `GET /api/leads` | 401 | **HTTP 401** `{"detail":"Missing token"}` | **PASS** |
| `GET /api/lake` | 401 | **HTTP 401** `{"detail":"Missing token"}` | **PASS** |
| `GET /api/benchmark` | 401 | **HTTP 401** `{"detail":"Missing token"}` | **PASS** |
| `GET /api/routing` | 401 | **HTTP 401** `{"detail":"Missing token"}` | **PASS** |
| `GET /api/export.csv` | 401 | **HTTP 401** `{"detail":"Missing token"}` | **PASS** |
| `GET /api/territory` | 401 | **HTTP 401** `{"detail":"Missing token"}` | **PASS** |
| `GET /api/brief/L1` | 401 | **HTTP 401** `{"detail":"Missing token"}` | **PASS** |

Login is required for all data endpoints.

### 2.3 Invalid token

| Test | Expected | Actual | PASS/FAIL |
|---|---|---|---|
| `POST /api/run` with `Authorization: Bearer INVALID_TOKEN_123` | 401 | **HTTP 401** `{"detail":"Invalid token"}` | **PASS** |

### 2.4 Garbage / malformed input (stack trace check)

| Test | Expected | Actual | PASS/FAIL |
|---|---|---|---|
| Garbage JSON fields to `POST /api/run` (null live, integer state, string age_min) | 4xx, no stack trace | **HTTP 422** FastAPI validation error JSON (field-level) | **PASS** |
| Completely non-JSON body to `POST /api/run` | 4xx, no stack trace | **HTTP 422** `{"detail":[{"type":"json_invalid",...}]}` | **PASS** |
| Garbage to `POST /api/webhook/test` (null url/lead_id) | 4xx or clean 200 | **HTTP 200** `{"ok":true,"sent":false,"reason":"no url supplied",...}` | **PASS** |
| `GET /api/brief/UNKNOWN_ID_XYZ_999` | 4xx | **HTTP 404** `{"detail":"Lead not found - run intelligence first"}` | **PASS** |
| `GET /api/verify/UNKNOWN_ID_XYZ_999` | 4xx | **HTTP 404** `{"detail":"Receipt not found"}` | **PASS** |

No stack traces exposed in any bad-input scenario. All errors are clean JSON.

### 2.5 Response headers

Headers on all responses:

```
server: uvicorn
x-proxied-host: http://10.112.31.72
x-proxied-replica: if5aynkx-96csp
x-proxied-path: /api/...
link: <https://huggingface.co/spaces/SZLHOLDINGS/david-leads>;rel="canonical"
x-request-id: [random 6-char ID]
vary: origin, access-control-request-method, access-control-request-headers
access-control-expose-headers: *
```

**Issues found:**

- **`server: uvicorn`** — Reveals the underlying ASGI framework. Low risk (it's publicly known), but best practice is to suppress or replace.
- **`x-proxied-host: http://10.112.31.72`** — Exposes an internal private IP address. This is a HuggingFace Spaces infrastructure header injected by their proxy, not application code. Cannot be removed without HuggingFace platform changes, but worth noting as an information-disclosure finding.
- **Missing security headers** — No `X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`, or `Strict-Transport-Security` headers are set. For a demo app this is P3, but should be added before any regulated/production deployment.

---

## 3. LIVE DATA FLOW

### 3.1 `/api/run` — sample mode

```
POST /api/run {"live":false,"state":"NY"}
HTTP 200 | Time: 849 ms
```

- Mode: `SAMPLE (offline)` — correctly labeled in `meta.mode`
- `meta.fabricated: 0`
- `meta.live_count: 0`
- 8 leads returned, 3 HOT, 5 WARM
- All signals have `"public": true, "live": false`
- `[SAMPLE]` suffix on all sample source names (e.g., `"SEC EDGAR (8-K) [SAMPLE]"`)
- L1 score: **87.2** (canonical sample score confirmed per model self-test)
- All receipts signed: `receipt_signed: true`
- Governance: `"verdict":"PASS — public-data-only, honest by design"`, `consensus: "4-of-4"`

**PASS**

### 3.2 `/api/run` — live mode

```
POST /api/run {"live":true,"state":"NY"}
HTTP 200 | Time: 7,831 ms (~7.8s)
```

- Mode: `LIVE`
- `meta.fabricated: 0`
- `meta.live_count: 47` (live signals)
- `meta.total_signals: 50`
- 8 leads returned, L1 score: **88.1** (fresh recency=1.0 → score boosted from 87.2 sample baseline — both expected values per doctrine)
- Real live signals include actual NY DOS LLC filings (e.g., `STARSEED AWAKENED LLC filed 2026-06-28`), BLS May 2026 wages (`$1092.08`), ACRIS deeds, ProPublica 990 nonprofits, SEC Form 4 (2,973 insider filings this week)
- Timing: **7.8s** — within the 15s budget. Note this is a single live probe; if the upstream APIs are slower on a given day it could approach the budget.

**PASS** (timing acceptable; monitor)

### 3.3 `/api/run` with empty body `{}`

```
POST /api/run {}
HTTP 200 | Time: ~7.8s
```

Defaults applied (`live:true`, `state:"NY"`). No error. Appropriate behavior.

**PASS**

### 3.4 `/api/run` with invalid state code `"XYZZY"`

```
POST /api/run {"live":false,"state":"XYZZY"}
HTTP 200
```

App returns sample data using NY fallback with no validation error. The state code "XYZZY" is silently accepted and falls back to defaults. This is not a security issue but could confuse callers.

**MINOR** (P3: consider returning 400 for unknown state codes)

### 3.5 `/api/pulse`

```
GET /api/pulse (with auth)
HTTP 200 | Time: 2,043 ms
```

**State mode breakdown across 3 consecutive calls (stable):**

| Mode | States | Count |
|---|---|---|
| LIVE | CT, DE, DC, NY, VA, MD, NJ | 7 |
| SAMPLE | PA, NC, FL, SC, GA, RI | 6 |
| STATIC/GAP | MA, NH, ME | 3 |
| Total | | 16 |

**LIVE states with actual counts (plausible, not fabricated):**
- CT: 1,283,462 records (Socrata daily)
- DE: 64,114 records
- DC: 4,788 ArcGIS features
- NY: 69,978 records
- VA: 9,936 records
- MD: 2,438,889 records
- NJ: 2,716,419 records

**SAMPLE states:** Coverage labels include `[SAMPLE] — live probe unavailable (HTTPError/RuntimeError); baseline richness X.X` — honestly labeled.

**GAP states (MA, NH, ME):** `"mode":"STATIC"`, `"gap":true`, `"count":null`, `"coverage_label":null` — honestly labeled with no fabricated counts.

**Note on `confirmed` flag:**  
NY, VA, and NJ are `mode=LIVE` but `confirmed=false`. The `confirmed` field appears to mean "count independently cross-verified against a second source" rather than "live probe succeeded." This is not a bug but should be documented for clients to avoid confusion.

**Methodology field:**  
```json
"resilience": "timeout 12s + 1 backoff retry; concurrent probes (6 workers, ~20s budget); last-good real counts served as 'LIVE (cached <ts>)' when a refetch fails"
```
Cache doctrine is stated. No cached entries were observed in this audit session (all states either probed live or fell to SAMPLE as labeled).

**PASS**

### 3.6 `/api/work`

```
POST /api/work {"max_steps":4,"convergence_threshold":0.1}
HTTP 200 | Time: 42 ms
```

Returns a loop trace showing time-decay simulation (4 steps, ~35-minute intervals each). L1 HOT→WARM transition confirmed at ~138 min (half-life). Events signed with `khipu_consensus: "4-of-4"`. Exit reason: `budgetExhausted` (correct, 4 steps requested).

**PASS**

### 3.7 `/api/lake`

```
GET /api/lake
HTTP 200 | Time: 68 ms
{"size":0,"count":0,"events":[]}
```

Empty lake (no durable outcomes logged — expected for a fresh session without `SZL_RECEIPT_LAKE_PATH` configured).

**PASS**

### 3.8 `/api/benchmark`

```
GET /api/benchmark
HTTP 200 | Time: 31 ms
```

Returns 8 surfaced leads, 0 outcomes (no conversions logged yet). Includes an honest note:  
`"honest_note":"Producer funnel based on 0 logged outcome(s) this session. Durable when SZL_RECEIPT_LAKE_PATH is set; no external data used."`

**PASS**

### 3.9 `/api/routing`

```
GET /api/routing
HTTP 200 | Time: 31 ms
```

Returns routing roster. Teammate agents (A. Rivera, M. Chen) are clearly labeled `"real":false, "label":"[illustrative roster]"`. David is `"real":true`. Routing recommendations include basis strings.

**PASS**

### 3.10 `/api/export.csv`

```
GET /api/export.csv
HTTP 200 | Time: 26 ms
Content-Type: application/json (note: should be text/csv)
```

Returns valid CSV with headers:
```
rank,id,name,event_type,score,bucket,urgency,wealth_tier,lapse_decile,receptivity,likely_gap,product,employer,liquidity,receipt_id,receipt_hash
```

All 8 leads present, correctly ranked. Receipt IDs present in every row. No `est_premium` column in the CSV export (consistent — see Doctrine section).

**Minor issue:** `Content-Type` header returns `application/json` instead of `text/csv`. This would cause browsers/tools to misinterpret the MIME type.

**PASS** (data correct; P2 fix Content-Type header)

### 3.11 `/api/model`

```
GET /api/model
HTTP 200 | Time: 94 ms
```

Full methodology card. Confirmed:
- Formula: `score = 100 × exp( Σ weight_i × ln(axis_i) )` — weighted geometric mean
- 5 axes, weights sum to 1.0 (0.3+0.2+0.2+0.2+0.1)
- HOT bucket: score ≥ 80
- Λ uniqueness: **`"Conjecture 1 (OPEN — CAUCHY_ND sorry + missing symmetry axiom; NOT a theorem)"`** ✓
- DOI: **`10.5281/zenodo.20434308`** with `doi_url` ✓
- FCRA note present in model lapse section ✓
- doctrine field: `"honest by design · open methodology · cryptographically receipted · Λ uniqueness is Conjecture 1 (OPEN) · DOI 10.5281/zenodo.20434308 · Open the Black Box"` ✓

**PASS**

### 3.12 `/api/territory`

```
GET /api/territory?state=36
HTTP 200 | Time: 366 ms
```

Returns Census ACS 2023 1-year county data for New York. Top county: Nassau (index 84.6, median income $141,568). All records have `"public":true, "live":true`. Source and vintage disclosed.

**PASS**

### 3.13 `/api/ask`

```
POST /api/ask {"question":"What is the top lead?"}
HTTP 200 | Time: 568 ms
```

Grounded answer citing L1/L2/L8. Doctrine footer: `"public-data-only · cited · signed · honest by design"`. Receipt signed.

**Minor issue:** Citation URLs are empty strings (`"url":""` for all 3 receipt citations). A citation without a URL is functionally unverifiable.

**MINOR** (P2: populate receipt URL or omit empty URL field)

---

## 4. RECEIPTS / DOCTRINE

### 4.1 `/api/brief/{id}` for L1

```
GET /api/brief/L1
HTTP 200 | Time: 36 ms
```

Returns full lead brief with:
- Priority section with `formula_verdict: LambdaMonotonicity` pass, lambdaScore 1.0
- Why-now section with `formula_verdict: FalsePosition` pass (HOT threshold crossing time: ~172 min)
- Opening lines with multiple angle options
- `wealth_tier.advisory: true`, `basis: "estimated from public records"`
- `lapse.advisory: true`, `lapse.fcra: false`, `lapse.note: "Advisory prioritization from public proxies — NOT an FCRA consumer report or eligibility decision."`

**PASS**

### 4.2 `/api/receipt/{rid}` — sample run L1

```
GET /api/receipt/rcpt_58dd7a0fdf57af1b
HTTP 200 | Time: 34 ms
```

Full receipt includes:
- `"all_signals_public": true`
- `"fabricated_signals": 0`
- `"doctrine": "SZL governed-AI · public-data-only · honest by design"`
- `"signed": true`, `"signature_status": "DSSE-ECDSA-P256 SIGNED"`
- Consensus: 4 organs (a11oy, sentra, killinchu, amaru), all `verdict: "allow"`

**Note on signing_mode disclosure:**  
The receipt includes `"signing_mode":"ephemeral-witness-keys (real ECDSA-P256-SHA256 DSSE; in-memory test witnesses, not the production cosign key)"`. This is correctly honest — the ephemeral key is disclosed. However, a client reading this may not understand that the signatures do not persist across server restarts. Should be explained in the UI if receipts are presented as long-term audit trail.

**PASS** (with note)

### 4.3 `/api/verify/{rid}` — 5 honesty checks

```
GET /api/verify/rcpt_58dd7a0fdf57af1b
HTTP 200 | Time: 67 ms
{
  "receipt_id": "rcpt_58dd7a0fdf57af1b",
  "verdict": "VERIFIED",
  "checks": [
    {"check": "Payload hash re-derives (tamper-evident)", "pass": true},
    {"check": "All signals are public data", "pass": true},
    {"check": "Zero fabricated signals (honest by design)", "pass": true},
    {"check": "Chained to prior receipt", "pass": true},
    {"check": "ECDSA-P256 signature verifies", "pass": true}
  ],
  "recomputed_hash": "58dd7a0fdf57af1b018512dbbfee73e1de15aaa9a9102ded705c7e36f0d2cc3e"
}
```

All 5 honesty checks: **PASS**. Verdict: **VERIFIED**.

### 4.4 Signal public labeling

Every signal in live and sample runs carries `"public": true`. Sample signals carry `"live": false`. Live signals carry `"live": true`. The `[SAMPLE]` tag appears in source names for sample-mode signals.

The CDC Natality signal includes a note: `"note":"public aggregate (CDC disallows location via API)"` — correctly disclaims the nature of the aggregate.

**PASS**

### 4.5 SAMPLE / GAP state labeling in `/api/pulse`

- SAMPLE states: `coverage_label` includes `[SAMPLE]` and states the failure reason (e.g., `HTTPError`, `RuntimeError`)
- GAP states: `"mode":"STATIC"`, `"gap":true`, `"count":null`, `"coverage_label":null` — no fabricated counts
- Methodology doctrine field states: `"GAP states flagged honestly · failed probes → last-good cache or [SAMPLE] · no fabricated counts"`

**PASS**

### 4.6 Λ score confirmation

| Condition | Score | Match |
|---|---|---|
| Sample mode (recency_base=0.9 at age 0) | **87.2** | ✓ Expected |
| Live mode (recency_base=1.0 at age 0, fresh daily signal) | **88.1** | ✓ Expected |

Both values confirmed live. Model self-test in `/api/model` states: `"L1 archetype Λ score == 87.2 at age 0 (canonical drop-in reproduction)"` — matches sample output.

**PASS**

---

## 5. DOCTRINE GAPS — UNLABELED ESTIMATES

### 5.1 `est_premium` — **P1: MUST FIX before client**

Every lead carries an `est_premium` field (e.g., L1: `2335`, L4: `7935`, L8: `14908`). This is a dollar estimate of potential annual premium.

**The field has no machine-readable advisory label.** There is no `est_premium_advisory: true`, no `est_premium_note`, no `est_premium_basis` key alongside it. The numeric value appears bare.

```json
"est_premium": 2335
```

Compare to how `lapse` and `wealth_tier` are correctly labeled:
```json
"wealth_tier": { ..., "advisory": true, "basis": "estimated from public records" }
"lapse": { ..., "advisory": true, "fcra": false, "note": "NOT an FCRA consumer report..." }
```

A New York Life agent looking at `est_premium: 14908` could reasonably treat this as a known or quoted premium rather than an actuarial estimate derived from public-data proxies. This is the most significant doctrine gap.

The `est_premium` value does not appear in the CSV export (the export omits it), in `/api/brief/L1`, or in the webhook payload — but it is present in every `/api/run` lead object and `/api/leads` response.

**Required fix:** Add `est_premium_advisory: true` and `est_premium_note: "Estimated from public-data proxies (Census ACS income, product propensity); not a quoted or underwritten premium."` alongside `est_premium`.

**Verdict: FAIL — P1**

### 5.2 `kpi.pipeline_premium` — **P1: MUST FIX before client**

The KPI block returns:
```json
"kpi": {
  "pipeline_premium": 39101,
  ...
}
```

This is the sum of all `est_premium` values — a headline number a client will read as "my pipeline is worth $39,101/year in potential premium." It has no advisory label, no note, no basis field.

**Required fix:** Add `pipeline_premium_advisory: true` and a note explaining it sums estimated (not quoted) premiums.

**Verdict: FAIL — P1**

### 5.3 Delaware signal with `"?"` count — **P2**

One live signal contains a literal `?` as a data value:
```json
{
  "source": "Delaware (data.delaware.gov)",
  "signal": "Delaware: professional & occupational licenses → new professionals to cover",
  "detail": "? professional & occupational licenses issued in 2026 — first-earning-year prospects",
  "live": true
}
```

The `?` suggests a query returned no parseable count but the signal was emitted anyway. The signal is labeled `"live":true`, which is misleading when the actual count is unknown. This should either be suppressed or labeled `"live":false` with a note about the failed parse.

**Verdict: MINOR — P2**

### 5.4 `/api/ask` citation URLs are empty strings — **P2**

```json
"citations": [
  {"label":"Lead L1 signed receipt rcpt_490710e8134c3268", "url":""},
  ...
]
```

Citations with empty URLs are unverifiable. The receipt ID is present in the label, but a client cannot click through to verify. Should either populate the URL (e.g., `/api/receipt/{rid}`) or omit the `url` field if not resolvable.

**Verdict: MINOR — P2**

---

## 6. RESILIENCE

### 6.1 Pulse repeated calls

Three consecutive `/api/pulse` calls (1-second apart):

| Call | HTTP | Time | States LIVE | States SAMPLE | States GAP | Receipt signed |
|---|---|---|---|---|---|---|
| 1 | 200 | 2.04s | 7 | 6 | 3 | true |
| 2 | 200 | ~2s | 7 | 6 | 3 | true |
| 3 | 200 | ~2s | 7 | 6 | 3 | true |

Consistent results across calls. No oscillation. SAMPLE states are consistently labeled. GAP states consistently have `null` counts.

**PASS**

### 6.2 Cache / fallback doctrine

The methodology states: `"last-good real counts served as 'LIVE (cached <ts>)' when a refetch fails"`. No cached entries were observed during this audit (all live probes succeeded or correctly fell to SAMPLE). The doctrine is stated; cache behavior under failure could not be triggered in a read-only audit.

**PASS (doctrine stated; live behavior not stress-tested)**

### 6.3 Timing summary

| Endpoint | Time | Status |
|---|---|---|
| `/healthz` | 62 ms | Fast |
| `POST /api/login` | 61 ms | Fast |
| `POST /api/run` (sample) | 849 ms | Fast |
| `POST /api/run` (live) | **7,831 ms** | Acceptable (<15s) |
| `GET /api/pulse` | 2,043 ms | Acceptable |
| `GET /api/brief/L1` | 36 ms | Fast |
| `GET /api/receipt/{rid}` | 34 ms | Fast |
| `GET /api/verify/{rid}` | 67 ms | Fast |
| `POST /api/work` | 42 ms | Fast |
| `GET /api/lake` | 68 ms | Fast |
| `GET /api/benchmark` | 31 ms | Fast |
| `GET /api/routing` | 31 ms | Fast |
| `GET /api/export.csv` | 26 ms | Fast |
| `GET /api/model` | 94 ms | Fast |
| `GET /api/territory` | 366 ms | Fast |
| `POST /api/ask` | 568 ms | Fast |

No endpoint exceeded 15s. Live `/api/run` at ~7.8s is the slowest; this is expected given concurrent upstream probes (NY DOS, ACRIS, BLS, SEC, Census, etc.).

---

## 7. SIGNAL DEDUPLICATION NOTE

In the receipt for a sample-mode L1 run, the U.S. Treasury FiscalData signal appears **6 times** (3 instrument types × 2 duplicate assembly passes):

```
"U.S. Treasury FiscalData (avg_interest_rates) [SAMPLE]" — 6 occurrences
```

This is not a fabrication (same public source, same data), but it inflates `signals_used` count and creates a noisy receipt. The governance `fabricated: 0` count remains correct since these are genuinely the same public signal duplicated, not invented signals. Low priority, but should be deduplicated for receipt cleanliness.

**Verdict: P3 (cosmetic)**

---

## 8. PRIORITIZED FIX LIST

### P1 — Must fix before sending to David Abraham (NYL agent)

| # | Issue | Location | Fix |
|---|---|---|---|
| 1 | `est_premium` has no advisory label — a bare dollar number could be mistaken for a quoted premium | `/api/run`, `/api/leads` lead objects | Add `est_premium_advisory: true` + `est_premium_note: "Estimated from public-data proxies; not a quoted or underwritten premium."` alongside `est_premium` |
| 2 | `kpi.pipeline_premium` has no advisory label — "$39,101" headline could be read as verified pipeline value | `/api/run` KPI block | Add `pipeline_premium_advisory: true` + explanatory note |

### P2 — Fix before broader deployment

| # | Issue | Location | Fix |
|---|---|---|---|
| 3 | Delaware professional-license signal emits `"?"` as count with `"live":true` | `/api/run` live signals | Suppress signal or set `"live":false` with a parse-failure note when count is unavailable |
| 4 | `/api/export.csv` returns `Content-Type: application/json` instead of `text/csv` | HTTP response header | Set `media_type="text/csv"` in the FastAPI route |
| 5 | `/api/ask` citations have `"url":""` (empty string) | `/api/ask` response | Populate URL with `{base_url}/api/receipt/{rid}` or omit the url key |

### P3 — Low priority / polish

| # | Issue | Location | Fix |
|---|---|---|---|
| 6 | `server: uvicorn` header reveals framework | All responses | Suppress or replace with a custom server name |
| 7 | `x-proxied-host: http://10.112.31.72` exposes internal IP | All responses (HuggingFace proxy header) | Infrastructure-level fix (HuggingFace platform); document as known |
| 8 | Missing HTTP security headers (`X-Content-Type-Options`, `X-Frame-Options`, `CSP`, `HSTS`) | All responses | Add middleware to set standard security headers |
| 9 | Invalid state code (e.g., `"XYZZY"`) silently falls back to NY defaults with HTTP 200 | `POST /api/run` | Return HTTP 400 with a list of valid state codes |
| 10 | Treasury FiscalData signal duplicated 6× in receipts | Receipt signal assembly | Deduplicate signals by (source, signal) key before including in receipt |
| 11 | Ephemeral signing key disclosure in receipt `signing_mode` | Receipt consensus block | Add UI note explaining ephemeral keys don't survive server restarts; clarify durability model |

---

## 9. OVERALL VERDICT BY CATEGORY

| Category | Verdict | Notes |
|---|---|---|
| Authentication — login rejects wrong credentials | **PASS** | Clean 401 for all wrong-credential variants |
| Authentication — endpoints require token | **PASS** | All data endpoints reject missing/invalid tokens with 401 |
| No stack traces on bad input | **PASS** | 422 or 404 with clean JSON for all garbage inputs |
| Response headers — alarming leaks | **MINOR** | Internal IP in x-proxied-host (HuggingFace infra); server: uvicorn |
| Live data flow — /api/run (sample) | **PASS** | 849ms, mode labeled SAMPLE, fabricated=0 |
| Live data flow — /api/run (live) | **PASS** | 7.8s, fabricated=0, 47 live signals, real data |
| Live data flow — /api/pulse | **PASS** | 16 states, honest LIVE/SAMPLE/GAP labeling, plausible counts |
| Live data flow — all other endpoints | **PASS** | All return 200 with correct data |
| Receipt /api/receipt — signed | **PASS** | DSSE-ECDSA-P256 signed, 4-of-4 consensus |
| Receipt /api/verify — 5 honesty checks | **PASS** | All 5 checks pass: hash, public signals, zero fabricated, chain, ECDSA |
| Signals labeled public, fabricated=0 | **PASS** | All signals public:true; fabricated:0 in governance |
| SAMPLE/GAP states labeled honestly | **PASS** | [SAMPLE] in source names; GAP states have gap:true, count:null |
| /api/model — Λ as Conjecture 1 (OPEN) | **PASS** | "Conjecture 1 (OPEN — CAUCHY_ND sorry + missing symmetry axiom; NOT a theorem)" |
| /api/model — DOI 10.5281/zenodo.20434308 | **PASS** | doi and doi_url both present |
| /api/model — advisory/non-FCRA notes | **PASS** | FCRA: false + note in lapse; advisory: true in wealth/lapse/receptivity/gap |
| Λ score: 87.2 (sample) / 88.1 (live) | **PASS** | Both confirmed |
| est_premium has advisory label | **FAIL — P1** | Bare dollar number, no advisory/note field |
| kpi.pipeline_premium has advisory label | **FAIL — P1** | Bare dollar number, no advisory/note field |
| Resilience — pulse stable across calls | **PASS** | Consistent 3/3 calls |
| Cold start timing | **PASS** | Space was warm; 62ms healthz |

---

*Audit completed read-only. No code or configuration was modified. All test tokens used during this audit are session-scoped and were obtained via the documented login flow.*
