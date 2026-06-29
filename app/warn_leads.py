# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads · WARN Act Layoff Intelligence (public records)
"""
warn_leads.py — WARN Act layoff leads for the covered states (NY, NJ, PA, MD, DE, CT).

HARD DOCTRINE (SZL governed-AI · honest by design):
  * PUBLIC records only. Federal/State WARN (Worker Adjustment and Retraining
    Notification) notices are filed with state Departments of Labor and published.
    A layoff with 60-day legal advance notice is a high-intent trigger for
    ACA / Short-Term Health / COBRA-alternative coverage.
  * LIVE where a state exposes an open-data/CSV endpoint; otherwise a SMALL,
    clearly-labelled "source_status": "sample" set derived from the REAL public
    WARN notice schema. Sample employer names are illustrative placeholders —
    we NEVER present a specific real employer's data as if live-verified.
  * Every lead carries its official state WARN portal citation + a frontier receipt.
  * Per-trigger time-decay (warn_layoff) + honest confidence band (ESTIMATE) applied.
"""
from __future__ import annotations

import urllib.request
from datetime import datetime, timezone
from typing import Any

try:
    from . import frontier as fr
except Exception:  # pragma: no cover
    fr = None

UA = {"User-Agent": "SZL-David-Leads research@szlholdings.com"}
TIMEOUT = 12  # seconds — short, per doctrine

COVERED = ["NY", "NJ", "PA", "MD", "DE", "CT"]

PRODUCT = "ACA / Short-Term Health / COBRA alternative"
ANGLE = ("60-day WARN notice = a coverage cliff on a known date. Position an ACA / "
         "short-term / COBRA-alternative bridge BEFORE employer coverage lapses.")

# ---- official state WARN portals (public citations) -----------------------------------------
WARN_PORTAL: dict[str, dict[str, str]] = {
    "NY": {"label": "NY DOL — WARN Notices",
           "url": "https://dol.ny.gov/warn-notices"},
    "NJ": {"label": "NJ DOL — WARN Notices (Dislocated Worker)",
           "url": "https://www.nj.gov/labor/employer-services/warn/"},
    "PA": {"label": "PA L&I — WARN Notices",
           "url": "https://www.dli.pa.gov/Individuals/Workforce-Development/warn/Pages/default.aspx"},
    "MD": {"label": "MD Dept. of Labor — WARN Notices",
           "url": "https://www.dllr.state.md.us/employment/warn.shtml"},
    "DE": {"label": "DE Dept. of Labor — WARN Notices",
           "url": "https://labor.delaware.gov/divisions/employment-training/warn/"},
    "CT": {"label": "CT DOL — WARN Notices",
           "url": "https://www.ctdol.state.ct.us/progsupt/bussrvce/warnreport.htm"},
}

# ---- known open-data endpoints (best-effort live; absent -> honest sample) -------------------
# Most states publish WARN as HTML/PDF, not machine-readable open data. We register only
# endpoints we can honestly fetch as structured rows; everything else degrades to sample.
LIVE_ENDPOINTS: dict[str, str] = {
    # (left intentionally conservative — add a state only when a stable JSON/CSV exists)
}

# ---- SMALL illustrative sample set (clearly labelled; schema-faithful) -----------------------
# Employer names are ILLUSTRATIVE PLACEHOLDERS, not specific real companies. This demonstrates
# the WARN pipeline schema honestly when no machine-readable live feed is available in-sandbox.
_SAMPLE: list[dict[str, Any]] = [
    {"employer": "[SAMPLE] Hudson Valley Manufacturing Co.", "city": "Newburgh", "state": "NY",
     "county": "Orange", "affected_count": 240, "notice_date": "2026-05-18", "effective_date": "2026-07-17"},
    {"employer": "[SAMPLE] Garden State Logistics LLC", "city": "Edison", "state": "NJ",
     "county": "Middlesex", "affected_count": 165, "notice_date": "2026-06-01", "effective_date": "2026-07-31"},
    {"employer": "[SAMPLE] Keystone Foods Processing Inc.", "city": "Allentown", "state": "PA",
     "county": "Lehigh", "affected_count": 310, "notice_date": "2026-05-05", "effective_date": "2026-07-06"},
    {"employer": "[SAMPLE] Chesapeake Retail Group", "city": "Baltimore", "state": "MD",
     "county": "Baltimore City", "affected_count": 120, "notice_date": "2026-06-10", "effective_date": "2026-08-10"},
    {"employer": "[SAMPLE] First State Distribution Center", "city": "New Castle", "state": "DE",
     "county": "New Castle", "affected_count": 95, "notice_date": "2026-06-15", "effective_date": "2026-08-14"},
    {"employer": "[SAMPLE] Constitution Insurance Services", "city": "Hartford", "state": "CT",
     "county": "Hartford", "affected_count": 180, "notice_date": "2026-05-22", "effective_date": "2026-07-21"},
]


def _days_since(date_str: str) -> float:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - d).total_seconds() / 86400.0)
    except Exception:
        return 0.0


