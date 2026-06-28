# David Leads — V2 "Fashion-House" Design Spec
**Author:** Opus Dev Agent 2 · **Project:** David Leads (NYL lead-intelligence app for David Abraham)
**Optimizes:** qualified appointments/week (lead quality) + premium pipeline.
**Doctrine carried forward:** public-data-only · honest-by-design · transparent Λ-style scoring · signed receipts.

---

## 0. How to read this spec

This document is organized so a **frontend dev agent** and a **backend dev agent** can each pick up their parts independently. Each feature section has four fixed sub-headings:

- **WHAT** — what the feature does for David.
- **OUT-CLASSES** — the named field leader it borrows from, and *why ours is better*.
- **FRONTEND** — exact DOM placement in `index.html` / functions in `app.js`, component names, CSS using our existing tokens.
- **BACKEND** — endpoint shape (request + JSON response), data source (free public only), and which module it lives in (`signals.py` / `scoring.py` / `server.py` / new module).

**Hard rules (non-negotiable, inherited from V1):**
1. **No fabricated data, ever.** Every number a user sees is either (a) computed transparently from public signals, or (b) explicitly labelled illustrative/modeled (as `est_premium` already is).
2. **Public sources only**, no paid APIs: SEC EDGAR (`efts.sec.gov` / `data.sec.gov`), BLS v1 (`api.bls.gov`), U.S. Census ACS (`api.census.gov`), CDC natality aggregate.
3. **Keep the visual identity.** Navy `#0a2540`, gold `#c08f2f`, teal `#168f89`, Fraunces (display) + Inter (body). Reuse existing CSS classes (`.card`, `.kpi`, `.badge`, `.btn`, `.modal`, `.sig`) — do not invent a new look.
4. **Every new artifact that asserts a lead is qualified must remain receiptable** — features that change a lead's standing should hang off the same `/api/run` lead objects and their receipts.

**Competitive context (from field-leader recon):** RGA *Predictive Moments* proved life-events + immediate context drive insurance receptiveness — but it's a carrier-level whitepaper model, opaque to the agent ([RGA Predictive Moments whitepaper](https://www.rgare.com/docs/default-source/-/predictive-moments-whitepaperv3.pdf?sfvrsn=fb8d64cc_2)). LexisNexis *Lead Optimizer for Life* / *Life in the Market* ranks and signals life-event readiness — but it is paid, carrier-focused, and a black box on *why* ([LexisNexis Lead Optimizer for Life](https://risk.lexisnexis.com/products/lead-optimizer-for-life), [LexisNexis acquisition & retention](https://risk.lexisnexis.com/insurance/acquisition-retention)). EverQuote sells warm leads on a "call fast" marketplace at ~20–30% bind rates — but the agent buys volume with no transparent provenance and no explanation ([EverQuote live-transfer leads](https://learn.everquote.com/live-transfer-insurance-leads)). **Our wedge across all of them: agent-level, transparent, public-data-only, cryptographically receipted intelligence that explains itself.** V2 turns that wedge into a daily workflow David actually loves opening.

---

## 1. Layout overview — where V2 lands in the current page

Current `index.html` body (inside `<div id="app">`):
```
header.top
.wrap
  .kpis            (4 KPI cards)
  .toolbar         (Run Live / Load Sample buttons + hint)
  .grid2
    .card  #leadsWrap          (Ranked Leads — left, 1.6fr)
    column:
      .card #gov               (Governance Gate)
      .card #signals           (Public Signals Used)
  footer.legal
```

V2 inserts the following, in DOM order, **without breaking the existing grid**:

```
header.top
.wrap
  [NEW] #briefBar      → Morning Brief banner (full-width, above KPIs)
  .kpis                → +1 card (now 5; grid becomes repeat(5,1fr)) — "Appts/Week Trend" sparkline card
  .toolbar             → + "Export Call List" + "Territory Map" buttons
  [NEW] #tickerBar     → Intelligence Feed ticker (full-width, thin, below toolbar)
  .grid2
    .card #leadsWrap   → each lead row gets a ▸ expander → "Why this lead" + "Predictive Moments" timeline + "Next Best Action"
    column:
      .card #gov
      .card #signals
      [NEW] .card #pipelineCard  → Premium Pipeline projection chart
  [NEW] #territoryModal  → Territory/ZIP heatmap (modal, like receipt modal)
  footer.legal
```

All new full-width blocks live directly inside `.wrap` and use `.card` styling so they inherit shadows/borders/radius automatically.

---

