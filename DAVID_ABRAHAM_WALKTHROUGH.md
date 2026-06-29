# David Leads — Client Walkthrough (for the meeting with David Abraham, New York Life)

This is the narrative script for the **real, live application** at
**https://szlholdings-david-leads.hf.space** — not a simulation.
Everything David sees is computed live from public data, and every lead/brief carries a
cryptographically verifiable receipt. Honest by design: public-data only, no fabricated signals,
estimates clearly labeled.

**Login (live, in front of David):**
- Username: `david`
- Password: `David2026!`
- Secure access key: `DAVID-2026-SECURE-DEMO`

---

## 0. One-sentence takeaway (say this first or last)
"David — this finds the people in your territory who just had a life event that creates a real
insurance need, ranks them by fit and readiness, hands you a signed, citation-backed brief and a
ready talk track, and every single claim is verifiable. It's prospecting you can defend to compliance."

---

## 1. The private console (login)
- Open the URL, enter the three credentials above. It's a private, login-gated console — not a
  public website. Frame it as "your own intelligence desk."
- Note the footer: "public, aggregate data only … never private PII … every lead carries a
  tamper-evident, compliance-grade receipt. Honest by design."

## 2. Morning Brief + KPIs (top of the dashboard)
Point to the KPI cards:
- **Qualified Appts / Week** — modeled from lead quality (HOT×0.70 + WARM×0.35).
- **HOT Leads** — score ≥ 80, ready to engage now.
- **Pipeline Premium** — illustrative annualized estimate across leads (say "illustrative" out loud).
- **Avg Λ-Score** and **Appts/Week trend**.
Say: "This is your morning brief — where to spend today, before you've made a single call."

## 3. Run Live Public-Data Intelligence
- Click **Run Live Public-Data Intelligence**. It pulls live public signals (SEC EDGAR, BLS wages,
  U.S. Census ACS, CDC natality, and 13-state open-data portals — business formations, licenses,
  deeds, permits).
- Then click **Territory Pulse** to show the live 13-state Atlantic seaboard map: states light up by
  activity (CT/DE surging with real counts in the hundreds-of-thousands to millions), with
  Massachusetts/New Hampshire/Maine shown honestly as data gaps — "we don't pretend to have data we
  don't have."

## 4. Ranked Leads (the core)
Walk down the ranked list. For each lead:
- **HOT / WARM / NURTURE** badge + the Λ-score, matched **NYL product**, and an **estimated annual
  premium** (illustrative).
- **Urgency chip** — ACT NOW (within 48h of the trigger), WARM, or COLD. (Research shows ~14×
  conversion when you reach someone inside the life-event window.)
- **Wealth tier** (Mass / Mass-Affluent / Affluent / HNW) — estimated from public proxies
  (assessed property value, Census income, insider status). Say "estimated from public records."
- **Lapse-risk decile** and **receptivity** — how likely to stick, and how ready to talk now.
- **Likely coverage gap** chip — e.g. "education-funding gap" for a new-parent household.

Expand a lead (▸) to show:
- **Why this lead** — the scoring factors, in plain English.
- **Predictive Moments** — the timeline of public sources that surfaced them (each a real citation).
- **Next Best Action** — the concrete move + a ready talk track David can use verbatim.

## 5. The Signed 4-Part Brief (the boardroom moment)
Click **Signed Brief** on the top lead. Read it aloud — it has four parts:
1. **Priority** — why this lead, now.
2. **Why now** — the time-sensitive trigger + freshness.
3. **Opening line** — three ranked outreach angles (e.g. Family Coverage / Income Replacement /
   College Head-Start), each copyable.
4. **Sensitivity** — where to tread carefully.
Each part shows a green ✓ formula badge (LambdaMonotonicity, FalsePosition, SummationInvariant) —
these are **witness-signed by a math engine, not an AI guess**. Then click **Verify signed brief**.

## 6. Verify Receipt (the moat)
Click **Verify Receipt** on any lead → a **VERIFIED** modal with the five checks:
- Payload hash re-derives (tamper-evident)
- All signals are public data
- Zero fabricated signals (honest by design)
- Chained to the prior receipt
- (When the cosign key is set) ECDSA-P256 signature verifies
Say: "This is the part no competitor has — you can prove to compliance exactly where every claim
came from, and that nothing was made up."

## 7. Open the Black Box (the Λ score)
Click **Open the Black Box**. Show the model card:
- The transparent Λ formula (weighted geometric mean — one weak axis pulls the whole score down).
- Time-decay (freshness erodes honestly), the receptivity score, the lapse decile (advisory, NOT FCRA).
- Provenance: advisory; Λ uniqueness is **Conjecture 1 (open)**; DOI 10.5281/zenodo.20434308; cites
  Aczél 1957, Guo 2017, McAllester 1999.
Say: "There's no hidden black box — the methodology is published and citable."

## 8. Territory Map + Export + Push to CRM
- **Territory Map / Pulse** — live NY-metro + seaboard coverage from Census + open data.
- **Export Call List** — downloads a CSV of the ranked list (with scores, triggers, gaps, receipt
  hashes) — David can work it in his own tools.
- **Push to CRM** — one-click webhook to send enriched, receipted leads into AgencyZoom / Salesforce
  FSC / HubSpot.

## 9. Where this goes (future, say only if asked)
- More states + deeper county coverage; SEC Form 4 liquidity-event triggers; IRS-990 wealth signals;
  a producer benchmarking dashboard (your conversion funnel by trigger type); best-fit lead routing
  across a team of agents.
Frame as roadmap, not promises.

---

## Honesty guardrails (do not skip — this is the differentiator)
- Say "illustrative" for premium/pipeline numbers; "estimated from public records" for wealth tier;
  "advisory, not a credit/FCRA decision" for lapse risk.
- If a state shows [SAMPLE] or GAP, say so — that honesty is the selling point.
- Never imply we use private PII. We don't.
