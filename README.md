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
tags:
  - insurance
  - lead-intelligence
  - public-data
  - receipts
  - governance
  - szl-holdings
---

> **SZL Holdings** · Doctrine v11 · Λ = Conjecture 1 (advisory, never "green"/theorem) · canonical [a-11-oy.com](https://a-11-oy.com)

# David Leads — Sovereign Insurance Intelligence

Audit-defensible insurance lead intelligence for **New York Life** financial professionals.
Built by **SZL Holdings** on the sovereign governed-AI substrate.

**The edge:** the kind of life-event predictive scoring carriers buy from vendors like
LexisNexis / Deloitte — but transparent, **public-data-only**, and **cryptographically
receipted** so every lead is audit-defensible. We are not aware of an agent-level competitor
that ships signed, verifiable lead provenance.

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

## V8.4 — Open box + EDGAR workforce window (latest)
- **Public methodology** (`GET /api/methodology`, no login): the full scoring model card — formula, axes, weights, sources — open to everyone. It contains no PII or lead data; transparency is the brand.
- **EDGAR workforce-event window** (`GET /api/edgar-signals`, login-gated): 8-K filings matching disclosed workforce-event phrases via the KEYLESS SEC full-text search, REPORTED pass-through with SEC's own Item 2.05 flag — a phrase match is a real filing, never a verdict. Honest `UNAVAILABLE` on upstream failure.
- **Maine GAP re-verified (2026-07-11):** data.maine.gov Socrata is decommissioned (redirects to socrata.com 404). ME stays an honest GAP — no fabricated feed.

## Access (login-gated)
Set as Space secrets (Settings → Variables and secrets):
- `DAVID_USER`, `DAVID_PASS`, `DAVID_ACCESS_KEY`
- `SZL_COSIGN_PRIVATE_PEM`, `SZL_COSIGN_PUBLIC_PEM` (for real signing; otherwise honest UNSIGNED receipts)
- `CENSUS_API_KEY` (optional free key for live Census)

© 2026 SZL Holdings · Apache-2.0 · public-data-only · honest by design

---

## SZL Estate

Part of the **SZL Holdings** governed-AI estate — *governed AI you can prove*: every decision carries a signed, checkable receipt.

- **Flagship:** [a11oy command console → a-11-oy.com](https://a-11-oy.com)
- **Orgs:** [GitHub · szl-holdings](https://github.com/szl-holdings) · [Hugging Face · SZLHOLDINGS](https://huggingface.co/SZLHOLDINGS)
- **Related Spaces:** [🧬 immune](https://huggingface.co/spaces/SZLHOLDINGS/immune) · [✅ governed-receipt-verifier](https://huggingface.co/spaces/SZLHOLDINGS/governed-receipt-verifier) · [🌌 cosmos](https://huggingface.co/spaces/SZLHOLDINGS/cosmos)
- **Estate hub (every Space, live status):** [szl-estate-live](https://szlholdings-szl-estate-live.static.hf.space)

**Status:** responding as of 2026-07-11 (HF Space root probe, this session).

<sub>Doctrine v11 · Λ = Conjecture 1 (advisory — never "green"/theorem; open) · honest by design · public data only.</sub>
