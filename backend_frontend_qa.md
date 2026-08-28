> **LEGACY / RETIRED / DO NOT USE AS CURRENT RELEASE OR RUNTIME EVIDENCE.**
> This report describes a historical branch-local QA run. Its status, counts, and product
> concepts are not the active demo contract. Use [README.md](README.md) and
> [FOR_DAVID.md](FOR_DAVID.md), then verify the running release directly.

# Archived — David Leads Production-Readiness Hardening QA Report

**Branch:** `hardening/production-ready` (off `main`, HEAD 85430e6) · **Workdir:** `/home/user/workspace/dlv8`
**Scope:** Harden only — no new features. Behavior preserved (L1 Λ = 87.2; honest-by-design doctrine intact).
**Status:** All issues fixed; full verify green. **Not pushed / not deployed.**

---

## 1. Backend hardening (app/server.py)

Goal: every endpoint does a proper auth check, validates input, returns a clean 4xx/503 (JSON body) on bad/missing input or a failing data feed — **never a 500 stack trace**.

| # | Endpoint / area | Issue found | Fix |
|---|---|---|---|
| B1 | `/api/run` | `gather_all`, `build_leads`, per-lead `make_receipt`, brief construction, learning/kpi were unguarded — any single failing feed could 500 the whole run. | Wrapped each stage in `try/except` with honest fallbacks (empty SAMPLE meta, `leads=[]`, `receipt_id=None`, brief "run intelligence" placeholder). Governance dict now reads `meta.get(...)`. `/api/run` can no longer 500. |
| B2 | `/api/territory` | `territory_index()` unguarded. | `try/except` → falls back to cached territory or an honest `SAMPLE (offline)` stub. |
| B3 | `/api/ask` | `answer()` + receipt creation unguarded; `result["intent"]`/`["citations"]` direct-indexed. | Wrapped `answer()` (honest "temporarily unavailable" fallback) and receipt block; switched to `.get()` accessors. |
| B4 | `/api/pulse` | `territory_pulse()` unguarded; `result["summary"]["top_state"]` could `KeyError`. | Wrapped pulse call → clean **503**; guarded `summary`/`seaboard` with `.get()`; receipt block wrapped. |
| B5 | `/api/brief/{id}` | `build_signed_brief()` unguarded; no fallback if formulas engine throws. | Wrapped; falls back to `sc.build_brief`, then clean **503**. Receipt block wrapped. Unknown id still clean **404**. |
| B6 | `/api/work` | `run_territory_pulse()` + `lake.size()` unguarded; direct `out["..."]` indexing. | Wrapped loop → clean **503**; `.get()` accessors; `lake.size()` guarded. |
| B7 | `/api/model` | `model_card()` unguarded. | `try/except` → clean **503**. |
| B8 | `/api/leads` | `kpi_summary()` unguarded. | Guarded → `kpi={}` on failure. |
| B9 | `/api/benchmark` | `outcome_summary()` + `build_benchmark()` unguarded. | Both guarded → clean **503** on benchmark failure. |
| B10 | `/api/lake` | `lake.query()`/`size()` unguarded. | Wrapped → clean **503**. |
| B11 | `/api/outcome` | `classify()` + `record_outcome()` unguarded; f-string `summary['total_outcomes']` could `KeyError`. | Both guarded; message uses `.get('total_outcomes', 0)`. |
| B12 | **`/api/webhook/test`** (security) | Accepted **any** URL scheme — `file://`, `gopher://` etc. → local-file-read / SSRF risk. | Added `urllib.parse` scheme validation: **only `http`/`https` with a netloc**. Invalid → honest `would_send` payload (never a send, never a 500). Verified `file:///etc/passwd` is rejected. |
| B13 | `/api/login` (security) | Plain `==` password/key compare (timing side-channel). | Switched to `secrets.compare_digest` (constant-time) for both password and access key. |
| B14 | CORS (security) | Hardwired `allow_origins=["*"]`. | Now env-configurable via `DAVID_CORS_ORIGINS` (comma-separated); default `*` is safe here because auth is a **bearer token in a header**, not a cookie — no credentials are sent cross-site. |

### Confirmed already-correct (no change needed)
- **No hardcoded secrets / keys.** Cosign keys read **only** from env (`SZL_COSIGN_PRIVATE_PEM` / `SZL_COSIGN_PUBLIC_PEM`); BLS/FRED/Census API keys from env; consensus PEM passed as a param. `grep` for `BEGIN ... PRIVATE KEY` → none.
- **Outbound timeouts** already present (12s in liquidity/wealth990/signals; 8s in webhook). Per-source helpers already fall back to `[SAMPLE]` when a feed is unreachable.
- `/healthz` (no auth, correct), `/api/verify/{id}` & `/api/receipt/{id}` (clean 404), `/api/export.csv` (per-row `try/except`), `/api/routing` (already fully defensive w/ empty-table fallback).
- Demo credentials are env-overridable (`DAVID_USER`/`DAVID_PASS`/`DAVID_ACCESS_KEY`).

