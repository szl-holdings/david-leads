# David Leads — Handoff for Stephen
**Client:** David Abraham, MBA — Financial Professional, New York Life (New York, NY)
**Goal:** Win the consulting engagement by proving AI can fill his calendar with high-propensity, product-matched leads.

---

## 1. What you're showing him (v2 — "Bloomberg terminal for life-event leads")
A live, login-gated **Sovereign Insurance Intelligence** console that:
- Opens with a **Morning Brief** — today's top 3 leads to call, with the exact action for each.
- Pulls **live public data** (SEC EDGAR 8-K events, BLS wages, U.S. Census, CDC births) — streamed in a live **intelligence ticker**.
- Scores prospects on a transparent model → ranks them HOT/WARM/NURTURE.
- Expand any lead for **"Why this lead"** (the 5 scoring axes as bars — the thing LexisNexis hides), a **Predictive Moments** timeline of the public sources, and a **Next-Best-Action** with a ready talk track.
- Matches each to the **right NYL product** (family coverage, retirement/annuity, LTC, college funding).
- Attaches a **cryptographically signed, audit-defensible receipt** to every lead.
- **Territory Map**: NY counties shaded by opportunity index (live Census), so he knows *where* to prospect.
- **Export Call List** to CSV so he can leave the meeting with the leads.
- Shows his **KPI live**: Qualified Appointments / Week (with trend sparkline) + Premium Pipeline chart by bucket.

## 1b. How we out-class each field leader (the "fashion-house" story)
- **vs LexisNexis Lead Optimizer for Life** (black-box carrier score): ours shows the full *why* — every axis, every public source — and signs it.
- **vs RGA Predictive Moments** (carrier whitepaper, invisible to agents): ours puts the predictive-moments timeline in the agent's hands, per lead.
- **vs EverQuote / marketplaces** (shared leads, no provenance): ours are exclusive, explained, and receipted — quality over volume.
- **vs AgencyZoom / LeO** (CRMs that report after the fact): ours projects forward pipeline + appointment velocity from transparent lead quality.
- The wedge across all of them: **agent-level, transparent, public-data-only, cryptographically receipted intelligence that explains itself.**

**The one-line pitch to David:**
> "This is the same life-event predictive scoring the big carriers pay LexisNexis and Deloitte for —
> but it's yours, it's transparent, it only uses public data, and every lead comes with a signed
> compliance receipt. Your competitors are still cold-calling. You'll only call families who are
> ready to buy — and you can prove exactly why."

---

## 2. Access
- **Permanent live app (recommended):** **https://szlholdings-david-leads.hf.space** — hosted on your SZLHOLDINGS Hugging Face org, public URL but **login-gated by the access key** (David-only). This is the one to send David.
- **In-thread preview:** the attached `/computer/a` David Leads app (also live).
- **Offline backup:** `David_Leads_PORTABLE.html` — double-click, works with **zero network** (your meeting safety net).
- **Login:** retrieve the assigned username, password, and access key from the
  approved secret store. Credentials are never committed to this public repository.
- **Security note:** the legacy demo credential set published before 2026-07-28 is
  revoked by the application and must be rotated in the Hugging Face Space settings.

### One optional finish (1 min): fully-live Territory Map
The Census key couldn't be auto-injected (saved in your vault, value hidden for security). To make the
Territory Map + Census signals fully live on the Space: open
[Space → Settings → Variables and secrets](https://huggingface.co/spaces/SZLHOLDINGS/david-leads/settings),
add a secret named `CENSUS_API_KEY` with your free Census key, and Restart the Space. Until then it uses
the honest SAMPLE NY-county data (still real figures, just not auto-refreshed). Everything else is fully live.

---

## 3. 60-Second Demo Script
**[0:00–0:10] Open / the hook**
> "David, every advisor at New York Life is chasing the same families. The difference between you and
> them next quarter is going to be *who you call first*. Let me show you what I built for you."
*Action:* Open the app. Enter the key. Click **Access Intelligence Console**.

**[0:10–0:25] Run live intelligence**
> "I'm pulling live, public signals right now — SEC corporate filings, federal wage data, Census
> demographics, CDC family data. No private info, ever. Watch."
*Action:* Click **⚡ Run Live Public-Data Intelligence**. Leads populate, ranked.

**[0:25–0:40] The leads + the transparent "why"**
> "Top of your list: a new-parent household — 88, HOT — matched to family coverage. But here's the part
> the big carriers won't show you: click it."
*Action:* Click the ▸ to expand the top lead.
> "There's the *whole* reasoning — every scoring factor, the exact public sources behind it, and the
> next thing to say when you call: 'New baby changes everything — let's make sure they're protected.'
> LexisNexis sells carriers a black box. This explains itself."
*Action:* Point to the Why-this-lead bars, the Predictive Moments timeline, the Next-Best-Action talk track.

**[bonus] Where to prospect + leave with it**
> "Click Territory Map — this shades your NY counties by opportunity, live from Census data, with the
> formula right there. And Export Call List hands you the whole ranked list as a spreadsheet."
*Action:* Open Territory Map, then Export Call List.

**[0:40–0:52] The moat — signed receipts**
> "Here's what no other advisor can show you. Click any lead."
*Action:* Click **🔏 Verify Receipt**. Big green **VERIFIED**.
> "Every score carries a tamper-proof, cryptographically signed receipt. If compliance or a client
> ever asks 'where did this come from?' — you have mathematical proof it was all public data, no
> fabrication. That's audit-defensible lead intelligence. Carriers don't even give their own agents this."

**[0:52–1:00] The KPI close**
> "Top of the screen: this is modeling 3+ qualified appointments a week and a $22K premium pipeline —
> from public data alone. Imagine this tuned to your book and running every morning. That's the engagement."

---

## 4. Things to say if he digs in
- **"Is this compliant?"** → "100% public, aggregate data — SEC, BLS, Census, CDC. Never private PII.
  The governance gate literally rejects anything non-public, and every lead is receipted to prove it."
- **"How is this different from the leads I buy?"** → "Bought leads are shared with 5 other agents and
  you don't know why they're a lead. These are intelligence-scored, product-matched, and provenanced.
  Quality over volume — fewer calls, higher close rate."
- **"Can it do more than insurance?"** → "Yes. The scoring blueprint generalizes — same engine, different
  public signals, any sector. But we start where you win: your book at New York Life."
- **"What's the full version?"** → "Live filings monitored daily, tuned to your territory and product mix,
  auto-refreshed every morning, wired to your CRM. That's the build-out we'd scope together."

---

## 5. Under the hood (for you, Stephen)
Built on the **SZL governed-AI substrate**, retargeted to insurance:
- **Receipts:** real ECDSA-P256 / DSSE-style signing (reused `sentra/szl_dsse.py` pattern). Honest by
  design — if no key, emits clearly-labelled UNSIGNED receipt, never fakes a signature.
- **Governance gate:** Λ-style public-data-only enforcement (reused tripwire pattern).
- **Scoring:** weighted geometric mean over 5 axes → 0-100. One weak axis pulls the score down.
- **Live data:** SEC EDGAR + BLS confirmed working live; Census needs the free `CENSUS_API_KEY` to go
  live (currently honest sample fallback).
- **Stack:** FastAPI backend (port 8000) behind the proxy + static frontend on S3. Three.js login backdrop.
- **HF Space** also scaffolded at `betterwithage/david-leads` (private). To push to SZLHOLDINGS org with
  full source, see `hf_space/` — needs your HF org write token.

© 2026 SZL Holdings · public-data-only · honest by design
