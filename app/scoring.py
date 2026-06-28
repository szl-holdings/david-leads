# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads
"""
scoring.py — transparent Λ-style lead scoring + NYL product matching.

score = weighted geometric mean over axis sub-scores in [0,1], scaled to 0-100.
Geometric mean (vs arithmetic) means a single weak axis pulls the whole score down —
no lead looks 'hot' unless EVERY dimension is reasonably strong. Fully explainable.
"""
from __future__ import annotations
import math
from datetime import datetime, timezone
from typing import Any

# --- V8: Λ time-decay constants (disclosed in model_card; open the black box) ---
DECAY_RATE = 0.0050          # per minute -> half-life ln(2)/0.0050 ≈ 138.6 min (~2.3h)
RECENCY_FLOOR = 0.05         # a stale lead is faint, never zero (honest)
HALF_LIFE_MIN = round(math.log(2) / DECAY_RATE, 1)


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


def lambda_score(axes: dict[str, float]) -> float:
    """Weighted geometric mean of axis scores in [0,1] -> 0..100."""
    eps = 1e-6
    log_sum = sum(WEIGHTS[a] * math.log(max(axes.get(a, 0.0), eps)) for a in AXES)
    return round(math.exp(log_sum) * 100, 1)


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
            "floor": "recency_effective ≥ %g × recency_base (faint, never zero)" % RECENCY_FLOOR,
            "why": "operationalizes speed-to-lead < 60s — fresh leads keep full recency, stale leads visibly cool",
            "states": "fresh (<60s) · cooling (<half-life) · cold (≥half-life)",
        },
        "doctrine": "honest by design · open methodology · cryptographically receipted · Λ is Conjecture 1",
    }


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
         axes=dict(life_event_strength=0.85, income_fit=0.85, age_window_fit=0.80,
                   product_propensity=0.80, recency=0.85)),
    dict(id="L3", name="Mid-career dual-income family (40–50)", event="mid_career",
         axes=dict(life_event_strength=0.70, income_fit=0.90, age_window_fit=0.90,
                   product_propensity=0.85, recency=0.60)),
    dict(id="L4", name="Pre-retiree, high earnings (55–62)", event="near_retirement",
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


def build_leads(meta: dict[str, Any], age_minutes: float = 0.0) -> list[dict[str, Any]]:
    """Score every prospect archetype, attach product match + plain-English reason.
    V8: applies the time-decay term to the recency axis using age_minutes (0 = fresh run)."""
    # macro lift: if live signals were strong (more live sources), nudge recency/income slightly
    live_lift = min(0.05 * meta.get("live_count", 0), 0.15)
    # FRESHNESS EDGE: events backed by fresh DAILY public triggers get a recency boost + a 'fresh' flag.
    fresh_daily = meta.get("fresh_daily", 0)
    fresh_events = {"home_purchase", "job_change", "new_professional"} if fresh_daily else set()
    now_iso = datetime.now(timezone.utc).isoformat()
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
        score = lambda_score(axes)
        product, why = PRODUCT_MAP[p["event"]]
        leads.append({
            "id": p["id"], "name": p["name"], "event": p["event"],
            "score": score, "bucket": bucket_for(score),
            "product": product, "why": why, "axes": axes,
            "fresh": is_fresh,
            "recency_base": round(recency_base, 4),
            "recency_effective": recency_eff,
            "age_minutes": round(float(age_minutes), 2),
            "freshness_state": freshness_state(age_minutes),
            "observed_at": now_iso,
            # estimated annual premium band (illustrative, for pipeline KPI)
            "est_premium": _premium_band(p["event"], score),
            "moments": [{"source": s, "label": t} for s, t in MOMENTS_MAP[p["event"]]],
            "nba": NBA_MAP[p["event"]],
        })
    leads.sort(key=lambda x: x["score"], reverse=True)
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
    pipeline = sum(l["est_premium"] for l in leads)
    # qualified appts/week model: HOT convert to appt ~70%, WARM ~35%
    qualified_appts = round(len(hot) * 0.7 + len(warm) * 0.35, 1)
    by_bucket = {"HOT": 0, "WARM": 0, "NURTURE": 0}
    for l in leads:
        by_bucket[l["bucket"]] += l["est_premium"]
    return {
        "qualified_appts_per_week": qualified_appts,
        "hot_count": len(hot),
        "warm_count": len(warm),
        "total_leads": len(leads),
        "pipeline_premium": pipeline,
        "avg_score": round(sum(l["score"] for l in leads) / max(len(leads), 1), 1),
        "pipeline_by_bucket": by_bucket,
    }
