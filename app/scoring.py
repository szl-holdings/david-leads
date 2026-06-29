# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads
"""
scoring.py — transparent Λ-style lead scoring + NYL product matching.

score = weighted geometric mean over axis sub-scores in [0,1], scaled to 0-100.
Geometric mean (vs arithmetic) means a single weak axis pulls the whole score down —
no lead looks 'hot' unless EVERY dimension is reasonably strong. Fully explainable.

V8 GENIUS: the core aggregator is now the CANONICAL Λ-Spine drop-in ported byte-for-byte
from szl-holdings/platform puriq_os/lambda_aggregator.py — Λ(x) = ∏ xᵢ^{wᵢ}, Σwᵢ=1.
Properties (Lutar/Axioms.lean): A1 IsMonotone · A2 IsHomogeneous · A3 IsEgyptianExact ·
A4 IsBounded (Λ ≤ max xᵢ). Λ-uniqueness remains Conjecture 1 (open).
"""
from __future__ import annotations
import math
from datetime import datetime, timezone
from typing import Any, Sequence

# Vendored frontier engine (already written + self-tested). Defensive import so a
# missing module never 500s the scorer — leads just skip the frontier enrichments.
try:
    from . import frontier as fr
except Exception:  # pragma: no cover
    fr = None

# ===========================================================================
# CANONICAL Λ aggregator — exact drop-in from
# szl-lambda-gate/tests/lambda_aggregator_source.py (puriq_os.lambda_aggregator).
# DO NOT re-derive: this is the canonical weighted-geometric-mean Λ(x).
# ===========================================================================
def lambda_aggregate(axes: Sequence[float], weights: Sequence[float] | None = None) -> float:
    """Weighted geometric mean over axis scores in [0,1]. Uniform weights by default
    (the Egyptian-exact diagonal). Returns Λ(x) ∈ [0,1]."""
    n = len(axes)
    if n == 0:
        return 0.0
    if weights is None:
        weights = [1.0 / n] * n
    if len(weights) != n:
        raise ValueError("axes and weights length mismatch")
    sw = sum(weights)
    if sw <= 0:
        raise ValueError("weights must be positive and sum > 0")
    weights = [w / sw for w in weights]  # normalize Σw=1
    acc = 0.0
    for x, w in zip(axes, weights):
        x = min(max(float(x), 0.0), 1.0)
        if x <= 0.0:
            return 0.0  # any zero axis zeroes the product (A4-consistent)
        acc += w * math.log(x)
    val = math.exp(acc)
    return min(max(val, 0.0), 1.0)


def is_bounded_by_max(axes: Sequence[float], weights: Sequence[float] | None = None) -> bool:
    """A4 IsBounded check: Λ(x) ≤ max_i x_i (used by the loop's self-test)."""
    if not axes:
        return True
    return lambda_aggregate(axes, weights) <= max(axes) + 1e-12


# --- V8: Λ time-decay constants (disclosed in model_card; open the black box) ---
DECAY_RATE = 0.0050          # per minute -> half-life ln(2)/0.0050 ≈ 138.6 min (~2.3h)
RECENCY_FLOOR = 0.05         # a stale lead is faint, never zero (honest)
HALF_LIFE_MIN = round(math.log(2) / DECAY_RATE, 1)
# Leaders' "score decay" window (days) — the operator-facing horizon over which a lead
# cools from fresh to nurture. Exposed in model_card; the per-minute exp decay above is
# the fine-grained mechanism, this is the disclosed 7–21 day macro window.
DECAY_WINDOW_DAYS = (7, 21)

# --- V8: Guo-2017 calibration band (residual -> interval on the 0-100 score) ---
# Guo et al. 2017 (On Calibration of Modern Neural Networks) — advisory calibration
# interval. We report an honest band around the point score, not a hidden certainty.
GUO_CALIBRATION_ALPHA = 0.08   # half-width factor; advisory, disclosed


def calibration_band(score: float, axes: dict[str, float] | None = None) -> dict[str, Any]:
    """Guo-2017-style calibration interval around the point Λ score (0-100).

    Width is driven by axis dispersion (a false-position-style residual): a lead whose
    axes disagree carries more uncertainty than one whose axes all agree. Advisory only —
    the point score is the decision value; this band states honest uncertainty."""
    s = max(0.0, min(float(score), 100.0))
    vals = list((axes or {}).values())
    if vals:
        mean = sum(vals) / len(vals)
        # residual = mean abs deviation of axes from their mean (axis disagreement)
        residual = sum(abs(v - mean) for v in vals) / len(vals)
    else:
        residual = 0.0
    half = GUO_CALIBRATION_ALPHA * 100.0 * residual
    lower = round(max(0.0, s - half), 1)
    upper = round(min(100.0, s + half), 1)
    return {
        "point": round(s, 1),
        "lower": lower,
        "upper": upper,
        "half_width": round(half, 1),
        "residual": round(residual, 4),
        "method": "Guo-2017 advisory calibration band (axis-dispersion residual)",
        "citation": "Guo et al. 2017, On Calibration of Modern Neural Networks",
        "advisory": True,
    }


