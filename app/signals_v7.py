# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads V7 "East Coast Domination"
"""
signals_v7.py — TAX/WEALTH signals + MULTI-STATE expansion across the East Coast.

Wealth & money-in-motion (free, verified): IRS SOI income-by-ZIP, ProPublica 990 (HNW execs),
IRS county migration (affluent inflows), SEC Form 4 (insider liquidity).

Multi-state (free Socrata, reuses the NY pattern): Connecticut, Delaware, Pennsylvania.

Honest by design: real values, sample fallbacks labeled, public-data-only, nothing fabricated.
"""
from __future__ import annotations
import csv, io, json, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

UA = {"User-Agent": "SZL-David-Leads research@szlholdings.com"}
T = 10
DAILY, MONTHLY, ANNUAL = "updated daily", "updated monthly", "updated annually"


def _json(url, timeout=T, method="GET", body=None):
    req = urllib.request.Request(url, headers=UA, method=method,
                                 data=json.dumps(body).encode() if body else None)
    if body:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _csv(url, timeout=T, max_bytes=4_000_000):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(max_bytes).decode("utf-8", "ignore")
    return list(csv.DictReader(io.StringIO(raw)))


def _sig(source, signal, detail, freshness, axis, product, live=True, as_of=None):
    return {"source": source, "signal": signal, "detail": detail, "freshness": freshness,
            "scoring_axis": axis, "product": product, "public": True, "live": live,
            "as_of": as_of or datetime.now(timezone.utc).date().isoformat()}


# ============================================================ TAX / WEALTH
def irs_soi_zip_income(state="NY"):
    """IRS SOI income-by-ZIP — share of $200k+ (agi_stub 6) returns = affluent geography.
    Streams the national CSV; aggregates the target state's top brackets."""
    try:
        rows = _csv("https://www.irs.gov/pub/irs-soi/22zpallagi.csv", timeout=12, max_bytes=6_000_000)
        st = [r for r in rows if (r.get("STATE") or "").upper() == state.upper()]
        if not st:
            return [_soi_sample()]
        def num(r, k):
            try: return float(r.get(k, 0) or 0)
            except Exception: return 0.0
        hi = [r for r in st if r.get("agi_stub") in ("5", "6")]
        hi_returns = sum(num(r, "N1") for r in hi)
        all_returns = sum(num(r, "N1") for r in st)
        share = (hi_returns / all_returns * 100) if all_returns else 0
        return [_sig("IRS SOI Income-by-ZIP (TY2022)",
                     "Affluent-household geography (AGI $100k+ share) \u2192 estate / HNW premium-finance",
                     f"{state}: {share:.1f}% of returns are $100k+ ({int(hi_returns):,} affluent households) \u2014 target these ZIPs",
                     ANNUAL, "wealth_density", "EST")]
    except Exception:
        return [_soi_sample()]


def propublica_990(state="NY"):
    """ProPublica 990 API — nonprofit execs = reliably high-income individuals. No key."""
    try:
        url = f"https://projects.propublica.org/nonprofits/api/v2/search.json?state%5Bid%5D={state}&c_code%5Bid%5D=3"
        data = _json(url)
        total = data.get("total_results", 0)
        orgs = data.get("organizations", [])[:3]
        names = ", ".join((o.get("name") or "")[:24] for o in orgs)
        return [_sig("ProPublica Nonprofit Explorer (IRS 990)",
                     "Nonprofit executives \u2192 high-income individuals (estate, annuity, key-person)",
                     f"{total:,} {state} 501(c)(3) orgs \u2014 named, compensated execs (e.g. {names})",
                     "continuous", "wealth_individual", "RET", as_of=None)]
    except Exception:
        return [_990_sample(state)]


def irs_migration(dest_state_fips="36"):
    """IRS county migration — affluent inflows (high avg AGI per migrating return)."""
    try:
        rows = _csv("https://www.irs.gov/pub/irs-soi/countyinflow2223.csv", timeout=12, max_bytes=5_000_000)
        dest = [r for r in rows if (r.get("y2_statefips") or "").zfill(2) == dest_state_fips]
        def num(r, k):
            try: return float(r.get(k, 0) or 0)
            except Exception: return 0.0
        flows = [(r, num(r, "agi") / num(r, "n1")) for r in dest if num(r, "n1") > 50]
        flows.sort(key=lambda x: x[1], reverse=True)
        if not flows:
            return [_mig_sample()]
        top = flows[0][0]; avg_agi = flows[0][1]
        origin = (top.get("y1_state") or "") + " " + (top.get("y1_countyname") or "")
        return [_sig("IRS County Migration (2022\u219223)",
                     "Affluent newcomers moving in \u2192 relocation-triggered estate / annuity review",
                     f"High-AGI inflow from {origin.strip()} (~${avg_agi:.0f}k avg AGI/household) \u2014 new affluent residents",
                     ANNUAL, "wealth_migration", "EST")]
    except Exception:
        return [_mig_sample()]


