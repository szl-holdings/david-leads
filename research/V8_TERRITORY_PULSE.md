# V8 Spec 1 — Territory Pulse

**Goal:** A live, ranked pulse of the 13-state seaboard (see `V8_SEABOARD_SCOPE.md` §1) showing where the freshest lead-generating public activity is right now.

## Endpoint
`GET /api/pulse?states=CT,DE,DC,...` (auth required). Omit `states` → full 13-state seaboard.

## Pulse score (transparent, disclosed)
For each state `s`:

```
pulse(s) = 100 × richness_norm(s) × freshness(s) × activity(s)
```

- `richness_norm(s)` = V7 data-richness (0–4) ÷ 4 → [0,1]. Source: `V7_MULTISTATE.md` §1. Static, citable.
- `freshness(s)` ∈ [0,1] = decays from 1.0 based on the most recent verified update cadence of that state's primary feed (daily=1.0, monthly=0.6, annual=0.3, none/gap=0.15 baseline).
- `activity(s)` ∈ [0,1] = normalized recent-issuance volume when a live count is available (e.g. CT "4,323 business formations in last 30 days"); falls back to richness when no live count.

Output bucket per state: **SURGING** (≥70), **ACTIVE** (40–69), **QUIET** (<40), **GAP** (flagged no-API states).

## Response shape
```json
{
  "generated_at": "2026-06-28T23:11:00Z",
  "seaboard": [
    {"state":"CT","name":"Connecticut","pulse":92.0,"bucket":"SURGING",
     "richness":4.0,"freshness":1.0,"activity":0.92,
     "primary_feed":"data.ct.gov (Socrata)","cadence":"daily",
     "headline":"4,323 new business formations in last 30 days",
     "citations":[{"label":"CT Business Filing History ah3s-bes7","url":"https://data.ct.gov/resource/ah3s-bes7.json"}],
     "gap": false}
  ],
  "summary": {"surging":["CT","DE","DC"], "gaps":["MA","NH","ME"], "top_state":"CT"},
  "receipt_id": "rcpt_..."
}
```

## Rules
- Every state row carries citations to the public feed it was scored from.
- Gap states (MA/NH/ME) return `bucket:"GAP"`, `gap:true`, baseline freshness, and an honest headline ("no keyless statewide API verified — baseline only").
- The whole pulse is bound to one signed receipt (reuse `receipts.make_receipt`).
- Offline/no-live mode: use the static V7 richness + verified counts already in research (deterministic, citable) — never fabricate fresh counts.

## Frontend
- New "Territory Pulse" panel above the leads table: 13 state chips, color-coded by bucket, sorted by pulse. Click a chip → its headline + citations + [Verify receipt].
- Reuse existing CSS tokens (navy/gold/teal). 2D default; optional holo bars via existing `holo.js`.