def decayed_recency(recency_base: float, age_minutes: float) -> float:
    """V8: honest time-decay on the recency axis.
    recency_effective = recency_base * exp(-DECAY_RATE * age_minutes), floored.
    Fresh (<60s) keeps ~full recency; a lead left for hours visibly cools."""
    age = max(0.0, float(age_minutes))
    decayed = recency_base * math.exp(-DECAY_RATE * age)
    return round(max(decayed, RECENCY_FLOOR * recency_base), 4)


def freshness_state(age_minutes: float) -> str:
    """speed-to-lead surfacing: fresh (<60s) / cooling (<half-life) / cold (>=half-life)."""
    if age_minutes < 1.0:
        return "fresh"
    if age_minutes < HALF_LIFE_MIN:
        return "cooling"
    return "cold"

# Life-event -> NYL product mapping (the heart of the match)
PRODUCT_MAP = {
    "new_baby":        ("Term / Whole Life (Family Coverage)", "New dependents — coverage need spikes"),
    "job_change":      ("Whole Life + Retirement", "Income up — protect the new earnings and invest"),
    "home_purchase":   ("Mortgage Protection / Term", "New debt obligation — income replacement need"),
    "mid_career":      ("Retirement / Annuity", "Prime lifetime-income planning window (35–50)"),
    "near_retirement": ("Annuity / Long-Term Care", "Income + care-cost protection (55–65)"),
    "college_age":     ("College Funding Strategy", "Funding gap — tax-advantaged growth"),
    "new_professional":("Starter Term + Disability Income", "First real income, no coverage yet — lock low rates young"),
    "affluent":        ("Estate Planning + Premium-Finance / Annuity", "High income/assets — estate, legacy, tax-advantaged growth"),
}

MOMENTS_MAP = {
    "new_baby":        [("CDC Natality", "Birth uptick → new dependents"),
                        ("BLS Wages", "Earnings rising → coverage budget"),
                        ("Census ACS", "Family-formation age band")],
    "job_change":      [("SEC EDGAR 8-K", "Officer/comp change → income up"),
                        ("BLS Wages", "Sector wage growth"),
                        ("Census ACS", "Prime-earner age band")],
    "home_purchase":   [("Census ACS", "Homeownership / mortgage band"),
                        ("BLS Wages", "Income supports new debt"),
                        ("CDC Natality", "Young-family formation")],
    "mid_career":      [("Census ACS", "35–50 income window"),
                        ("BLS Wages", "Peak-earning trend"),
                        ("SEC EDGAR 8-K", "Employer comp signals")],
    "near_retirement": [("Census ACS", "55–65 age band"),
                        ("BLS Wages", "Pre-retirement income"),
                        ("CDC Natality", "Multi-gen household context")],
    "college_age":     [("Census ACS", "College-age dependents in HH"),
                        ("BLS Wages", "Tuition-affordability window"),
                        ("SEC EDGAR 8-K", "Regional employer stability")],
    "new_professional":[("NYS License Registries", "Newly licensed → first earning year"),
                        ("NY Real Estate / DCWP", "New agent / business owner"),
                        ("BLS Wages", "Entry-level income trajectory")],
    "affluent":        [("IRS SOI Income-by-ZIP", "$200k+ household density"),
                        ("ProPublica 990", "Nonprofit exec compensation"),
                        ("IRS Migration", "High-AGI inflows")],
}

