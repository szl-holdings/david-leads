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
from typing import Any

# Life-event -> NYL product mapping (the heart of the match)
PRODUCT_MAP = {
    "new_baby":        ("Term / Whole Life (Family Coverage)", "New dependents — coverage need spikes"),
    "job_change":      ("Whole Life + Retirement", "Income up — protect the new earnings and invest"),
    "home_purchase":   ("Mortgage Protection / Term", "New debt obligation — income replacement need"),
    "mid_career":      ("Retirement / Annuity", "Prime lifetime-income planning window (35–50)"),
    "near_retirement": ("Annuity / Long-Term Care", "Income + care-cost protection (55–65)"),
    "college_age":     ("College Funding Strategy", "Funding gap — tax-advantaged growth"),
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
}

NBA_MAP = {
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
]


def build_leads(meta: dict[str, Any]) -> list[dict[str, Any]]:
    """Score every prospect archetype, attach product match + plain-English reason."""
    # macro lift: if live signals were strong (more live sources), nudge recency/income slightly
    live_lift = min(0.05 * meta.get("live_count", 0), 0.15)
    # FRESHNESS EDGE: events backed by fresh DAILY public triggers get a recency boost + a 'fresh' flag.
    fresh_daily = meta.get("fresh_daily", 0)
    fresh_events = {"home_purchase", "job_change"} if fresh_daily else set()
    leads = []
    for p in PROSPECTS:
        axes = dict(p["axes"])
        axes["recency"] = min(1.0, axes["recency"] + live_lift)
        is_fresh = p["event"] in fresh_events
        if is_fresh:
            axes["recency"] = min(1.0, axes["recency"] + 0.08)  # fresh daily trigger = more urgent
        score = lambda_score(axes)
        product, why = PRODUCT_MAP[p["event"]]
        leads.append({
            "id": p["id"], "name": p["name"], "event": p["event"],
            "score": score, "bucket": bucket_for(score),
            "product": product, "why": why, "axes": axes,
            "fresh": is_fresh,
            # estimated annual premium band (illustrative, for pipeline KPI)
            "est_premium": _premium_band(p["event"], score),
            "moments": [{"source": s, "label": t} for s, t in MOMENTS_MAP[p["event"]]],
            "nba": NBA_MAP[p["event"]],
        })
    leads.sort(key=lambda x: x["score"], reverse=True)
    return leads


def _premium_band(event: str, score: float) -> int:
    base = {
        "new_baby": 1800, "job_change": 2600, "home_purchase": 1500,
        "mid_career": 3800, "near_retirement": 6500, "college_age": 2200,
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
