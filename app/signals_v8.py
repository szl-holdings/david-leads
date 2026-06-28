# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads V8
"""
signals_v8.py — Territory Pulse for the 13-state Atlantic seaboard.

Ranks each state by a transparent, disclosed pulse:
    pulse = 100 * richness_norm * freshness * activity

All inputs are grounded in the V7 multi-state open-data research (research/V7_MULTISTATE.md),
which was verified live on 2026-06-28. Honest by design: states with no verified keyless
statewide API (MA/NH/ME) are flagged as GAP at a baseline weight — never shown as live-rich.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any

# 13-state seaboard, grounded in V7_MULTISTATE.md §1 (data-richness 0-4, verified 2026-06-28).
# activity = normalized recent-issuance volume where a live count was verified, else None (-> falls back to richness).
SEABOARD: list[dict[str, Any]] = [
    dict(state="CT", name="Connecticut", richness=4.0, cadence="daily", activity=0.92,
         primary_feed="data.ct.gov (Socrata)",
         headline="4,323 new business formations in last 30 days",
         citations=[("CT Business Filing History ah3s-bes7", "https://data.ct.gov/resource/ah3s-bes7.json"),
                    ("CT State Licenses & Credentials ngch-56tr", "https://data.ct.gov/resource/ngch-56tr.json")],
         gap=False),
    dict(state="DE", name="Delaware", richness=3.5, cadence="daily", activity=0.78,
         primary_feed="data.delaware.gov (Socrata)",
         headline="Daily business + individual professional license issuances",
         citations=[("DE Business Licenses 5zy2-grhr", "https://data.delaware.gov/resource/5zy2-grhr.json"),
                    ("DE Professional & Occupational Licensing pjnv-eaih", "https://data.delaware.gov/resource/pjnv-eaih.json")],
         gap=False),
    dict(state="DC", name="District of Columbia", richness=3.5, cadence="daily", activity=0.80,
         primary_feed="opendata.dc.gov (ArcGIS Hub)",
         headline="14,342 construction permits in 2026; daily business licenses",
         citations=[("DC Basic Business License (30d)", "https://maps2.dcgis.dc.gov/dcgis/rest/services/FEEDS/DCRA/FeatureServer/1/query"),
                    ("DC Construction Permits 2026", "https://maps2.dcgis.dc.gov/dcgis/rest/services/FEEDS/DDOT/FeatureServer/48/query")],
         gap=False),
    dict(state="PA", name="Pennsylvania", richness=2.0, cadence="monthly", activity=0.70,
         primary_feed="data.pa.gov (Socrata)",
         headline="43,449 new business registrations in last ~90 days",
         citations=[("PA Registered Businesses xvd7-5r2c", "https://data.pa.gov/resource/xvd7-5r2c.json")],
         gap=False),
    dict(state="MD", name="Maryland", richness=2.0, cadence="monthly", activity=0.55,
         primary_feed="opendata.maryland.gov (Socrata)",
         headline="2,438,889 statewide real-property assessments",
         citations=[("MD Real Property Assessments ed4q-f8tm", "https://opendata.maryland.gov/resource/ed4q-f8tm.json")],
         gap=False),
    dict(state="VA", name="Virginia", richness=2.0, cadence="daily", activity=0.50,
         primary_feed="city portals (Norfolk Socrata + Virginia Beach ArcGIS)",
         headline="Norfolk business licenses + Virginia Beach sales/permits (city-by-city)",
         citations=[("Norfolk Business Licenses dpi6-sct5", "https://data.norfolk.gov/resource/dpi6-sct5.json"),
                    ("Virginia Beach Property Sales", "https://services2.arcgis.com/CyVvlIiUfRBmMQuu/arcgis/rest/services/Property_Sales_/FeatureServer/0/query")],
         gap=False),
    dict(state="NY", name="New York", richness=2.0, cadence="daily", activity=0.85,
         primary_feed="data.ny.gov / data.cityofnewyork.us (Socrata) + ACRIS",
         headline="Home state — DOS business filings, ACRIS deeds, license registries (live)",
         citations=[("NY DOS / Socrata", "https://data.ny.gov"),
                    ("NYC ACRIS", "https://data.cityofnewyork.us")],
         gap=False),
    dict(state="FL", name="Florida", richness=1.5, cadence="daily", activity=0.45,
         primary_feed="Sunbiz SFTP bulk + county ArcGIS",
         headline="Sunbiz daily business files (bulk, needs parse) + county property",
         citations=[("FL Sunbiz public SFTP", "https://dos.fl.gov/sunbiz/")],
         gap=False),
    dict(state="NJ", name="New Jersey", richness=1.0, cadence="monthly", activity=0.30,
         primary_feed="data.nj.gov (Socrata, thin) + bulk license roster",
         headline="Construction permits dataset + bulk professional-license roster",
         citations=[("NJ Open Data", "https://data.nj.gov")],
         gap=False),
    dict(state="RI", name="Rhode Island", richness=0.5, cadence="annual", activity=0.18,
         primary_feed="data.providenceri.gov (Providence only, stale)",
         headline="Providence city portal stale; property tax rolls (annual) only",
         citations=[("Providence Open Data", "https://data.providenceri.gov")],
         gap=False),
    dict(state="MA", name="Massachusetts", richness=0.0, cadence="none", activity=None,
         primary_feed="data.mass.gov (download portal) + gated licensing API",
         headline="No keyless statewide API verified for our categories — baseline only",
         citations=[("MA Data Hub", "https://data.mass.gov")],
         gap=True),
    dict(state="NH", name="New Hampshire", richness=0.0, cadence="none", activity=None,
         primary_feed="none (HTML-only SoS search)",
         headline="No open-data portal / API verified — baseline only",
         citations=[("NH Secretary of State", "https://quickstart.sos.nh.gov")],
         gap=True),
    dict(state="ME", name="Maine", richness=0.0, cadence="none", activity=None,
         primary_feed="none verified",
         headline="No keyless statewide API verified — included for seaboard completeness, baseline only",
         citations=[("Maine.gov", "https://www.maine.gov")],
         gap=True),
]

_CADENCE_FRESHNESS = {"daily": 1.0, "weekly": 0.8, "monthly": 0.6, "annual": 0.3, "none": 0.15}
_SEABOARD_BY_CODE = {s["state"]: s for s in SEABOARD}


def _freshness(cadence: str) -> float:
    return _CADENCE_FRESHNESS.get(cadence, 0.15)


def _pulse(richness: float, freshness: float, activity: float | None) -> float:
    richness_norm = max(0.0, min(richness / 4.0, 1.0))
    act = activity if activity is not None else richness_norm  # honest fallback, no fabricated count
    return round(100.0 * richness_norm * freshness * act, 1)


def _bucket(pulse: float, gap: bool) -> str:
    if gap:
        return "GAP"
    if pulse >= 70:
        return "SURGING"
    if pulse >= 40:
        return "ACTIVE"
    return "QUIET"


def territory_pulse(states: list[str] | None = None) -> dict[str, Any]:
    """Compute the Territory Pulse over the 13-state seaboard (or a subset)."""
    rows = []
    for s in SEABOARD:
        if states and s["state"] not in states:
            continue
        fresh = _freshness(s["cadence"])
        pulse = _pulse(s["richness"], fresh, s["activity"])
        rows.append({
            "state": s["state"], "name": s["name"],
            "pulse": pulse, "bucket": _bucket(pulse, s["gap"]),
            "richness": s["richness"], "freshness": round(fresh, 2),
            "activity": s["activity"] if s["activity"] is not None else round(s["richness"] / 4.0, 2),
            "primary_feed": s["primary_feed"], "cadence": s["cadence"],
            "headline": s["headline"],
            "citations": [{"label": l, "url": u} for l, u in s["citations"]],
            "gap": s["gap"],
        })
    rows.sort(key=lambda r: r["pulse"], reverse=True)
    surging = [r["state"] for r in rows if r["bucket"] == "SURGING"]
    gaps = [r["state"] for r in rows if r["bucket"] == "GAP"]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seaboard": rows,
        "summary": {
            "surging": surging,
            "active": [r["state"] for r in rows if r["bucket"] == "ACTIVE"],
            "quiet": [r["state"] for r in rows if r["bucket"] == "QUIET"],
            "gaps": gaps,
            "top_state": rows[0]["state"] if rows else None,
            "state_count": len(rows),
        },
        "methodology": {
            "formula": "pulse = 100 × (richness/4) × freshness × activity",
            "freshness_by_cadence": _CADENCE_FRESHNESS,
            "source": "V7 multi-state open-data research, verified 2026-06-28",
            "doctrine": "public-data-only · GAP states flagged honestly · no fabricated counts",
        },
    }


def all_pulse_signals(states: list[str] | None = None) -> list[dict[str, Any]]:
    """Flatten pulse citations into signal records for the receipt (public-data provenance)."""
    out = []
    for s in SEABOARD:
        if states and s["state"] not in states:
            continue
        for label, url in s["citations"]:
            out.append({"source": f"{s['state']}: {label}", "signal": url, "public": True})
    return out
