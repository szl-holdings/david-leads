# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads V5 "Freshness Edge"
"""
signals_v5.py — the freshest free public-data triggers (daily / real-time), each tagged with
a freshness class so the UI and scoring can favor 'act now' signals over stale averages.

All sources verified live. No keys required for the wired feeds. Honest by design: timestamps
are real, fallbacks are labeled SAMPLE, nothing fabricated. PII note: where feeds expose names
(DOB owners), we surface them as PUBLIC RECORD prospecting signals only.
"""
from __future__ import annotations
import json, os, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone

UA = {"User-Agent": "SZL-David-Leads research@szlholdings.com"}
TIMEOUT = 9

FRESH = {"REALTIME": "real-time", "DAILY": "updated daily", "WEEKLY": "updated weekly",
         "MONTHLY": "updated monthly", "ANNUAL": "updated annually"}


def _get(url, headers=None, timeout=TIMEOUT, method="GET", body=None):
    req = urllib.request.Request(url, headers=headers or UA, method=method,
                                 data=json.dumps(body).encode() if body else None)
    if body:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _sig(source, signal, detail, freshness, axis, product, as_of=None, live=True, extra=None):
    d = {"source": source, "signal": signal, "detail": detail, "freshness": freshness,
         "scoring_axis": axis, "product": product, "public": True, "live": live,
         "as_of": as_of or datetime.now(timezone.utc).date().isoformat()}
    if extra:
        d.update(extra)
    return d


# ---------------------------------------------------------------- DAILY feeds (no key)
def acris_deeds(limit=8):
    """NYC ACRIS recorded DEEDs — a home purchase is the #1 mortgage-protection trigger. Daily, no key."""
    try:
        url = ("https://data.cityofnewyork.us/resource/bnx9-e6tj.json"
               "?doc_type=DEED&$order=recorded_datetime%20DESC&$limit=" + str(limit))
        rows = _get(url)
        if not rows:
            return [_acris_sample()]
        out = []
        for r in rows[:limit]:
            amt = r.get("document_amt")
            when = (r.get("recorded_datetime") or "")[:10]
            try:
                amt_s = f"${int(float(amt)):,}" if amt and float(amt) > 0 else "amount on record"
            except Exception:
                amt_s = "amount on record"
            out.append(_sig("NYC ACRIS Deeds (data.cityofnewyork.us)",
                            "New home purchase \u2192 mortgage-protection / term need",
                            f"Deed recorded {when} \u00b7 {amt_s} \u2014 new homeowner to protect",
                            FRESH["DAILY"], "home_purchase", "FAM", as_of=when,
                            extra={"amount": amt}))
        return out[:3]  # surface a few; full set drives scoring
    except Exception:
        return [_acris_sample()]


def dob_new_buildings(limit=8):
    """NYC DOB NOW New Building filings — named owners building new homes. Daily, no key."""
    try:
        url = ("https://data.cityofnewyork.us/resource/w9ak-ipjd.json"
               "?job_type=New%20Building&$order=filing_date%20DESC&$limit=" + str(limit))
        rows = _get(url)
        if not rows:
            return [_dob_sample()]
        out = []
        for r in rows[:limit]:
            owner = " ".join(x for x in [r.get("owner_first_name"), r.get("owner_last_name")] if x).title() or "New-build owner"
            boro = (r.get("borough") or "").title()
            units = r.get("proposed_dwelling_units") or "?"
            when = (r.get("filing_date") or "")[:10]
            out.append(_sig("NYC DOB NOW New Building (data.cityofnewyork.us)",
                            "New construction / new home \u2192 family coverage opportunity",
                            f"{owner} \u2014 new building filed {when}, {units} unit(s){', ' + boro if boro else ''}",
                            FRESH["DAILY"], "home_purchase", "FAM", as_of=when))
        return out[:3]
    except Exception:
        return [_dob_sample()]


