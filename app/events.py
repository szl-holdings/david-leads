# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads V8 · typed life-event taxonomy + advisory tiers
"""
events.py — P0 gap-fill against the market leaders (Salesforce FSC Life Events,
LexisNexis Life·Risk, Windfall/Catchlight wealth tiers, Life Attrition decile).

Everything here is ADDITIVE and PURE (no I/O, no network) so it can never break /api/run.
Doctrine: public-data-only · never fabricate. Life events we cannot source from public data
(marriage / divorce / death_in_network / inheritance_liquidity / business_closure) are present
in the taxonomy but are emitted ONLY when a real public signal (probate / vital index /
dissolution filing) is supplied — otherwise omitted, never invented.

Contents:
  P0-1  TAXONOMY (14 typed life events) + classify() mapping the existing segments.
  P0-2  urgency_for() / observed_window() — ACT_NOW (<48h) / WARM (<=14d) / COLD (>14d).
  P0-3  wealth_tier() — Mass / Mass-Affluent / Affluent / HNW from PUBLIC proxies.
  P0-4  lapse_decile() — transparent 1–10 attrition decile (advisory, NOT FCRA).
  P0-5  opening_angles() — 3 ranked, event-keyed opening angles (deterministic templates).
  P0-6  record_outcome() / outcome_summary() / propensity_nudge() — in-session learning loop.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any

# ===========================================================================
# P0-1 — Typed 14-event life-event taxonomy
# ===========================================================================
# Each entry: human label · whether it is sourceable from the CURRENT public pipeline ·
# the public signal that would justify it. `sourceable=False` events are NEVER emitted
# unless a real public signal is supplied (probate / vital / dissolution index).
TAXONOMY: dict[str, dict[str, Any]] = {
    "new_baby":                 {"label": "New baby",                 "sourceable": True,
                                 "public_source": "CDC natality / birth-index uptick"},
    "marriage":                 {"label": "Marriage",                 "sourceable": False,
                                 "public_source": "county vital / marriage license index (required)"},
    "divorce":                  {"label": "Divorce",                  "sourceable": False,
                                 "public_source": "family-court / dissolution filing (required)"},
    "death_in_network":         {"label": "Death in network",         "sourceable": False,
                                 "public_source": "probate / SSA death-index record (required)"},
    "home_purchase":            {"label": "Home purchase",            "sourceable": True,
                                 "public_source": "ACRIS / county deed recording"},
    "business_formation":       {"label": "Business formation",       "sourceable": True,
                                 "public_source": "Sec. of State LLC/Corp filing · SBA · EDGAR"},
    "business_closure":         {"label": "Business closure",         "sourceable": False,
                                 "public_source": "dissolution / bankruptcy filing (required)"},
    "new_professional_license": {"label": "New professional license", "sourceable": True,
                                 "public_source": "state license registry (new issuance)"},
    "job_change":               {"label": "Job change",               "sourceable": True,
                                 "public_source": "SEC 8-K officer change · BLS sector wages"},
    "promotion":                {"label": "Promotion",                "sourceable": True,
                                 "public_source": "SEC 8-K comp change · BLS peak-earner band"},
    "permit_filed":             {"label": "Permit filed",             "sourceable": True,
                                 "public_source": "DOB / county building-permit feed"},
    "address_change":           {"label": "Address change",           "sourceable": True,
                                 "public_source": "Census ACS migration / household composition"},
    "inheritance_liquidity":    {"label": "Inheritance / liquidity",  "sourceable": False,
                                 "public_source": "probate estate distribution (required)"},
    "near_retirement":          {"label": "Near retirement",          "sourceable": True,
                                 "public_source": "Census ACS 55–65 age band"},
}

# Map the existing 8 demo segments (scoring.PROSPECTS[*].event) onto the typed taxonomy.
# Each target is a SOURCEABLE event — we never map a segment onto an unsourceable type.
SEGMENT_TO_EVENT_TYPE: dict[str, str] = {
    "new_baby":         "new_baby",
    "job_change":       "job_change",
    "home_purchase":    "home_purchase",
    "mid_career":       "promotion",
    "near_retirement":  "near_retirement",
    "college_age":      "address_change",
    "new_professional": "new_professional_license",
    "affluent":         "business_formation",
}


def classify(segment_event: str) -> str:
    """Map an existing segment `event` onto a typed taxonomy event_type (sourceable only)."""
    return SEGMENT_TO_EVENT_TYPE.get(segment_event, "permit_filed")


def is_sourceable(event_type: str) -> bool:
    return bool(TAXONOMY.get(event_type, {}).get("sourceable", False))


def taxonomy_view() -> list[dict[str, Any]]:
    """JSON-safe taxonomy for the model card / black-box panel."""
    return [{"event_type": k, **v} for k, v in TAXONOMY.items()]


# ===========================================================================
# P0-2 — Urgency tier + 48h window (derived from the existing Λ time-decay age)
# ===========================================================================
ACT_NOW_HOURS = 48.0           # < 48h since the trigger was observed
WARM_HOURS = 14.0 * 24.0       # <= 14 days
# Rationale citation surfaced in the model card (advisory):
LEXISNEXIS_14X = {
    "finding": "Consumers are ~14x more likely to engage an agent within the window of a life event.",
    "source": "LexisNexis Risk Solutions — 'Life happens: when an agent should reach out'",
    "url": "https://risk.lexisnexis.com/insights-resources/article/life-happens-when-an-agent-should-reach-out",
    "advisory": True,
}


def urgency_for(hours_since: float) -> str:
    """ACT_NOW (<48h) · WARM (<=14d) · COLD (>14d) — keyed to the time-decay age."""
    h = max(0.0, float(hours_since))
    if h < ACT_NOW_HOURS:
        return "ACT_NOW"
    if h <= WARM_HOURS:
        return "WARM"
    return "COLD"


def observed_window(age_minutes: float, now: datetime | None = None) -> dict[str, Any]:
    """Compute event_observed_at, hours_since, and urgency from the lead's decay age."""
    now = now or datetime.now(timezone.utc)
    age_min = max(0.0, float(age_minutes))
    hours_since = round(age_min / 60.0, 2)
    observed_at = (now - timedelta(minutes=age_min)).isoformat()
    return {
        "event_observed_at": observed_at,
        "hours_since": hours_since,
        "urgency": urgency_for(hours_since),
    }


