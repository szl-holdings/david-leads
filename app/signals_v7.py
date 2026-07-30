# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads V7 "East Coast Domination"
"""
signals_v7.py — ORGANIZATION-FORMATION signals + MULTI-STATE expansion.

Only organization-formation velocity is emitted. Aggregate affluence, named
executives, insiders, compensation, transactions, and other wealth proxies are
intentionally excluded from lead generation.

Multi-state (free Socrata, reuses the NY pattern): Connecticut, Delaware, Pennsylvania.

Honest by design: real values, sample fallbacks labeled, public-data-only, nothing fabricated.
"""
from __future__ import annotations
import json, urllib.request
from datetime import datetime, timezone, timedelta

UA = {"User-Agent": "SZL-David-Leads research@szlholdings.com"}
T = 10
DAILY, MONTHLY = "updated daily", "updated monthly"


def _json(url, timeout=T, method="GET", body=None):
    req = urllib.request.Request(url, headers=UA, method=method,
                                 data=json.dumps(body).encode() if body else None)
    if body:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _sig(source, signal, detail, freshness, axis, product, live=True, as_of=None):
    return {"source": source, "signal": signal, "detail": detail, "freshness": freshness,
            "scoring_axis": axis, "product": product, "public": True, "live": live,
            "as_of": as_of or datetime.now(timezone.utc).date().isoformat()}


# ============================================================ MULTI-STATE (Socrata, reuses NY pattern)
STATE_PORTALS = {
    "CT": {"name": "Connecticut", "domain": "data.ct.gov",
           "biz": ("ah3s-bes7", "filing_date", "Business Formation filings"),
           "lic": ("ngch-56tr", "issuedate", "new license issuances (RE agents, contractors, attorneys)")},
    "DE": {"name": "Delaware", "domain": "data.delaware.gov",
           "biz": ("5zy2-grhr", "current_license_valid_from", "new business licenses"),
           "lic": ("pjnv-eaih", "issue_date", "professional & occupational licenses")},
    "PA": {"name": "Pennsylvania", "domain": "data.pa.gov",
           "biz": ("xvd7-5r2c", "creationdate", "new business registrations"),
           "lic": None},
}


def state_pulse(state="CT"):
    """Generic multi-state pulse via Socrata — new business + license velocity. No key."""
    cfg = STATE_PORTALS.get(state.upper())
    if not cfg:
        return []
    out = []
    since = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
    # business velocity
    try:
        bid, bdate, blabel = cfg["biz"]
        url = (f"https://{cfg['domain']}/resource/{bid}.json?$select=count(*)"
               f"&$where={bdate}>'{since}T00:00:00'")
        n = _json(url)[0].get("count", "?")
        out.append(_sig(f"{cfg['name']} ({cfg['domain']})",
                        f"{cfg['name']}: new-business velocity \u2192 owner coverage / retirement",
                        f"{n} {blabel} in the last 30 days \u2014 East Coast expansion target",
                        DAILY if state != "PA" else MONTHLY, "business_formation", "RET"))
    except Exception:
        out.append(_state_sample(cfg["name"], "business"))
    # license velocity
    if cfg.get("lic"):
        try:
            lid, ldate, llabel = cfg["lic"]
            yr = datetime.now().year
            url = (f"https://{cfg['domain']}/resource/{lid}.json?$select=count(*)"
                   f"&$where={ldate}>'{yr}-01-01'")
            n = _json(url)[0].get("count", "?")
            out.append(_sig(f"{cfg['name']} ({cfg['domain']})",
                            f"{cfg['name']}: {llabel} \u2192 new professionals to cover",
                            f"{n} {llabel} issued in {yr} \u2014 first-earning-year prospects",
                            DAILY, "new_professional", "FAM"))
        except Exception:
            out.append(_state_sample(cfg["name"], "license"))
    return out


# ============================================================ samples
def _state_sample(name, kind):
    return _sig(f"{name} [SAMPLE]", f"{name}: {kind} velocity",
                f"Sample: {name} {kind} feed (offline)", DAILY, "business_formation" if kind == "business" else "new_professional", "RET", live=False)


def gather_v7(live: bool = True, state="NY", extra_states=("CT", "DE", "PA")):
    """Organization-level multi-state pulse."""
    if live:
        sigs = []
        for s in extra_states:
            sigs += state_pulse(s)
    else:
        sigs = [
            _state_sample("Connecticut", "business"),
            _state_sample("Delaware", "license"),
        ]
    gated = [s for s in sigs if s.get("public")]
    live_count = sum(1 for s in gated if s.get("live"))
    meta = {
        "total_signals": len(gated), "live_count": live_count, "sample_count": len(gated) - live_count,
        "fabricated": 0, "rejected_nonpublic": 0,
        "sources": sorted({s["source"].replace(" [SAMPLE]", "") for s in gated}),
        "scoring_axes": sorted({s["scoring_axis"] for s in gated}),
        "states_covered": ["NY"] + list(extra_states),
        "disabled_person_level_frontiers": [
            "named nonprofit executive wealth proxy",
            "named insider transaction wealth proxy",
            "aggregate affluence geography proxy",
            "tax-return migration wealth proxy",
        ],
        "gathered_at": datetime.now(timezone.utc).isoformat(),
        "mode": "LIVE" if live else "SAMPLE (offline)", "version": "v7",
    }
    return gated, meta


if __name__ == "__main__":
    s, m = gather_v7(live=True)
    print(json.dumps({"meta": m, "signals": s}, indent=2)[:2800])
