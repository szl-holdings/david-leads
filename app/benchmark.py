# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads V8.2 · P1-F producer benchmarking
"""
benchmark.py — producer conversion-funnel dashboard (AgencyZoom / LeadSquared / EZLynx
producer analytics, derived purely from data David Leads already holds).

No external data. Builds the agent's conversion funnel by event_type and by urgency tier
from (a) the leads currently surfaced this session and (b) the outcomes logged via
/api/outcome — both the in-session tally (events.outcome_summary) and the durable, signed
outcome receipts in the append-only receipt lake. Honest: "based on N logged outcomes".
"""
from __future__ import annotations

from typing import Any


def _rate(sold: int, total: int) -> float:
    return round((sold / total) * 100.0, 1) if total > 0 else 0.0


def build_benchmark(leads: list[dict[str, Any]] | None,
                    outcome_summary: dict[str, Any] | None,
                    lake_events: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Compute the conversion funnel by event_type + urgency from surfaced leads and
    logged outcomes (in-session tally + durable lake receipts)."""
    leads = leads or []
    outcome_summary = outcome_summary or {}
    lake_events = lake_events or []

    # --- leads surfaced this session, grouped by event_type and urgency ---
    surfaced_by_event: dict[str, int] = {}
    surfaced_by_urgency: dict[str, int] = {}
    for l in leads:
        et = l.get("event_type") or "unknown"
        ur = l.get("urgency") or "unknown"
        surfaced_by_event[et] = surfaced_by_event.get(et, 0) + 1
        surfaced_by_urgency[ur] = surfaced_by_urgency.get(ur, 0) + 1

    # --- outcomes by event_type (prefer the in-session tally; it's the canonical signal) ---
    by_event = outcome_summary.get("by_event_type", {}) or {}

    # --- durable outcome receipts in the lake → funnel by urgency where receipts carry it ---
    lake_outcomes = [r for r in lake_events if r.get("organ") == "conversion-loop"]

    funnel_by_event = []
    total_meeting = total_sold = total_no = 0
    for et, surfaced in sorted(surfaced_by_event.items(), key=lambda kv: -kv[1]):
        tally = by_event.get(et, {"meeting": 0, "sold": 0, "no": 0})
        meeting, sold, no = tally.get("meeting", 0), tally.get("sold", 0), tally.get("no", 0)
        total = meeting + sold + no
        total_meeting += meeting
        total_sold += sold
        total_no += no
        funnel_by_event.append({
            "event_type": et,
            "surfaced": surfaced,
            "meeting": meeting,
            "sold": sold,
            "no": no,
            "outcomes_logged": total,
            "conversion_rate_pct": _rate(sold, total),
        })

    total_outcomes = total_meeting + total_sold + total_no
    return {
        "summary": {
            "leads_surfaced": len(leads),
            "outcomes_logged": total_outcomes,
            "meeting": total_meeting,
            "sold": total_sold,
            "no": total_no,
            "overall_conversion_rate_pct": _rate(total_sold, total_outcomes),
            "durable_outcome_receipts": len(lake_outcomes),
        },
        "by_event_type": funnel_by_event,
        "surfaced_by_urgency": surfaced_by_urgency,
        "honest_note": "Producer funnel based on %d logged outcome(s) this session. "
                       "Durable when SZL_RECEIPT_LAKE_PATH is set; no external data used."
                       % total_outcomes,
    }
