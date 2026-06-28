# V8 Spec 2 — Signed 4-Part Brief

**Goal:** Every lead carries a structured, citation-grounded four-part brief wrapped in one signed, tamper-evident receipt. This is the boardroom artifact David reads to a prospect.

## The four parts
1. **WHO** — prospect segment + the public signal that surfaced them. Cites the source feed(s).
2. **WHY NOW** — the time-sensitive trigger, with the dated public source and the Λ time-decay status (fresh / cooling).
3. **PRODUCT** — matched NYL product + suitability rationale (from `scoring.PRODUCT_MAP`).
4. **NEXT ACTION** — concrete advisor move + talk track (from `scoring.NBA_MAP`) + a freshness deadline derived from time-decay ("act within N min to keep HOT").

## Builder
`scoring.build_brief(lead, signals, now) -> dict` returns:
```json
{
  "lead_id":"L1",
  "parts":[
    {"key":"WHO","title":"Who","body":"New-parent household (NY metro)","citations":[{"label":"CDC Natality","url":"..."}]},
    {"key":"WHY_NOW","title":"Why now","body":"Birth uptick → new dependents; signal fresh (age 0.2 min, recency 0.98)","citations":[...]},
    {"key":"PRODUCT","title":"Product","body":"Term / Whole Life (Family Coverage) — new dependents, coverage need spikes","citations":[...]},
    {"key":"NEXT_ACTION","title":"Next action","body":"Call within 24h... | Talk track: ...","deadline_min":58,"citations":[]}
  ],
  "score":91.4,"bucket":"HOT"
}
```

## Signed receipt
- `receipts.make_brief_receipt(brief, signals)` canonicalizes the full 4-part brief + its citations, hash-chains it, and ECDSA-P256-signs when `SZL_COSIGN_PRIVATE_PEM` is present (else honest UNSIGNED, hash-chained).
- The receipt payload binds: `lead_id`, the 4 part bodies, all citation sources, `all_signals_public`, `fabricated_signals:0`, `prev_receipt_hash`.
- `GET /api/brief/{lead_id}` returns the brief + `receipt_id`; existing `/api/verify/{rid}` verifies it.

## Rules
- Each part must carry at least one public-data citation except NEXT_ACTION (advisory, may have none).
- WHY_NOW must surface the live Λ time-decay status so the brief itself proves freshness.
- Honest by design: no fabricated citations; if a source is sample/offline, label it.

## Frontend
- Expanding a lead row reveals the 4-part brief as four labelled cards (Who / Why now / Product / Next action), each with citation pills and a single [Verify signed brief] button → green check.
- A "Copy brief" button for David to paste into his CRM.