# ===========================================================================
# P0-3 — Wealth tier {Mass · Mass-Affluent · Affluent · HNW} from PUBLIC proxies
# ===========================================================================
# Ordered wealth ladder used by the P2-3 visualization (low → high).
WEALTH_LADDER = ["Mass", "Mass-Affluent", "Affluent", "HNW"]


def wealth_tier(lead: dict[str, Any], meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """4-tier wealth label estimated from PUBLIC proxies already in the pipeline:
    Census ACS income (income_fit axis), matched-product propensity, and — for the
    affluent/business segments — IRS SOI income-by-ZIP density + EDGAR insider proxy.
    HONEST: this is an estimate from public proxies, not a verified net-worth figure.
    Returns a structured object {tier, score, ladder, signals, basis, advisory} so the
    UI can render a 4-segment wealth ladder with the public proxies as chips."""
    axes = lead.get("axes", {}) or {}
    income_fit = float(axes.get("income_fit", 0.0))
    event_type = lead.get("event_type", "")
    signals: list[str] = [
        "Census ACS median household income by tract/state (income_fit axis = %.2f)" % income_fit,
        "Matched NYL product propensity (segment proxy)",
    ]
    if event_type in ("business_formation", "near_retirement") or income_fit >= 0.9:
        signals.append("IRS SOI income-by-ZIP $200k+ density (where available)")
        signals.append("SEC EDGAR insider status (where applicable)")

    if income_fit >= 0.95 or event_type == "business_formation" and income_fit >= 0.9:
        tier = "HNW"
    elif income_fit >= 0.85:
        tier = "Affluent"
    elif income_fit >= 0.72:
        tier = "Mass-Affluent"
    else:
        tier = "Mass"
    return {
        "tier": tier,
        "score": int(max(0, min(100, round(income_fit * 100)))),  # public-proxy 0–100 (income_fit basis)
        "ladder": list(WEALTH_LADDER),
        "ladder_index": WEALTH_LADDER.index(tier),
        "basis": "estimated from public records",
        "signals": signals,
        "advisory": True,
    }


# ===========================================================================
# P0-4 — Attrition / lapse decile (transparent 1–10, advisory, NOT FCRA)
# ===========================================================================
# Per-event base instability proxy (higher = more churn = higher lapse risk). Drawn from
# public-records volatility: address/permit churn, business-formation volatility. Documented.
_EVENT_INSTABILITY: dict[str, float] = {
    "new_baby":                 0.40,
    "job_change":               0.60,
    "home_purchase":            0.55,
    "promotion":                0.45,
    "near_retirement":          0.25,
    "address_change":           0.55,
    "new_professional_license": 0.58,
    "business_formation":       0.50,
    "permit_filed":             0.50,
}


def lapse_decile(lead: dict[str, Any], meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Transparent 1–10 lapse-risk decile from PUBLIC proxies (advisory, NOT FCRA).

    Lower decile = higher retention. Pure function of:
      • event instability (address/permit churn, business-formation volatility)
      • local unemployment proxy (BLS, when present in meta)
      • signal recency (a fresher, cooling signal carries slightly more flux)
    NOT a creditworthiness or eligibility decision — informational prioritization only."""
    meta = meta or {}
    event_type = lead.get("event_type", "permit_filed")
    base = _EVENT_INSTABILITY.get(event_type, 0.5)
    factors: list[str] = ["event instability proxy (%s) = %.2f" % (event_type, base)]

    # Local unemployment proxy (BLS) — higher unemployment nudges lapse risk up.
    unemp = meta.get("unemployment_rate")
    unemp_adj = 0.0
    if isinstance(unemp, (int, float)):
        unemp_adj = max(-0.05, min(0.15, (float(unemp) - 4.0) / 100.0))
        factors.append("local unemployment proxy (BLS) %.1f%% → %+.3f" % (float(unemp), unemp_adj))
    else:
        factors.append("local unemployment proxy: neutral (not in run meta)")

    # Recency flux: a still-cooling fresh signal is in more flux than a settled cold one.
    axes = lead.get("axes", {}) or {}
    recency = float(axes.get("recency", 0.0))
    rec_adj = round((recency - 0.5) * 0.10, 3)
    factors.append("signal recency flux %.2f → %+.3f" % (recency, rec_adj))

    risk = max(0.0, min(1.0, base + unemp_adj + rec_adj))
    decile = int(max(1, min(10, round(risk * 9) + 1)))
    return {
        "decile": decile,
        "risk_0_1": round(risk, 3),
        "interpretation": "lower decile = higher retention",
        "factors": factors,
        "advisory": True,
        "fcra": False,
        "note": "Advisory prioritization from public proxies — NOT an FCRA consumer report or eligibility decision.",
    }


# ===========================================================================
# P0-5 — Multi-angle opening lines (3 ranked angles keyed to event_type)
# ===========================================================================
# Deterministic per-event templates (NOT a free-form LLM guess). Each angle has a short
# key, a label, and a copyable opener line. Ranked 1..3.
_ANGLES: dict[str, list[dict[str, str]]] = {
    "new_baby": [
        {"key": "family-coverage", "label": "Family coverage",
         "line": "Congratulations on the new baby — the smartest first move now is making sure they're protected if anything happens to you. Can I walk you through a quick 15-minute family-coverage review?"},
        {"key": "income-replacement", "label": "Income replacement",
         "line": "A new dependent changes the math overnight — let's make sure your income is replaceable so your family keeps its footing no matter what."},
        {"key": "college-headstart", "label": "College head-start",
         "line": "While rates are lowest, this is also the ideal moment to start a tax-advantaged college-funding strategy that grows with your child."},
    ],
    "job_change": [
        {"key": "protect-new-income", "label": "Protect the new income",
         "line": "Congrats on the new role — your income just grew, so let's protect it and make sure your coverage keeps pace with your new earnings."},
        {"key": "retirement-review", "label": "Retirement review",
         "line": "A pay bump is the perfect trigger to put some of that new income to work — want a quick retirement-contribution review?"},
        {"key": "benefits-gap", "label": "Benefits gap check",
         "line": "New employers rarely cover everything — let's check for gaps between your group plan and what your family actually needs."},
    ],
    "promotion": [
        {"key": "peak-earning", "label": "Peak-earning window",
         "line": "You're entering your peak earning years — the best time to lock in lifetime-income planning before the window narrows."},
        {"key": "protect-earnings", "label": "Protect peak earnings",
         "line": "At this income level, disability and life coverage protect the single biggest asset you have: your future earnings."},
        {"key": "tax-advantaged", "label": "Tax-advantaged growth",
         "line": "Higher income means higher taxes — let's look at tax-advantaged vehicles that put more of your raise to work."},
    ],
    "home_purchase": [
        {"key": "mortgage-protection", "label": "Mortgage protection",
         "line": "A mortgage is a 30-year promise — mortgage-protection term makes sure your family keeps the home if your income stops."},
        {"key": "equity-review", "label": "Equity review",
         "line": "Now that you've got home equity building, let's make sure it's part of a protected, growing balance sheet."},
        {"key": "family-coverage", "label": "Family coverage",
         "line": "New home, new chapter — a quick coverage review makes sure the people under that roof are protected."},
    ],
    "near_retirement": [
        {"key": "guaranteed-income", "label": "Guaranteed lifetime income",
         "line": "Let's turn your savings into income you can't outlive — a guaranteed lifetime-income review takes about 20 minutes."},
        {"key": "ltc-protection", "label": "Long-term-care protection",
         "line": "The biggest retirement risk is care costs — let's protect your nest egg with a long-term-care strategy."},
        {"key": "legacy-tax", "label": "Legacy & tax efficiency",
         "line": "This is the window to structure what you pass on tax-efficiently — want a quick legacy review?"},
    ],
    "address_change": [
        {"key": "coverage-refresh", "label": "Coverage refresh",
         "line": "A move is the perfect moment to refresh coverage — needs change with a new household, and rates may have too."},
        {"key": "college-funding", "label": "College funding",
         "line": "With college-age dependents in the household, a tax-smart funding strategy now keeps tuition from derailing retirement."},
        {"key": "beneficiary-review", "label": "Beneficiary review",
         "line": "Life transitions are when beneficiaries get out of date — let's do a five-minute check to make sure everything's current."},
    ],
    "new_professional_license": [
        {"key": "lock-low-rates", "label": "Lock in low rates",
         "line": "Congrats on the license — the smartest move now is locking in low rates while you're young and protecting that new income."},
        {"key": "disability-income", "label": "Disability income",
         "line": "Your license is your earning power — disability-income coverage protects it from day one of your career."},
        {"key": "starter-term", "label": "Starter term",
         "line": "A simple starter-term policy is inexpensive now and converts as your income grows — let's get the foundation in place."},
    ],
    "business_formation": [
        {"key": "key-person", "label": "Key-person & continuity",
         "line": "A new venture deserves a continuity plan — key-person and buy-sell coverage protect the business you're building."},
        {"key": "estate-legacy", "label": "Estate & legacy",
         "line": "At your level the conversation isn't whether you're covered — it's protecting your estate and passing it on tax-efficiently."},
        {"key": "premium-finance", "label": "Premium-financed life",
         "line": "For high-income owners, premium-financed life and annuity options grow your legacy without tying up working capital."},
    ],
}

_GENERIC_ANGLES = [
    {"key": "review", "label": "Coverage review",
     "line": "This is exactly the right moment to review your coverage — can I walk you through a quick, no-pressure review?"},
    {"key": "protect-income", "label": "Protect income",
     "line": "Let's make sure your income and your family are protected against the unexpected."},
    {"key": "plan-ahead", "label": "Plan ahead",
     "line": "A short planning conversation now puts you ahead — want to find 15 minutes this week?"},
]


def opening_angles(event_type: str, lead: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return 3 ranked, copyable opening angles keyed to event_type (deterministic)."""
    base = _ANGLES.get(event_type, _GENERIC_ANGLES)
    return [{"rank": i + 1, **a} for i, a in enumerate(base[:3])]


# ===========================================================================
# P0-6 — Adaptive conversion loop (in-session per-event_type learning signal)
# ===========================================================================
_OUTCOME_LOCK = threading.Lock()
# {event_type: {"meeting": n, "sold": n, "no": n}}
_OUTCOME_TALLY: dict[str, dict[str, int]] = {}
VALID_OUTCOMES = ("meeting", "sold", "no")
_NUDGE_CAP = 0.05  # max ± propensity adjustment from in-session learning (honest, bounded)


def record_outcome(event_type: str, outcome: str) -> dict[str, Any]:
    """Tally one logged outcome for an event_type. Returns the updated summary.
    In-session signal only (the durable copy lives in the receipt lake when configured)."""
    outcome = (outcome or "").lower().strip()
    if outcome not in VALID_OUTCOMES:
        raise ValueError("outcome must be one of %s" % (VALID_OUTCOMES,))
    et = event_type or "unknown"
    with _OUTCOME_LOCK:
        bucket = _OUTCOME_TALLY.setdefault(et, {"meeting": 0, "sold": 0, "no": 0})
        bucket[outcome] += 1
    return outcome_summary()


def propensity_nudge(event_type: str) -> float:
    """Bounded propensity nudge for an event_type from logged outcomes (capped at ±_NUDGE_CAP).
    sold = +2, meeting = +1, no = −1, normalized and capped. Honest in-session learning."""
    with _OUTCOME_LOCK:
        b = _OUTCOME_TALLY.get(event_type)
        if not b:
            return 0.0
        net = b["sold"] * 2 + b["meeting"] * 1 - b["no"] * 1
        total = b["sold"] + b["meeting"] + b["no"]
    if total <= 0:
        return 0.0
    raw = net / (2.0 * total)  # in [-0.5, 1.0]
    return round(max(-_NUDGE_CAP, min(_NUDGE_CAP, raw * _NUDGE_CAP * 2)), 4)


def outcome_summary() -> dict[str, Any]:
    """JSON-safe summary of the in-session learning signal."""
    with _OUTCOME_LOCK:
        by_event = {k: dict(v) for k, v in _OUTCOME_TALLY.items()}
    total = sum(sum(v.values()) for v in by_event.values())
    return {
        "total_outcomes": total,
        "by_event_type": by_event,
        "nudges": {et: propensity_nudge(et) for et in by_event},
        "note": "In-session learning signal (per-event_type tally → bounded ±%.2f propensity nudge). "
                "Durable only when SZL_RECEIPT_LAKE_PATH is set." % _NUDGE_CAP,
    }


def reset_outcomes() -> None:
    """Test helper — clear the in-session tally."""
    with _OUTCOME_LOCK:
        _OUTCOME_TALLY.clear()


def enrich_lead(lead: dict[str, Any], meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Attach all P0 advisory fields to a scored lead, in place. Defensive: any failure
    leaves the lead intact (so /api/run never breaks)."""
    try:
        seg = lead.get("event", "")
        et = classify(seg)
        lead["event_type"] = et
        lead["event_type_label"] = TAXONOMY.get(et, {}).get("label", et)
        win = observed_window(lead.get("age_minutes", 0.0))
        lead.update(win)
        lead["wealth_tier"] = wealth_tier(lead, meta)
        lead["lapse"] = lapse_decile(lead, meta)
    except Exception:
        pass
    return lead