def _intensity_from(affected: int, days_since_notice: float) -> float:
    """Honest 0-1 intensity: scale by affected headcount (saturating) × decay multiplier."""
    head = min(1.0, float(affected) / 300.0)          # 300+ affected -> max headcount signal
    base = 0.55 + 0.40 * head                          # WARN is inherently high-intent
    if fr is not None:
        base *= fr.trigger_decay("warn_layoff", days_since_notice)
    return round(min(1.0, max(0.0, base)), 4)


def _build_lead(rec: dict[str, Any], source_status: str) -> dict[str, Any]:
    state = rec["state"]
    portal = WARN_PORTAL.get(state, {"label": "State DOL — WARN", "url": ""})
    affected = int(rec.get("affected_count") or 0)
    notice_date = rec.get("notice_date") or ""
    effective_date = rec.get("effective_date") or ""
    days_since = _days_since(notice_date)
    intensity = _intensity_from(affected, days_since)
    score = round(100.0 * intensity, 1)
    lead: dict[str, Any] = {
        "id": "WARN-%s-%s" % (state, (rec.get("employer", "?")[:24]
                                      .replace(" ", "_").replace("[", "").replace("]", ""))),
        "employer": rec.get("employer"),
        "city": rec.get("city"),
        "state": state,
        "county": rec.get("county"),
        "affected_count": affected,
        "notice_date": notice_date,
        "effective_date": effective_date,
        "coverage_loss_date": effective_date,
        "trigger_type": "warn_layoff",
        "product": PRODUCT,
        "angle": ANGLE,
        "score": score,
        "intensity": intensity,
        "days_since_notice": round(days_since, 1),
        "decay_multiplier": (fr.trigger_decay("warn_layoff", days_since) if fr is not None else 1.0),
        "source": {"label": portal["label"], "url": portal["url"]},
        "source_status": source_status,
    }
    if fr is not None:
        try:
            # one corroborating public source (the state WARN filing) -> n_sources=1
            lead["confidence"] = fr.confidence_band(score, 1, {"intensity": intensity})
            try:
                lead["confidence"]["level"] = fr.confidence_word(
                    lead["confidence"].get("half_width", 99.0))
            except Exception:
                pass
        except Exception:
            pass
        try:
            lead["receipt"] = fr.frontier_receipt(lead["id"], {
                "employer": lead["employer"], "state": state, "affected_count": affected,
                "notice_date": notice_date, "effective_date": effective_date,
                "trigger_type": "warn_layoff", "score": score,
                "source": lead["source"], "source_status": source_status,
            })
        except Exception:
            pass
    return lead


def _fetch_live(state: str) -> list[dict[str, Any]]:
    """Best-effort live fetch where a structured endpoint exists. Returns [] on any failure."""
    url = LIVE_ENDPOINTS.get(state)
    if not url:
        return []
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310 (public gov endpoint)
            import json as _json
            data = _json.loads(resp.read().decode("utf-8", "replace"))
        rows: list[dict[str, Any]] = []
        for r in (data if isinstance(data, list) else []):
            rows.append({
                "employer": r.get("company") or r.get("employer"),
                "city": r.get("city"),
                "state": state,
                "county": r.get("county"),
                "affected_count": r.get("affected") or r.get("number_affected") or 0,
                "notice_date": (r.get("notice_date") or "")[:10],
                "effective_date": (r.get("effective_date") or r.get("layoff_date") or "")[:10],
            })
        return rows
    except Exception:
        return []


def warn_leads(states: list[str] | None = None) -> dict[str, Any]:
    """Return WARN Act layoff leads for the covered states (live where possible, else sample)."""
    want = [s.strip().upper() for s in (states or COVERED) if s.strip()]
    want = [s for s in want if s in COVERED] or COVERED
    leads: list[dict[str, Any]] = []
    live_states: list[str] = []
    sample_states: list[str] = []
    for state in want:
        live_rows = _fetch_live(state)
        if live_rows:
            live_states.append(state)
            for r in live_rows:
                leads.append(_build_lead(r, "live"))
        else:
            sample_states.append(state)
            for r in _SAMPLE:
                if r["state"] == state:
                    leads.append(_build_lead(r, "sample"))
    leads.sort(key=lambda l: l.get("score", 0.0), reverse=True)
    return {
        "count": len(leads),
        "states": want,
        "live_states": live_states,
        "sample_states": sample_states,
        "leads": leads,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": (
            "WARN Act notices are PUBLIC records filed with state Departments of Labor. "
            "Rows labelled source_status='sample' use illustrative placeholder employers on the "
            "REAL WARN schema (no live feed available in-sandbox) and are NOT presented as "
            "live-verified. Each lead cites its official state WARN portal. Coverage angle is "
            "ACA / short-term / COBRA-alternative — public-data-only, honest by design."
        ),
    }


if __name__ == "__main__":
    import json
    out = warn_leads(["NY", "NJ"])
    print(json.dumps({k: v for k, v in out.items() if k != "leads"}, indent=2))
    print("first lead:", json.dumps(out["leads"][0], indent=2, default=str))
