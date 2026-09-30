# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — david-leads vertical
"""Transparent lead scoring wired to SZL doctrine primitives.

The aggregator is the canonical estate Lambda-spine: weighted geometric mean
Lambda(x) = prod x_i^w_i, sum w_i = 1 (ported with attribution from
app/scoring.py, itself a drop-in of szl-lambda-gate puriq_os.lambda_aggregator).
Geometric mean means one weak axis pulls the whole score down — no lead looks
hot on a single strong signal. Every parameter below is disclosed, not tuned
behind a black box: this is the entire model.

Doctrine gates:
- Default DENY: a signal is admitted only if its source_class is permitted for
  the record AND it carries an evidence_ref. Denied signals are disclosed with
  reasons, never silently dropped and never scored.
- Zero-Bandaid: an axis with no admitted evidence reports value=None and
  truth_state=UNKNOWN; it is excluded from aggregation and shown as a hole.
- Law 4: a lead with zero admitted evidence scores INCOMPLETE — never a number.
- A synthetic record can never produce a VERIFIED real-world claim: its
  response truth_state is UNKNOWN by construction, however clean the math.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from .models import AxisResult, LeadRecord, Signal, SourceClass, TruthState
from . import receipts

# --- Disclosed model parameters (the whole "model card" fits in this file) ---
WEIGHTS = {"recency": 0.30, "corroboration": 0.30, "authority": 0.20, "completeness": 0.20}
RECENCY_HALF_LIFE_DAYS = 45.0   # a public event's timing value halves every 45 days
RECENCY_FLOOR = 0.05            # a stale event is faint, never zero (honest)
CORROBORATION_MAP = {1: 0.40, 2: 0.70}  # distinct independent sources; 3+ => 1.00
AUTHORITY_MAP = {1: 1.00, 2: 0.70, 3: 0.40}  # federal / state / other public record
BUCKETS = ((65.0, "RESEARCH_FIRST"), (40.0, "STANDARD"), (0.0, "MONITOR"))

# Default DENY policy. LICENSED_THIRD_PARTY is deliberately absent: no license
# is configured in this deployment, and the policy denies unless a rule allows.
_PERMITTED_ALWAYS = {SourceClass.PUBLIC, SourceClass.FIRST_PARTY_CONSENT, SourceClass.INTERNAL_OPERATIONAL}

DISCLAIMER_ADVISORY = (
    "Advisory research-priority signal only. Not a probability, quote, "
    "underwriting decision, consumer report, or permission to contact."
)
DISCLAIMER_SYNTHETIC = (
    "Synthetic demonstration record: the scoring mechanics are real, the "
    "organization is not. A synthetic record cannot support a VERIFIED "
    "real-world claim (Zero-Bandaid), so truth_state is UNKNOWN by construction."
)


def lambda_aggregate(axes: Sequence[float], weights: Sequence[float]) -> float:
    """Canonical weighted geometric mean over axis scores in [0,1].

    Ported from the estate Lambda aggregator (A1 monotone, A2 homogeneous,
    A3 egyptian-exact, A4 bounded by max). Any zero axis zeroes the product.
    """
    if not axes:
        return 0.0
    if len(axes) != len(weights):
        raise ValueError("axes and weights length mismatch")
    sw = sum(weights)
    if sw <= 0:
        raise ValueError("weights must sum > 0")
    acc = 0.0
    for x, w in zip(axes, weights):
        x = min(max(float(x), 0.0), 1.0)
        if x <= 0.0:
            return 0.0
        acc += (w / sw) * math.log(x)
    return min(max(math.exp(acc), 0.0), 1.0)


def _permit(signal: Signal, lead: LeadRecord) -> Optional[str]:
    """Default DENY gate. Returns a denial reason, or None when admitted."""
    if signal.source_class in _PERMITTED_ALWAYS:
        pass  # explicitly allowed classes
    elif signal.source_class is SourceClass.SYNTHETIC_DEMO and lead.synthetic:
        pass  # synthetic evidence is admissible only on records labeled synthetic
    elif signal.source_class is SourceClass.LICENSED_THIRD_PARTY:
        return "LICENSED_THIRD_PARTY denied: no license/credentials configured (Default DENY)"
    elif signal.source_class is SourceClass.SYNTHETIC_DEMO:
        return "SYNTHETIC_DEMO signal on a record not labeled synthetic (Default DENY)"
    else:
        return f"source_class {signal.source_class.value} not permitted (Default DENY)"
    if not signal.evidence_ref:
        return "no evidence_ref: an observation without a followable reference is not evidence"
    return None


def _axis_recency(signals: list[Signal], now: datetime) -> AxisResult:
    if not signals:
        return AxisResult(weight=WEIGHTS["recency"], truth_state=TruthState.UNKNOWN,
                          detail="no admitted evidence; recency not evaluated")
    newest = max(s.observed_at for s in signals)
    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=timezone.utc)
    age_days = max((now - newest).total_seconds() / 86400.0, 0.0)
    k = math.log(2) / RECENCY_HALF_LIFE_DAYS
    value = max(RECENCY_FLOOR, math.exp(-k * age_days))
    refs = sorted({s.evidence_ref for s in signals if s.evidence_ref})
    return AxisResult(
        value=round(value, 4), weight=WEIGHTS["recency"], truth_state=TruthState.VERIFIED,
        detail=f"newest admitted public event is {age_days:.1f} days old; "
               f"half-life {RECENCY_HALF_LIFE_DAYS} days, floor {RECENCY_FLOOR}",
        evidence_refs=refs,
    )


def _axis_corroboration(signals: list[Signal]) -> AxisResult:
    if not signals:
        return AxisResult(weight=WEIGHTS["corroboration"], truth_state=TruthState.UNKNOWN,
                          detail="no admitted evidence; corroboration not evaluated")
    sources = {s.source for s in signals}
    n = len(sources)
    value = CORROBORATION_MAP.get(n, 1.0)
    refs = sorted({s.evidence_ref for s in signals if s.evidence_ref})
    return AxisResult(
        value=value, weight=WEIGHTS["corroboration"], truth_state=TruthState.VERIFIED,
        detail=f"{n} independent source(s): {sorted(sources)}; mapping {CORROBORATION_MAP}, 3+ => 1.0",
        evidence_refs=refs,
    )


def _axis_authority(signals: list[Signal]) -> AxisResult:
    if not signals:
        return AxisResult(weight=WEIGHTS["authority"], truth_state=TruthState.UNKNOWN,
                          detail="no admitted evidence; source authority not evaluated")
    best = min(s.authority_tier for s in signals)
    refs = sorted({s.evidence_ref for s in signals if s.evidence_ref})
    return AxisResult(
        value=AUTHORITY_MAP[best], weight=WEIGHTS["authority"], truth_state=TruthState.VERIFIED,
        detail=f"strongest admitted source is authority tier {best} "
               f"(1 federal / 2 state / 3 other); mapping {AUTHORITY_MAP}",
        evidence_refs=refs,
    )


def _axis_completeness(lead: LeadRecord, signals: list[Signal]) -> AxisResult:
    fields = {
        "legal_name": bool(lead.legal_name),
        "state": bool(lead.state),
        "naics": bool(lead.naics),
        "evidenced_signal": any(s.evidence_ref for s in signals),
    }
    present = sum(1 for v in fields.values() if v)
    value = present / len(fields)
    missing = [k for k, v in fields.items() if not v]
    state = TruthState.VERIFIED if present == len(fields) else TruthState.INCOMPLETE
    return AxisResult(
        value=round(value, 4), weight=WEIGHTS["completeness"], truth_state=state,
        detail=(f"{present}/{len(fields)} core fields evidenced"
                + (f"; missing: {', '.join(missing)}" if missing else "")),
        evidence_refs=sorted({s.evidence_ref for s in signals if s.evidence_ref}),
    )


def _bucket(score: float) -> str:
    for threshold, name in BUCKETS:
        if score >= threshold:
            return name
    return BUCKETS[-1][1]


def score_lead(lead: LeadRecord, now: Optional[datetime] = None) -> dict[str, Any]:
    """Score one lead and mint the receipt for the decision.

    Every return path carries a receipt — including INCOMPLETE and denial-heavy
    outcomes. The decision to refuse a number is itself a receipted decision.
    """
    now = now or datetime.now(timezone.utc)

    admitted: list[Signal] = []
    denied: list[dict[str, Any]] = []
    for s in lead.signals:
        reason = _permit(s, lead)
        if reason is None:
            admitted.append(s)
        else:
            denied.append({"source": s.source, "signal": s.signal, "denied": reason})

    axes = {
        "recency": _axis_recency(admitted, now),
        "corroboration": _axis_corroboration(admitted),
        "authority": _axis_authority(admitted),
        "completeness": _axis_completeness(lead, admitted),
    }

    # Every axis with a value aggregates; axes with no evidence (value=None)
    # are excluded and their weights renormalize — the receipt discloses both
    # the per-axis values and the full weight table, so nothing is hidden.
    evidenced = {k: a for k, a in axes.items() if a.value is not None}
    disclaimers = [DISCLAIMER_ADVISORY]
    if lead.synthetic:
        disclaimers.append(DISCLAIMER_SYNTHETIC)

    if not admitted:
        # Law 4: missing evidence => INCOMPLETE, never a fabricated number.
        truth_state = TruthState.INCOMPLETE
        score: Optional[float] = None
        bucket: Optional[str] = None
        disclaimers.append("No admitted evidence; no score emitted (Law 4: INCOMPLETE, never PASS).")
    else:
        score01 = lambda_aggregate(
            [a.value for a in evidenced.values()], [a.weight for a in evidenced.values()]
        )
        score = round(score01 * 100.0, 1)
        bucket = _bucket(score)
        # A synthetic record can never ground a VERIFIED real-world claim.
        truth_state = TruthState.UNKNOWN if lead.synthetic else TruthState.VERIFIED

    receipt_body = {
        "lead_id": lead.id,
        "legal_name": lead.legal_name,
        "synthetic": lead.synthetic,
        "score": score,
        "bucket": bucket,
        "axes": {
            k: {"value": a.value, "weight": a.weight, "truth_state": a.truth_state.value,
                "detail": a.detail, "evidence_refs": a.evidence_refs}
            for k, a in axes.items()
        },
        "signals_used": [
            {"source": s.source, "source_class": s.source_class.value, "signal": s.signal,
             "observed_at": s.observed_at.isoformat(), "evidence_ref": s.evidence_ref}
            for s in admitted
        ],
        "denied_signals": denied,
        "model": {
            "aggregator": "weighted geometric mean (canonical Lambda-spine)",
            "weights": WEIGHTS,
            "recency_half_life_days": RECENCY_HALF_LIFE_DAYS,
            "recency_floor": RECENCY_FLOOR,
            "corroboration_map": CORROBORATION_MAP,
            "authority_map": AUTHORITY_MAP,
        },
    }
    receipt = receipts.make_receipt(receipt_body, truth_state.value)

    return {
        "lead_id": lead.id,
        "legal_name": lead.legal_name,
        "score": score,
        "bucket": bucket,
        "truth_state": truth_state,
        "synthetic": lead.synthetic,
        "axes": axes,
        "admitted_signals": len(admitted),
        "denied_signals": denied,
        "disclaimers": disclaimers,
        "receipt": receipt,
    }
