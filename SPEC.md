> [!CAUTION]
> **LEGACY / RETIRED / DO NOT USE FOR IMPLEMENTATION, DEMOS, OR PRODUCT CLAIMS.**
> This early person-level concept is retained only as design history. It is
> superseded by the organization-only, public-research-only contract in
> [`README.md`](README.md) and [`FOR_DAVID.md`](FOR_DAVID.md). The active live
> path never substitutes sample prospects and never infers permission to contact.

# Archived concept - David Leads Sovereign Insurance Intelligence
**Client:** David Abraham, MBA — Financial Professional, New York Life Insurance Company (New York, NY)
**Built by:** SZL Holdings (Stephen Lutar) — sovereign governed-AI substrate, retargeted to insurance lead intelligence.
**Meeting:** tomorrow. Goal = impress David, prove the KPI, win the consulting engagement.

---

## 0. The KPI we optimize for
**Primary:** Qualified appointments booked per week, driven by LEAD QUALITY (right person × right life-event × right NYL product).
**Secondary:** Projected premium / pipeline value of those leads.
The whole app must visibly drive these two numbers.

## 1. What David does (so the product fits him exactly)
NYL financial professional. Sells: term/whole life (family coverage), retirement & annuities (lifetime income),
college funding (529-adjacent), long-term care, lifetime income strategies. His job = find the right family at the
right life-moment and match the right product. Field is hyper-competitive; every advisor chases the same families.

## 2. The edge / moat (why David beats competitors)
Enterprise tools (LexisNexis Lead Optimizer for Life, Deloitte PredictRisk, RGA Predictive Moments, Verisk) sell
life-event predictive scoring to CARRIERS — black-box, expensive, compliance-opaque. Agent CRMs (AgencyZoom, EZLynx,
LeO) only manage/route leads. NOBODY at the agent level gives transparent, public-data-only, cryptographically
**receipted** lead intelligence. Insurance compliance (NY DFS, suitability) punishes opaque data sourcing.
**Our moat = the SZL governed-AI substrate applied to leads:**
  - Every lead score carries a **signed receipt** (DSSE / SHA-256 hash-chain) — audit-defensible provenance.
  - A **governance gate** (Λ-style) enforces: public-data-only, compliant signals, no fabricated data ("honest by design").
  - **Live business observability** dashboard shows David's KPI in real time.
  - **3D wow** layer for the meeting.

## 3. Live FREE public data signals (no paid keys)
- **SEC EDGAR** (data.sec.gov + efts.sec.gov): no key, User-Agent header only. 8-K events, hiring/comp, layoffs,
  exec changes → workforce salary-up / job-change signals (job change = #1 life-insurance trigger).
- **BLS** (api.bls.gov v1): no registration. Wage growth, employment by sector → "salary up" bracket signals.
- **U.S. Census ACS** (api.census.gov): free instant key. Income, age, homeownership, family composition by area.
- **CDC WONDER Natality**: births trends (national/state; no location via API) → "new baby" family-coverage trigger.
- All signals are PUBLIC and AGGREGATE — never private PII. This is the compliance story.

## 4. Life-event → NYL product mapping (the scoring core)
| Life event signal        | Public source        | NYL product matched          | Why (talking point)                       |
|--------------------------|----------------------|------------------------------|-------------------------------------------|
| New baby / birth uptick  | CDC natality, Census | Term/Whole life (family)     | New dependents → coverage need spikes     |
| Job change / promotion   | SEC 8-K, BLS wages   | Whole life + retirement      | Income up → protect + invest              |
| Home purchase / area     | Census homeownership | Mortgage-protection / term   | Debt obligation → income replacement      |
| Mid-career 35-50 + income| Census ACS, BLS      | Retirement / annuity         | Lifetime income planning window           |
| Near-retirement 55-65    | Census age bands     | Annuity / LTC                | Income + care-cost protection             |
| College-age dependents   | Census household     | College funding strategy     | Funding gap, tax-advantaged growth        |

## 5. Scoring model (Λ-style, transparent)
score = weighted geometric mean over axis sub-scores in [0,1]:
  axes = {life_event_strength, income_fit, age_window_fit, product_propensity, recency}
Output 0-100. Bucketed: HOT (>=80), WARM (60-79), NURTURE (<60).
Each lead returns: score, bucket, matched product, plain-English "why" tied to public source, signed receipt id.
Governance gate: REJECT any lead whose signals are non-public or fabricated → never emitted (honest by design).

## 6. App surfaces (UI)
1. **Login gate** — David-only credentialed access (not public). Username/password + access key.
2. **Command dashboard** — headline KPI cards: Qualified Appts/Week target, Pipeline $ value, HOT lead count.
3. **Lead intelligence table** — ranked leads, score, bucket, product match, "why", [Verify Receipt] button.
4. **Run intelligence** — pull live public signals (SEC/BLS/Census/CDC) → score → populate leads. Has a
   "Load Sample (offline)" button as backup if wifi fails in the meeting.
5. **Receipt verifier** — click any lead → show its signed receipt (hash chain) → verify → green check. THE MOAT.
6. **Governance panel** — shows the gate: "X signals checked, all public, 0 fabricated, compliant."
7. **3D ecosystem view** — borrowed anatomy/cathedral visual (Three.js) — the wow.

## 7. Tech
- Backend: FastAPI (Python). Endpoints: /login, /run, /leads, /receipt/{id}, /verify, /kpi, /healthz.
- Live data fetchers for SEC/BLS/Census/CDC with graceful offline fallback to bundled sample data.
- Receipts: SHA-256 hash-chained JSON (DSSE-style envelope), reuse pattern from sentra/szl_dsse.py. Honest:
  if no signing key, emit clearly-labelled UNSIGNED receipt — never fake a signature.
- Frontend: clean professional single-page (NYL-appropriate: navy/white, trustworthy, NOT defense-jargon heavy).
  Three.js 3D panel for wow.
- Deploy targets: (a) Hugging Face Space (gated, SZLHOLDINGS), (b) user's domain, (c) portable offline single-file HTML backup.

## 8. Tone for THIS client
David is an insurance advisor, not a defense-tech founder. Keep copy about: trust, compliance, audit-defensible
leads, "see exactly why each lead scored," "spend time only on families ready to buy." Downplay Lean/Doctrine/Quechua
jargon. The signed-receipt = "compliance-grade proof," not "DSSE Khipu." Translate the moat into HIS language.

## 9. Deliverables for the meeting
- Live hosted app (URL) + offline backup HTML.
- README_FOR_STEPHEN equivalent: demo script + talking points + David's login creds.
- One-pager PDF: "David Leads — your unfair advantage."
