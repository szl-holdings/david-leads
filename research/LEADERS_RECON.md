# Field Leaders Recon — Insurance / Life Lead Intelligence

**Project:** David Leads (AI lead-intelligence app for David Abraham, NYL financial professional)
**Author:** Opus Dev Agent 1
**Date:** 2026-06-28
**Mission:** Study the leaders in life/insurance lead intelligence, capture their concrete features, UX, claims, and exploitable weaknesses, then synthesize a "steal-and-improve" feature roadmap built on transparent, public-data lead intelligence with cryptographic provenance.

> **Read this first — our angle.** Every leader below sells a *black box* (proprietary scores, non-FCRA models, opaque data lakes) to *carriers and marketing departments*, not to an individual agent. They never show their work, they share leads across competitors, and they cost real money. Our wedge: a transparent, public-data-only, individual-agent tool with a **signed receipt for every lead** ("here is the exact public record that triggered this, here's the URL, here's the date, here's the hash"). That is the one thing none of them can do, because their moat *is* opacity.

---

## 1. LexisNexis Risk Solutions — the 800-lb gorilla of life lead scoring

LexisNexis sells a tightly integrated **four-product life acquisition stack**, all explicitly **non-FCRA** (they cannot legally be used for eligibility decisions — only marketing/prioritization). All are sold to **carriers at "the point of marketing,"** not to individual agents.