def usaspending_awards(limit=5):
    """USAspending federal awards to NY businesses = liquidity event. Daily, no key (POST)."""
    try:
        body = {
            "filters": {
                "recipient_locations": [{"country": "USA", "state": "NY"}],
                "award_type_codes": ["A", "B", "C", "D"],
                "time_period": [{"start_date": "2026-01-01", "end_date": datetime.now().date().isoformat()}],
            },
            "fields": ["Recipient Name", "Award Amount", "Awarding Agency", "Start Date"],
            "sort": "Award Amount", "order": "desc", "limit": limit,
        }
        data = _get("https://api.usaspending.gov/api/v2/search/spending_by_award/",
                    method="POST", body=body)
        results = data.get("results", [])
        if not results:
            return [_usa_sample()]
        out = []
        for r in results[:limit]:
            name = r.get("Recipient Name", "NY business")
            amt = r.get("Award Amount", 0)
            try:
                amt_s = f"${int(float(amt)):,}"
            except Exception:
                amt_s = str(amt)
            out.append(_sig("USAspending.gov (federal awards)",
                            "Business liquidity event \u2192 retirement / key-person / succession",
                            f"{name[:42]} awarded {amt_s} \u2014 owner can fund a plan now",
                            FRESH["DAILY"], "business_liquidity", "RET"))
        return out[:2]
    except Exception:
        return [_usa_sample()]


def ny_business_county_delta(days=7):
    """NY DOS new-business velocity by county (last N days) — territory timing. Daily, no key."""
    try:
        from datetime import timedelta
        since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
        q = ("https://data.ny.gov/resource/n9v6-gdp6.json?$select=county,count(*)"
             f"&$where=initial_dos_filing_date>'{since}T00:00:00'&$group=county&$order=count%20DESC&$limit=5")
        rows = _get(q)
        if not rows:
            return [_biz_delta_sample()]
        top = ", ".join(f"{(r.get('county') or '?').title()} {r.get('count','?')}" for r in rows[:5])
        return [_sig("NY DOS Active Corporations (data.ny.gov)",
                     f"New-business velocity (last {days} days) by county \u2192 where owners are forming now",
                     f"Top counties: {top}", FRESH["DAILY"], "business_formation", "RET")]
    except Exception:
        return [_biz_delta_sample()]


# ---------------------------------------------------------------- samples (offline / failure)
def _acris_sample():
    return _sig("NYC ACRIS Deeds [SAMPLE]", "New home purchase \u2192 mortgage-protection need",
                "Sample: deed recorded, ~$650,000 \u2014 new homeowner to protect",
                FRESH["DAILY"], "home_purchase", "FAM", live=False)

def _dob_sample():
    return _sig("NYC DOB NOW New Building [SAMPLE]", "New construction \u2192 family coverage",
                "Sample: new building filed, 2 units, Queens", FRESH["DAILY"], "home_purchase", "FAM", live=False)

def _usa_sample():
    return _sig("USAspending.gov [SAMPLE]", "Business liquidity \u2192 retirement / key-person",
                "Sample: NY firm awarded $1.2M federal contract", FRESH["DAILY"], "business_liquidity", "RET", live=False)

def _biz_delta_sample():
    return _sig("NY DOS Active Corporations [SAMPLE]", "New-business velocity by county",
                "Sample: Kings 700, Queens 557, Nassau 443 (last 7 days)", FRESH["DAILY"], "business_formation", "RET", live=False)


def gather_v5(live: bool = True):
    """Collect the freshest triggers. Returns (signals, meta)."""
    if live:
        sigs = acris_deeds() + dob_new_buildings() + usaspending_awards() + ny_business_county_delta()
    else:
        sigs = [_acris_sample(), _dob_sample(), _usa_sample(), _biz_delta_sample()]
    gated = [s for s in sigs if s.get("public")]
    live_count = sum(1 for s in gated if s.get("live"))
    meta = {
        "total_signals": len(gated),
        "live_count": live_count,
        "sample_count": len(gated) - live_count,
        "fabricated": 0,
        "rejected_nonpublic": len(sigs) - len(gated),
        "sources": sorted({s["source"].replace(" [SAMPLE]", "") for s in gated}),
        "freshness_classes": sorted({s["freshness"] for s in gated}),
        "scoring_axes": sorted({s["scoring_axis"] for s in gated}),
        "gathered_at": datetime.now(timezone.utc).isoformat(),
        "mode": "LIVE" if live else "SAMPLE (offline)",
        "version": "v5",
    }
    return gated, meta


if __name__ == "__main__":
    s, m = gather_v5(live=True)
    print(json.dumps({"meta": m, "signals": s}, indent=2)[:2500])
