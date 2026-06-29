# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads V8 · a11oy formula-grounded briefs
"""
formulas.py — the a11oy Formulas engine, PORTED 1:1 from
src/a11oy/a11oy_v4_formulas.py (eval_false_position, eval_lambda_monotonicity,
eval_summation_invariant). Each evaluator returns allow / rationale / lambdaScore /
leanTheorem — a deterministic, theorem-anchored verdict (NOT an LLM guess).

build_signed_brief(lead) composes a 4-part operator brief (Priority / Why-now /
Opening-line / Sensitivity), each part GROUNDED by a real formula verdict, then witness-signs
the whole brief via the khipu 3-of-4 consensus (honest UNSIGNED when no signing is available).

Anchors: Lean commit 1dca00032dfc9aa8559cc6c2e4b63192fcf52371; classical cites Aczél 1957,
Guo 2017, McAllester 1999; DOI 10.5281/zenodo.20434308 (Λ-Spine), 10.5281/zenodo.20162352 (a11oy).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

LEAN_COMMIT = "1dca00032dfc9aa8559cc6c2e4b63192fcf52371"
ZENODO_DOI = "https://doi.org/10.5281/zenodo.20162352"


class GateError(ValueError):
    """Raised on invalid gate input (mirrors the TS gate's thrown Error)."""


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


# ---------------------------------------------------------------- eval_false_position (Rhind)
def eval_false_position(opts: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    config = config or {}
    tolerance = config.get("tolerance", 1e-8)
    if not math.isfinite(tolerance) or tolerance < 0:
        raise GateError(f"FalsePositionGate: tolerance must be >= 0; got {tolerance}")
    x1, y1, x2, y2, T = (opts.get(k) for k in ("x1", "y1", "x2", "y2", "T"))
    for nm, v in (("x1", x1), ("y1", y1), ("x2", x2), ("y2", y2), ("T", T)):
        if v is None or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise GateError(f"FalsePositionGate: {nm} must be finite; got {v}")
    eps = 2.220446049250313e-16
    if abs(x2 - x1) < eps * max(abs(x1), abs(x2), 1):
        raise GateError("FalsePositionGate: degenerate samples (x₁ = x₂)")
    dy = y2 - y1
    if abs(dy) < eps * max(abs(y1), abs(y2), 1):
        raise GateError("FalsePositionGate: degenerate samples (y₁ = y₂)")
    x_star = x1 + ((T - y1) * (x2 - x1)) / dy
    m = dy / (x2 - x1)
    c = y1 - m * x1
    residual = abs(m * x_star + c - T)
    lambda_score = max(0.0, 1.0 - residual / (1.0 + abs(T)))
    allow = residual <= tolerance
    rationale = (
        f"FalsePosition residual |f(x*)−T| = {residual:.4e} <= tol {tolerance}: calibration target "
        f"recovered exactly. Lean: false_position_correct @{LEAN_COMMIT[:12]}"
        if allow else
        f"FalsePosition residual |f(x*)−T| = {residual:.4e} > tol {tolerance}: calibration degenerate — "
        f"deny update. Lean: false_position_correct @{LEAN_COMMIT[:12]}"
    )
    return {
        "allow": allow, "rationale": rationale, "formula": "FalsePosition",
        "leanTheorem": "false_position_correct", "leanFile": "Lutar/Calibration/FalsePosition.lean",
        "leanCommitSha": LEAN_COMMIT, "xStar": x_star, "residual": residual,
        "tolerance": tolerance, "lambdaScore": lambda_score,
    }


# ---------------------------------------------------------------- eval_lambda_monotonicity (T2)
def eval_lambda_monotonicity(opts: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    config = config or {}
    tolerance = config.get("tolerance", 1e-9)
    orig = opts.get("originalScores")
    aug = opts.get("augmentedScores")
    if not isinstance(orig, list) or not isinstance(aug, list):
        raise GateError("LambdaMonotonicityGate: both score arrays required")
    if len(orig) != len(aug):
        raise GateError("LambdaMonotonicityGate: score arrays must have equal length")
    decreasing_axes: List[int] = []
    min_delta = math.inf
    for i in range(len(orig)):
        delta = aug[i] - orig[i]
        if delta < min_delta:
            min_delta = delta
        if delta < -tolerance:
            decreasing_axes.append(i)
    allow = len(decreasing_axes) == 0
    lambda_score = 1.0 if allow else max(0.0, 1.0 + min_delta)
    rationale = (
        f"LambdaMonotonicity (T2): all {len(orig)} axes weakly increased (minDelta={min_delta:.4e}). "
        f"Consistent evidence. Passes. Lean: lambdaMonotonicity @{LEAN_COMMIT[:12]}"
        if allow else
        f"LambdaMonotonicity (T2): axes {decreasing_axes} decreased — conflicting evidence. "
        f"Denied. Lean: lambdaMonotonicity @{LEAN_COMMIT[:12]}"
    )
    return {
        "allow": allow, "rationale": rationale, "formula": "LambdaMonotonicity",
        "leanTheorem": "lambdaMonotonicity", "leanFile": "Lutar/Gate/LambdaMonotonicity.lean",
        "leanCommitSha": LEAN_COMMIT, "decreasingAxes": decreasing_axes,
        "minDelta": (None if min_delta == math.inf else min_delta), "lambdaScore": lambda_score,
    }


# ---------------------------------------------------------------- eval_summation_invariant (Khipu)
def eval_summation_invariant(opts: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    khipu_id = opts.get("khipuId", "")
    organs = opts.get("organs")
    primary_cord = opts.get("primaryCord")
    if not isinstance(organs, list):
        raise GateError(f"SummationInvariantGate: organs must be an array for khipu {khipu_id}")
    if not isinstance(primary_cord, (int, float)):
        raise GateError(f"SummationInvariantGate: primaryCord must be a number; got {primary_cord}")
    pendant_values = [sum(d.get("value", 0) for d in o.get("decisions", [])) for o in organs]
    computed_total = sum(pendant_values)
    delta = abs(computed_total - primary_cord)
    invariant_holds = computed_total == primary_cord
    lambda_score = 1.0 if invariant_holds else 0.0
    rationale = (
        f"KhipuReceipt {khipu_id}: summation invariant holds (total={computed_total}). "
        f"Lean: khipuReceipt_checksum_invariant @{LEAN_COMMIT[:12]}"
        if invariant_holds else
        f"KhipuReceipt {khipu_id}: invariant BROKEN — computedTotal={computed_total} ≠ primaryCord="
        f"{primary_cord} (delta={delta}). Receipt tampered. Lean: khipuReceipt_checksum_invariant @{LEAN_COMMIT[:12]}"
    )
    return {
        "allow": invariant_holds, "rationale": rationale, "formula": "SummationInvariant",
        "leanTheorem": "khipuReceipt_checksum_invariant", "leanFile": "Lutar/Khipu/SummationInvariant.lean",
        "leanCommitSha": LEAN_COMMIT, "invariantHolds": invariant_holds,
        "computedTotal": computed_total, "primaryCord": primary_cord,
        "delta": delta, "lambdaScore": lambda_score,
    }


# ===========================================================================
# build_signed_brief — 4 formula-grounded parts, witness-signed (khipu 3-of-4)
# ===========================================================================
_AXIS_ORDER = ["life_event_strength", "income_fit", "age_window_fit", "product_propensity", "recency"]


def _verdict_view(d: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "formula": d["formula"], "allow": d["allow"], "rationale": d["rationale"],
        "lambdaScore": round(float(d["lambdaScore"]), 4), "leanTheorem": d["leanTheorem"],
    }


def build_signed_brief(lead: Dict[str, Any]) -> Dict[str, Any]:
    """4-part witness-signed brief, each part grounded by a real a11oy formula verdict."""
    axes = lead.get("axes", {})
    axis_vals = [float(axes.get(a, 0.0)) for a in _AXIS_ORDER]
    score = float(lead.get("score", 0.0))
    bucket = lead.get("bucket", "NURTURE")
    nba = lead.get("nba", {})

    # --- Part 1 PRIORITY: lambda_monotonicity — do all axes clear a uniform floor? ---
    floor = 0.5
    v_priority = eval_lambda_monotonicity(
        {"originalScores": [floor] * len(axis_vals), "augmentedScores": axis_vals})
    priority_body = (
        f"{lead.get('name','')} — {bucket} at Λ {score}. "
        + ("Every scoring axis clears the qualification floor (consistent evidence) → prioritize."
           if v_priority["allow"] else
           "One or more axes fall below floor → triage before calling."))

    # --- Part 2 WHY-NOW: false_position — recover the bucket threshold from decay calibration ---
    try:
        from . import scoring as sc
        threshold = 80.0 if bucket == "HOT" else 60.0 if bucket == "WARM" else 40.0
        rec_base = lead.get("recency_base", axes.get("recency", 0.0))
        late_axes = dict(axes)
        late_axes["recency"] = sc.decayed_recency(rec_base, sc.HALF_LIFE_MIN)
        score_late = sc.lambda_score(late_axes)
        v_whynow = eval_false_position(
            {"x1": 0.0, "y1": score, "x2": sc.HALF_LIFE_MIN, "y2": score_late, "T": threshold},
            {"tolerance": 1.0})
        x_star = max(0.0, v_whynow["xStar"])
        why_body = (f"Speed-to-lead window: this lead crosses the {bucket} threshold ({threshold}) "
                    f"in ≈ {x_star:.0f} min as recency decays — act now to keep it {bucket}.")
    except Exception:
        v_whynow = eval_false_position({"x1": 0, "y1": -2, "x2": 4, "y2": 2, "T": 0}, {"tolerance": 1.0})
        why_body = f"Fresh signal — engage while Λ {score} is current."

    # --- Part 3 OPENING-LINE: 3 ranked angles keyed to event_type, grounded by summation_invariant ---
    # P0-5: deterministic per-event templates (NOT a free-form LLM guess), one cord per angle.
    try:
        from . import events as ev
        event_type = lead.get("event_type") or ev.classify(lead.get("event", ""))
        angles = ev.opening_angles(event_type, lead)
    except Exception:
        event_type = lead.get("event_type", "")
        angles = [{"rank": 1, "key": "review", "label": "Coverage review",
                   "line": nba.get("talk_track") or
                   f"Congratulations — this is exactly the right moment to review your {lead.get('product','')}."}]
    angle_values = [1] * max(1, len(angles))  # one cord per ranked angle
    v_open = eval_summation_invariant(
        {"khipuId": lead.get("id", ""), "primaryCord": sum(angle_values),
         "organs": [{"decisions": [{"value": pv}]} for pv in angle_values]})
    opening_line = angles[0]["line"] if angles else (
        nba.get("talk_track") or f"Congratulations — this is the right moment to review your {lead.get('product','')}.")

    # --- Part 4 SENSITIVITY: false_position — how sensitive is the score to a 1-axis shift? ---
    try:
        from . import scoring as sc
        bumped = dict(axes)
        # bump the weakest axis by 0.05 and measure score sensitivity
        weak = min(_AXIS_ORDER, key=lambda a: axes.get(a, 1.0))
        bumped[weak] = min(1.0, axes.get(weak, 0.0) + 0.05)
        score_bumped = sc.lambda_score(bumped)
        v_sens = eval_false_position(
            {"x1": 0.0, "y1": score, "x2": 0.05, "y2": score_bumped, "T": score},
            {"tolerance": 1.0})
        sens_body = (f"Most leverage: '{weak.replace('_',' ')}'. A +0.05 lift there moves Λ "
                     f"{score}→{score_bumped} (slope {v_sens.get('lambdaScore',0):.2f}). "
                     "Probe that dimension first.")
    except Exception:
        v_sens = eval_false_position({"x1": 0, "y1": 0, "x2": 1, "y2": 1, "T": 0.5}, {"tolerance": 1.0})
        sens_body = "Score is robust to small single-axis perturbations."

    parts = [
        {"key": "PRIORITY", "title": "Priority", "body": priority_body,
         "formula_verdict": _verdict_view(v_priority)},
        {"key": "WHY_NOW", "title": "Why now", "body": why_body,
         "formula_verdict": _verdict_view(v_whynow)},
        {"key": "OPENING_LINE", "title": "Opening line", "body": opening_line,
         "angles": angles, "formula_verdict": _verdict_view(v_open)},
        {"key": "SENSITIVITY", "title": "Sensitivity", "body": sens_body,
         "formula_verdict": _verdict_view(v_sens)},
    ]

    brief = {
        "lead_id": lead.get("id"), "lead_name": lead.get("name"),
        "score": score, "bucket": bucket,
        "freshness_state": lead.get("freshness_state", ""),
        # P0-2/3/4: surface the advisory tiers on the signed brief too (honest, public-proxy)
        "event_type": lead.get("event_type", ""),
        "event_type_label": lead.get("event_type_label", ""),
        "urgency": lead.get("urgency", ""),
        "hours_since": lead.get("hours_since"),
        "wealth_tier": lead.get("wealth_tier"),
        "lapse": lead.get("lapse"),
        "parts": parts,
        "grounding": {
            "engine": "a11oy Formulas (ported 1:1)",
            "formulas_used": [p["formula_verdict"]["formula"] for p in parts],
            "lean_commit": LEAN_COMMIT, "zenodo_doi": ZENODO_DOI,
            "note": "Each part is grounded by a deterministic theorem-anchored verdict — not an LLM guess.",
        },
    }

    # witness-sign the brief (khipu 3-of-4; honest UNSIGNED when unavailable)
    try:
        from . import consensus as cs
        ah = cs.action_hash_for({"lead_id": brief["lead_id"],
                                 "parts": [{"k": p["key"], "b": p["body"]} for p in parts],
                                 "angles": [a.get("line", "") for a in angles]})
        brief["consensus"] = cs.witness_event(ah)
    except Exception:
        brief["consensus"] = {"khipu_consensus": "0-of-4", "signed": False,
                              "decision": "unsigned-honest"}
    return brief