---

## 2. Frontend / mobile hardening (app/static/)

Audited `index.html`, `app.js`, `holo.css` at **390 / 768 / 1280 px**.

**Already solid (verified, no change needed):**
- Overflow guards in place: `body{overflow-x:hidden}`, `.wrap{overflow-x:clip}`, `*{box-sizing:border-box}`, modal `width:min(560px,96vw); max-height:88vh; overflow:auto`, ladder `max-width:100%`, viewport meta present.
- Every fetch wrapped in `try/catch`; **loading skeletons** + **loading text** for leads/model/territory/benchmark/routing/pulse/CRM; friendly **empty/error** messages; clipboard `execCommand` fallback for copy.
- `app.js` loads **first**; three.js + holo.js **deferred** — a slow/blocked CDN never freezes the app (confirmed: only the deliberately-aborted CDN resource errors, app stays fully interactive).

**Result:** no frontend code changes were required — the prior P2 overflow/defer fixes hold under the production-hardening test matrix.

---

## 3. Verification results (all green)

**Tooling:** `py_compile` all modules · `uvicorn SERVE_STATIC=1` on fresh port 7771 · Playwright (bundled chromium-1217) driving the **local** app at 390/768/1280, CDN aborted.

### Compile & boot
- `python -m py_compile app/*.py` → **OK**.
- Boot + login using temporary test credentials supplied only through environment variables → token issued.

### API endpoints (authenticated, after a sample run)
| Endpoint | Result |
|---|---|
| `/api/run` (sample) | **200**, 8 leads, **L1 Λ = 87.2** ✓, brief 3 items |
| `/api/model` | **200**, DOI **10.5281/zenodo.20434308**, uniqueness **"Conjecture 1 (OPEN …)"** ✓ |
| `/api/brief/L1` | **200**, **4 parts** (Priority / Why now / Opening line / Sensitivity); receipt verify → **VERIFIED** ✓ |
| `/api/routing` | **200**, **8** routed rows ✓ |
| `/api/export.csv` | **200**, header + **8** data rows (9 lines) ✓ |
| `/api/territory`, `/api/pulse`, `/api/leads`, `/api/benchmark`, `/api/ask`, `/api/work`, `/api/outcome`, `/api/lake` | all **200** |

### Error / edge cases (no 500s anywhere)
| Case | Result |
|---|---|
| Missing token / bad token / bad login | **401** |
| `/api/brief/NOPE`, `/api/verify/NOPE` | **404** (clean JSON body) |
| `/api/outcome` bad outcome value | **422** |
| `/api/run` malformed body (`live:"notabool"`) | **422** (pydantic) |
| webhook `file:///etc/passwd` | **200**, `sent:false`, reason "invalid url (only http/https allowed)" — **no file read** |
| webhook garbage url | **200**, `sent:false`, invalid-url reason |
| webhook unreachable host | **200**, `sent:false`, returns `would_send` payload |
| webhook no url | **200**, `sent:false`, returns `would_send` (count 8) |

### Frontend (Playwright, all 3 widths)
- **Horizontal overflow = 0** at every step (login, after-run, all 5 panels, lead-expanded, brief-modal, brief-verified, final) at 390 / 768 / 1280. (17+ measurements, all 0.)
- **0 application JS errors.** Only error is the single deliberately-aborted external CDN resource (`net::ERR_FAILED`) — acceptable, not an app error.
- Drove: login → Run Sample → Territory Pulse / Black Box / Benchmark / Routing / Territory Map → expand lead → open + verify brief. All panels/modals open and close.
- Screenshots: `/tmp/hard_mobile.png`, `/tmp/hard_tablet.png`, `/tmp/hard_desktop.png` — modal + leads grid render cleanly at each width.

---

## 4. Doctrine preserved
Public-data only · `[SAMPLE]` labels on unreachable feeds · never fabricate · **UNSIGNED-honest** without a cosign key (receipts still hash-chain VERIFIED) · **Λ = Conjecture 1 (OPEN)**, never a theorem · **L1 Λ = 87.2** unchanged · David the only real advisor.

## 5. Files changed
- `app/server.py` — all hardening edits above.
- (No frontend code changes required.)
- `qa/backend_frontend_qa.md` — this report.

**Not pushed. Not deployed.**
