> **LEGACY / RETIRED / DO NOT USE AS CURRENT RELEASE OR RUNTIME EVIDENCE.**
> This is a historical local self-test for a superseded feature branch. Use
> [README.md](../README.md) and [FOR_DAVID.md](../FOR_DAVID.md) for the active contract.

# Archived Frontier Upgrade — Self-Test Report

Branch: `feat/frontier-upgrade` · **Not pushed / not deployed** (parent agent verifies & deploys).

All six tasks (T1–T6) wired to the **already-written, self-tested** `app/frontier.py` — the
frontier math (decay, Λ-gate, confidence band, Kalman fusion, receipt) is NOT reimplemented.

## Files changed
- `app/scoring.py` — T1 Λ-gate compliance (multiplicative, non-compensatory), T2 confidence
  bands, T3 fused track, T4 `per_trigger_half_life_days` in `model_card()`. Added helpers
  `_frontier_n_sources`, `_frontier_measurements`, `_attach_frontier`; appended a clearly-labelled
  DNC demo lead; guarded `kpi_summary`/`_rank` against the new `BLOCKED` bucket.
- `app/warn_leads.py` — **NEW** WARN Act layoff pipeline (T5).
- `app/server.py` — defensive `warn_leads` import + `GET /api/warn-leads` endpoint (T5).
- `app/static/app.js` — T6: `trendChip`, `confidenceLine`, `blockedBadge` in `renderLeads`;
  `openWarn`/`loadWarn` WARN panel.
- `app/static/index.html` — T6: `⚠️ WARN Layoffs` toolbar button, `#warnCard` panel, Frontier
  explainer note, CSS for trend chip / confidence line / Λ-GATE BLOCKED / demo note.

## Self-test commands & outputs

### 1. Imports clean
```
$ python3 -c "import app.server"          -> server import OK
$ node --check app/static/app.js          -> app.js OK
```

### 2. Server boot + endpoints (uvicorn, port 779x, SERVE_STATIC=1)
```
GET  /healthz                              -> {"status":"ok",...}
POST /api/login (access_key)               -> 32-char bearer token
POST /api/run  {"live":false}              -> 9 leads; keys: meta,signals,leads,kpi,brief,...
GET  /api/pulse                            -> HTTP 200
GET  /api/model                            -> per_trigger_half_life_days{table(10),formula,note}
GET  /api/warn-leads?states=NY,NJ,PA,MD,DE,CT -> count 6; sample_states all 6; top lead labelled
```

### 3. Frontier fields on every lead (from /api/run)
- L1 archetype: **score 87.2** · `confidence` present (CI 72.3–100.0) · `track.trend` = steady
  · `compliance.clear` = true.
- Every lead carries `confidence` (ESTIMATE), `track` (heating/cooling/steady ESTIMATE),
  `compliance` ({clear, reasons}).

### 4. Λ-gate (T1) — DNC structurally zeroed
- DNC demo lead "New-parent household (NY metro) — DNC (Λ-gate demo)":
  **score 0.0**, `score_pre_gate` 87.2, bucket **BLOCKED**, reason
  "On Do-Not-Call registry — outreach blocked (TCPA)". Sorts **last**.
- Honest framing: demonstrates gate behavior on a contact-status field; clearly labelled
  `demo_note`, NOT fabricated prospect data.

### 5. Canonical invariant preserved
- **L1 archetype Λ == 87.2 at age 0** (clear compliance axis value 1.0 → multiplicative gate is a
  no-op; the 5-axis Λ geometric mean is untouched, so the canonical self-test holds). Verified via
  both `scoring.lambda_score(...)` and the live `/api/run` output.

### 6. No 500s
- All exercised endpoints returned JSON (healthz, login, run, pulse, model, warn-leads).

## T5 WARN pipeline — honesty
- No machine-readable WARN feed reachable in-sandbox → all 6 states return
  `source_status: "sample"`. Sample rows use **illustrative placeholder employers** (prefixed
  `[SAMPLE]`) on the **real WARN schema**, each citing its **official state WARN portal** URL.
  No specific real employer's data is presented as live-verified. `LIVE_ENDPOINTS` is the hook to
  add a state the moment a stable structured endpoint is confirmed (then `source_status` flips to
  `live`). Each WARN lead carries `frontier.trigger_decay("warn_layoff", ...)`,
  `frontier.confidence_band(...)` (ESTIMATE), and a `frontier_receipt` (signed:false, UNSIGNED-honest).

## T6 frontend — mobile note (honest limitation)
- No browser binary was installable in the offline sandbox (`playwright install` cannot download),
  so an automated 390px screenshot run could **not** be executed this session. Verified
  **structurally** instead: new chips render inside `.lead-chips { display:flex; flex-wrap:wrap }`
  (wrap gracefully, `white-space:nowrap` per chip); the WARN panel reuses `.real-wrap
  { overflow-x:auto }` so the table scrolls within its card without page overflow; the Frontier
  note and confidence line are block elements with padding. No new external CDN dependencies; pure
  vanilla JS (`node --check` passes).

## Doctrine compliance
Public-data-only; ESTIMATE labels on confidence + track; Λ uniqueness remains Conjecture 1 (open);
WARN sample rows labelled and cited (no fabrication); UNSIGNED-honest receipts (no cosign key);
DNC/deceased/opt-out structurally blocked; no private cell/home/PII; no social scraping. All
additive — existing endpoints and the L1 Λ==87.2 invariant intact.
