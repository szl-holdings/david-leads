# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads V8
"""
signals_v8.py — LIVE Territory Pulse for the Atlantic seaboard.

Two public-data adapters, no paid keys:
  • socrata_query(domain, dataset, ...) — Socrata SODA endpoints (data.ct.gov, data.pa.gov, …)
  • arcgis_count(url) / arcgis_query(url, …) — ArcGIS FeatureServer query endpoints (DC, county GIS)

Honest by design (SZL doctrine):
  • Date hygiene: clamp_date() pins every observation window to [2015-01-01 .. today] so a portal's
    stray future-dated or pre-2015 rows never inflate a count.
  • Graceful per-feed fallback: a feed that fails to probe LIVE is returned as [SAMPLE] with a
    disclosed baseline — never a fabricated count.
  • ME / NH have no keyless statewide API we can verify → honest GAP, baseline only.
  • Every unconfirmed ArcGIS county FeatureServer is probed LIVE; failures are labelled [SAMPLE].

Regions (operator-facing seaboard selector):
  NE  = NY, CT, MA, RI
  MID = NJ, DE, MD, PA, DC
  SE  = VA, NC, SC, GA, FL
ME/NH are carried as honest GAP states for seaboard completeness.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone, date
from typing import Any, Optional

UA = {"User-Agent": "SZL-David-Leads research@szlholdings.com"}
TIMEOUT = 6

# ---------------------------------------------------------------- date hygiene
_MIN_DATE = date(2015, 1, 1)


def _today() -> date:
    return datetime.now(timezone.utc).date()


def clamp_date(d: Any) -> date:
    """Clamp a date (date | datetime | 'YYYY-MM-DD' | ISO string) to [2015-01-01 .. today].

    Honest date hygiene: portals occasionally emit future-dated or pre-2015 rows; pinning the
    window means a probe count reflects real recent issuance, not portal junk."""
    today = _today()
    if isinstance(d, datetime):
        d = d.date()
    elif isinstance(d, str):
        try:
            d = datetime.fromisoformat(d.replace("Z", "+00:00")).date()
        except Exception:
            try:
                d = datetime.strptime(d[:10], "%Y-%m-%d").date()
            except Exception:
                d = today
    elif not isinstance(d, date):
        d = today
    if d < _MIN_DATE:
        return _MIN_DATE
    if d > today:
        return today
    return d


def _window_start(days_back: int) -> date:
    """Lower bound of a 'last N days' window, date-hygiene clamped."""
    today = _today()
    raw = date.fromordinal(max(today.toordinal() - days_back, _MIN_DATE.toordinal()))
    return clamp_date(raw)


# ---------------------------------------------------------------- HTTP
def _get_json(url: str, headers=None, timeout=TIMEOUT) -> Any:
    req = urllib.request.Request(url, headers=headers or UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


# ---------------------------------------------------------------- Socrata adapter
def socrata_query(domain: str, dataset: str, where: Optional[str] = None,
                  select: Optional[str] = None, limit: int = 1,
                  timeout: int = TIMEOUT) -> list[dict[str, Any]]:
    """Query a Socrata SODA endpoint: https://{domain}/resource/{dataset}.json?...

    Returns a list of rows (possibly empty). Raises on network/HTTP error (callers fall back)."""
    params: dict[str, str] = {"$limit": str(limit)}
    if where:
        params["$where"] = where
    if select:
        params["$select"] = select
    url = f"https://{domain}/resource/{dataset}.json?" + urllib.parse.urlencode(params)
    return _get_json(url, timeout=timeout)


def socrata_count(domain: str, dataset: str, where: Optional[str] = None,
                  timeout: int = TIMEOUT) -> int:
    """Return COUNT(*) for a Socrata dataset (optionally windowed by `where`)."""
    rows = socrata_query(domain, dataset, where=where, select="count(*) as n",
                         limit=1, timeout=timeout)
    if rows:
        for key in ("n", "count", "count_1", "count_*"):
            if key in rows[0]:
                return int(float(rows[0][key]))
        # single-key fallback
        try:
            return int(float(next(iter(rows[0].values()))))
        except Exception:
            return 0
    return 0


# ---------------------------------------------------------------- ArcGIS adapter
def arcgis_query(url: str, where: str = "1=1", out_fields: str = "*",
                 result_count: int = 1, timeout: int = TIMEOUT) -> list[dict[str, Any]]:
    """Query an ArcGIS FeatureServer/MapServer layer .../query endpoint. Returns features list."""
    params = {
        "where": where, "outFields": out_fields, "resultRecordCount": str(result_count),
        "f": "json", "returnGeometry": "false",
    }
    full = url.rstrip("/")
    if not full.endswith("/query"):
        full += "/query"
    full += "?" + urllib.parse.urlencode(params)
    data = _get_json(full, timeout=timeout)
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(f"ArcGIS error: {data['error']}")
    return data.get("features", []) if isinstance(data, dict) else []


def arcgis_count(url: str, where: str = "1=1", timeout: int = TIMEOUT) -> int:
    """Return returnCountOnly count for an ArcGIS FeatureServer layer."""
    params = {"where": where, "returnCountOnly": "true", "f": "json"}
    full = url.rstrip("/")
    if not full.endswith("/query"):
        full += "/query"
    full += "?" + urllib.parse.urlencode(params)
    data = _get_json(full, timeout=timeout)
    if isinstance(data, dict):
        if data.get("error"):
            raise RuntimeError(f"ArcGIS error: {data['error']}")
        if "count" in data:
            return int(data["count"])
    raise RuntimeError("ArcGIS: no count in response")


# ---------------------------------------------------------------- portal registry
# kind: "socrata" | "arcgis" | "none". For socrata, `field` is the issuance date column used to
# build the date-clamped recent window (None -> unwindowed count). `confirmed` marks endpoints
# verified live in prior research; unconfirmed ones are probed and labelled [SAMPLE] on failure.
STATE_PORTALS: dict[str, dict[str, Any]] = {
    # ---- Northeast ----
    "NY": dict(name="New York", region="NE", kind="socrata", richness=2.0, cadence="daily",
               domain="data.ny.gov", dataset="n9v6-gdp6", field="initial_dos_filing_date",
               feed="data.ny.gov (Socrata) — DOS active corporations", confirmed=False,
               headline="DOS business filings, ACRIS deeds, license registries (home market)",
               citations=[("NY DOS Active Corporations n9v6-gdp6", "https://data.ny.gov/resource/n9v6-gdp6.json"),
                          ("NYC ACRIS", "https://data.cityofnewyork.us")]),
    "CT": dict(name="Connecticut", region="NE", kind="socrata", richness=4.0, cadence="daily",
               domain="data.ct.gov", dataset="n7gp-d28j", field=None,
               feed="data.ct.gov (Socrata) — business + license registries", confirmed=True,
               headline="Statewide business formations + license/credential issuance (daily)",
               citations=[("CT Business Master ah3s-bes7", "https://data.ct.gov/resource/ah3s-bes7.json"),
                          ("CT Licenses & Credentials ngch-56tr", "https://data.ct.gov/resource/ngch-56tr.json")]),
    "MA": dict(name="Massachusetts", region="NE", kind="none", richness=0.0, cadence="none", field=None,
               feed="data.mass.gov (download portal) + gated licensing API", confirmed=False,
               headline="No keyless statewide API verified for our categories — baseline only",
               citations=[("MA Data Hub", "https://data.mass.gov")]),
    "RI": dict(name="Rhode Island", region="NE", kind="socrata", richness=0.5, cadence="annual",
               domain="data.providenceri.gov", dataset="dn46-yvxe", field=None,
               feed="data.providenceri.gov (Providence only, stale)", confirmed=False,
               headline="Providence city portal stale; property tax rolls (annual) only",
               citations=[("Providence Open Data", "https://data.providenceri.gov")]),
    # ---- Mid-Atlantic ----
    "NJ": dict(name="New Jersey", region="MID", kind="socrata", richness=1.0, cadence="monthly",
               domain="data.nj.gov", dataset="w9se-dmra", field=None,
               feed="data.nj.gov (Socrata, thin) + bulk license roster", confirmed=False,
               headline="Construction permits dataset + bulk professional-license roster",
               citations=[("NJ Open Data", "https://data.nj.gov")]),
    "DE": dict(name="Delaware", region="MID", kind="socrata", richness=3.5, cadence="daily",
               domain="data.delaware.gov", dataset="5zy2-grhr", field=None,
               feed="data.delaware.gov (Socrata) — business + professional licensing", confirmed=True,
               headline="Daily business + individual professional license issuances",
               citations=[("DE Business Licenses 5zy2-grhr", "https://data.delaware.gov/resource/5zy2-grhr.json"),
                          ("DE Professional Licensing pjnv-eaih", "https://data.delaware.gov/resource/pjnv-eaih.json")]),
    "MD": dict(name="Maryland", region="MID", kind="socrata", richness=2.0, cadence="monthly",
               domain="opendata.maryland.gov", dataset="ed4q-f8tm", field=None,
               feed="opendata.maryland.gov (Socrata) — real-property assessments", confirmed=True,
               headline="Statewide real-property assessments (2.4M parcels)",
               citations=[("MD Real Property Assessments ed4q-f8tm", "https://opendata.maryland.gov/resource/ed4q-f8tm.json")]),
    "PA": dict(name="Pennsylvania", region="MID", kind="socrata", richness=2.0, cadence="monthly",
               domain="data.pa.gov", dataset="xvd7-5r2c", field="entity_create_date",
               feed="data.pa.gov (Socrata) — registered businesses", confirmed=True,
               headline="New business registrations (statewide)",
               citations=[("PA Registered Businesses xvd7-5r2c", "https://data.pa.gov/resource/xvd7-5r2c.json")]),
    "DC": dict(name="District of Columbia", region="MID", kind="arcgis", richness=3.5, cadence="daily",
               url="https://maps2.dcgis.dc.gov/dcgis/rest/services/FEEDS/DCRA/FeatureServer/1/query",
               feed="opendata.dc.gov (ArcGIS) — business licenses", confirmed=True,
               headline="Daily business licenses + construction permits (ArcGIS Hub)",
               citations=[("DC Basic Business License", "https://opendata.dc.gov"),
                          ("DC Construction Permits", "https://opendata.dc.gov")]),
    # ---- Southeast ----
    "VA": dict(name="Virginia", region="SE", kind="socrata", richness=2.0, cadence="daily",
               domain="data.norfolk.gov", dataset="dpi6-sct5", field=None,
               feed="city portals (Norfolk Socrata + Virginia Beach ArcGIS)", confirmed=False,
               headline="Norfolk business licenses + Virginia Beach sales/permits (city-by-city)",
               citations=[("Norfolk Business Licenses dpi6-sct5", "https://data.norfolk.gov/resource/dpi6-sct5.json"),
                          ("Virginia Beach Property Sales (ArcGIS)", "https://services2.arcgis.com/CyVvlIiUfRBmMQuu/arcgis/rest/services/Property_Sales_/FeatureServer/0/query")]),
    "NC": dict(name="North Carolina", region="SE", kind="arcgis", richness=1.5, cadence="daily",
               url="https://services.wake.gov/arcgis/rest/services/Property/Parcels/MapServer/0/query",
               feed="county ArcGIS (Wake, Mecklenburg) — parcels/permits", confirmed=False,
               headline="County GIS parcels/permits (Wake/Mecklenburg) — probed live",
               citations=[("Wake County GIS", "https://www.wake.gov/departments-government/geographic-information-services-gis")]),
    "SC": dict(name="South Carolina", region="SE", kind="arcgis", richness=1.0, cadence="monthly",
               url="https://services1.arcgis.com/VaY7cY9pvUYUP1Lf/arcgis/rest/services/Business_Licenses/FeatureServer/0/query",
               feed="county/city ArcGIS — business licenses", confirmed=False,
               headline="County/city ArcGIS business licenses — probed live",
               citations=[("SC GIS", "https://gis.sc.gov")]),
    "GA": dict(name="Georgia", region="SE", kind="arcgis", richness=1.0, cadence="monthly",
               url="https://services1.arcgis.com/Ko5rxt00spOfjMqj/arcgis/rest/services/Business_License/FeatureServer/0/query",
               feed="county ArcGIS (Fulton, Gwinnett) — business licenses", confirmed=False,
               headline="County ArcGIS business licenses — probed live",
               citations=[("Georgia GIO", "https://gio.georgia.gov")]),
    "FL": dict(name="Florida", region="SE", kind="arcgis", richness=1.5, cadence="daily",
               url="https://services1.arcgis.com/Ck2Gdc9bxnq3kPRl/arcgis/rest/services/Building_Permits/FeatureServer/0/query",
               feed="Sunbiz bulk + county ArcGIS (permits/property)", confirmed=False,
               headline="Sunbiz daily business files (bulk) + county property/permits",
               citations=[("FL Sunbiz public SFTP", "https://dos.fl.gov/sunbiz/")]),
    # ---- honest GAP states (seaboard completeness) ----
    "NH": dict(name="New Hampshire", region="NE", kind="none", richness=0.0, cadence="none", field=None,
               feed="none (HTML-only SoS search)", confirmed=False,
               headline="No open-data portal / API verified — baseline only",
               citations=[("NH Secretary of State", "https://quickstart.sos.nh.gov")]),
    "ME": dict(name="Maine", region="NE", kind="none", richness=0.0, cadence="none", field=None,
               feed="none verified", confirmed=False,
               headline="No keyless statewide API verified — included for completeness, baseline only",
               citations=[("Maine.gov", "https://www.maine.gov")]),
}

REGIONS: dict[str, list[str]] = {
    "NE": ["NY", "CT", "MA", "RI"],
    "MID": ["NJ", "DE", "MD", "PA", "DC"],
    "SE": ["VA", "NC", "SC", "GA", "FL"],
}
GAP_STATES = ["MA", "NH", "ME"]

_CADENCE_FRESHNESS = {"daily": 1.0, "weekly": 0.8, "monthly": 0.6, "annual": 0.3, "none": 0.15}


def _freshness(cadence: str) -> float:
    return _CADENCE_FRESHNESS.get(cadence, 0.15)


def _is_gap(p: dict[str, Any]) -> bool:
    return p.get("kind") == "none"


# ---------------------------------------------------------------- per-state LIVE coverage
def coverage(state: str, days_back: int = 90, timeout: int = TIMEOUT) -> dict[str, Any]:
    """Probe ONE state's portal LIVE and return a coverage record with a real recent count,
    or an honest [SAMPLE] baseline if the feed is unreachable / unconfirmed and fails.

    Date hygiene: the recent window lower bound is clamp_date()-pinned to ≥ 2015-01-01."""
    p = STATE_PORTALS.get(state)
    if p is None:
        return {"state": state, "mode": "SAMPLE", "count": None, "gap": True,
                "label": f"{state} [SAMPLE] — unknown state", "feed": "", "citations": []}

    base = {
        "state": state, "name": p["name"], "region": p.get("region", ""),
        "feed": p["feed"], "cadence": p.get("cadence", "none"),
        "headline": p["headline"], "confirmed": p.get("confirmed", False),
        "citations": [{"label": l, "url": u} for l, u in p.get("citations", [])],
        "gap": _is_gap(p),
        "window_start": _window_start(days_back).isoformat(),
        "window_end": _today().isoformat(),
    }

    if _is_gap(p):
        base.update(mode="GAP", count=None,
                    label=f"{p['name']} — honest GAP (no keyless statewide API verified)")
        return base

    win_start = _window_start(days_back)
    try:
        if p["kind"] == "socrata":
            where = None
            if p.get("field"):
                where = f"{p['field']} >= '{win_start.isoformat()}T00:00:00'"
            count = socrata_count(p["domain"], p["dataset"], where=where, timeout=timeout)
            base.update(mode="LIVE", count=int(count),
                        label=f"{p['name']} — {count:,} records (LIVE, window ≥ {win_start.isoformat()})")
            return base
        if p["kind"] == "arcgis":
            count = arcgis_count(p["url"], where="1=1", timeout=timeout)
            base.update(mode="LIVE", count=int(count),
                        label=f"{p['name']} — {count:,} features (LIVE ArcGIS probe)")
            return base
    except Exception as e:  # noqa: BLE001 — any probe failure → honest [SAMPLE]
        base.update(mode="SAMPLE", count=None,
                    label=f"{p['name']} [SAMPLE] — live probe unavailable "
                          f"({type(e).__name__}); baseline richness {p.get('richness', 0.0)}",
                    probe_error=f"{type(e).__name__}")
        return base

    base.update(mode="SAMPLE", count=None, label=f"{p['name']} [SAMPLE] — no adapter")
    return base


# ---------------------------------------------------------------- Territory Pulse
def _pulse(richness: float, freshness: float, activity: float | None) -> float:
    richness_norm = max(0.0, min(richness / 4.0, 1.0))
    act = activity if activity is not None else richness_norm
    return round(100.0 * richness_norm * freshness * act, 1)


def _bucket(pulse: float, gap: bool) -> str:
    if gap:
        return "GAP"
    if pulse >= 70:
        return "SURGING"
    if pulse >= 40:
        return "ACTIVE"
    return "QUIET"


def _all_states() -> list[str]:
    seen: list[str] = []
    for grp in REGIONS.values():
        for s in grp:
            if s not in seen:
                seen.append(s)
    for s in GAP_STATES:
        if s not in seen:
            seen.append(s)
    return seen


def territory_pulse(states: list[str] | None = None, live: bool = False,
                    region: str | None = None) -> dict[str, Any]:
    """Compute the Territory Pulse across the seaboard.

    Static richness/cadence drives the pulse for a fast, deterministic ranking. When live=True,
    each state is probed via coverage() and a real LIVE count lifts its activity term; states whose
    probe fails are kept at baseline and flagged [SAMPLE] (never a fabricated count)."""
    if region and region.upper() in REGIONS:
        states = REGIONS[region.upper()]
    target = states or _all_states()

    rows = []
    for st in target:
        p = STATE_PORTALS.get(st)
        if not p:
            continue
        gap = _is_gap(p)
        fresh = _freshness(p.get("cadence", "none"))
        richness = float(p.get("richness", 0.0))
        activity = None
        mode = "STATIC"
        cov_label = None
        cov_count = None
        if live and not gap:
            cov = coverage(st)
            mode = cov["mode"]
            cov_label = cov["label"]
            cov_count = cov.get("count")
            if cov["mode"] == "LIVE" and cov_count is not None:
                # log-scale a real recent count into a [0,1] activity term (disclosed)
                import math as _m
                activity = max(0.0, min(_m.log10(cov_count + 1) / 5.0, 1.0))
        pulse = _pulse(richness, fresh, activity)
        rows.append({
            "state": st, "name": p["name"], "region": p.get("region", ""),
            "pulse": pulse, "bucket": _bucket(pulse, gap),
            "richness": richness, "freshness": round(fresh, 2),
            "activity": round(activity, 3) if activity is not None else round(richness / 4.0, 2),
            "primary_feed": p["feed"], "cadence": p.get("cadence", "none"),
            "headline": p["headline"], "confirmed": p.get("confirmed", False),
            "citations": [{"label": l, "url": u} for l, u in p.get("citations", [])],
            "gap": gap, "mode": mode,
            "coverage_label": cov_label, "coverage_count": cov_count,
        })
    rows.sort(key=lambda r: r["pulse"], reverse=True)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "regions": REGIONS,
        "seaboard": rows,
        "summary": {
            "surging": [r["state"] for r in rows if r["bucket"] == "SURGING"],
            "active": [r["state"] for r in rows if r["bucket"] == "ACTIVE"],
            "quiet": [r["state"] for r in rows if r["bucket"] == "QUIET"],
            "gaps": [r["state"] for r in rows if r["bucket"] == "GAP"],
            "top_state": rows[0]["state"] if rows else None,
            "state_count": len(rows),
            "live": live,
        },
        "methodology": {
            "formula": "pulse = 100 × (richness/4) × freshness × activity",
            "freshness_by_cadence": _CADENCE_FRESHNESS,
            "activity_live": "log10(recent_count+1)/5 clamped to [0,1] when live probe succeeds",
            "date_hygiene": f"observation window clamped to [{_MIN_DATE.isoformat()} .. today]",
            "doctrine": "public-data-only · GAP states flagged honestly · failed probes → [SAMPLE] · no fabricated counts",
        },
    }


def all_pulse_signals(states: list[str] | None = None) -> list[dict[str, Any]]:
    """Flatten portal citations into signal records for the receipt (public-data provenance)."""
    out = []
    target = states or _all_states()
    for st in target:
        p = STATE_PORTALS.get(st)
        if not p:
            continue
        for label, url in p.get("citations", []):
            out.append({"source": f"{st}: {label}", "signal": url, "public": True})
    return out
