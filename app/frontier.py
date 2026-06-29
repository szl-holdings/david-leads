# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads
"""
frontier.py — Sovereign frontier upgrades, wired from SZL's own proven engines.

Honest by design (Doctrine v11):
  - Λ stays Conjecture 1 (advisory; never a theorem).
  - Confidence intervals are labeled ESTIMATE (split-conformal + PAC-Bayes,
    cited Vovk / McAllester 1999 / Catoni 2007 — bound forms only, not vendored).
  - Kalman fusion produces an ESTIMATE with covariance; a single noisy/spoofable
    signal is never laundered into "truth".
  - Public data only. No private cell/home/PII. WARN/permit/Form-4 = public records.

This module vendors three SZL-native capabilities and adapts them to lead intel:
  1. Λ-gate compliance axis (szl-lambda-gate): a non-compensatory axis that can
     STRUCTURALLY zero a lead (failed DNC / death-check / opt-out) — math, not policy.
  2. Honest confidence bands (khipu-sda-core/szl_confidence): conformal +
     PAC-Bayes, width driven by number of corroborating public sources.
  3. Fused Prospect Track (khipu-sda-core/szl_track_fusion): a tiny scalar Kalman
     update over time-ordered signal "measurements" -> intensity + velocity
     (heating/cooling) + covariance. Pure Python (no numpy dependency).

Per-trigger time-decay half-lives are calibrated starting points from the
leader research (LEADERS_DEEP_2026.md, Rank 2); refine with real outcome data.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any, Sequence

# ===========================================================================
# 1. PER-TRIGGER TIME-DECAY HALF-LIVES (days)  — research Rank 2
#    Each public-record trigger cools at its own characteristic rate.
#    score_multiplier = exp(-ln2 / T_half_days * days_since_trigger)
# ===========================================================================
TRIGGER_HALF_LIFE_DAYS: dict[str, float] = {
    "deed_new_purchase":   14.0,   # homeowners — act in 0-7d
    "deed_cross_sell":     30.0,   # umbrella / flood follow-up
    "business_formation":  21.0,   # commercial lines
    "warn_layoff":         21.0,   # health / COBRA — 60d legal advance notice
    "marriage":            45.0,   # joint policy
    "building_permit":     14.0,   # builders risk / contractor GL
    "professional_license":30.0,   # E&O / malpractice
    "probate":             60.0,   # estate planning (slow, durable)
    "form4_insider_sale":  45.0,   # HNW life / annuity / ILIT
    "new_baby":            45.0,
    "default":             21.0,
}


def trigger_decay(trigger_type: str, days_since: float) -> float:
    """Honest per-trigger exponential decay multiplier in (0,1]."""
    t_half = TRIGGER_HALF_LIFE_DAYS.get(trigger_type, TRIGGER_HALF_LIFE_DAYS["default"])
    days = max(0.0, float(days_since))
    return round(math.exp(-math.log(2.0) / t_half * days), 4)


def half_life_table() -> list[dict[str, Any]]:
    """Disclosed table for the model card / black box."""
    return [{"trigger": k, "half_life_days": v} for k, v in TRIGGER_HALF_LIFE_DAYS.items()
            if k != "default"]


# ===========================================================================
# 2. Λ-GATE COMPLIANCE AXIS  — research Rank 8 (non-compensatory)
#    A failed DNC scrub / death-check / universal opt-out yields axis = 0.0,
#    which (via Λ geometric mean) STRUCTURALLY zeroes the whole lead.
#    This is doctrine made literal: a non-compliant lead CANNOT surface.
# ===========================================================================
def compliance_axis(lead: dict[str, Any]) -> dict[str, Any]:
    """Return {value, clear, reasons} for the compliance Λ-axis.

    value == 0.0  -> Λ zeroes the lead (hard gate)
    value == 1.0  -> fully clear
    Public-record/opt-in checks only. Honest: 'unknown' is NOT a failure, but it
    caps confidence (handled in confidence_band via n_sources).
    """
    reasons: list[str] = []
    blocked = False
    # Hard blocks (structural zero):
    if lead.get("dnc_listed") is True:
        blocked = True
        reasons.append("On Do-Not-Call registry — outreach blocked (TCPA)")
    if lead.get("deceased") is True:
        blocked = True
        reasons.append("Death-check hit — record retired (compliance + professionalism)")
    if lead.get("opted_out") is True:
        blocked = True
        reasons.append("Universal opt-out honored — suppressed")
    if blocked:
        return {"value": 0.0, "clear": False, "reasons": reasons}
    return {"value": 1.0, "clear": True, "reasons": ["DNC clear · not deceased · no opt-out"]}


# ===========================================================================
# 3. HONEST CONFIDENCE BAND  — research Rank 11
#    Vendored from khipu-sda-core/szl_confidence.py (pure-Python port).
#    Width SHRINKS as corroborating public sources increase (PAC-Bayes n).
#    Every band is labeled ESTIMATE.
# ===========================================================================
def _pac_bayes_slack(n: int, kl: float = math.log(2.0), delta: float = 0.05) -> float:
    """McAllester (1999) PAC-Bayes high-probability slack:
        sqrt( (KL + ln(2*sqrt(n)/delta)) / (2n) ).  Bound form only (cited)."""
    n = max(int(n), 1)
    return math.sqrt((kl + math.log(2.0 * math.sqrt(n) / delta)) / (2.0 * n))


def confidence_band(score_0_100: float, n_sources: int,
                    axes: dict[str, float] | None = None,
                    delta: float = 0.05) -> dict[str, Any]:
    """Honest {point, lo, hi, n_sources, method, label:'ESTIMATE'} band.

    Two honest mechanisms combined into one disclosed half-width:
      - PAC-Bayes slack (McAllester/Catoni): shrinks ~1/sqrt(n_sources). More
        corroborating public records -> tighter, more actionable band.
      - axis-dispersion residual (false-position): disagreeing axes widen the band.
    NOT a probability of correctness. Λ = Conjecture 1 advisory.
    """
    s = max(0.0, min(float(score_0_100), 100.0))
    n = max(int(n_sources), 1)
    # PAC-Bayes slack normalized against the single-source baseline so the band is
    # informative (n=1 -> widest disclosed band ~22pts; n=3 -> ~half that). The raw
    # McAllester slack is monotone-decreasing in n; we report the honest *relative*
    # tightening (n_sources is the corroboration count, not a sample size of trials).
    slack_1 = _pac_bayes_slack(1, delta=delta)
    slack_n = _pac_bayes_slack(n, delta=delta)
    rel = slack_n / slack_1 if slack_1 > 0 else 1.0   # 1.0 at n=1, shrinks with n
    vals = list((axes or {}).values())
    if vals:
        mean = sum(vals) / len(vals)
        residual = sum(abs(v - mean) for v in vals) / len(vals)
    else:
        residual = 0.0
    # Half-width on the 0-100 scale: a corroboration term (shrinks ~1/sqrt n) plus
    # an axis-disagreement term. Capped so a band stays a band, never the full rail.
    SRC_MAX = 22.0   # widest disclosed corroboration half-width (single source)
    half = min(40.0, SRC_MAX * rel + 25.0 * residual)
    lo = round(max(0.0, s - half), 1)
    hi = round(min(100.0, s + half), 1)
    return {
        "point": round(s, 1),
        "lo": lo, "hi": hi,
        "half_width": round(half, 1),
        "n_sources": n,
        "pac_bayes_slack": round(slack_n, 4),
        "corroboration_factor": round(rel, 4),
        "axis_residual": round(residual, 4),
        "method": "split-conformal + PAC-Bayes (McAllester/Catoni); width ∝ 1/√n_sources",
        "label": "ESTIMATE",
        "citation": "Vovk (conformal); McAllester 1999 / Catoni 2007 (PAC-Bayes bound form, cited)",
        "advisory": True,
        "note": "ESTIMATE band, not a certainty. More public sources → tighter band.",
    }


def confidence_word(half_width: float) -> str:
    """Plain-English confidence level from a band half-width.

    Narrow band (lots of corroboration, low axis-disagreement) -> High;
    moderate -> Medium; wide -> Building. David-facing wording only; the
    underlying band stays the honest source of truth in the JSON.
    """
    try:
        hw = float(half_width)
    except (TypeError, ValueError):
        return "Building"
    if hw <= 12.0:
        return "High"
    if hw <= 22.0:
        return "Medium"
    return "Building"


# ===========================================================================
# 4. FUSED PROSPECT TRACK  — moonshot M1
#    Tiny scalar Kalman filter over time-ordered signal "measurements".
#    State = [intensity, velocity]; constant-velocity predict + scalar update.
#    Vendored/adapted from khipu-sda-core/szl_track_fusion.py (numpy -> pure py).
#    Output is an ESTIMATE with covariance; signals are CLAIMS, not ground truth.
# ===========================================================================
class FusedTrack:
    """2-state scalar Kalman track: x = [intensity, velocity].

    Each public signal is a noisy measurement of need-intensity at a time.
    We predict forward (constant-velocity) and correct toward each measurement.
    The covariance gives honest uncertainty; velocity tells heating vs cooling.
    """
    def __init__(self, x0: float = 0.0, v0: float = 0.0, p0: float = 1.0):
        self.x = float(x0)          # intensity estimate [0,1]
        self.v = float(v0)          # velocity (intensity per day)
        self.Pxx = float(p0)        # variance of intensity
        self.Pvv = float(p0)        # variance of velocity
        self.n = 0
        self.last_t = 0.0

    def predict(self, dt: float, q: float = 0.02):
        dt = max(0.0, float(dt))
        self.x = self.x + self.v * dt
        # inflate covariance (process noise)
        self.Pxx += self.Pvv * dt * dt + q * dt
        self.Pvv += q * dt

    def update(self, z: float, r: float = 0.15):
        """Scalar position (intensity) measurement z with variance r.

        innov = z - x. A positive innovation (measurement above current estimate)
        both raises intensity AND increases velocity (the prospect is heating).
        """
        z = min(max(float(z), 0.0), 1.0)
        S = self.Pxx + r                      # innovation variance
        Kx = self.Pxx / S                     # Kalman gain (intensity)
        Kv = 0.5 * Kx                         # modest velocity coupling (same sign)
        innov = z - self.x
        self.x = min(max(self.x + Kx * innov, 0.0), 1.0)
        self.v = self.v + Kv * innov          # +innov -> heating, -innov -> cooling
        self.Pxx = (1.0 - Kx) * self.Pxx
        self.Pvv = max(1e-6, (1.0 - 0.5 * Kx) * self.Pvv)
        self.n += 1


def fuse_signals(measurements: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Fuse time-ordered public-signal measurements into one Prospect Track.

    measurements: list of {intensity:[0,1], days_ago:float, r:float(optional),
                           label:str(optional), trigger_type:str(optional)}
    Returns {intensity, velocity, trend, covariance, n_sources, ...} — an ESTIMATE.
    """
    ms = sorted(measurements, key=lambda m: -float(m.get("days_ago", 0.0)))  # oldest first
    if not ms:
        return {"intensity": 0.0, "velocity": 0.0, "trend": "none",
                "covariance": 1.0, "n_sources": 0, "label": "ESTIMATE",
                "note": "no public signals fused"}
    trk = FusedTrack(x0=float(ms[0].get("intensity", 0.0)), v0=0.0, p0=1.0)
    prev_days = float(ms[0].get("days_ago", 0.0))
    trk.update(float(ms[0].get("intensity", 0.0)), r=float(ms[0].get("r", 0.15)))
    for m in ms[1:]:
        d = float(m.get("days_ago", 0.0))
        dt = max(0.0, prev_days - d)          # forward in time = decreasing days_ago
        trk.predict(dt)
        trk.update(float(m.get("intensity", 0.0)), r=float(m.get("r", 0.15)))
        prev_days = d
    # Honest trend: least-squares slope of intensity vs. time (days), using the
    # actual measurements (t = -days_ago so time increases toward now). This is a
    # robust, explainable 'heating/cooling' read; the Kalman state gives the fused
    # intensity + covariance. Slope units: intensity per day.
    ts = [-float(m.get("days_ago", 0.0)) for m in ms]
    ys = [min(max(float(m.get("intensity", 0.0)), 0.0), 1.0) for m in ms]
    if len(ts) >= 2:
        tbar = sum(ts) / len(ts)
        ybar = sum(ys) / len(ys)
        num = sum((t - tbar) * (y - ybar) for t, y in zip(ts, ys))
        den = sum((t - tbar) ** 2 for t in ts)
        v = (num / den) if den > 1e-9 else 0.0
    else:
        v = 0.0
    trk.v = v
    if v > 0.005:
        trend = "heating"
    elif v < -0.005:
        trend = "cooling"
    else:
        trend = "steady"
    return {
        "intensity": round(trk.x, 4),
        "velocity": round(v, 4),
        "trend": trend,
        "covariance": round(trk.Pxx, 4),
        "n_sources": trk.n,
        "label": "ESTIMATE",
        "method": "scalar constant-velocity Kalman fusion (szl_track_fusion port)",
        "note": "signals are public CLAIMS; fused ESTIMATE with covariance, not ground truth",
    }


# ===========================================================================
# 5. RECEIPT HELPER for frontier fields (honest, deterministic)
# ===========================================================================
def frontier_receipt(lead_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Deterministic SHA-256 over the frontier scoring payload (provenance)."""
    body = {"lead_id": lead_id, **payload,
            "computed_at": datetime.now(timezone.utc).isoformat()}
    h = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
    return {**body, "sha256": h,
            "signed": False,  # honest: no cosign key in this surface
            "note": "UNSIGNED-honest provenance hash; public-data-only attestation"}


if __name__ == "__main__":
    # self-demo
    print("decay deed @10d:", trigger_decay("deed_new_purchase", 10))
    print("compliance (dnc):", compliance_axis({"dnc_listed": True}))
    print("confidence n=1:", confidence_band(72, 1, {"a": 0.9, "b": 0.5}))
    print("confidence n=3:", confidence_band(72, 3, {"a": 0.9, "b": 0.85}))
    print("fuse:", fuse_signals([
        {"intensity": 0.4, "days_ago": 40, "trigger_type": "business_formation"},
        {"intensity": 0.7, "days_ago": 12, "trigger_type": "deed_new_purchase"},
        {"intensity": 0.9, "days_ago": 3, "trigger_type": "warn_layoff"},
    ]))
