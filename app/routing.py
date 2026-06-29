# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads V8.3 · P2-1 best-fit advisor lead routing
"""
routing.py — pure-function lead → best-fit advisor matching (gap #8).

Scores each lead against a roster of advisors on three public/operational factors:
  • trigger specialty   — does the advisor specialize in this event_type?
  • territory overlap    — does the advisor cover the lead's state/region?
  • historical conversion — the advisor's logged conversion for this trigger (from the
                            producer benchmark / outcome tally), when available.

Honest: the demo roster has ONE real agent (David) plus 2–3 illustrative teammates
CLEARLY LABELLED "[illustrative roster]". No network, no fabrication of real people.
"""
from __future__ import annotations

from typing import Any

# David is the real agent; the rest are illustrative so the routing table has alternatives.
# Each advisor: id, name, real flag, covered states, and per-event_type specialty weights (0–1).
DEFAULT_ROSTER: list[dict[str, Any]] = [
    {
        "id": "david", "name": "David", "real": True, "label": "primary advisor",
        "states": ["NY", "NJ", "CT", "PA"],
        "specialties": {
            "new_baby": 0.95, "home_purchase": 0.90, "near_retirement": 0.85,
            "job_change": 0.80, "promotion": 0.80, "business_formation": 0.78,
            "new_professional_license": 0.82, "address_change": 0.70,
        },
    },
    {
        "id": "teammate_estate", "name": "A. Rivera", "real": False, "label": "[illustrative roster]",
        "states": ["NY", "NJ", "CT", "MA", "FL"],
        "specialties": {
            "business_formation": 0.95, "near_retirement": 0.92, "promotion": 0.85,
            "job_change": 0.70, "home_purchase": 0.65,
        },
    },
    {
        "id": "teammate_family", "name": "M. Chen", "real": False, "label": "[illustrative roster]",
        "states": ["NJ", "PA", "DE", "MD", "VA"],
        "specialties": {
            "new_baby": 0.96, "home_purchase": 0.93, "new_professional_license": 0.88,
            "address_change": 0.80, "job_change": 0.72,
        },
    },
]

# Weighting of the three factors (sum = 1.0). Specialty leads; territory + history support it.
_W_SPECIALTY = 0.50
_W_TERRITORY = 0.25
_W_HISTORY = 0.25


def _lead_state(lead: dict[str, Any], meta: dict[str, Any] | None) -> str:
    st = (lead.get("state") or (meta or {}).get("state") or "NY")
    return str(st).upper()


def _history_rate(agent: dict[str, Any], event_type: str,
                  conversion_by_event: dict[str, float] | None) -> tuple[float, bool]:
    """Return (rate_0_1, had_data). Roster-level historical conversion for this trigger,
    sourced from the producer benchmark when present; else neutral 0.5 (no penalty)."""
    if conversion_by_event and event_type in conversion_by_event:
        return max(0.0, min(1.0, float(conversion_by_event[event_type]))), True
    return 0.5, False


def route_lead(lead: dict[str, Any], roster: list[dict[str, Any]],
               meta: dict[str, Any] | None = None,
               conversion_by_event: dict[str, float] | None = None) -> dict[str, Any]:
    """Score one lead against the roster and return the best-fit advisor + alternatives."""
    event_type = lead.get("event_type") or "permit_filed"
    state = _lead_state(lead, meta)
    ranked = []
    for agent in roster:
        specialty = float(agent.get("specialties", {}).get(event_type, 0.4))
        territory = 1.0 if state in [s.upper() for s in agent.get("states", [])] else 0.4
        hist, had = _history_rate(agent, event_type, conversion_by_event)
        score = _W_SPECIALTY * specialty + _W_TERRITORY * territory + _W_HISTORY * hist
        basis_bits = [
            "specialty %.2f" % specialty,
            "territory %s" % ("match" if territory >= 1.0 else "out-of-area"),
            ("historical conversion %.0f%%" % (hist * 100)) if had else "no logged history (neutral)",
        ]
        ranked.append({
            "agent_id": agent["id"],
            "agent": agent["name"],
            "real": bool(agent.get("real")),
            "label": agent.get("label", ""),
            "score": round(score * 100, 1),
            "basis": " · ".join(basis_bits),
        })
    ranked.sort(key=lambda a: a["score"], reverse=True)
    best = ranked[0]
    return {
        "lead_id": lead.get("id"),
        "lead_name": lead.get("name"),
        "event_type": event_type,
        "state": state,
        "recommended_agent": best["agent"],
        "recommended_agent_id": best["agent_id"],
        "recommended_is_real": best["real"],
        "score": best["score"],
        "basis": best["basis"],
        "alternatives": ranked[1:],
    }


def route_leads(leads: list[dict[str, Any]] | None,
                roster: list[dict[str, Any]] | None = None,
                meta: dict[str, Any] | None = None,
                conversion_by_event: dict[str, float] | None = None) -> dict[str, Any]:
    """Route every lead to its best-fit advisor. Pure; returns a JSON-safe routing table.
    `conversion_by_event` is an optional {event_type: rate_0_1} map from the benchmark."""
    leads = leads or []
    roster = roster or DEFAULT_ROSTER
    table = []
    for l in leads:
        try:
            table.append(route_lead(l, roster, meta, conversion_by_event))
        except Exception:
            continue
    return {
        "roster": [
            {"id": a["id"], "name": a["name"], "real": bool(a.get("real")),
             "label": a.get("label", ""), "states": a.get("states", [])}
            for a in roster
        ],
        "routing": table,
        "factors": {"specialty": _W_SPECIALTY, "territory": _W_TERRITORY, "history": _W_HISTORY},
        "honest_note": "David is the real advisor; teammates are an [illustrative roster] so the "
                       "table can show alternatives. Routing uses public/operational factors only.",
    }


def conversion_by_event_from_benchmark(bench: dict[str, Any] | None) -> dict[str, float]:
    """Extract {event_type: conversion_rate_0_1} from a build_benchmark() result, if present."""
    out: dict[str, float] = {}
    if not bench:
        return out
    for row in bench.get("by_event_type", []) or []:
        et = row.get("event_type")
        pct = row.get("conversion_rate_pct")
        if et and isinstance(pct, (int, float)) and row.get("outcomes_logged", 0):
            out[et] = float(pct) / 100.0
    return out