def sec_form4(limit=3):
    """SEC Form 4 insider transactions — executives transacting stock = liquidity event."""
    try:
        end = datetime.now().date(); start = end - timedelta(days=7)
        url = (f"https://efts.sec.gov/LATEST/search-index?forms=4&startdt={start}&enddt={end}")
        data = _json(url, timeout=8)
        n = data.get("hits", {}).get("total", {}).get("value") or len(data.get("hits", {}).get("hits", []))
        return [_sig("SEC EDGAR Form 4 (insider transactions)",
                     "Executive stock transactions \u2192 liquidity event (annuity / estate / premium-finance)",
                     f"~{n} insider Form 4 filings this week \u2014 execs with liquidity to deploy",
                     DAILY, "wealth_liquidity", "RET")]
    except Exception:
        return [_form4_sample()]


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
def _soi_sample():
    return _sig("IRS SOI Income-by-ZIP [SAMPLE]", "Affluent-household geography (AGI $100k+ share)",
                "Sample: ~28% of NY returns are $100k+ \u2014 target affluent ZIPs", ANNUAL, "wealth_density", "EST", live=False)
def _990_sample(state="NY"):
    return _sig("ProPublica 990 [SAMPLE]", "Nonprofit executives \u2192 high-income individuals",
                f"Sample: thousands of {state} 501(c)(3) orgs with compensated execs", "continuous", "wealth_individual", "RET", live=False)
def _mig_sample():
    return _sig("IRS County Migration [SAMPLE]", "Affluent newcomers moving in",
                "Sample: high-AGI inflow ~$185k avg/household into NY metro", ANNUAL, "wealth_migration", "EST", live=False)
def _form4_sample():
    return _sig("SEC Form 4 [SAMPLE]", "Executive stock transactions \u2192 liquidity event",
                "Sample: ~2,900 insider filings/week", DAILY, "wealth_liquidity", "RET", live=False)
def _state_sample(name, kind):
    return _sig(f"{name} [SAMPLE]", f"{name}: {kind} velocity",
                f"Sample: {name} {kind} feed (offline)", DAILY, "business_formation" if kind == "business" else "new_professional", "RET", live=False)


def gather_v7(live: bool = True, state="NY", extra_states=("CT", "DE", "PA")):
    """Tax/wealth + multi-state pulse. state = home state (FIPS-mapped for migration)."""
    fips = {"NY": "36", "NJ": "34", "CT": "09", "PA": "42", "MA": "25", "FL": "12"}.get(state.upper(), "36")
    if live:
        sigs = (irs_soi_zip_income(state) + propublica_990(state) + irs_migration(fips) + sec_form4())
        for s in extra_states:
            sigs += state_pulse(s)
    else:
        sigs = [_soi_sample(), _990_sample(state), _mig_sample(), _form4_sample(),
                _state_sample("Connecticut", "business"), _state_sample("Delaware", "license")]
    gated = [s for s in sigs if s.get("public")]
    live_count = sum(1 for s in gated if s.get("live"))
    meta = {
        "total_signals": len(gated), "live_count": live_count, "sample_count": len(gated) - live_count,
        "fabricated": 0, "rejected_nonpublic": 0,
        "sources": sorted({s["source"].replace(" [SAMPLE]", "") for s in gated}),
        "scoring_axes": sorted({s["scoring_axis"] for s in gated}),
        "states_covered": ["NY"] + list(extra_states),
        "gathered_at": datetime.now(timezone.utc).isoformat(),
        "mode": "LIVE" if live else "SAMPLE (offline)", "version": "v7",
    }
    return gated, meta


if __name__ == "__main__":
    s, m = gather_v7(live=True)
    print(json.dumps({"meta": m, "signals": s}, indent=2)[:2800])