## 2. FEATURE 1 — "Morning Brief": today's top 3 leads to call

### WHAT
A single hero banner at the very top of the console that auto-generates **"Your 3 calls today,"** each with the lead name, score, the one-line reason, the matched NYL product, and a **[Open]** action that scrolls to + expands that lead's row. It reframes the whole app from "a table to browse" into "a daily action list" — directly serving the KPI (appointments/week) by telling David exactly who to dial first.

### OUT-CLASSES
EverQuote's pitch is "call fast" on a stream of purchased leads ([EverQuote live-transfer leads](https://learn.everquote.com/live-transfer-insurance-leads)) — but the agent gets volume with no ranking rationale. Our Morning Brief picks the **top 3 by transparent Λ score**, states the public-data reason, and every pick is backed by a verifiable receipt. David doesn't "call fast into noise" — he calls the 3 highest-probability, fully-explained families first.

### FRONTEND
- **Placement:** new `<div id="briefBar" class="card brief hidden">` as the first child inside `.wrap`, above `.kpis`.
- **Render fn (app.js):** `renderBrief(leads)` — called at the end of `runIntel()` after `renderLeads`. Take `leads.slice(0,3)` (already score-sorted by backend).
- **Component markup per pick:**
  ```html
  <div class="brief-pick" onclick="focusLead('L1')">
    <span class="brief-rank">1</span>
    <div>
      <div class="brief-name">New-parent household (NY metro) · <span class="badge HOT">HOT</span> 88.4</div>
      <div class="brief-line">New dependents — coverage need spikes · Term/Whole Life</div>
    </div>
    <button class="btn gold brief-open">Open ▸</button>
  </div>
  ```
- **`focusLead(id)`** new helper: expands the matching lead row (calls `toggleLeadDetail(id, true)` from Feature 4) and `scrollIntoView({behavior:'smooth'})`.
- **CSS (add to `<style>`):**
  ```css
  .brief{padding:16px 20px;margin-bottom:18px;background:linear-gradient(160deg,#0a2540,#143a5e);color:#fff;border:none}
  .brief h3{color:#fff;padding:0 0 10px;border:none;font-size:16px}
  .brief h3 .sec-title-meta{color:var(--gold-300)}
  .brief-pick{display:flex;align-items:center;gap:14px;padding:10px 0;border-top:1px solid rgba(255,255,255,.12);cursor:pointer}
  .brief-pick:first-of-type{border-top:none}
  .brief-rank{font-family:'Fraunces';font-size:22px;color:var(--gold-300);width:26px;text-align:center;flex:none}
  .brief-name{font-weight:600}.brief-line{font-size:12px;color:#bcd;margin-top:2px}
  .brief-open{margin-left:auto;flex:none;padding:7px 14px}
  ```
- Heading: `<h3>☀️ Your Morning Brief <span class="sec-title-meta">top 3 to call today · <span id="briefDate"></span></span></h3>` — set `briefDate` to `new Date().toLocaleDateString()`.

### BACKEND
**No new endpoint required** — the Morning Brief is a pure frontend projection over the existing `data.leads` array (already sorted descending by score in `scoring.build_leads`). Optional nicety: add a `brief` block to the `/api/run` response so the "today" framing can include a freshness stamp:
```jsonc
// add to server.run() return dict
"brief": {
  "generated_at": "2026-06-28T05:10:00Z",
  "top_ids": ["L1", "L2", "L3"],            // first 3 lead ids by score
  "headline": "3 high-probability families ready to engage today"
}
```
Implementation: in `server.run()`, after `leads` is built, `top = [l["id"] for l in leads[:3]]`. Trivial; no new data source.

---

## 3. FEATURE 2 — "Predictive Moments" life-event timeline per lead

### WHAT
Inside each expanded lead row, a horizontal **life-event timeline** showing the sequence of public-data triggers that make *this segment* receptive right now: e.g. for the new-parent segment → `Birth uptick (CDC)` → `Wage growth window (BLS)` → `Family-formation age band (Census)`. Each node is a real public signal with its source. It visually narrates *why this is the moment*.

