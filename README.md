---
title: David Leads — Sovereign Insurance Intelligence
emoji: 🛡️
colorFrom: blue
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
short_description: Audit-defensible, public-data lead intelligence for NYL pros
---

> **SZL Holdings** · Doctrine v11 · Λ = Conjecture 1 (advisory, never "green"/theorem) · canonical [a-11-oy.com](https://a-11-oy.com)

# David Leads — Sovereign Insurance Intelligence

Audit-defensible insurance lead intelligence for **New York Life** financial professionals.
Built by **SZL Holdings** on the sovereign governed-AI substrate.

**The edge:** the same life-event predictive scoring carriers buy from LexisNexis / Deloitte —
but transparent, **public-data-only**, and **cryptographically receipted** so every lead is
audit-defensible. No agent-level competitor offers signed lead provenance.

## What it does
- Pulls **live public signals**: SEC EDGAR (8-K events), BLS (wages), U.S. Census (income/age), CDC (births).
- Scores leads with a transparent Λ-style model → ranks → matches each to the right NYL product.
- Emits a **compliance-grade signed receipt** (ECDSA-P256 / hash-chain) per lead — verifiable in-app.
- A **governance gate** enforces public-data-only, zero-fabrication (honest by design).
- KPI dashboard: qualified appts/week, HOT leads, pipeline premium.


## V8 — Genius Seaboard (latest)
- **Territory Pulse** (`GET /api/pulse`): live ranked pulse of the 13-state Atlantic seaboard (CT→ME), grounded in verified free open-data richness. MA/NH/ME honestly flagged as data GAPs.
- **Signed 4-Part Brief** (`GET /api/brief/{lead_id}`): every lead → WHO / WHY NOW / PRODUCT / NEXT ACTION, citation-grounded, bound to one tamper-evident signed receipt.
- **Λ with time-decay**: the recency axis now decays as `recency × exp(−0.005·age_min)` (half-life ≈ 139 min), operationalizing speed-to-lead < 60s. Fully disclosed in `/api/model`. Λ remains Conjecture 1.

## Access (login-gated)
Set as Space secrets (Settings → Variables and secrets):
- `DAVID_USER`, `DAVID_PASS`, `DAVID_ACCESS_KEY`
- `SZL_COSIGN_PRIVATE_PEM`, `SZL_COSIGN_PUBLIC_PEM` (for real signing; otherwise honest UNSIGNED receipts)
- `CENSUS_API_KEY` (optional free key for live Census)

© 2026 SZL Holdings · Apache-2.0 · public-data-only · honest by design
