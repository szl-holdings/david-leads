# SPDX-License-Identifier: Apache-2.0
"""Bounded Ouroboros Director for David Leads.

This is deterministic orchestration over the existing SZL engines. It is not an
LLM and it never sends outreach, changes a lead, or calls a mutating tool. Each
step re-scores the current public-signal state, applies the non-compensatory
compliance gate, attaches the confidence/fusion/formula evidence already used by
the product, routes the lead, and emits a reversible proposal plus a trace.
"""
from __future__ import annotations

from typing import Any

from . import formulas as fm
from . import frontier as fr
from . import routing as rt
from . import scoring as sc
from . import work as wk


MAX_STEPS = 8
DEFAULT_TOP_K = 5


def _avg_score(leads: list[dict[str, Any]]) -> float:
    eligible = [float(l.get("score", 0.0)) for l in leads]
    return round(sum(eligible) / max(1, len(eligible)), 4)


def _proposal(lead: dict[str, Any], brief: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    compliance = lead.get("compliance") or fr.compliance_axis(lead)
    if not compliance.get("clear", False):
        action, reason = "SUPPRESS", "compliance gate blocked outreach"
    elif lead.get("bucket") == "HOT" and (lead.get("confidence") or {}).get("level") in {"High", "Medium"}:
        action, reason = "REVIEW_CALL", "high-priority lead with non-trivial public corroboration"
    elif lead.get("bucket") == "WARM":
        action, reason = "REVIEW", "warm lead; inspect the signed brief before deciding"
    else:
        action, reason = "WATCH", "nurture/watch; no automatic outreach"
    return {
        "action": action,
        "reason": reason,
        "lead_id": lead.get("id"),
        "recommended_agent_id": route.get("recommended_agent_id"),
        "recommended_agent": route.get("recommended_agent"),
        "formula_ids": (brief.get("grounding") or {}).get("formulas_used", []),
        "receipt_id": lead.get("receipt_id"),
        "mutating_action": False,
    }


def _decorate(leads: list[dict[str, Any]], meta: dict[str, Any], top_k: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    conversion: dict[str, float] = {}
    roster = rt.DEFAULT_ROSTER
    ranked = sorted(leads, key=lambda l: float(l.get("score", 0.0)), reverse=True)
    decorated: list[dict[str, Any]] = []
    proposals: list[dict[str, Any]] = []
    for lead in ranked[: max(1, top_k)]:
        # Re-use the canonical engines; do not reimplement Lambda or confidence math here.
        compliance = fr.compliance_axis(lead)
        lead_view = dict(lead)
        lead_view["compliance"] = compliance
        brief = fm.build_signed_brief(lead_view)
        route = rt.route_lead(lead_view, roster, meta, conversion)
        decorated.append({
            "lead_id": lead.get("id"),
            "score": lead.get("score"),
            "bucket": lead.get("bucket"),
            "compliance": compliance,
            "confidence": lead.get("confidence") or fr.confidence_band(float(lead.get("score", 0.0)), 1, lead.get("axes", {})),
            "track": lead.get("track") or fr.fuse_signals([{
                "intensity": sum(float(v) for v in (lead.get("axes") or {}).values()) / max(1, len(lead.get("axes") or {})),
                "days_ago": float(lead.get("hours_since") or 0.0) / 24.0,
                "label": "lead-axis aggregate",
            }]),
            "brief": brief,
            "routing": route,
        })
        proposals.append(_proposal(lead_view, brief, route))
    return decorated, proposals


def run_cycle(meta: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run one bounded, read-only director cycle over the canonical lead state."""
    cfg = config or {}
    requested_steps = int(cfg.get("max_steps", 4))
    max_steps = min(MAX_STEPS, max(1, requested_steps))
    top_k = min(20, max(1, int(cfg.get("top_k", DEFAULT_TOP_K))))
    step_minutes = max(0.0, float(cfg.get("step_minutes", sc.HALF_LIFE_MIN / 4.0)))
    label = str(cfg.get("label", "david-leads.oroboros.director"))[:96]
    step_outputs: list[dict[str, Any]] = []

    def step(state: dict[str, Any], index: int) -> dict[str, Any]:
        age = float(state.get("age_minutes", 0.0)) + (0.0 if index == 0 else step_minutes)
        leads = sc.build_leads(meta or {}, age_minutes=age)
        decorated, proposals = _decorate(leads, meta or {}, top_k)
        output = {
            "age_minutes": round(age, 3),
            "avg_score": _avg_score(leads),
            "eligible_leads": sum(1 for l in leads if (l.get("compliance") or {}).get("clear", True)),
            "proposals": proposals,
            "evidence": decorated,
            "data_state": "LIVE" if int((meta or {}).get("live_count", 0)) > 0 else "SAMPLE",
        }
        step_outputs.append(output)
        return {"state": {"age_minutes": age, "avg_score": output["avg_score"]}, "output": output}

    def delta(prev: dict[str, Any], nxt: dict[str, Any]) -> float:
        return abs(float(nxt.get("avg_score", 0.0)) - float(prev.get("avg_score", 0.0)))

    trace = wk.run_loop(
        {"age_minutes": 0.0, "avg_score": 0.0}, step, delta,
        config={"maxSteps": max_steps, "convergenceThreshold": float(cfg.get("convergence_threshold", 0.1)), "label": label},
    )
    loop_receipt = wk.build_loop_receipt(trace)
    final = step_outputs[-1] if step_outputs else {"proposals": [], "evidence": []}
    return {
        "agent": "Ouroboros Director",
        "version": "1.0",
        "mode": "bounded-read-only",
        "formula_registry": [
            {"id": "LambdaMonotonicity", "source": "app.formulas", "role": "priority consistency"},
            {"id": "FalsePosition", "source": "app.formulas", "role": "decay/threshold sensitivity"},
            {"id": "SummationInvariant", "source": "app.formulas", "role": "brief integrity"},
            {"id": "LambdaCompliance", "source": "app.frontier", "role": "non-compensatory outreach gate"},
            {"id": "ConfidenceBand", "source": "app.frontier", "role": "public-source uncertainty"},
            {"id": "FusedTrack", "source": "app.frontier", "role": "heating/cooling estimate"},
            {"id": "AdvisorRouting", "source": "app.routing", "role": "best-fit human review queue"},
        ],
        "trace": trace,
        "final": final,
        "loop_receipt": loop_receipt,
        "limits": [
            "No outreach, CRM write, or external mutation is executed.",
            "Public signals are claims; fused tracks and confidence bands are ESTIMATES.",
            "Lambda remains Conjecture 1 and is advisory, never a truth oracle.",
            "A human must approve any contact or downstream action.",
        ],
    }


__all__ = ["run_cycle", "MAX_STEPS"]
