# David Leads V3 — "Genius Edition" build brief (for the 4 Opus agents)

## Context
Live app for David Abraham (NYL financial professional). Already deployed:
- HF Space: SZLHOLDINGS/david-leads (https://szlholdings-david-leads.hf.space)
- GitHub: szl-holdings/david-leads (public, Apache-2.0)
- Local source: /home/user/workspace/david-leads/app/  (server.py, signals.py, scoring.py, receipts.py, static/index.html, static/app.js)

Current endpoints: /healthz, /api/login, /api/run, /api/territory, /api/leads, /api/receipt/{id}, /api/verify/{id}
Current signals: SEC EDGAR 8-K (live), BLS wages (live), Census ACS (live via Newdave key), CDC natality (aggregate)
Current frontend: login gate, Morning Brief, KPI cards, ticker, ranked leads w/ expandable Why+Moments+NBA,
  Premium Pipeline, Territory Map (tiles), signed-receipt verifier, governance gate, Three.js login backdrop.
Visual identity: navy #0a2540, gold #c08f2f, teal #168f89, Fraunces + Inter. CSS vars in index.html :root.

## Goal
Make it genius-grade: harden front<->back wiring, wire in MORE free public data, add HOLOGRAPHIC 3D graphs
(dazzle + boardroom-credible, with a Holo-mode toggle). Honest by design — never fabricate; label sample data.

## Hard rules
1. No fabricated data. Public sources only. Keep signed-receipt + governance moat intact.
2. Keep visual identity + existing CSS tokens.
3. localStorage is BLOCKED in the deploy iframe — use in-memory JS state only.
4. Frontend API base must stay proxy-aware (deploy_build uses __PORT_8000__).
5. New public data that needs a key: read from env with graceful sample fallback (like Census/Newdave).

## Free public data candidates (wire the high-value ones)
- FRED (api.stlouisfed.org) — interest rates, mortgage rates (30Y), CPI, housing — needs free key (env FRED_API_KEY).
- BEA (apps.bea.gov) — regional personal income — free key.
- IRS SOI county migration — bulk CSV (no live API) → bundle a curated NY inflow slice as a static asset.
- HUD/USPS address-change (vacancy) — proxy for moves.
- BLS additional series (unemployment, sector wages) — no key.
- Census ACS extra variables (homeownership B25003, college B15003) — have key.
- Treasury/FiscalData (api.fiscaldata.treasury.gov) — rates — no key.
Pick the ones with strongest LIFE-INSURANCE lead signal and that respond reliably from a server.

## Holographic 3D ideas (Three.js already loaded; deck.gl optional via CDN)
- Lead Constellation: 3D node cloud, each node = a lead, size=score, color=bucket, links=shared signals; rotate/hover.
- Territory Globe/Hex: 3D extruded county bars (height=opportunity) — deck.gl HexagonLayer or Three.js bars.
- Pipeline 3D: premium pipeline as 3D stacked/extruded bars.
- "Holo mode" toggle: switches the dashboard's 2D charts to glowing 3D holographic versions (bloom, wireframe, particles).
- Keep a 2D fallback always (boardroom-credible default; holo = wow toggle).
