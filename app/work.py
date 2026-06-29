# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads V8 · ouroboros bounded work loop
"""
work.py — the Ouroboros bounded work loop, PORTED 1:1 from
src/ouroboros/src/loop-kernel.ts (runLoop) + types.ts + receipt-emitter.ts.

runLoop(initial_state, step, delta, consistency=None, config=None) runs steps until ONE of
four exit conditions fires:
  • converged       — adjacent-state delta ≤ convergenceThreshold
  • consistent      — ONLINE PROXY: two successive outputs agree ≥ earlyExitConsistency
  • aborted         — step returned {"abort": True}
  • budgetExhausted — hit maxSteps

It returns a LoopTrace dict (the trace IS the product). Honest: the kernel does NOT compute a
Λ score or measure energy, so the emitted loop receipt carries governance.lambda = null and
energy.label = "UNAVAILABLE" — never fabricated.

run_territory_pulse(...) drives a real bounded loop over the David-Leads time-decay state and
mints a khipu 3-of-4 witnessed change-event receipt into the append-only receipt_lake per step.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

DEFAULT_MAX_STEPS = 8
DEFAULT_CONVERGENCE = 1e-3
DEFAULT_EARLY_EXIT_CONSISTENCY = 1.01  # disabled by default (>1 sentinel)
DEFAULT_SAFE_EXIT_CONSISTENCY = 0.95


def _now_ms() -> float:
    return time.perf_counter() * 1000.0


def _gen_id() -> str:
    import random
    return f"loop_{int(time.time()*1000):x}_{random.randint(0, 0xFFFFFF):06x}"


def run_loop(initial_state: Any, step: Callable[[Any, int], dict],
             delta: Callable[[Any, Any], float],
             consistency: Optional[Callable[[Any, Any], float]] = None,
             config: Optional[dict] = None) -> dict:
    """Bounded recursion with measurable convergence (ouroboros runLoop port).

    step(state, index) -> {"state": next, "output": out} | {"abort": True}
    delta(prev, next) -> magnitude of change in [0, ∞)
    consistency(a, b) -> agreement in [0, 1] (optional)
    Returns a LoopTrace dict."""
    config = config or {}
    max_steps = config.get("maxSteps", DEFAULT_MAX_STEPS)
    convergence_threshold = config.get("convergenceThreshold", DEFAULT_CONVERGENCE)
    raw_early = config.get("earlyExitConsistency", DEFAULT_EARLY_EXIT_CONSISTENCY)
    early_exit_consistency = max(0.0, raw_early)
    raw_safe = config.get("safeExitConsistency", DEFAULT_SAFE_EXIT_CONSISTENCY)
    safe_exit_consistency = max(0.0, min(1.0, raw_safe))
    loop_id = config.get("id") or _gen_id()
    label = config.get("label", "ouroboros.loop")

    steps: list[dict] = []
    state = initial_state
    prev_output: Any = None
    exit_reason = "budgetExhausted"
    last_output: Any = None

    started_at = _now_ms()

    for i in range(max_steps):
        step_started_at = _now_ms()
        # Kernel never swallows errors — let any throw from step propagate to the caller.
        result = step(state, i)

        if isinstance(result, dict) and result.get("abort") is True:
            exit_reason = "aborted"
            break

        nxt = result["state"]
        output = result.get("output")

        delta_magnitude = 0.0 if i == 0 else max(0.0, delta(state, nxt))
        step_record = {
            "index": i,
            "state": nxt,
            "output": output,
            "deltaMagnitude": delta_magnitude,
            "durationMs": max(0.0, _now_ms() - step_started_at),
        }
        steps.append(step_record)

        state = nxt

        # Online convergence — adjacent-state delta at/below threshold.
        if i > 0 and delta_magnitude <= convergence_threshold:
            exit_reason = "converged"
            last_output = output if output is not None else last_output
            break

        # Online step-stability proxy — successive outputs agree.
        if (consistency is not None and output is not None and prev_output is not None
                and i > 0 and early_exit_consistency <= 1.0
                and consistency(prev_output, output) >= early_exit_consistency):
            exit_reason = "consistent"
            last_output = output
            break

        prev_output = output if output is not None else prev_output
        last_output = output if output is not None else last_output

    total_duration_ms = max(0.0, _now_ms() - started_at)
    final_output = last_output

    # Retroactive cross-step consistency: each intermediate output scored vs the FINAL output.
    earliest_safe_exit = -1
    if consistency is not None and final_output is not None:
        for s in steps:
            c = consistency(s.get("output"), final_output)
            s["consistency"] = c
            if (earliest_safe_exit == -1 and c >= safe_exit_consistency
                    and s["index"] < len(steps) - 1):
                earliest_safe_exit = s["index"]

    trace = {
        "id": loop_id,
        "label": label,
        "steps": steps,
        "finalState": state,
        "finalOutput": final_output,
        "exitReason": exit_reason,
        "stepsRun": len(steps),
        "maxSteps": max_steps,
        "earliestSafeExit": earliest_safe_exit,
        "totalDurationMs": round(total_duration_ms, 3),
    }
    return trace


def build_loop_receipt(trace: dict) -> dict:
    """Honest loop receipt (receipt-emitter.ts port): Λ is NOT computed by the kernel →
    governance.lambda = null; no energy meter → energy.label = 'UNAVAILABLE'. Never fabricated."""
    canonical = json.dumps({
        "id": trace["id"], "label": trace["label"], "exitReason": trace["exitReason"],
        "stepsRun": trace["stepsRun"], "maxSteps": trace["maxSteps"],
    }, separators=(",", ":"))
    rid = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {
        "id": rid,
        "ts": datetime.now(timezone.utc).isoformat(),
        "organ": "ouroboros",
        "decision": trace["exitReason"],
        "governance": {"lambda": None},  # honest null — kernel computes no Λ
        "energy": {"label": "UNAVAILABLE", "joules": None},
        "meta": {
            "loopId": trace["id"], "label": trace["label"],
            "stepsRun": trace["stepsRun"], "maxSteps": trace["maxSteps"],
            "earliestSafeExit": trace["earliestSafeExit"],
        },
    }


def _witness(action_hash: str) -> Optional[dict]:
    """Best-effort khipu 3-of-4 witness over a change-event; never breaks the loop."""
    try:
        from . import consensus as cs
        return cs.witness_event(action_hash)
    except Exception:
        return None


def run_territory_pulse(meta: Optional[dict] = None, config: Optional[dict] = None) -> dict:
    """Run ONE bounded ouroboros loop over the David-Leads time-decay state.

    Each step advances the observation age, rescores every lead through the canonical Λ
    aggregator, and mints a khipu 3-of-4 witnessed change-event receipt into the append-only
    receipt_lake. The loop converges when the aggregate Λ across leads stops moving.

    Returns {"trace": LoopTrace, "events": [change-event receipts], "loop_receipt": receipt}."""
    from . import scoring as sc
    try:
        from . import receipt_lake as lake
    except Exception:
        lake = None

    meta = meta or {}
    config = config or {}
    step_minutes = float(config.get("stepMinutes", sc.HALF_LIFE_MIN / 4.0))

    emitted: list[dict] = []

    def _avg_score(age_min: float) -> float:
        leads = sc.build_leads(meta, age_minutes=age_min)
        return sum(l["score"] for l in leads) / max(len(leads), 1)

    def step(state: dict, index: int) -> dict:
        age = state["age_minutes"] + (0.0 if index == 0 else step_minutes)
        leads = sc.build_leads(meta, age_minutes=age)
        avg = sum(l["score"] for l in leads) / max(len(leads), 1)
        buckets = {"HOT": 0, "WARM": 0, "NURTURE": 0}
        for l in leads:
            buckets[l["bucket"]] += 1
        next_state = {"age_minutes": age, "avg_score": round(avg, 4)}

        # change-event: a state transition → mint a khipu 3-of-4 witnessed receipt
        event_body = {
            "kind": "territory-pulse-change-event",
            "loop_step": index,
            "age_minutes": round(age, 3),
            "avg_score": round(avg, 4),
            "buckets": buckets,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        action_hash = hashlib.sha256(
            json.dumps(event_body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        consensus = _witness(action_hash)
        receipt = {
            "id": "evt_" + action_hash[:16],
            "organ": "ouroboros",
            "decision": "pulse-step",
            "action_hash": action_hash,
            "payload": event_body,
            "consensus": consensus,
            "signed": bool(consensus and consensus.get("signed")),
        }
        emitted.append(receipt)
        if lake is not None:
            try:
                lake.append(receipt)
            except Exception:
                pass
        return {"state": next_state, "output": {"avg_score": round(avg, 4), "buckets": buckets}}

    def delta(prev: dict, nxt: dict) -> float:
        return abs(nxt["avg_score"] - prev["avg_score"])

    def consistency(a: Any, b: Any) -> float:
        if not a or not b:
            return 0.0
        diff = abs(a["avg_score"] - b["avg_score"])
        return max(0.0, 1.0 - diff / 100.0)

    initial = {"age_minutes": float(meta.get("age_minutes", 0.0)),
               "avg_score": round(_avg_score(float(meta.get("age_minutes", 0.0))), 4)}
    loop_cfg = {
        "label": "david.territory_pulse",
        "maxSteps": int(config.get("maxSteps", DEFAULT_MAX_STEPS)),
        "convergenceThreshold": float(config.get("convergenceThreshold", 0.1)),
        "safeExitConsistency": float(config.get("safeExitConsistency", DEFAULT_SAFE_EXIT_CONSISTENCY)),
    }
    trace = run_loop(initial, step, delta, consistency, loop_cfg)

    loop_receipt = build_loop_receipt(trace)
    if lake is not None:
        try:
            lake.append(loop_receipt)
        except Exception:
            pass

    return {"trace": trace, "events": emitted, "loop_receipt": loop_receipt}