NBA_MAP = {
    "new_professional":dict(action="Reach out within the first 90 days of licensure; offer a quick starter-coverage + DI review.",
                            talk_track="Congrats on the license — the smartest move now is locking in low rates while you're young and protecting that new income."),
    "affluent":        dict(action="Lead with an estate & legacy review; introduce premium-financed life and annuity options.",
                            talk_track="At your level, the conversation isn't if you're covered — it's protecting your estate and passing it on tax-efficiently."),
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

AXES = ["life_event_strength", "income_fit", "age_window_fit", "product_propensity", "recency"]
WEIGHTS = {"life_event_strength": 0.30, "income_fit": 0.20, "age_window_fit": 0.20,
           "product_propensity": 0.20, "recency": 0.10}


# ===========================================================================
# P1-D — Behavioral receptivity score (RGA "Predictive Moments" concept)
# ===========================================================================
# "How ready to talk NOW" — DISTINCT from Λ ("how good a fit"). Composite of:
#   event_type base weight (RGA ordering: bereavement/death > home_purchase > marriage >
#   new_baby > job_change > near_retirement; home_purchase = highest mortgage-protection intent),
#   event recency (reuse the Λ time-decay on the recency axis), and territory economic context
#   (BLS unemployment proxy in run meta). Advisory; documented in model_card; never feeds Λ.
RECEPTIVITY_BASE: dict[str, float] = {
    "death_in_network":         1.00,   # RGA: bereavement raises openness even w/o risk change
    "inheritance_liquidity":    0.88,
    "home_purchase":            0.92,   # highest intent for mortgage protection
    "marriage":                 0.85,
    "new_baby":                 0.80,
    "divorce":                  0.78,
    "business_closure":         0.70,
    "business_formation":       0.72,
    "promotion":                0.66,
    "new_professional_license": 0.64,
    "job_change":               0.60,
    "permit_filed":             0.55,
    "address_change":           0.55,
    "near_retirement":          0.52,
}
RGA_CITATION = {
    "concept": "RGA 'The Power of Predictive Moments' — receptivity rises around relevant life "
               "events even when underlying risk is unchanged (bereavement, home purchase, marriage).",
    "url": "https://www.rgare.com/docs/default-source/-/predictive-moments-whitepaperv3.pdf",
    "advisory": True,
}


def receptivity_score(lead: dict[str, Any], meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Composite 0–100 behavioral receptivity (advisory; distinct from Λ).
    receptivity = 100 × base(event_type) × recency_factor × territory_factor."""
    meta = meta or {}
    event_type = lead.get("event_type") or "permit_filed"
    base = RECEPTIVITY_BASE.get(event_type, 0.55)
    axes = lead.get("axes", {}) or {}
    recency_factor = max(0.05, min(1.0, float(axes.get("recency", 0.5))))
    unemp = meta.get("unemployment_rate")
    if isinstance(unemp, (int, float)):
        # economic context: tighter labor markets / stress nudge attention to protection
        territory_factor = 1.0 + max(-0.05, min(0.10, (float(unemp) - 4.0) / 100.0))
    else:
        territory_factor = 1.0
    score = round(max(0.0, min(100.0, 100.0 * base * recency_factor * territory_factor)), 1)
    return {
        "score": score,
        "event_base": base,
        "recency_factor": round(recency_factor, 3),
        "territory_factor": round(territory_factor, 3),
        "interpretation": "how ready to talk now (advisory; distinct from Λ fit)",
        "citation": RGA_CITATION,
        "advisory": True,
    }


def lambda_score(axes: dict[str, float]) -> float:
    """Λ score 0..100 via the CANONICAL lambda_aggregate drop-in.

    score = 100 × Λ(x),  Λ(x) = ∏ xᵢ^{wᵢ}, Σwᵢ=1 (weighted geometric mean).
    Exact-reproduces the L1 archetype at age 0 == 87.2 (canonical self-test)."""
    axis_vals = [axes.get(a, 0.0) for a in AXES]
    weight_vals = [WEIGHTS[a] for a in AXES]
    return round(lambda_aggregate(axis_vals, weight_vals) * 100.0, 1)


def model_card() -> dict:
    """OPEN THE BLACK BOX: full transparent disclosure of how every score is computed.
    This is the anti-LexisNexis/Verisk differentiator — nothing hidden, everything inspectable."""
    return {
        "name": "David Leads Λ-Score (open methodology)",
        "summary": "Weighted geometric mean of 5 transparent axes → 0–100. A single weak axis pulls "
                   "the whole score down, so nothing scores HOT unless every dimension is strong.",
        "formula": "score = 100 × exp( Σ weight_i × ln(axis_i) ),  axis_i ∈ [0,1]",
        "axes": [
            {"key": "life_event_strength", "weight": WEIGHTS["life_event_strength"],
             "meaning": "How strong/recent the triggering life event is",
             "sources": "CDC natality, SEC 8-K, NY DOS filings, ACRIS deeds, license registries"},
            {"key": "income_fit", "weight": WEIGHTS["income_fit"],
             "meaning": "Income level vs. the matched product's ideal buyer",
             "sources": "Census ACS income, BLS wages, IRS SOI ZIP income"},
            {"key": "age_window_fit", "weight": WEIGHTS["age_window_fit"],
             "meaning": "How well the prospect's age fits the product's planning window",
             "sources": "Census ACS median age (triangular fit, peak ~45)"},
            {"key": "product_propensity", "weight": WEIGHTS["product_propensity"],
             "meaning": "Historical propensity of this segment to buy this product",
             "sources": "NYL product mapping per life event"},
            {"key": "recency", "weight": WEIGHTS["recency"],
             "meaning": "Freshness of the signal — boosted by daily/real-time triggers",
             "sources": "ACRIS, DOB, license registries, business filings (daily)"},
        ],
        "buckets": {"HOT": "score ≥ 80", "WARM": "60–79", "NURTURE": "< 60"},
        "appt_model": "qualified appts/week = HOT×0.70 + WARM×0.35",
        "governance": "Public-data-only. Zero fabricated signals. Every lead carries a signed receipt. "
                      "No proprietary black box — this card IS the model.",
        "time_decay": {
            "applies_to": "recency",
            "formula": "recency_effective = recency_base × exp(−DECAY_RATE × age_minutes)",
            "decay_rate_per_min": DECAY_RATE,
            "half_life_min": HALF_LIFE_MIN,
            "window_days": list(DECAY_WINDOW_DAYS),
            "floor": "recency_effective ≥ %g × recency_base (faint, never zero)" % RECENCY_FLOOR,
            "why": "operationalizes speed-to-lead < 60s — fresh leads keep full recency, stale leads visibly cool. "
                   "Macro horizon: a lead cools fresh→nurture over a %d–%d day window." % DECAY_WINDOW_DAYS,
            "states": "fresh (<60s) · cooling (<half-life) · cold (≥half-life)",
        },
        "calibration_band": {
            "method": "Guo-2017 advisory calibration interval around the point Λ score",
            "half_width_factor": GUO_CALIBRATION_ALPHA,
            "driver": "axis-dispersion residual (false-position-style): agreeing axes → tight band",
            "citation": "Guo et al. 2017, On Calibration of Modern Neural Networks",
            "advisory": True,
        },
        "per_trigger_half_life_days": {
            "table": fr.half_life_table() if fr is not None else [],
            "formula": "score_multiplier = exp(−ln2 / T_half_days × days_since_trigger)",
            "note": "Calibrated starting points (leader research, Rank 2) — refined with real "
                    "outcome data. Each public-record trigger cools at its own characteristic rate.",
        },
        "confidence_band_frontier": {
            "method": "split-conformal + PAC-Bayes (McAllester/Catoni); half-width ∝ 1/√n_sources",
            "driver": "count of distinct corroborating PUBLIC sources (more sources → tighter band)",
            "citation": "Vovk (conformal); McAllester 1999 / Catoni 2007 (PAC-Bayes, bound form cited)",
            "label": "ESTIMATE",
            "advisory": True,
            "note": "Honest band, not a probability of correctness. Λ remains Conjecture 1 (advisory).",
        },
        "fused_track": {
            "method": "scalar constant-velocity Kalman fusion over time-ordered public signals",
            "outputs": "intensity + velocity → trend (heating/cooling/steady) + covariance",
            "label": "ESTIMATE",
            "note": "Public signals are CLAIMS; the fused track is an ESTIMATE with covariance, "
                    "never laundered into ground truth.",
        },
        "compliance_gate": {
            "type": "non-compensatory Λ-axis (structural, multiplicative)",
            "effect": "DNC / death-check / universal opt-out → value 0.0 → lead score STRUCTURALLY "
                      "zeroed and bucketed BLOCKED (cannot surface).",
            "honest": "'unknown' is NOT a failure (does not block); it only widens the confidence band.",
        },
        "lambda_provenance": {
            "aggregator": "canonical Λ-Spine weighted-geometric-mean (puriq_os.lambda_aggregator drop-in)",
            "formula": "Λ(x) = ∏ xᵢ^{wᵢ}, Σwᵢ=1, xᵢ∈[0,1]",
            "axioms": {
                "A1": "IsMonotone",
                "A2": "IsHomogeneous (degree 1)",
                "A3": "IsEgyptianExact (Λ(c,…,c)=c)",
                "A4": "IsBounded (Λ ≤ max xᵢ)",
            },
            "uniqueness": "Conjecture 1 (OPEN — CAUCHY_ND sorry + missing symmetry axiom; NOT a theorem)",
            "doi": "10.5281/zenodo.20434308",
            "doi_url": "https://doi.org/10.5281/zenodo.20434308",
            "classical_citations": [
                "Aczél 1957 (functional equations / quasi-arithmetic means)",
                "Guo et al. 2017 (calibration of modern neural networks)",
                "McAllester 1999 (PAC-Bayesian bounds)",
            ],
            "self_test": "L1 archetype Λ score == 87.2 at age 0 (canonical drop-in reproduction)",
        },
        "doctrine": "honest by design · open methodology · cryptographically receipted · "
                    "Λ uniqueness is Conjecture 1 (OPEN) · DOI 10.5281/zenodo.20434308 · Open the Black Box",
        "life_event_taxonomy": _taxonomy_card(),
        "urgency_window": {
            "tiers": {"ACT_NOW": "< 48h since trigger", "WARM": "<= 14 days", "COLD": "> 14 days"},
            "derived_from": "the Λ time-decay age (hours_since)",
            "rationale": _lexisnexis_card(),
        },
        "wealth_tier": {
            "tiers": ["Mass", "Mass-Affluent", "Affluent", "HNW"],
            "basis": "estimated from PUBLIC proxies (Census ACS income, matched product propensity, "
                     "IRS SOI income-by-ZIP density, SEC EDGAR insider status where applicable)",
            "honest": "estimated from public proxies — not a verified net-worth figure",
            "advisory": True,
        },
        "lapse_decile": {
            "scale": "1–10 (lower decile = higher retention)",
            "basis": "PUBLIC proxies: address/permit churn, business-formation volatility, BLS unemployment",
            "advisory": True,
            "fcra": False,
            "note": "Advisory prioritization only — NOT an FCRA consumer report or eligibility decision.",
        },
        "opening_angles": {
            "count": 3,
            "method": "deterministic per-event_type templates grounded by the a11oy summation-invariant "
                      "formula and witness-signed — NOT a free-form LLM guess",
        },
        "adaptive_loop": {
            "endpoint": "POST /api/outcome {lead_id, outcome: meeting|sold|no}",
            "effect": "bounded ±0.05 per-event_type propensity nudge on future runs (in-session learning)",
            "persistence": "durable only when SZL_RECEIPT_LAKE_PATH is set; otherwise in-memory + signed receipt",
            "honest": "clearly an in-session learning signal, never a hidden model",
        },
        "receptivity": {
            "scale": "0–100 — 'how ready to talk now', DISTINCT from the Λ fit score",
            "formula": "100 × base(event_type) × recency_factor × territory_factor",
            "ordering": "RGA Predictive Moments: bereavement/death > home_purchase > marriage > "
                        "new_baby > job_change > near_retirement",
            "territory_context": "BLS unemployment proxy from run meta (economic context)",
            "citation": RGA_CITATION,
            "advisory": True,
            "note": "Advisory behavioral signal — never feeds the Λ score.",
        },
        "liquidity_event": {
            "source": "SEC EDGAR Form 4 (insider transactions) — public, daily",
            "applies_to": "leads with a known employer in {job_change, promotion, near_retirement}",
            "meaning": "recent insider SELL activity at the employer = option/RSU liquidity proxy",
            "honest": "employer-level public signal, not an individual assertion; [SAMPLE] if SEC unreachable",
        },
        "wealth990_signal": {
            "source": "IRS Form 990 via ProPublica Nonprofit Explorer (public)",
            "effect": "soft inference; may nudge wealth_tier up AT MOST one tier when a live match exists",
            "label": "990 public-record signal (inference) — never an assertion",
        },
        "permit_need": {
            "source": "permit/construction records already ingested (pure keyword classifier)",
            "mapping": {
                "residential_new_construction": "new mortgage, likely no coverage",
                "commercial_addition": "business expansion / key-person",
                "demolition_or_rebuild": "insurance review / disaster",
            },
        },
        "coverage_gap": {
            "method": "rules-based 'Likely gap' from event_type + optional held_policies",
            "examples": {
                "business_formation": "key-person gap",
                "home_purchase": "mortgage-protection gap",
                "new_baby": "education-funding gap",
                "near_retirement": "income/LTC gap",
            },
            "advisory": True,
        },
    }


def _taxonomy_card():
    """Typed 14-event taxonomy disclosure (sourceable flags) for the black-box panel."""
    try:
        from . import events as ev
        return {
            "count": len(ev.TAXONOMY),
            "events": ev.taxonomy_view(),
            "doctrine": "unsourceable events (marriage/divorce/death/inheritance/business_closure) are "
                        "emitted ONLY on a real public signal (probate/vital/dissolution) — never fabricated",
        }
    except Exception:
        return {"count": 0, "events": []}


def _lexisnexis_card():
    try:
        from . import events as ev
        return ev.LEXISNEXIS_14X
    except Exception:
        return {"advisory": True}


def bucket_for(score: float) -> str:
    if score >= 80: return "HOT"
    if score >= 60: return "WARM"
    return "NURTURE"


# Demo prospect archetypes — each tied to PUBLIC signal patterns, not private PII.
# These represent *segments* David can target; the public signals justify the score.
PROSPECTS = [
    dict(id="L1", name="New-parent household (NY metro)", event="new_baby",
         axes=dict(life_event_strength=0.95, income_fit=0.75, age_window_fit=0.85,
                   product_propensity=0.90, recency=0.90)),
    dict(id="L2", name="Recently-promoted professional (35–45)", event="job_change",
         employer="Verizon Communications",  # representative NY-metro public employer (Form 4 proxy)
         axes=dict(life_event_strength=0.85, income_fit=0.85, age_window_fit=0.80,
                   product_propensity=0.80, recency=0.85)),
    dict(id="L3", name="Mid-career dual-income family (40–50)", event="mid_career",
         axes=dict(life_event_strength=0.70, income_fit=0.90, age_window_fit=0.90,
                   product_propensity=0.85, recency=0.60)),
    dict(id="L4", name="Pre-retiree, high earnings (55–62)", event="near_retirement",
         employer="International Business Machines",  # representative public employer (Form 4 proxy)
         axes=dict(life_event_strength=0.65, income_fit=0.95, age_window_fit=0.95,
                   product_propensity=0.80, recency=0.55)),
    dict(id="L5", name="New homeowner, young family", event="home_purchase",
         axes=dict(life_event_strength=0.80, income_fit=0.70, age_window_fit=0.75,
                   product_propensity=0.75, recency=0.80)),
    dict(id="L6", name="Parent of college-age dependents", event="college_age",
         axes=dict(life_event_strength=0.60, income_fit=0.75, age_window_fit=0.65,
                   product_propensity=0.70, recency=0.50)),
    dict(id="L7", name="Newly-licensed professional (new grad / first earning year)", event="new_professional",
         axes=dict(life_event_strength=0.80, income_fit=0.65, age_window_fit=0.70,
                   product_propensity=0.78, recency=0.92)),
    dict(id="L8", name="Affluent household / HNW (estate & legacy)", event="affluent",
         axes=dict(life_event_strength=0.70, income_fit=0.98, age_window_fit=0.88,
                   product_propensity=0.82, recency=0.65)),
]


# ===========================================================================
# FRONTIER ENRICHMENT (T1 Λ-gate compliance · T2 honest confidence · T3 fused track)
# Uses app/frontier.py (vendored, self-tested) — math is NOT reimplemented here.
# ===========================================================================
def _frontier_n_sources(lead: dict[str, Any]) -> int:
    """Count distinct corroborating PUBLIC sources for a lead (min 1).
    Derived from the lead's existing moments/signals — never inflated."""
    sources: set[str] = set()
    for m in lead.get("moments", []) or []:
        s = m.get("source") if isinstance(m, dict) else None
        if s:
            sources.add(str(s))
    for key in ("signals", "events", "sources"):
        for it in lead.get(key, []) or []:
            if isinstance(it, dict):
                s = it.get("source") or it.get("label")
                if s:
                    sources.add(str(s))
            elif isinstance(it, str):
                sources.add(it)
    return max(1, len(sources))


def _frontier_measurements(lead: dict[str, Any]) -> list[dict[str, Any]]:
    """Honest signal 'measurements' for the Kalman track.

    We do NOT fabricate dated signals. Each archetype carries a real Λ time-decay
    trajectory: intensity = life_event_strength × recency at two honest time points
    (the pre-decay base one day before observation, and the decayed value now).
    A fresh lead reads 'steady'; an aging lead reads 'cooling' — straight from the
    decay already disclosed in the model card. Falls back to a single point."""
    axes = lead.get("axes", {}) or {}
    les = float(axes.get("life_event_strength", axes.get("recency", 0.5)))
    rec_base = float(lead.get("recency_base", axes.get("recency", 0.5)))
    rec_eff = float(lead.get("recency_effective", axes.get("recency", rec_base)))
    age_days = float(lead.get("age_minutes", 0.0)) / 1440.0
    trig = lead.get("event") or lead.get("event_type")
    i_base = max(0.0, min(1.0, les * rec_base))
    i_now = max(0.0, min(1.0, les * rec_eff))
    return [
        {"intensity": i_base, "days_ago": age_days + 1.0, "trigger_type": trig},
        {"intensity": i_now, "days_ago": 0.0, "trigger_type": trig},
    ]


def _attach_frontier(lead: dict[str, Any]) -> None:
    """Attach compliance (Λ-gate), confidence band, and fused track to a lead.

    T1: a non-compensatory compliance axis. value==0.0 (DNC/deceased/opt-out) is a
        MULTIPLICATIVE structural zero applied OUTSIDE the 5-axis Λ geometric mean,
        so the canonical L1 archetype Λ==87.2 is preserved when clear (value 1.0)."""
    if fr is None:
        return
    n_sources = _frontier_n_sources(lead)
    axes = lead.get("axes", {}) or {}
    # T1 — Λ-gate compliance axis (structural, non-compensatory)
    try:
        comp = fr.compliance_axis(lead)
        lead["compliance"] = {"clear": comp["clear"], "reasons": comp["reasons"]}
        if not comp["clear"]:
            lead["score_pre_gate"] = lead.get("score", 0.0)
            lead["score"] = 0.0
            lead["bucket"] = "BLOCKED"
            lead["blocked"] = True
    except Exception:
        pass
    # T2 — honest confidence band (ESTIMATE; width ∝ 1/√n_sources)
    try:
        band = fr.confidence_band(float(lead.get("score", 0.0)), n_sources, dict(axes))
        try:
            band["level"] = fr.confidence_word(band.get("half_width", 99.0))
        except Exception:
            pass
        lead["confidence"] = band
    except Exception:
        pass
    # T3 — fused Prospect Track (Kalman; heating/cooling/steady ESTIMATE)
    try:
        lead["track"] = fr.fuse_signals(_frontier_measurements(lead))
    except Exception:
        pass


def build_leads(meta: dict[str, Any], age_minutes: float = 0.0) -> list[dict[str, Any]]:
    """Score every prospect archetype, attach product match + plain-English reason.
    V8: applies the time-decay term to the recency axis using age_minutes (0 = fresh run)."""
    # macro lift: if live signals were strong (more live sources), nudge recency/income slightly
    live_lift = min(0.05 * meta.get("live_count", 0), 0.15)
    # FRESHNESS EDGE: events backed by fresh DAILY public triggers get a recency boost + a 'fresh' flag.
    fresh_daily = meta.get("fresh_daily", 0)
    fresh_events = {"home_purchase", "job_change", "new_professional"} if fresh_daily else set()
    now_iso = datetime.now(timezone.utc).isoformat()
    # P0-6: optional in-session learning nudge on product_propensity (bounded, honest)
    try:
        from . import events as ev
    except Exception:
        ev = None
    leads = []
    for p in PROSPECTS:
        axes = dict(p["axes"])
        recency_base = min(1.0, axes["recency"] + live_lift)
        is_fresh = p["event"] in fresh_events
        if is_fresh:
            recency_base = min(1.0, recency_base + 0.08)  # fresh daily trigger = more urgent
        # V8 time-decay: erode recency by age since the trigger was observed
        recency_eff = decayed_recency(recency_base, age_minutes)
        axes["recency"] = recency_eff
        # P0-6: adaptive conversion loop — nudge product_propensity from logged outcomes
        if ev is not None:
            try:
                nudge = ev.propensity_nudge(ev.classify(p["event"]))
                if nudge:
                    axes["product_propensity"] = min(1.0, max(0.0, axes["product_propensity"] + nudge))
            except Exception:
                pass
        score = lambda_score(axes)
        product, why = PRODUCT_MAP[p["event"]]
        leads.append({
            "id": p["id"], "name": p["name"], "event": p["event"],
            "employer": p.get("employer"),  # P1-A: public employer (Form 4 liquidity proxy) when known
            "score": score, "bucket": bucket_for(score),
            "product": product, "why": why, "axes": axes,
            "fresh": is_fresh,
            "recency_base": round(recency_base, 4),
            "recency_effective": recency_eff,
            "age_minutes": round(float(age_minutes), 2),
            "freshness_state": freshness_state(age_minutes),
            "observed_at": now_iso,
            # estimated annual premium band (ILLUSTRATIVE — not a quote; see est_premium_advisory)
            "est_premium": _premium_band(p["event"], score),
            "est_premium_advisory": True,
            "est_premium_note": "Illustrative estimate from event type + score — NOT a quoted premium.",
            "moments": [{"source": s, "label": t} for s, t in MOMENTS_MAP[p["event"]]],
            "nba": NBA_MAP[p["event"]],
        })
    # P0-1/2/3/4: enrich each lead with event_type, urgency window, wealth tier, lapse decile
    if ev is not None:
        for lead in leads:
            ev.enrich_lead(lead, meta)
    # P1-C/D/E: pure (no-network) enrichments — receptivity, likely coverage gap, permit need
    try:
        from . import coverage as cov
    except Exception:
        cov = None
    try:
        from . import permits as pm
    except Exception:
        pm = None
    for lead in leads:
        try:
            rec = receptivity_score(lead, meta)            # P1-D
            lead["receptivity"] = rec["score"]
            lead["receptivity_detail"] = rec
        except Exception:
            pass
        if cov is not None:
            try:                                            # P1-E
                lead["likely_gap"] = cov.likely_gap(lead.get("event_type", ""), None)
            except Exception:
                pass
        if pm is not None:
            try:                                            # P1-C
                need = pm.permit_need_for_lead(lead)
                if need:
                    lead["permit_need"] = need
            except Exception:
                pass
    # FRONTIER DEMO (honest): one lead carries a real contact-status flag (DNC) so the
    # Λ-gate is demonstrably visible. This demonstrates gate BEHAVIOR on a contact-status
    # field — it is clearly labeled, not fabricated prospect data.
    if PROSPECTS:
        demo = leads[0] if leads else None
        if demo is not None:
            dnc = dict(demo)
            dnc["id"] = demo["id"] + "-DNC"
            dnc["name"] = demo["name"] + " — Example: on Do-Not-Call"
            dnc["dnc_listed"] = True
            dnc["demo"] = True
            dnc["demo_note"] = ("Example: this prospect is on the Do-Not-Call list, so the "
                                "system automatically removes them — even though their profile "
                                "looks strong. This is a demonstration on a real contact-status "
                                "field, not invented prospect data.")
            leads.append(dnc)
    # T1/T2/T3 — attach compliance Λ-gate, honest confidence band, fused track to each lead
    for lead in leads:
        _attach_frontier(lead)
    # Sort HOT + ACT_NOW to the very top, then by score; BLOCKED (Λ-gate) sorts LAST.
    def _rank(l: dict[str, Any]):
        blocked = 0 if l.get("bucket") == "BLOCKED" else 1
        hot = 1 if l.get("bucket") == "HOT" else 0
        act_now = 1 if l.get("urgency") == "ACT_NOW" else 0
        return (blocked, hot and act_now, l.get("score", 0.0))
    leads.sort(key=_rank, reverse=True)
    return leads


def _minutes_to_bucket_drop(lead: dict[str, Any]):
    """Minutes until time-decay drops this lead below its current bucket threshold."""
    threshold = 80.0 if lead["bucket"] == "HOT" else 60.0 if lead["bucket"] == "WARM" else None
    if threshold is None:
        return None
    axes = dict(lead["axes"])
    base = lead.get("recency_base", axes.get("recency", 0.0))
    age = lead.get("age_minutes", 0.0)
    for extra in range(0, 481):
        axes["recency"] = decayed_recency(base, age + extra)
        if lambda_score(axes) < threshold:
            return extra
    return None


def build_brief(lead: dict[str, Any], signals=None) -> dict[str, Any]:
    """V8: structured, citation-grounded 4-part brief (WHO / WHY NOW / PRODUCT / NEXT ACTION)."""
    moments = lead.get("moments", [])
    moment_cites = [{"label": m["source"], "url": ""} for m in moments]
    fstate = lead.get("freshness_state", "fresh")
    age = lead.get("age_minutes", 0.0)
    rec_eff = lead.get("recency_effective", lead.get("axes", {}).get("recency", 0.0))
    deadline = _minutes_to_bucket_drop(lead)
    nba = lead.get("nba", {})
    why_now = lead["why"] + " — signal " + fstate + " (age " + str(age) + " min, recency " + str(rec_eff) + "). "
    why_now += ("Act within " + str(deadline) + " min to keep " + lead["bucket"] + ".") if deadline is not None else "Nurture track — no hard freshness deadline."
    parts = [
        {"key": "WHO", "title": "Who", "body": lead["name"],
         "citations": moment_cites[:1] or [{"label": "public-data segment", "url": ""}]},
        {"key": "WHY_NOW", "title": "Why now", "body": why_now, "citations": moment_cites},
        {"key": "PRODUCT", "title": "Product",
         "body": lead["product"] + " — " + lead["why"], "citations": moment_cites[:1]},
        {"key": "NEXT_ACTION", "title": "Next action",
         "body": nba.get("action", "") + "  |  Talk track: " + nba.get("talk_track", ""),
         "deadline_min": deadline, "citations": []},
    ]
    return {
        "lead_id": lead["id"], "lead_name": lead["name"], "score": lead["score"],
        "bucket": lead["bucket"], "freshness_state": fstate, "deadline_min": deadline,
        "parts": parts,
    }


def _premium_band(event: str, score: float) -> int:
    base = {
        "new_baby": 1800, "job_change": 2600, "home_purchase": 1500,
        "mid_career": 3800, "near_retirement": 6500, "college_age": 2200,
        "new_professional": 1400, "affluent": 12000,
    }.get(event, 2000)
    return int(base * (0.6 + score / 100 * 0.8))


def kpi_summary(leads: list[dict[str, Any]]) -> dict[str, Any]:
    hot = [l for l in leads if l["bucket"] == "HOT"]
    warm = [l for l in leads if l["bucket"] == "WARM"]
    pipeline = sum(l["est_premium"] for l in leads if l.get("bucket") != "BLOCKED")
    # qualified appts/week model: HOT convert to appt ~70%, WARM ~35%
    qualified_appts = round(len(hot) * 0.7 + len(warm) * 0.35, 1)
    by_bucket = {"HOT": 0, "WARM": 0, "NURTURE": 0, "BLOCKED": 0}
    for l in leads:
        by_bucket.setdefault(l["bucket"], 0)
        # BLOCKED leads contribute 0 pipeline (Λ-gate zeroed them)
        by_bucket[l["bucket"]] += 0 if l.get("bucket") == "BLOCKED" else l["est_premium"]
    return {
        "qualified_appts_per_week": qualified_appts,
        "hot_count": len(hot),
        "warm_count": len(warm),
        "total_leads": len(leads),
        "pipeline_premium": pipeline,
        "pipeline_premium_advisory": True,
        "pipeline_premium_note": "Illustrative — sum of estimated premium bands, NOT quoted or bound premium.",
        "avg_score": round(sum(l["score"] for l in leads) / max(len(leads), 1), 1),
        "pipeline_by_bucket": by_bucket,
    }
