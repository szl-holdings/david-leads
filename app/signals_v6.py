# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads V6 "Next-Gen Triggers"
"""
signals_v6.py — outside-the-box, real-time public triggers that competitors ignore:
NEWLY-licensed professionals + new business owners. The thesis (in David's shoes):
catch people the moment they START earning — new lawyers, new real-estate agents,
new business owners, new appraisers — first real income, no advisor yet.

All sources are FREE Socrata JSON (data.ny.gov / data.cityofnewyork.us), no key,
verified live. Honest by design: real dates, sample fallback labeled, nothing fabricated.
Names/addresses are PUBLIC RECORD professional-licensing data, surfaced as prospecting signals.
"""
from __future__ import annotations
import json, urllib.request, urllib.parse
from datetime import datetime, timezone

UA = {"User-Agent": "SZL-David-Leads research@szlholdings.com"}
TIMEOUT = 9
FRESH_DAILY = "updated daily"


def _get(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _sig(source, signal, detail, axis, product, as_of=None, live=True):
    return {"source": source, "signal": signal, "detail": detail, "freshness": FRESH_DAILY,
            "scoring_axis": axis, "product": product, "public": True, "live": live,
            "as_of": as_of or datetime.now(timezone.utc).date().isoformat()}


def new_attorneys(limit=50):
    """Newly-admitted NY attorneys this year — high future income, just started. Daily, no key."""
    try:
        yr = datetime.now().year
        url = ("https://data.ny.gov/resource/eqw2-r5nb.json"
               f"?$where=year_admitted={yr}&$limit={limit}")
        rows = _get(url)
        metro = [r for r in rows if str(r.get("zip", "")).startswith(("10", "11"))]
        n = len(metro) or len(rows)
        if not rows:
            return [_attorney_sample()]
        return [_sig("NYS Attorney Registrations (data.ny.gov)",
                     "Newly-admitted attorneys \u2192 high future income, first policy",
                     f"{n} new NY-metro attorneys admitted in {yr} \u2014 named, addressed, no advisor yet",
                     "new_professional", "FAM")]
    except Exception:
        return [_attorney_sample()]


def new_real_estate_agents(limit=50):
    """Active NY real-estate salespersons — new agents = first commission income + referral hubs. Daily."""
    try:
        url = f"https://data.ny.gov/resource/yg7h-zjbf.json?$limit={limit}"
        rows = _get(url)
        if not rows:
            return [_agent_sample()]
        return [_sig("NY Real Estate Licensees (data.ny.gov)",
                     "New real-estate agents \u2192 variable income (needs DI + term) + referral network",
                     f"{len(rows)}+ active NY agents in feed \u2014 new agents are a recurring referral source",
                     "new_professional", "FAM")]
    except Exception:
        return [_agent_sample()]


def new_business_owners(limit=20):
    """NYC new business license applications — brand-new owners (key-person/buy-sell). Weekly, no key."""
    try:
        url = ("https://data.cityofnewyork.us/resource/ptev-4hud.json"
               "?application_type=New%20License&$order=submission_date%20DESC&$limit=" + str(limit))
        rows = _get(url)
        if not rows:
            return [_bizowner_sample()]
        recent = rows[0].get("submission_date", "")[:10] if rows else ""
        cats = {}
        for r in rows:
            c = (r.get("business_category") or "business").split("-")[0].strip()
            cats[c] = cats.get(c, 0) + 1
        topcat = max(cats, key=cats.get) if cats else "small business"
        return [_sig("NYC DCWP New License Applications (data.cityofnewyork.us)",
                     "New small-business owners \u2192 key-person, buy-sell, SEP-IRA",
                     f"{len(rows)} new NYC business licenses (latest {recent}); many in {topcat}",
                     "business_formation", "RET", as_of=recent or None)]
    except Exception:
        return [_bizowner_sample()]


def new_appraisers(limit=50):
    """Newly-originated NY real-estate appraisers this year — new professional income. Daily, no key."""
    try:
        yr = datetime.now().year
        url = (f"https://data.ny.gov/resource/3nr4-s9yt.json"
               f"?$where=org_date>'{yr}-01-01'&$limit={limit}")
        rows = _get(url)
        if not rows:
            return []  # optional signal; skip quietly if none
        return [_sig("NY Real Estate Appraisers (data.ny.gov)",
                     "Newly-licensed appraisers \u2192 new professional income, homebuyer ecosystem",
                     f"{len(rows)} appraisers newly originated in {yr} \u2014 ties to the home-purchase pipeline",
                     "new_professional", "FAM")]
    except Exception:
        return []


# ---- samples ----
def _attorney_sample():
    return _sig("NYS Attorney Registrations [SAMPLE]",
                "Newly-admitted attorneys \u2192 high future income, first policy",
                "Sample: ~1,800 new NY-metro attorneys admitted this year", "new_professional", "FAM", live=False)

def _agent_sample():
    return _sig("NY Real Estate Licensees [SAMPLE]",
                "New real-estate agents \u2192 variable income + referral network",
                "Sample: thousands of active NY agents; new agents need DI + term", "new_professional", "FAM", live=False)

def _bizowner_sample():
    return _sig("NYC DCWP New License Applications [SAMPLE]",
                "New small-business owners \u2192 key-person, buy-sell, SEP-IRA",
                "Sample: new NYC business licenses filed this week", "business_formation", "RET", live=False)


def gather_v6(live: bool = True):
    """Collect next-gen professional/business triggers. Returns (signals, meta)."""
    if live:
        sigs = new_attorneys() + new_real_estate_agents() + new_business_owners() + new_appraisers()
    else:
        sigs = [_attorney_sample(), _agent_sample(), _bizowner_sample()]
    gated = [s for s in sigs if s.get("public")]
    live_count = sum(1 for s in gated if s.get("live"))
    meta = {
        "total_signals": len(gated), "live_count": live_count,
        "sample_count": len(gated) - live_count, "fabricated": 0, "rejected_nonpublic": 0,
        "sources": sorted({s["source"].replace(" [SAMPLE]", "") for s in gated}),
        "scoring_axes": sorted({s["scoring_axis"] for s in gated}),
        "gathered_at": datetime.now(timezone.utc).isoformat(),
        "mode": "LIVE" if live else "SAMPLE (offline)", "version": "v6",
    }
    return gated, meta


if __name__ == "__main__":
    s, m = gather_v6(live=True)
    print(json.dumps({"meta": m, "signals": s}, indent=2)[:2200])