### 1a. Lead Optimizer for Life
([LexisNexis — Lead Optimizer for Life](https://risk.lexisnexis.com/products/lead-optimizer-for-life))

- **What it does:** insurance-specific lead scoring at the point of marketing; segments prospects by **readiness, fit, and staying power**.
- **Signals / data:** built on **LexID®** (a persistent unique consumer identifier used to resolve/de-dupe identities); enriches each prospect with **demographics, household composition, home ownership, and asset details**.
- **Scores/models:** mortality fit + retention potential (pulls from the sibling Life Attrition Model and Life Target Evaluator).
- **UX concept:** a decision-support view that lets a carrier "see who's ready, who's a better fit, and who's likely to stay," remove noise early, and spot cross-sell/upsell.
- **Headline claims:** **LexID removes ~3–5% of volume** (fraud/duplicates) before it reaches the team; promises focus on "more profitable life insurance customers."
- **Weaknesses to exploit:** (1) Black box — no explanation of *why* a prospect scored high. (2) Built for carrier marketing teams buying large lists, not one agent working a territory. (3) Enrichment fields (home ownership, assets) are commercial-data inferences with no provenance and "may contain errors" (their own disclaimer). (4) Non-FCRA = the agent legally can't use it for eligibility, only outreach — same constraint we'd have, so no disadvantage to us.

### 1b. Life in the Market Insights — the bereavement trigger
([LexisNexis — Life in the Market Insights](https://risk.lexisnexis.com/products/life-in-the-market-insights))

- **The single sharpest signal in their stack:** flags when a prospect **experiences a loss within their immediate circle** — defined as **first-degree relatives, second-degree relatives, and associates at a shared address (partners, roommates)**.
- **Why it works:** their cited stat — **"1 in 4 life insurance purchasers buy coverage shortly after a loss in their network"** (LIMRA 2017 U.S. Individual Life Insurance Consumer Survey).
- **Positioning:** "non-FCRA indicator" that adds **timing context** so teams "route and prioritize with more empathy and precision."
- **UX language:** *Spot readiness early → Focus your effort → Engage more thoughtfully → Support long-term value.*
- **Sibling product Market Magnifier** segments using **3,200+ proprietary and third-party data sources**.
- **Weaknesses to exploit:** (1) The "loss in network" signal is derived from opaque commercial death/obituary linkage — no source shown to the agent. (2) Sold to carriers, never surfaced as "here's the obituary, here's the relationship." We can reproduce a large share of this from **public obituary data + public records linkage and show the receipt.** (3) Empathy is their pitch but their delivery is a list dump — an agent gets a name, not context.

### 1c. Life Target Evaluator — individual mortality-risk deciles
([LexisNexis — Life Target Evaluator](https://risk.lexisnexis.com/products/life-target-evaluator))

- **What it does:** early, individual-level **mortality risk profile** *before an application begins*.
- **Model:** non-FCRA model; groups prospects into **10 deciles** based on an **A/E ratio** (Actual/Expected mortality vs. similar individuals).
- **Headline metric:** "the three riskiest deciles have A/E ratios > 1 and together contain **more than 50% of consumers with higher-than-expected mortality**" (LexisNexis internal study, 2025).
- **UX language:** *See mortality risk earlier → Reduce waste early → Prioritize the prospects who fit → Strengthen long-term performance.*
- **Weaknesses to exploit:** (1) This is a *carrier risk-screening* tool dressed as marketing — it tells a carrier to *avoid* high-mortality prospects, which is the opposite of an agent's job (an agent wants to *serve* everyone). (2) Pure black box deciles; agent never knows why. (3) Built around protecting the carrier's loss ratio, not growing the agent's book.

### 1d. Life Attrition Model — early-lapse / retention deciles
([LexisNexis — Life Attrition Model](https://risk.lexisnexis.com/products/life-attrition-model))

- **What it does:** predicts **early-lapse / retention potential** at the point of marketing, powered by **individual-level public records data**.
- **Model:** **10 deciles** by retention potential.
- **Headline metrics:** **58% of first-two-year lapses come from deciles 8–10**; consumers in **decile 10 lapse >4x as often as decile 1** (LexisNexis internal study, 2025).
- **Weaknesses to exploit:** (1) Black box deciles again. (2) Built on "individual-level public records data" — *exactly our raw material*, but they hide which records. We can use the same public records and **disclose the source**.

**LexisNexis stack-wide takeaways for us:**
- Their entire stack is **carrier-grade and opaque**. The four scores (readiness, fit/mortality, staying power/attrition, timing/bereavement) are a great *feature checklist* — we should reproduce the *concepts* (readiness, fit, retention, life-event timing) but invert the delivery: **individual agent, full transparency, signed source receipts**.
- Their best idea is the **bereavement / loss-in-network trigger**. It's reproducible from public obituary + relationship data.

---

## 2. Deloitte PredictRisk — health-intelligence lead gen & qualification
([Deloitte — PredictRisk overview](https://www2.deloitte.com/us/en/pages/consulting/topics/strategic-health-intelligence-targeted-lead-generation-tools-predictrisk-analysis.html)) · ([Deloitte life-insurance case study PDF](https://www2.deloitte.com/content/dam/Deloitte/us/Documents/process-and-operations/us-predictrisk-case-study-2-life-insurance.pdf))

- **What it is:** Deloitte's targeted **lead-generation and qualification platform** using **health intelligence, lifestyle analytics, and customer insights** to qualify life leads and accelerate underwriting.
- **Scale:** **scoring of 230M+ US adults**; analytics on **25+ terabytes of consumer lifestyle / purchasing data**; **dozens of disease/medical condition models** and **100s of algorithms**.
- **Specific outputs/signals:** **policy face amount needed**, **likelihood to qualify**, **likelihood to buy**, **best-fit product**, segmentation by **mortality + morbidity risk**.
- **Data sources:** application data, motor vehicle reports, underwriting process data, plus **non-traditional lifestyle insights & health-risk inference** (avoids blood/urine).
- **Headline metrics:** **+30% sales close rate** vs. traditional lead gen; **$15M additional annual revenue** for one client; **+10% individual life sales in year one**; **−30% not-taken rate**; reduced underwriting requirements for **40% of applicants**; cut time-to-issue from **30+ days to 1 day**. Context stats they cite: **48% of Americans carry no life insurance**, and the insured are **underinsured by ~$200K on average**.
- **Weaknesses to exploit:** (1) **Health/disease inference on individuals** is privacy-toxic and increasingly regulator-targeted (algorithmic discrimination, AI-bias rules). We deliberately avoid health inference — a *compliance & trust* advantage. (2) Enterprise consulting engagement — not a self-serve agent tool; no individual NYL agent will ever touch it. (3) Patented "secret sauce" algorithms = maximum opacity. (4) Their best *consumer-facing* idea is the **coverage-gap quantification** ("underinsured by $200K") and **"face amount needed"** — both fully reproducible from public BLS/Census income + household data with full math shown.

---

## 3. Verisk — risk intelligence & (former) marketing solutions
([Verisk — blending human + AI underwriting](https://www.verisk.com/blog/blending-human-insight-and-ai-to-improve-underwriting/)) · ([Verisk Marketing Solutions — Real-Time Decisions](https://www.verisk.com/company/newsroom/verisk-marketing-solutions-launches-real-time-decisions-product-suite/)) · ([Verisk sells Marketing Solutions to ActiveProspect, Jan 2026](https://www.verisk.com/company/newsroom/verisk-announces-sale-of-its-marketing-solutions-business-to-activeprospect/))

- **What it is/was:** Verisk's **Marketing Solutions** ran a **Real-Time Decisions** suite — **inbound identity resolution, behavioral signals, TCPA/consent protection**, and lead-scoring at the point of a web form fill, with a **Tableau dashboard** for buyers. Verisk **sold the Marketing Solutions business to ActiveProspect in Jan 2026**, signaling the lead-marketing layer is being decoupled from its core risk franchise.
- **Core franchise today:** underwriting & risk intelligence — augmented/automated underwriting, fraud (FAST life platform), and a 2025–2026 push into **generative-AI underwriting assistants**, including a **Verisk Underwriting Intelligence connector inside Anthropic's Claude** ([GlobeNewswire, May 2026](https://www.globenewswire.com/news-release/2026/05/05/3288003/0/en/verisk-brings-its-trusted-analytics-and-generative-ai-capabilities-directly-into-anthropic-s-claude.html)).
- **Useful concepts:** **real-time identity resolution at form-fill**, **consent/TCPA compliance baked into the lead record**, and a **dashboard buyers actually look at** (Tableau).
- **Weaknesses to exploit:** (1) Pure carrier/enterprise tooling; nothing for an individual agent. (2) Just divested the marketing-data layer — fragmented. (3) Opaque. (4) Their *good idea worth stealing* is **compliance metadata attached to every lead (consent timestamp, TCPA status)** — which maps perfectly to our signed-receipt provenance concept.

---

## 4. RGA — "Predictive Moments" & behavioral/contextual digital signals
([RGA — The Power of Predictive Moments (whitepaper PDF)](https://www.rgare.com/docs/default-source/-/predictive-moments-whitepaperv3.pdf?sfvrsn=fb8d64cc_2)) · ([RGA — behavioral & contextual signals from digital distribution](https://www.rgare.com/knowledge-center/article/leveraging-behavioral-and-contextual-signals-from-digital-distribution-and-underwriting)) · ([RGA — optimizing the customer journey](https://www.rgare.com/knowledge-center/article/optimizing-the-customer-journey-the-keys-to-succeeding-in-digital-distribution-for-life-insurance))

- **The core idea — "Predictive Moments":** the convergence of a **life event** *and* an **immediate context** that makes risk/responsibility *salient* (top of mind). Their research-validated triggers:
  - **Recent house buyer / mortgage** (creates an objective need).
  - **Becoming a parent / having a child under 18.**
  - **Bereavement — personally OR knowing someone recently bereaved** (raises receptiveness *even when objective risk is unchanged*).
- **Key finding:** people who experienced these events were significantly more likely to *own* a policy AND to have *recently changed* a policy — and "even when a predictive moment exists, marketers still must prompt with persuasive messaging." I.e., **timing creates the window; messaging closes it.**
- **Behavioral/contextual signals (digital distribution):** time-on-page, clicks, form-completion time, device type, even keystroke/mouse cadence — used to **predict sales conversion and early lapse** and to detect non-disclosure.
- **Behavioral-science UX results:** simplified language + a **needs calculator** + interactive tools + video raised comprehension **up to 28%** ([RGA — value of improved comprehension](https://www.rgare.com/knowledge-center/article/behavioral-science-and-life-insurance--the-value-of-improved-comprehension-in-the-customer-journey)); "layering" (top-line info + deeper detail on click), evocative imagery, "replay their situation to make the insurance gap real," and asking questions (e.g., "if your income stops, can you cover the mortgage?") as nudges.
- **Weaknesses to exploit:** (1) RGA is a *reinsurer / thought-leader*, not a product an agent can buy — this is a **free playbook** we can implement directly. (2) Their digital-behavior signals require owning the consumer's web session — we can't and shouldn't, but their **life-event taxonomy (mortgage, new child, bereavement)** is fully reproducible from public data. (3) Their own conclusion — "timing alone isn't enough, you must message persuasively" — is our cue to pair each public-data trigger with a **ready-to-send, NYL-compliant talk track.**

---

## 5. Lead Marketplaces — EverQuote, SmartFinancial, MediaAlpha

These are the incumbents an NYL agent actually *pays today* — and their structural flaws are our biggest opportunity.

### EverQuote
([EverQuote Pro — lead gen playbook](https://learn.everquote.com/insurance-lead-generation)) · ([EverQuote — shared vs exclusive leads](https://learn.everquote.com/exclusive-auto-insurance-leads-for-agents))
- **Model:** *lead generator* (sources its own traffic via ads/SEM), sells **real-time** leads; shared leads capped at **max 3 agents, never 2 from the same carrier**; also sells **exclusive leads** and **inbound call transfers**.
- **Price:** roughly **$15–$45 per lead** depending on vertical/risk; life/Medicare priced higher.
- **Economics:** key metric is **Variable Marketing Margin (VMM)** — the spread between what agents pay and EverQuote's ad cost.

### SmartFinancial
([InsureLeads — SmartFinancial pricing 2026](https://www.getinsureleads.com/blog/smartfinancial-insurance-leads-pricing)) · ([Insurance Leads Guide — SmartFinancial review](https://insuranceleadsguide.com/review-smartfinancialagents/))
- **Model:** lead aggregator/marketplace; **prepaid credit system**; filters by **geography, product line, exclusivity**.
- **Distribution:** shared leads sold a **max of 3 times** (at most one per carrier); exclusive available at premium.
- **Price:** web leads ~**$5–$25** (life higher due to policy value); call transfers **$15–$35**; dedicated account manager + rewards/free-lead program.

### MediaAlpha
([MediaAlpha for Agents](https://mediaalpha.com/referred-agents/)) · ([MediaAlpha — the bidded auction model](https://mediaalpha.com/article/bidded-is-better-mediaalpha-insurance-lead-auction/)) · ([MediaAlpha — lead quality](https://mediaalpha.com/article/lead-quality/))
- **Model:** **real-time transparent auction** — agents set the **exact price** they'll pay per consumer type; price stays fixed until changed; **daily lead caps** prevent overspend.
- **Differentiator (their pitch):** **transparency + right-price bidding + custom targeting/pricing tools**; sources from **owned-and-operated shopping sites** (e.g., QuoteLab) for higher intent.
- **Powers the Farmers Agents Lead Marketplace** with a custom bidding model ([MediaAlpha — Farmers Agents](https://mediaalpha.com/farmersagents/)).

**Shared-lead reality (the wound to press on):** a shared lead is a consumer who filled a quote form that is **distributed to multiple matching agents who are each billed**; caps vary — **EverQuote max 3, QuoteWizard max 4, others 4–6** ([Maverick Marketing — how shared leads work](https://www.maverickmarketingllc.com/resources/exclusive-vs-shared-insurance-leads), [Insurance Business / industry analysis](https://dojocases.netlify.app)). By the time an agent calls, the consumer "filled out 3 different forms and is being contacted by a dozen agents" — **lead-quality complaints are constant.**

**Marketplace weaknesses to exploit:**
1. **Shared leads = a race to the phone** against up to a dozen competitors. Our public-data leads are **not for sale to anyone else** — exclusive by construction.
2. **Pay-per-lead with no provenance** — the agent has no idea why this consumer was surfaced or whether they're real. We attach a **signed source receipt**.
3. **Low intent / form-fill fatigue** — consumers "fill out any form that promises savings." Our triggers are *real public events* (new business filing, property purchase, obituary), not a discount-shopping form.
4. **Recurring cost with poor ROI** — agents constantly test filters and burn budget. Our public-data sourcing has **near-zero marginal cost**, so we can offer flat/transparent pricing.
5. **No territory ownership** — anyone can buy into any ZIP. We can give David **exclusive territory targeting** over public-data signals.

---

## 6. Agent Tools — LeO, AgencyZoom, Salesforce Insurance Cloud

These are the closest analogs to *what we're building* (an agent-facing tool), so their UX is the most directly stealable.

### LeO — "Personal AI Sales Assistant for Insurance Agents"
([LeO — meetleo.com](https://www.meetleo.com/lp/facebook-call)) · ([Insurance Business — LeO product showcase](https://www.insurancebusinessmag.com/us/news/technology/product-showcase-leos-sales-assistant-tool-403744.aspx)) · ([SoftwareOne — LeO listing](https://platform.softwareone.com/product/leo/PCP-5249-1984))
- **What it is:** AI prospecting assistant for **commercial** insurance agents (P&C + benefits). Access to **32–40M+ businesses**, all states.
- **Killer signal — X-Dates:** filter prospects by **policy renewal/expiration dates** ("coverages renewing in X months"), the single most actionable B2B insurance trigger. Plus **Workers' Comp, DOT, OSHA, Form 5500 (pension/benefits), fidelity bonds, commercial auto.**
- **Data depth:** **150+ filter criteria** (location, industry, company size, compliance, insurance intel, x-dates, risk indicators); key contacts (Owner/CEO/CFO/HR/5500 signatory) with email, phone, LinkedIn; **AI recommendations**; CRM/AMS integration. **Conversational/voice query interface** ("Siri for prospecting"). Entry pricing **~$57/user/mo**.
- **Weaknesses to exploit:** (1) **Commercial-only** — there is no strong *individual life / personal-lines* equivalent doing public-data triggers. That's a wide-open lane for David (life). (2) Much of LeO's gold (5500, DOT, OSHA, x-dates) **is public/regulatory data** — proving the model that *public data + filters + contacts = a sellable agent tool.* For life, the equivalent public datasets are different (Census, CDC, obituaries, county records, IRS migration) and **nobody has packaged them for a life agent yet.**
- **Steal directly:** the **X-Date concept** (event-dated, time-to-act prospecting) and the **conversational query UX**.

### AgencyZoom (Vertafore)
([AgencyZoom](https://www.agencyzoom.com)) · ([AgencyZoom — managing leads/pipeline & SmartCycle](http://support.agencyzoom.com/en/articles/5669585-managing-leads)) · ([Sonant — AgencyZoom review 2026](https://www.sonant.ai/blog/agencyzoom-alternative-review)) · ([AgencyZoom pricing](https://www.agencyzoom.com/pricing))
- **What it is:** insurance sales-automation CRM (**6,000+ agencies, 50,000+ users**); $99/mo single-location to $129/mo multi.
- **Stealable UX patterns:**
  - **Click-and-drag Kanban pipeline** (New → Contacted → Quoted → Sold) with per-producer views.
  - **SmartCycle** — the standout: drop an unsold lead into a holding bucket tied to a **recycle event** (an accident/claim "falling off soon," or an **upcoming X-Date**); the system **auto-resurfaces the lead at the perfect future date** with all prior notes. *This is a time-machine for leads.*
  - **Shot Clocks** — timed nudges (down to 15-min/1-hr) that auto-advance or flag stalled leads.
  - **Goal dashboards / team scoreboards**, automated **Google Review** requests after each sale, **comp/commission calculator**, mobile app.
  - Ecosystem add-ons show where the value is going: **DONNA** pushes **30-day-before-renewal cross-sell insights** into AgencyZoom; **EffiZoom CrossSell Intelligence** runs a weekly **"Gather → Score → Execute → Learn"** loop that **scores the whole book and dispatches 15–30 cross-sell opportunities every Monday with call scripts** ([EffiZoom](https://effizoom.com/pricing)).
- **Weaknesses to exploit:** (1) **It's a CRM, not a lead source** — it organizes leads you already paid for; it doesn't *generate* intelligence. (2) Built primarily for **personal-lines P&C**, thin on life. (3) AI is shallow/bolt-on. (4) No public-data sourcing, no provenance.

### Salesforce Insurance / Financial Services Cloud (Agentforce FSC)
([Salesforce — Work with Insurance for FSC](https://help.salesforce.com/s/articleView?id=ind.fsc_insurance_admin_work_with_insurance.htm&language=en_US&type=5)) · ([Salesforce — Get Started with FSC for Insurance](https://help.salesforce.com/s/articleView?id=ind.fsc_admin_insurance_landing.htm&language=en_US&type=5)) · ([Salesforce — What is FSC](https://www.salesforce.com/financial-services/cloud/guide/?bc=OTH))
- **What it is:** enterprise CRM with an **Insurance data model**; now branded **Agentforce Financial Services**.
- **Stealable UX patterns:**
  - **Events and Milestones component** — surfaces **life events on a person/contact record** (and business milestones on company records); admins define event types, icons, hover details, and **contextual actions** per event.
  - **Action Plan templates** tied to **Person Life Event / Milestone / Policy / Claim** objects — capture repeatable tasks and **auto-assign owners + deadlines** when an event fires.
  - **Insurance Agent Console home page** — customizable **performance metrics + report charts**; **360° customer / household view**; **FlexCard Policy 360** (all policies for a person regardless of role).
  - **Relationship/household modeling** (one of FSC's signature concepts for life/wealth).
- **Weaknesses to exploit:** (1) **Enterprise-heavy, expensive, admin-config-required** — totally wrong fit for one NYL agent. (2) Life events must be **manually entered or fed in** — Salesforce doesn't *detect* them from the outside world. *We do.* (3) No native public-data lead generation; no provenance.

---

## 7. SYNTHESIS — Top 10 features worth stealing & how we make them OURS

Each is concrete and buildable on **public, free data** (SEC, BLS, Census, CDC, FRED, BEA, IRS county-to-county migration, USPS, county recorder/assessor, obituaries) with **cryptographic provenance**.

| # | Idea we're stealing (and from whom) | How we make it better / ours |
|---|---|---|
| 1 | **Life-event triggers** (LexisNexis "Life in the Market Insights"; RGA "Predictive Moments": bereavement, new home, new child) | Reconstruct from **public obituaries + county property deeds + public records linkage**. Every trigger ships with a **signed receipt**: the source URL, capture date, and a SHA-256 hash — David can *show the client where it came from*. No black box. |
| 2 | **Readiness / Fit / Staying-power scoring** (LexisNexis Lead Optimizer's 3-axis model) | A **transparent, explainable score** where each axis is a sum of *named, sourced public signals* with weights David can see and adjust. "Glass-box" instead of black-box deciles. |
| 3 | **Mortality / risk deciles** (LexisNexis Life Target Evaluator) | **Invert it for good:** instead of a carrier avoiding high-mortality people, surface **coverage-gap urgency** from public actuarial data (CDC life tables by age/county) — "this household's protection need is highest now," shown with the math. |
| 4 | **Coverage-gap / "face amount needed" quantification** (Deloitte PredictRisk: "$200K underinsured") | A **public-data needs calculator**: BLS/Census household income + CDC dependents + FRED mortgage-rate data → an estimated protection gap *with every input cited.* Doubles as the client-facing nudge RGA proved works (+28% comprehension). |
| 5 | **X-Dates / renewal-dated prospecting** (LeO) | For life, build the equivalent from **public time-anchored events**: mortgage recording dates (term-need windows), business formation filings, age-band birthdays (term conversion / RMD ages), IRS migration into territory. "Time-to-act" countdowns on each lead. |
| 6 | **SmartCycle lead time-machine** (AgencyZoom) | Auto-resurface a lead **when a future public event is predicted to fire** (mortgage anniversary, child reaching college age, business renewal) — not just a manual date. The recycle trigger is itself a sourced public signal. |
| 7 | **Weekly auto-dispatched opportunity list + call scripts** (EffiZoom "Gather→Score→Execute→Learn"; DONNA 30-day insights) | A **Daily Morning Brief**: every morning David gets the day's top territory opportunities, each with a sourced trigger and a **ready-to-send NYL-compliant talk track** (RGA's lesson: timing needs messaging). |
| 8 | **Events & Milestones + Action Plans** (Salesforce FSC) | Same UX (life-event timeline on each contact, contextual one-click actions) but **events arrive automatically from public data**, not hand-entered — and each event carries its provenance receipt. |
| 9 | **Consent / TCPA compliance metadata on every lead** (Verisk Real-Time Decisions) | Because we use **public records only (non-FCRA, no consumer-report use)**, every lead ships with a **compliance card**: data source classification, FCRA status, and "permitted use = outreach only." Turns compliance from friction into a trust badge. |
| 10 | **Transparent right-price / territory model** (MediaAlpha auction; vs. shared-lead marketplaces) | **Exclusive by construction** — public-data leads aren't resold to a dozen competitors. Give David **owned territory targeting** (his ZIPs/counties) with flat, transparent economics instead of per-lead bidding wars. |

### Cross-cutting design principles we should bake in
- **Glass-box everything** — every score decomposes into named, sourced signals (the opposite of all six leaders' deciles/algorithms).
- **Provenance-first** — signed receipt (source URL + date + hash) on every lead and every signal. This is the moat.
- **Public-data-only / non-FCRA-clean** — turns the leaders' biggest legal constraint into our marketing message ("we never touch credit, health, or consumer-report data").
- **Agent-grade, not carrier-grade** — built for one NYL professional working a territory, not a marketing department buying lists.
- **Timing + talk track together** — RGA proved the moment alone doesn't sell; pair every trigger with a compliant message.

---

## 8. The single "WOW" feature to out-class them all

### 🏆 The Provenance-Verified Life-Event Radar with a Signed "Why This Lead" Receipt

A live, territory-scoped radar that detects **real public life events** as they happen — a **property deed recorded** (new homeowner → mortgage protection need), an **obituary naming surviving family** (RGA/LexisNexis-validated bereavement window), a **new business registration** (key-person/buy-sell need), an **IRS-migration inflow** into David's county — and for **each surfaced lead it issues a cryptographically signed "Why This Lead" receipt**: the exact public source, the URL, the capture timestamp, and a SHA-256 hash, plus the named signals that drove the score and a ready-to-send NYL-compliant talk track.

**Why it out-classes all six leaders simultaneously:**
- **LexisNexis / Deloitte / Verisk** sell *opaque* scores to carriers — we hand the *agent* the receipt and let him show the client. Their moat is secrecy; ours is the proof.
- **RGA** proved bereavement + new-home + new-child are the highest-converting moments but only published a whitepaper — **we operationalize it** from public data with provenance.
- **The marketplaces (EverQuote/SmartFinancial/MediaAlpha)** sell the *same* low-intent form-fill to a dozen agents — our radar surfaces **exclusive, event-real, non-resold** prospects.
- **LeO / AgencyZoom / Salesforce** organize or query leads but never *generate verified life-event intelligence with a chain of custody* — and none serve the **individual life agent**.

It is, in one line: **"a Bloomberg terminal for life-event leads, where every alert comes with a signed citation."** Nobody in this field can copy it without dismantling the opacity that is their entire business model.

---

### Sources index (primary)
- LexisNexis Lead Optimizer for Life — https://risk.lexisnexis.com/products/lead-optimizer-for-life
- LexisNexis Life in the Market Insights — https://risk.lexisnexis.com/products/life-in-the-market-insights
- LexisNexis Life Target Evaluator — https://risk.lexisnexis.com/products/life-target-evaluator
- LexisNexis Life Attrition Model — https://risk.lexisnexis.com/products/life-attrition-model
- Deloitte PredictRisk overview — https://www2.deloitte.com/us/en/pages/consulting/topics/strategic-health-intelligence-targeted-lead-generation-tools-predictrisk-analysis.html
- Deloitte PredictRisk life case study (PDF) — https://www2.deloitte.com/content/dam/Deloitte/us/Documents/process-and-operations/us-predictrisk-case-study-2-life-insurance.pdf
- Verisk Real-Time Decisions launch — https://www.verisk.com/company/newsroom/verisk-marketing-solutions-launches-real-time-decisions-product-suite/
- Verisk sells Marketing Solutions to ActiveProspect — https://www.verisk.com/company/newsroom/verisk-announces-sale-of-its-marketing-solutions-business-to-activeprospect/
- RGA Predictive Moments whitepaper (PDF) — https://www.rgare.com/docs/default-source/-/predictive-moments-whitepaperv3.pdf?sfvrsn=fb8d64cc_2
- RGA behavioral/contextual signals — https://www.rgare.com/knowledge-center/article/leveraging-behavioral-and-contextual-signals-from-digital-distribution-and-underwriting
- RGA comprehension / behavioral science — https://www.rgare.com/knowledge-center/article/behavioral-science-and-life-insurance--the-value-of-improved-comprehension-in-the-customer-journey
- EverQuote lead-gen playbook — https://learn.everquote.com/insurance-lead-generation
- SmartFinancial pricing 2026 — https://www.getinsureleads.com/blog/smartfinancial-insurance-leads-pricing
- MediaAlpha bidded auction — https://mediaalpha.com/article/bidded-is-better-mediaalpha-insurance-lead-auction/
- Shared vs exclusive lead mechanics — https://www.maverickmarketingllc.com/resources/exclusive-vs-shared-insurance-leads
- LeO — https://www.meetleo.com/lp/facebook-call
- AgencyZoom — https://www.agencyzoom.com and SmartCycle docs https://support.agencyzoom.com/en/articles/5669585-managing-leads
- EffiZoom CrossSell Intelligence — https://effizoom.com/pricing
- Salesforce FSC for Insurance — https://help.salesforce.com/s/articleView?id=ind.fsc_insurance_admin_work_with_insurance.htm&language=en_US&type=5