### OUT-CLASSES
This is the agent-facing, transparent answer to **RGA Predictive Moments**, which proved life-events + context drive receptiveness but lives in a carrier whitepaper the field agent never sees ([RGA Predictive Moments](https://www.rgare.com/docs/default-source/-/predictive-moments-whitepaperv3.pdf?sfvrsn=fb8d64cc_2)). We take the same science (life-event × salient context) and **render it as a per-lead, source-cited timeline David can read aloud to a prospect** — and it's backed by a signed receipt, which RGA's model is not.

### FRONTEND
- **Placement:** inside the lead detail panel (Feature 4's expander), a `<div class="moments">` strip.
- **Render fn:** `renderMoments(lead)` returns HTML string, called by `renderLeadDetail`.
- **Markup:**
  ```html
  <div class="moments">
    <div class="moment"><span class="m-dot"></span><div class="m-src">CDC Natality</div><div class="m-txt">Birth uptick → new dependents</div></div>
    <div class="m-line"></div>
    <div class="moment"><span class="m-dot"></span><div class="m-src">BLS Wages</div><div class="m-txt">Earnings rising → "salary up"</div></div>
    <div class="m-line"></div>
    <div class="moment"><span class="m-dot gold"></span><div class="m-src">Census ACS</div><div class="m-txt">Family-formation age band</div></div>
  </div>
  ```
- **CSS:**
  ```css
  .moments{display:flex;align-items:flex-start;gap:0;padding:14px 4px;overflow-x:auto}
  .moment{display:flex;flex-direction:column;align-items:center;text-align:center;min-width:120px;gap:4px}
  .m-dot{width:14px;height:14px;border-radius:50%;background:var(--teal);box-shadow:0 0 0 4px rgba(22,143,137,.18)}
  .m-dot.gold{background:var(--gold);box-shadow:0 0 0 4px rgba(192,143,47,.18)}
  .m-src{font-size:10px;font-weight:700;color:var(--teal);text-transform:uppercase;letter-spacing:.03em}
  .m-txt{font-size:11px;color:var(--muted);max-width:110px}
  .m-line{flex:1;height:2px;background:var(--line);margin-top:6px;min-width:24px}
  ```

### BACKEND
Add a per-lead `moments` array built in `scoring.build_leads()`. Map each life-event to an ordered list of the **specific public sources** that justify it (drawn from the same gathered signals). Honest: each moment references a real source label; no invented dates/PII.
- Add to `scoring.py`:
  ```python
  MOMENTS_MAP = {
    "new_baby":        [("CDC Natality","Birth uptick → new dependents"),
                        ("BLS Wages","Earnings rising → coverage budget"),
                        ("Census ACS","Family-formation age band")],
    "job_change":      [("SEC EDGAR 8-K","Officer/comp change → income up"),
                        ("BLS Wages","Sector wage growth"),
                        ("Census ACS","Prime-earner age band")],
    "home_purchase":   [("Census ACS","Homeownership / mortgage band"),
                        ("BLS Wages","Income supports new debt"),
                        ("CDC Natality","Young-family formation")],
    "mid_career":      [("Census ACS","35–50 income window"),
                        ("BLS Wages","Peak-earning trend"),
                        ("SEC EDGAR 8-K","Employer comp signals")],
    "near_retirement": [("Census ACS","55–65 age band"),
                        ("BLS Wages","Pre-retirement income"),
                        ("CDC Natality","Multi-gen household context")],
    "college_age":     [("Census ACS","College-age dependents in HH"),
                        ("BLS Wages","Tuition-affordability window"),
                        ("SEC EDGAR 8-K","Regional employer stability")],
  }
  ```
- In `build_leads`, attach `lead["moments"] = [{"source": s, "label": t} for s,t in MOMENTS_MAP[p["event"]]]`.
- These flow through `/api/run` automatically (already returns full `leads`). **No new endpoint.** The receipt's `signals_used` already binds the real sources, so the timeline stays audit-consistent.

---

## 4. FEATURE 3 — "Why this lead" expandable explanation (source-cited)

### WHAT
Each lead row becomes expandable (▸). Expanding reveals: (a) the **Λ-score breakdown** — the 5 axis scores as labelled bars, so David sees exactly which dimensions drove the score; (b) the **plain-English why**; (c) **cited public sources**; (d) the Predictive Moments timeline (Feature 2); (e) the Next-Best-Action (Feature 4). This is the transparency moat made tactile.

### OUT-CLASSES
LexisNexis Lead Optimizer ranks leads but is a **black box** on *why* a lead scored — the agent cannot interrogate or defend it ([LexisNexis Lead Optimizer](https://risk.lexisnexis.com/products/lead-optimizer-for-life)). Ours opens the entire computation: weighted geometric mean over five named axes, each tied to a public source, each receipted. For an NYL professional under NY DFS suitability scrutiny, **explainability is not a nicety — it's a compliance asset.**

### FRONTEND
- **Placement:** modify `renderLeads()` in `app.js`. Add a leading expander cell and a hidden detail row per lead.
- **Component:** each `<tr class="lead-row" onclick="toggleLeadDetail('L1')">` followed by `<tr class="lead-detail hidden" id="detail-L1"><td colspan="4">…</td></tr>`.
- **New fns:**
  - `toggleLeadDetail(id, forceOpen)` — toggles `.hidden` on `#detail-{id}`, lazy-renders via `renderLeadDetail(id)` on first open.
  - `renderLeadDetail(id)` — looks up lead in `lastData.leads`, builds: axis bars + why + sources + `renderMoments(lead)` + NBA block.
- **Axis-bar markup:**
  ```html
  <div class="axis"><span class="axis-lbl">Life-event strength</span>
    <div class="axis-track"><div class="axis-fill" style="width:95%"></div></div>
    <span class="axis-val">0.95</span></div>
  ```
  Axis labels (map from `lead.axes` keys): life_event_strength→"Life-event strength", income_fit→"Income fit", age_window_fit→"Age-window fit", product_propensity→"Product propensity", recency→"Recency".
- **Sources line:** render the distinct `source` values from `lastData.signals` as small `.src` pills (reuse `.sig .src` styling), with text "Scored from public data:".
- **CSS:**
  ```css
  .lead-detail td{background:#fafcff;padding:16px 18px}
  .axis{display:flex;align-items:center;gap:10px;margin:5px 0;font-size:12px}
  .axis-lbl{width:140px;color:var(--muted);font-weight:600}
  .axis-track{flex:1;height:8px;background:#e8edf3;border-radius:6px;overflow:hidden}
  .axis-fill{height:100%;background:linear-gradient(90deg,var(--teal),var(--teal-300))}
  .axis-val{width:34px;text-align:right;font-family:'Fraunces';color:var(--navy)}
  .expander{display:inline-block;transition:transform .15s;color:var(--muted)}
  .lead-row.open .expander{transform:rotate(90deg)}
  .nba{margin-top:12px;background:#fff;border:1px solid var(--line);border-left:3px solid var(--gold);border-radius:8px;padding:10px 12px}
  .nba .nba-lbl{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:var(--gold)}
  .nba .nba-txt{font-size:13px;color:var(--ink);margin-top:2px}
  ```
- Add an "Open ▸" affordance: prepend `<span class="expander">▸</span>` to the lead-name cell; toggle `.open` class on the row.

### BACKEND
**No new endpoint** — `lead.axes`, `lead.why`, and `data.signals` are already in the `/api/run` payload. The frontend renders them. (The receipt modal already cites sources; this surfaces them inline too.)

---

## 5. FEATURE 4 — Opportunity Radar / Next-Best-Action per lead

### WHAT
Within each expanded lead, a single **prescriptive next step**: the concrete action + suggested talk-track tied to the matched product and life-event. E.g. for `near_retirement`: *"Lead with guaranteed lifetime income; open with the BLS pre-retirement earnings stat. Suggested: 15-min annuity + LTC review."* It converts a score into a *script*, shrinking the gap between "good lead" and "booked appointment" (the KPI).

### OUT-CLASSES
LexisNexis / Verisk give carriers a propensity number; **none hand the field agent the next sentence to say.** RGA's research even concluded that predictive moments only convert when paired with a persuasive, relevant prompt ([RGA Predictive Moments](https://www.rgare.com/docs/default-source/-/predictive-moments-whitepaperv3.pdf?sfvrsn=fb8d64cc_2)). We operationalize exactly that: every lead ships with the prompt, grounded in the public signal — turning insight into a dialed call.

### FRONTEND
- **Placement:** the `.nba` block (CSS above) rendered at the bottom of `renderLeadDetail(id)`.
- **Markup:**
  ```html
  <div class="nba">
    <div class="nba-lbl">Next best action</div>
    <div class="nba-txt">{lead.nba.action}</div>
    <div class="nba-txt" style="color:var(--muted);margin-top:4px">Talk track: "{lead.nba.talk_track}"</div>
  </div>
  ```

### BACKEND
Add an `nba` object per lead in `scoring.build_leads()`, keyed by life-event. Static, honest, product-aligned copy — references the public signal type, never fabricated personal facts.
```python
NBA_MAP = {
  "new_baby":        dict(action="Call within 24h; offer a 15-min family-coverage review.",
                          talk_track="New baby changes everything — let's make sure they're protected if anything happens to you."),
  "job_change":      dict(action="Congratulate on the role; propose protecting the new income + a retirement contribution review.",
                          talk_track="Your income just grew — let's protect it and put some to work for retirement."),
  "home_purchase":   dict(action="Position mortgage-protection / term tied to the new loan balance.",
                          talk_track="A mortgage is a 30-year promise — term coverage makes sure your family keeps the home."),
  "mid_career":      dict(action="Book a lifetime-income planning session; lead with the peak-earning window.",
                          talk_track="These are your peak earning years — the best time to lock in lifetime income."),
  "near_retirement": dict(action="Offer an annuity + LTC review; lead with guaranteed lifetime income.",
                          talk_track="Let's turn your savings into income you can't outlive, and protect against care costs."),
  "college_age":     dict(action="Present a tax-advantaged college funding strategy now.",
                          talk_track="Tuition is coming fast — here's a tax-smart way to be ready without derailing retirement."),
}
```
Attach `lead["nba"] = NBA_MAP[p["event"]]`. Flows through `/api/run`. **No new endpoint.**

---

## 6. FEATURE 5 — Premium Pipeline projection + Appts/Week trend

### WHAT
Two lightweight charts rendered with pure SVG/canvas (no new libs):
1. A **right-column pipeline card** (`#pipelineCard`) — a horizontal bar breakdown of `est_premium` by bucket (HOT/WARM/NURTURE) so David sees where the dollars concentrate.
2. A **5th KPI card "Appts/Week Trend"** — a tiny sparkline of qualified-appts-per-week across recent runs (session history), with the current value large.

Together they make the KPI *visible and trending*, not a static number — the core business-observability promise.

### OUT-CLASSES
Agent CRMs (AgencyZoom, LeO) report activity *after the fact*; carrier tools project at portfolio scale, invisible to the agent. **Ours projects the individual advisor's forward pipeline and appointment velocity from transparent, receipted lead quality** — David's own KPI, live, in his language. EverQuote charges per lead and leaves ROI math to the agent ([EverQuote how-it-works](https://portersfiveforce.com/blogs/how-it-works/everquote)); we show the modeled pipeline value already attached to each scored lead.

### FRONTEND
- **KPI card (5th):** extend `renderKpis()` to add a 5th `.kpi` card "Appts/Week Trend" containing the current value + an inline SVG sparkline. Update `.kpis` grid to `repeat(5,1fr)` (and the `@media(max-width:880px)` rule to keep 2-up wrapping; on mobile the 5th simply wraps).
- **Session trend store:** in `app.js`, `let apptHistory = JSON.parse(localStorage.getItem('apptHistory')||'[]');` push `k.qualified_appts_per_week` on each run, cap to last 12, persist. Honest: clearly a *session/local* trend, labelled "this device, recent runs."
- **Sparkline fn:** `sparkline(values, w=120, h=30)` returns an inline `<svg>` polyline in teal — pure math, no dependency.
- **Pipeline card:** new `<div class="card" id="pipelineCard">` appended in the right column of `.grid2` (after `#signals`). Render fn `renderPipeline(leads)`:
  ```html
  <h3>📈 Premium Pipeline <span class="sec-title-meta" id="pipeTotal"></span></h3>
  <div class="body" style="padding:16px 18px">
    <div class="pipe-row"><span class="pipe-lbl">HOT</span><div class="pipe-track"><div class="pipe-fill hot" style="width:62%"></div></div><span class="pipe-val">$8,200</span></div>
    ... WARM, NURTURE ...
  </div>
  ```
- **CSS:**
  ```css
  .pipe-row{display:flex;align-items:center;gap:10px;margin:8px 0;font-size:12px}
  .pipe-lbl{width:64px;font-weight:700;color:var(--muted)}
  .pipe-track{flex:1;height:14px;background:#eef1f5;border-radius:7px;overflow:hidden}
  .pipe-fill{height:100%}.pipe-fill.hot{background:var(--hot)}.pipe-fill.warm{background:var(--gold)}.pipe-fill.nurture{background:var(--nurture)}
  .pipe-val{width:64px;text-align:right;font-family:'Fraunces';color:var(--navy)}
  .spark{display:block;margin-top:6px}
  ```

### BACKEND
Add a `pipeline_by_bucket` block to `kpi_summary()` in `scoring.py` so the bar widths come from the server, not invented client-side:
```python
def kpi_summary(leads):
    ...
    by_bucket = {"HOT":0,"WARM":0,"NURTURE":0}
    for l in leads: by_bucket[l["bucket"]] += l["est_premium"]
    return { ..., "pipeline_by_bucket": by_bucket }
```
The appts/week trend is **client-local session history** (localStorage) — explicitly labelled as such; we do not invent server-side history we don't have. **No new endpoint.**

---

## 7. FEATURE 6 — Territory / ZIP Opportunity Heatmap (Census-driven)

### WHAT
A **[Territory Map]** toolbar button opens a modal showing David's market (NY counties or a chosen state) shaded by **opportunity index** — a transparent blend of Census ACS median household income, median age fit, and family-formation indicators per area. Each shaded area shows its underlying public stats on hover/click. It answers "*where* should I prospect," complementing "*who*."

### OUT-CLASSES
LexisNexis "Life in the Market" hints at geographic readiness but is paid and opaque ([LexisNexis acquisition & retention](https://risk.lexisnexis.com/insurance/acquisition-retention)). Ours builds the territory index **live from free Census ACS data, with the formula and every input visible** — and labels each area's score with the exact median income / age it came from. David can defend the targeting to a compliance officer.

### FRONTEND
- **Trigger:** add `<button class="btn ghost" onclick="openTerritory()">🗺️ Territory Map</button>` to `.toolbar`.
- **Modal:** reuse the existing `.modal-bg/.modal` pattern (like `openReceipt`). Mount into `#modalMount`.
- **Visualization (no map lib):** a CSS-grid of county/area tiles, each tile background-shaded by opportunity index (teal scale), value + name inside; click a tile to expand its public stats. This keeps zero dependencies and stays on-brand. (If a lightweight choropleth is wanted later, US county TopoJSON can be added — but tiles ship tonight.)
- **Render fn:** `openTerritory()` → `await api('/api/territory')` → render tiles sorted by index desc.
- **CSS:**
  ```css
  .terr-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px;margin-top:12px}
  .terr-tile{border-radius:10px;padding:12px 10px;color:#fff;cursor:pointer;min-height:74px;display:flex;flex-direction:column;justify-content:space-between}
  .terr-name{font-size:12px;font-weight:600;line-height:1.2}
  .terr-idx{font-family:'Fraunces';font-size:20px}
  .terr-meta{font-size:11px;color:var(--muted);margin-top:10px}
  ```
  Tile background: `style="background:rgba(22,143,137,{0.25 + 0.7*normIndex})"` — darker teal = higher opportunity.

### BACKEND
**New endpoint** `GET /api/territory` (auth required, mirrors `_auth`). Lives in `server.py`, backed by a new function in `signals.py`.
- **Request:** optional `?state=36` (default NY). Auth header required.
- **Data source:** Census ACS county-level for the state:
  `https://api.census.gov/data/2023/acs/acs5?get=NAME,B19013_001E,B01002_001E,B11003_001E&for=county:*&in=state:36`
  (B19013 = median HH income, B01002 = median age, B11003 = family households w/ own children — the family-formation proxy.) Free, no key (ACS5 county is open; key optional).
- **Opportunity index (transparent):** normalize each metric to [0,1] across the returned counties, then
  `index = round(100 * (0.45*income_n + 0.25*age_fit_n + 0.30*family_n), 1)`
  where `age_fit_n` peaks near the prime planning window (35–55) via a simple triangular fit. Document the weights in the response so it's auditable.
- **Response shape:**
  ```jsonc
  {
    "state": "New York",
    "source": "U.S. Census ACS 2023 (5-yr), county level",
    "formula": "0.45*income + 0.25*age_fit + 0.30*family_households (each min-max normalized)",
    "areas": [
      { "name": "Westchester County, New York",
        "index": 92.4,
        "median_income": 112000,
        "median_age": 41.2,
        "family_households": 118000,
        "public": true }
    ],
    "meta": { "count": 62, "all_public": true, "fabricated": 0, "gathered_at": "..." }
  }
  ```
- **Graceful offline fallback:** if the Census call fails (meeting wifi), return a bundled `_sample_territory()` set of ~6 NY counties, each labelled `"live": false` / SAMPLE — same honest pattern as existing `_sample_*` fns. Never fabricate beyond clearly-labelled sample.
- **Governance:** every area carries `public:true`; `meta.fabricated:0`. Consistent with the gate.

---

## 8. FEATURE 7 — Export Call List (CSV + print-to-PDF)

### WHAT
An **[Export Call List]** toolbar button downloads the current ranked leads as a **CSV** (lead, score, bucket, product, why, est. premium, receipt id) and offers a **Print** view styled for PDF — so David walks into his day with a paper/【⌘P】call sheet, receipts referenced.

### OUT-CLASSES
EverQuote and CRMs lock leads inside their portal; ours lets David **take the intelligence with him**, with the receipt id printed next to each lead so the provenance travels too. Portable, honest, his to own (matches the V1 "portable offline HTML" ethos).

### FRONTEND
- **CSV:** client-side, no backend. `exportCSV()` builds a CSV string from `lastData.leads`, triggers a Blob download (`call-list-YYYYMMDD.csv`). Columns: `Rank,Lead,Score,Bucket,Product,Why,Est Premium,Receipt ID`.
- **PDF:** `printCallList()` opens a clean print window (or toggles a `.print-only` stylesheet) listing the brief + ranked leads with the David Leads logo + the footer compliance line; user uses browser Print → Save as PDF. Add `@media print` CSS to hide chrome and show only the call list.
- **Buttons:** add to `.toolbar`:
  `<button class="btn ghost" onclick="exportCSV()">⬇️ Export Call List (CSV)</button>`
  `<button class="btn ghost" onclick="printCallList()">🖨️ Print / PDF</button>`
- **CSS (`@media print`):** hide `header.top`, `.toolbar`, `#tickerBar`, `.grid2 > column`, `#bg3d`; show `#briefBar` + `#leadsWrap` full width in print colors.

### BACKEND
**No new endpoint required** for CSV/print (client-side over existing data). *Optional* server-side polished PDF can be deferred to a later iteration; tonight's build is client-side and zero-dependency.

---

## 9. FEATURE 8 — Live Intelligence Feed ticker

### WHAT
A thin, full-width **scrolling ticker** beneath the toolbar that streams the latest public signals as they're gathered: *"SEC EDGAR · officer comp change filed · BLS · avg weekly earnings +X% YoY · Census · NY median HH income $… · CDC · ~3.6M births/yr."* It makes the app feel *alive* and reinforces that the intelligence is freshly pulled from public sources.

### OUT-CLASSES
No agent-level competitor surfaces the **raw public signal stream** to the advisor — LexisNexis/Verisk hide it behind a score. Our ticker is the moat made ambient: David literally watches honest public data flow in. It's the "live business observability" promise turned into a heartbeat.

### FRONTEND
- **Placement:** `<div id="tickerBar" class="ticker hidden"></div>` directly after `.toolbar`, before `.grid2`.
- **Render fn:** `renderTicker(signals)` — concatenate each signal's `source` + short `detail` into a marquee track, duplicated once for seamless loop.
- **Markup:**
  ```html
  <div class="ticker-track">
    <span class="tick"><b>SEC EDGAR</b> · officer/comp change → income trigger</span>
    <span class="tick-sep">◆</span>
    <span class="tick"><b>BLS</b> · avg weekly earnings $1,210 (+4.2% YoY)</span> ...
  </div>
  ```
- **CSS:**
  ```css
  .ticker{background:var(--navy-800);color:#cdd9e6;border-radius:10px;overflow:hidden;white-space:nowrap;margin-bottom:18px;padding:8px 0;position:relative}
  .ticker-track{display:inline-block;animation:tick 28s linear infinite;will-change:transform}
  .ticker:hover .ticker-track{animation-play-state:paused}
  .tick{font-size:12px;margin:0 6px}.tick b{color:var(--gold-300)}
  .tick-sep{color:var(--teal-300);margin:0 4px}
  @keyframes tick{from{transform:translateX(0)}to{transform:translateX(-50%)}}
  ```
  (Track contains the signal list twice; translating -50% yields a seamless loop. Pauses on hover for readability — accessibility nicety.)

### BACKEND
**No new endpoint** — feeds directly from the existing `data.signals` array returned by `/api/run`. Each item already has `source`, `signal`, `detail`, `live`. Honest by construction.

---

## 10. Consolidated backend change summary

| Change | Module | New endpoint? | Public source |
|---|---|---|---|
| `brief.top_ids` block | `server.py` `run()` | no (extends `/api/run`) | — (derived) |
| `moments` per lead | `scoring.py` `MOMENTS_MAP` + `build_leads` | no (in `/api/run`) | labels of existing signals |
| `nba` per lead | `scoring.py` `NBA_MAP` + `build_leads` | no (in `/api/run`) | static, signal-grounded copy |
| `pipeline_by_bucket` | `scoring.py` `kpi_summary` | no (in `/api/run`) | derived from `est_premium` |
| Territory heatmap | `signals.py` `territory_index()` + `server.py` `GET /api/territory` | **yes** | Census ACS5 county |
| Ticker | — | no (in `/api/run` signals) | existing signals |
| Morning Brief / Why / Export / Trend | frontend only | no | — |

**Only ONE new backend endpoint** (`/api/territory`). Everything else extends the existing `/api/run` payload or is pure frontend. This keeps tonight's build tight and the receipt/governance model intact.

### Updated `/api/run` lead object (illustrative)
```jsonc
{
  "id": "L1",
  "name": "New-parent household (NY metro)",
  "event": "new_baby",
  "score": 88.4,
  "bucket": "HOT",
  "product": "Term / Whole Life (Family Coverage)",
  "why": "New dependents — coverage need spikes",
  "axes": { "life_event_strength": 0.95, "income_fit": 0.75, "age_window_fit": 0.85, "product_propensity": 0.90, "recency": 1.0 },
  "est_premium": 2304,
  "moments": [ {"source":"CDC Natality","label":"Birth uptick → new dependents"}, ... ],   // NEW
  "nba": { "action":"Call within 24h; offer a 15-min family-coverage review.",            // NEW
           "talk_track":"New baby changes everything — let's make sure they're protected." },
  "receipt_id": "rcpt_…",
  "receipt_signed": true
}
```

---

## 11. Frontend function map (for the frontend agent)

New functions to add to `app.js`:
- `renderBrief(leads)` — Morning Brief (Feature 1)
- `focusLead(id)` — scroll + expand a lead
- `toggleLeadDetail(id, forceOpen)` / `renderLeadDetail(id)` — expandable row (Feature 3)
- `renderMoments(lead)` → HTML string — Predictive Moments timeline (Feature 2)
- (NBA rendered inside `renderLeadDetail`) (Feature 4)
- `renderPipeline(leads)` + `sparkline(values)` + `apptHistory` localStorage — pipeline/trend (Feature 5)
- `openTerritory()` — territory modal (Feature 6)
- `exportCSV()` / `printCallList()` — export (Feature 7)
- `renderTicker(signals)` — ticker (Feature 8)

Wire-up: call `renderBrief`, `renderTicker`, `renderPipeline`, and push to `apptHistory` at the end of `runIntel()`'s success block, right after the existing `renderGov(...)` call. Modify `renderLeads()` to add expander cells + hidden detail rows. Extend `renderKpis()` for the 5th trend card. Add the four new toolbar buttons to `index.html`.

CSS: append all new rules to the single `<style>` block in `index.html`; everything uses existing `:root` tokens.

---

## 12. Prioritized build order (tonight)

Ordered for **maximum WOW per hour** and minimal risk, frontend (FE) / backend (BE) tagged. Items 1–4 are pure-frontend over data we already return → fastest, highest demo impact.

1. **Morning Brief banner** (FE only) — reframes the whole app; first thing David sees. *~30 min.* ⭐ highest impact.
2. **"Why this lead" expandable rows + axis bars** (FE only) — the transparency moat, tactile. *~45 min.*
3. **Predictive Moments timeline** (FE + tiny BE `MOMENTS_MAP`) — the RGA out-class, inside the expander from #2. *~30 min.*
4. **Next-Best-Action** (FE + tiny BE `NBA_MAP`) — turns scores into scripts; lives in the same expander. *~20 min.*
5. **Intelligence Feed ticker** (FE only) — ambient "alive" wow, low effort. *~20 min.*
6. **Premium Pipeline card + Appts/Week trend KPI** (FE + small `kpi_summary` extension) — makes the KPI trend visible. *~40 min.*
7. **Export Call List (CSV) + Print/PDF** (FE only) — portability, lets David leave with it. *~30 min.*
8. **Territory Heatmap** (FE + **new `/api/territory`** endpoint, Census ACS5) — biggest backend lift; do last so a network/Census hiccup never blocks the higher-impact items. Ship with the sample fallback so it always demos. *~60–75 min.*

**Definition of done per item:** renders with both Live and Sample (offline) runs; uses only existing CSS tokens; asserts nothing fabricated; passes the governance framing (public-only). The receipt modal and governance gate from V1 remain untouched and authoritative.

---

*Honest by design — public-data-only. Every V2 surface either computes transparently from public signals or is explicitly labelled illustrative/modeled. Visual identity preserved: navy #0a2540 · gold #c08f2f · teal #168f89 · Fraunces + Inter.*
