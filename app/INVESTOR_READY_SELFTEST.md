# Investor-Ready Surface — Self-Test Report

Branch: `feat/investor-ready` (off `main`). Built + self-tested locally. **Not pushed / not deployed.**

## What changed
Every David-facing UI string was rewritten into plain business English. All the math stays
in the code and in the `/api/model`, `/api/verify`, and receipt JSON (the proof layer). Two new
plain-English frontier rungs were added: a "Confirmed across N public records" confidence wording
and a "Where Need Is Rising" surge view.

### Files changed
- `app/frontier.py` — added `confidence_word(half_width)` → `High` (≤12) / `Medium` (≤22) / `Building` (else).
- `app/scoring.py` — `_attach_frontier` now sets `confidence.level` from `confidence_word`.
- `app/warn_leads.py` — layoff leads also carry `confidence.level`.
- `app/server.py` — new `GET /api/surge?states=...` (Rising/Steady/Quiet per area via honest baseline-delta over public-records activity; areas without a live count this run are labelled `sample`).
- `app/static/index.html` — toolbar labels, run hint, top banner, card titles, legend, governance panel; new trust strip, welcome/"How it works" 3-step overview, and "Where Need Is Rising" panel + styles.
- `app/static/app.js` — `trendChip` (Momentum / Heating up / Cooling off / Steady · % interest), `confidenceLine` (Match / Confidence word / "confirmed across N public records" / muted range), `blockedBadge` (🚫 Cannot contact — plain reason), `renderGov` (Trust & Compliance Check, plain lines), `openModel` (How scoring works — 5 plain factors + named public sources), `openBrief` (Call Brief), `openReceipt` (Proof & Sources), `loadWarn` (plain), new `openSurge`/`loadSurge`.

## Jargon → plain-English mapping applied
| Was | Now |
|---|---|
| fused Prospect Track | Momentum |
| ↑ heating / ↓ cooling / → steady | ↑ Heating up / ↓ Cooling off / → Steady · % interest |
| Score · CI · ESTIMATE | Match · Confidence: High/Medium/Building · confirmed across N public records (range lo–hi) |
| ⛔ Λ-GATE BLOCKED | 🚫 Cannot contact — On the Do-Not-Call list / Records show deceased / Asked not to be contacted |
| Governance Gate | Trust & Compliance Check |
| khipu witness consensus 4-of-4 | Independently double-checked — 4 separate verifications agree |
| Open the Black Box | How scoring works |
| Verify Receipt | Proof & Sources |
| Signed Brief | Call Brief |
| Provenance · Outcome | Proof · Outcome |
| WARN Layoffs | Layoff Alerts |
| Tax Territories | Wealth Map |
| Territory Pulse | Coverage Map |
| Real Prospects | Real Businesses |

Honesty is preserved by meaning: "Confidence: Medium", premiums "illustrative — not a quoted
premium", sample rows labelled "Example". The navy/gold style and the holo-mode toggle are unchanged.

## Self-test results (all pass)
1. `python3 -c "import app.server"` → **clean import**. `confidence_word(10/18/30)` → `High / Medium / Building`.
2. `node --check app/static/app.js` → **OK**.
3. Boot `uvicorn app.server:app`; login `david` → token issued. Then:
   - `POST /api/run` → **HTTP 200**; lead0 `score 87.2`, `confidence.level Medium`, `n_sources 3`; governance verdict PASS, consensus 4-of-4.
   - `GET /api/surge?states=NY,NJ,PA,MD,DE,CT` → **HTTP 200**; 6 areas with Rising/Steady/Quiet status, baseline 39.2, each row `{area,status,count,note,source,source_status}`.
   - `GET /api/warn-leads?states=NY,NJ` → **HTTP 200**; leads carry `confidence.level`.
   - `GET /api/model` → **HTTP 200**; 5 axes.
   - No 500s.
4. Banned-jargon grep (exact T1 command) over `app/static/*.html app/static/*.js` → **ZERO matches**.
5. Do-Not-Call lead `L1-DNC`: `score 0.0`, compliance reason maps in the UI to
   **"🚫 Cannot contact — On the Do-Not-Call list"** (verified via the `blockedBadge` logic for DNC / deceased / opt-out).
6. Canonical age-0 L1 archetype still computes **87.2** (in-process and via `/api/run` sample path).

## Grep proof
```
$ grep -niE "lambda|Λ|kalman|pac-bayes|conformal|khipu|dsse|merkle|conjecture|non-compensatory|geometric mean|covariance|aggregator|\bprovenance\b|substrate|ouroboros|black box|ESTIMATE| CI " app/static/*.html app/static/*.js
(zero matches)
```
