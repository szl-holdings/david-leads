# V8 Spec 3 — Λ with time-decay

**Goal:** Make freshness erode honestly over time on the transparent Λ-score, operationalizing speed-to-lead < 60s. Fully disclosed in the model card.

## The math (disclosed)
The existing Λ-score is a weighted geometric mean over 5 axes in [0,1]:
```
score = 100 × exp( Σ weight_i × ln(axis_i) )
```
V8 replaces the static `recency` axis input with a **time-decayed** value:
```
recency_effective = recency_base × exp(−DECAY_RATE × age_minutes)
```
- `recency_base` ∈ [0,1] — the V5/V6 freshness/live-lift value (unchanged upstream).
- `age_minutes` — minutes since the underlying trigger was observed (lead `observed_at`).
- `DECAY_RATE` — disclosed constant. Default `DECAY_RATE = 0.0050 /min` → half-life ≈ 139 min (~2.3h). A lead acted on within 60s loses <0.3% recency; one left 2h+ visibly cools.
- Floor: `recency_effective` never drops below `0.05` (a stale lead is faint, not zero — honest).

## Where it lives
- `scoring.decayed_recency(recency_base, age_minutes) -> float` — pure function, unit-testable.
- `scoring.build_leads(meta, now=...)` accepts an optional `now`; each PROSPECT gets an `observed_at`. For the demo, `observed_at = now` (age≈0 → full freshness) so a fresh run shows HOT; a `?age_min=` query param on `/api/run` lets David *demonstrate* cooling live in the meeting.
- `model_card()` gains a `time_decay` block: formula, DECAY_RATE, half-life, floor — open the black box.

## Speed-to-lead surfacing
- Each lead returns `recency_base`, `age_minutes`, `recency_effective`, and `freshness_state` ∈ {`fresh` (<60s), `cooling` (<half-life), `cold` (≥half-life)}.
- The 4-part brief WHY_NOW part and the leads table both show the freshness_state, and a "act within N min to keep HOT" deadline = minutes until the decay would drop the lead below its current bucket threshold.

## Rules
- DECAY_RATE and half-life are shown in the model card and in `/api/model` — never hidden (anti-black-box).
- Time-decay only affects the `recency` axis; the other four axes are unchanged, so the change is isolated and explainable.
- Λ remains **Conjecture 1** in all copy (SZL Doctrine). The decay term is engineering, not a proof claim.

## Tests (smoke)
- `decayed_recency(0.9, 0) == 0.9` (fresh).
- `decayed_recency(0.9, 139) ≈ 0.45` (≈half-life).
- `decayed_recency(0.9, 100000) == 0.05*0.9`-floored (never 0).
- A lead at age 0 scores ≥ the same lead at age 240 min.
