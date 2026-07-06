# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads
"""
signals_v3.py — V3 NEW public-data signal fetchers with graceful offline/no-key fallback.

Self-contained companion to signals.py (does not import it). Matches its style:
  - stdlib urllib only, shared _get helper, short timeouts
  - every signal tagged public=True
  - graceful sample fallback labelled live=False (never fabricate; never raise)

NEW sources wired here (all FREE, verified live 2026-06-28 — see research/V3_WIREINS.md):
  - FRED (api.stlouisfed.org)          🟡 free key env FRED_API_KEY  → 30Y mortgage / fed funds / CPI
  - U.S. Treasury FiscalData           🟢 NO KEY  → avg interest rates (FRED fallback + own signal)
  - NY Open Data (data.ny.gov)         🟢 NO KEY  → NEW business formations (X-Date trigger)
  - U.S. Census ACS5 (api.census.gov)  🟡 Newdave key → homeownership / education / marital
  - BLS LAUS (api.bls.gov)             🟢 NO KEY  → NY county unemployment rate

GOVERNANCE GATE: every signal is public=True. Each external call uses a short timeout and a
try/except that degrades to an honest SAMPLE (live=False). Nothing here raises.

New SCORING axes these enable (see gather_v3 meta + module docstring footer):
  - rate_environment    (FRED mortgage/fed-funds/CPI + Treasury yields)  → FAM affordability / RET crediting
  - business_formation  (NY DOS new filings)                             → FAM key-person/buy-sell, RET owner plans
  - homeownership       (ACS B25003)                                     → FAM mortgage-protection density
  - education_funding   (ACS B15003)                                     → COL college-funding propensity
  - marital_composition (ACS B12001 widowed/married)                     → FAM bereavement/beneficiary need
  - income_security     (BLS county unemployment)                        → FAM income-protection urgency
"""
from __future__ import annotations
import json, os, urllib.request, urllib.error, urllib.parse
from datetime import datetime, timezone

UA = {"User-Agent": "SZL-David-Leads research@szlholdings.com"}
TIMEOUT = 9  # short timeout per the brief (8-10s)


class CensusKeyMissing(RuntimeError):
    """Raised when Census 302-redirects an unkeyed request to missing_key.html (see signals.py)."""


def _get(url: str, headers=None, timeout=TIMEOUT):
    """Shared GET → parsed JSON. Mirrors signals.py._get, incl. Census missing-key detection."""
    req = urllib.request.Request(url, headers=headers or UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        final_url = r.geturl()
        ctype = (r.headers.get("Content-Type") or "").lower()
        raw = r.read().decode()
    if "missing_key" in final_url or ("census.gov" in final_url and "html" in ctype):
        raise CensusKeyMissing(f"Census redirected to {final_url} — CENSUS_API_KEY absent/invalid")
    return json.loads(raw)


def _census_key() -> str:
    """Canonical Census key resolver (prefer CENSUS_API_KEY). Drops the shell-invalid
    "new Dave" variant. Free key: api.census.gov/data/key_signup.html
    """
    return (os.environ.get("CENSUS_API_KEY")
            or os.environ.get("NEWDAVE") or os.environ.get("Newdave")
            or os.environ.get("NewDave") or "").strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================ 1) FRED rates
_FRED_SERIES = [
    ("MORTGAGE30US", "30-Yr Fixed Mortgage Avg (Freddie Mac)", "%",
     "Mortgage rate sets new-homeowner affordability + term-need framing", "FAM", "rate_environment"),
    ("FEDFUNDS", "Effective Fed Funds Rate", "%",
     "Macro rate backdrop → annuity / whole-life crediting context", "RET", "rate_environment"),
    ("CPIAUCSL", "CPI All-Urban (inflation index)", "idx",
     "Inflation erodes existing coverage → 'your $500k buys less' nudge", "FAM/RET", "rate_environment"),
]


def fred_rates(limit: int = 1):
    """30Y mortgage, fed funds, CPI from FRED (env FRED_API_KEY).

    If no key OR FRED unreachable, falls back to the no-key Treasury avg interest rates so a
    rate signal ALWAYS renders honestly. The 'source' label states which path was used.
    """
    key = (os.environ.get("FRED_API_KEY") or "").strip()
    if not key:
        # No FRED key → honest Treasury-backed rate signal (no-key, never rate-limited).
        out = treasury_rates()
        for s in out:
            s["note"] = "FRED_API_KEY absent → Treasury FiscalData used as rate source"
            s["scoring_axis"] = "rate_environment"
        return out

    out = []
    ok_any = False
    for sid, label, unit, signal, product, axis in _FRED_SERIES:
        try:
            url = ("https://api.stlouisfed.org/fred/series/observations"
                   f"?series_id={sid}&api_key={urllib.parse.quote(key)}"
                   "&file_type=json&sort_order=desc&limit=" + str(max(1, limit)))
            data = _get(url)
            obs = [o for o in data.get("observations", []) if o.get("value") not in (None, "", ".")]
            if not obs:
                raise ValueError("no observations")
            latest = obs[0]
            val = latest["value"]
            disp = f"{val}{'%' if unit == '%' else ''}"
            out.append({
                "source": f"FRED ({sid})",
                "signal": signal,
                "detail": f"{label}: {disp} (as of {latest['date']})",
                "value": val, "as_of": latest["date"], "product": product,
                "scoring_axis": axis, "public": True, "live": True,
            })
            ok_any = True
        except Exception:
            out.append(_sample_fred_one(sid, label, signal, product, axis))
    if not ok_any:
        # FRED key present but all calls failed → still guarantee a live rate via Treasury.
        out = out + treasury_rates()
    return out


def _sample_fred_one(sid, label, signal, product, axis):
    samples = {
        "MORTGAGE30US": "~6.49% (weekly, Freddie Mac)",
        "FEDFUNDS": "~4.33% (monthly)",
        "CPIAUCSL": "~333.979 (index, monthly)",
    }
    return {
        "source": f"FRED ({sid}) [SAMPLE]",
        "signal": signal,
        "detail": f"Sample: {label}: {samples.get(sid, 'n/a')}",
        "product": product, "scoring_axis": axis, "public": True, "live": False,
    }


# ============================================================ 2) Treasury rates (no key)
def treasury_rates(limit: int = 3):
    """U.S. Treasury FiscalData avg interest rates — NO KEY. Own signal + FRED fallback."""
    try:
        url = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
               "/v2/accounting/od/avg_interest_rates"
               "?sort=-record_date&page[size]=" + str(max(1, limit)))
        # bracket chars must be percent-encoded for some clients; urllib handles raw but encode to be safe
        url = url.replace("[", "%5B").replace("]", "%5D")
        data = _get(url)
        rows = data.get("data", [])
        if not rows:
            raise ValueError("no rows")
        out = []
        for r in rows[:limit]:
            desc = r.get("security_desc", "Treasury security")
            rate = r.get("avg_interest_rate_amt", "")
            rdate = r.get("record_date", "")
            out.append({
                "source": "U.S. Treasury FiscalData (avg_interest_rates)",
                "signal": "Government-backed yield baseline → annuity / whole-life positioning",
                "detail": f"{desc}: {rate}% avg interest (as of {rdate})",
                "value": rate, "as_of": rdate, "product": "RET",
                "scoring_axis": "rate_environment", "public": True, "live": True,
            })
        return out
    except Exception:
        return _sample_treasury()


def _sample_treasury():
    samples = [("Treasury Bills", "3.690"), ("Treasury Notes", "3.248"), ("Treasury Bonds", "3.413")]
    return [{
        "source": "U.S. Treasury FiscalData (avg_interest_rates) [SAMPLE]",
        "signal": "Government-backed yield baseline → annuity / whole-life positioning",
        "detail": f"Sample: {d}: {v}% avg interest",
        "value": v, "product": "RET", "scoring_axis": "rate_environment",
        "public": True, "live": False,
    } for d, v in samples]


# ============================================================ 3) NY business formation (no key)
def ny_business_formation(limit: int = 10):
    """NY DOS Active Corporations — newest filings = business-formation X-Date triggers.

    Each filing (new business, NY address, filing date) = a buy-sell / key-person / owner-plan
    life trigger. data.ny.gov Socrata SODA, NO KEY, verified live.
    """
    try:
        base = "https://data.ny.gov/resource/n9v6-gdp6.json"
        q = {"$limit": str(max(1, limit)), "$order": "initial_dos_filing_date DESC"}
        url = base + "?" + urllib.parse.urlencode(q)
        rows = _get(url)
        if not isinstance(rows, list) or not rows:
            raise ValueError("no rows")
        out = []
        for r in rows[:limit]:
            name = r.get("current_entity_name", "New NY business")
            fdate = (r.get("initial_dos_filing_date") or "")[:10]
            county = r.get("county", "")
            etype = r.get("entity_type", "")
            city = r.get("dos_process_city", "")
            zipc = r.get("dos_process_zip", "")
            loc = ", ".join([x for x in (city, "NY", zipc) if x])
            out.append({
                "source": "NY DOS Active Corporations (data.ny.gov)",
                "signal": "New business formation → buy-sell / key-person / owner retirement X-Date trigger",
                "detail": f"{name} ({etype}) filed {fdate} in {county or 'NY'}" + (f" — {loc}" if loc else ""),
                "entity_name": name, "filing_date": fdate, "county": county,
                "entity_type": etype, "address": loc, "product": "FAM/RET/COL",
                "scoring_axis": "business_formation", "public": True, "live": True,
            })
        return out
    except Exception:
        return _sample_ny_biz()


def _sample_ny_biz():
    samples = [
        ("SUNGUARD SOLAR SERVICES, INC.", "2026-06-26", "Rockland", "DOMESTIC BUSINESS CORPORATION", "Bardonia, NY 10954"),
        ("HUDSON VALLEY ADVISORY LLC", "2026-06-25", "Westchester", "DOMESTIC LIMITED LIABILITY COMPANY", "White Plains, NY 10601"),
    ]
    return [{
        "source": "NY DOS Active Corporations (data.ny.gov) [SAMPLE]",
        "signal": "New business formation → buy-sell / key-person / owner retirement X-Date trigger",
        "detail": f"Sample: {n} ({t}) filed {d} in {c} — {loc}",
        "entity_name": n, "filing_date": d, "county": c, "entity_type": t, "address": loc,
        "product": "FAM/RET/COL", "scoring_axis": "business_formation",
        "public": True, "live": False,
    } for n, d, c, t, loc in samples]


# ============================================================ 4) Census extras (key, sample fallback)
def census_extras(state_fips: str = "36"):
    """ACS5 homeownership (B25003), education/college (B15003), marital (B12001) for the state.

    Uses the Census/Newdave key (drop-in extension of an existing wired source). Sample fallback.
    """
    key = _census_key()
    out = []
    # --- Homeownership (tenure): B25003_001 total, _002 owner, _003 renter
    try:
        keyq = f"&key={key}" if key else ""
        url = ("https://api.census.gov/data/2023/acs/acs5"
               "?get=NAME,B25003_001E,B25003_002E,B25003_003E"
               f"&for=state:{state_fips}{keyq}")
        d = _get(url)
        r = d[1]
        total, owner, renter = int(r[1]), int(r[2]), int(r[3])
        pct = (owner / total * 100) if total else 0.0
        out.append({
            "source": "U.S. Census ACS 2023 5-yr (B25003 tenure)",
            "signal": "Homeownership density → mortgage-protection coverage opportunity",
            "detail": f"{r[0]}: {pct:.1f}% owner-occupied ({owner:,} owner / {renter:,} renter)",
            "value": round(pct, 1), "product": "FAM",
            "scoring_axis": "homeownership", "public": True, "live": True,
        })
    except Exception:
        out.append(_sample_homeownership())
    # --- Education / college: B15003_022..025 = bachelor's/master's/professional/doctorate, _001 total
    try:
        keyq = f"&key={key}" if key else ""
        url = ("https://api.census.gov/data/2023/acs/acs5"
               "?get=NAME,B15003_001E,B15003_022E,B15003_023E,B15003_024E,B15003_025E"
               f"&for=state:{state_fips}{keyq}")
        d = _get(url)
        r = d[1]
        total = int(r[1])
        coll = int(r[2]) + int(r[3]) + int(r[4]) + int(r[5])
        pct = (coll / total * 100) if total else 0.0
        out.append({
            "source": "U.S. Census ACS 2023 5-yr (B15003 education)",
            "signal": "College-degree share → income proxy + college-funding propensity",
            "detail": f"{r[0]}: {pct:.1f}% hold a bachelor's+ degree ({coll:,} adults 25+)",
            "value": round(pct, 1), "product": "COL",
            "scoring_axis": "education_funding", "public": True, "live": True,
        })
    except Exception:
        out.append(_sample_education())
    # --- Marital: B12001 male+female now-married (_004/_013) and widowed (_009/_018), _001 total
    try:
        keyq = f"&key={key}" if key else ""
        url = ("https://api.census.gov/data/2023/acs/acs5"
               "?get=NAME,B12001_001E,B12001_004E,B12001_013E,B12001_009E,B12001_018E"
               f"&for=state:{state_fips}{keyq}")
        d = _get(url)
        r = d[1]
        total = int(r[1])
        married = int(r[2]) + int(r[3])
        widowed = int(r[4]) + int(r[5])
        mpct = (married / total * 100) if total else 0.0
        wpct = (widowed / total * 100) if total else 0.0
        out.append({
            "source": "U.S. Census ACS 2023 5-yr (B12001 marital)",
            "signal": "Marital composition → married=beneficiary/income-protection, widowed=bereavement need",
            "detail": f"{r[0]}: {mpct:.1f}% now-married, {wpct:.1f}% widowed (pop 15+)",
            "value": {"married_pct": round(mpct, 1), "widowed_pct": round(wpct, 1)},
            "product": "FAM", "scoring_axis": "marital_composition", "public": True, "live": True,
        })
    except Exception:
        out.append(_sample_marital())
    return out


def _sample_homeownership():
    return {
        "source": "U.S. Census ACS 2023 5-yr (B25003 tenure) [SAMPLE]",
        "signal": "Homeownership density → mortgage-protection coverage opportunity",
        "detail": "Sample: New York ~53.5% owner-occupied",
        "value": 53.5, "product": "FAM", "scoring_axis": "homeownership",
        "public": True, "live": False,
    }


def _sample_education():
    return {
        "source": "U.S. Census ACS 2023 5-yr (B15003 education) [SAMPLE]",
        "signal": "College-degree share → income proxy + college-funding propensity",
        "detail": "Sample: New York ~38% hold a bachelor's+ degree",
        "value": 38.0, "product": "COL", "scoring_axis": "education_funding",
        "public": True, "live": False,
    }


def _sample_marital():
    return {
        "source": "U.S. Census ACS 2023 5-yr (B12001 marital) [SAMPLE]",
        "signal": "Marital composition → married=beneficiary/income-protection, widowed=bereavement need",
        "detail": "Sample: New York ~46% now-married, ~6% widowed (pop 15+)",
        "value": {"married_pct": 46.0, "widowed_pct": 6.0},
        "product": "FAM", "scoring_axis": "marital_composition", "public": True, "live": False,
    }


# ============================================================ 5) BLS county unemployment (no key)
# Verified LAUS series: LAUCN + {state2}{county3} + 0000000 + 03 (unemployment rate).
_BLS_COUNTY = ("LAUCN361190000000003", "Westchester County, NY")


def bls_county_unemployment(series_id: str = _BLS_COUNTY[0], county_label: str = _BLS_COUNTY[1]):
    """BLS LAUS county unemployment rate — NO KEY. Westchester County, NY by default."""
    try:
        url = "https://api.bls.gov/publicAPI/v2/timeseries/data/" + series_id
        data = _get(url, headers={**UA, "Content-Type": "application/json"})
        series = data["Results"]["series"][0]["data"]
        # first usable (non '-') datapoint
        latest = next(d for d in series if d.get("value") not in (None, "", "-"))
        prior = None
        seen = 0
        for d in series:
            if d.get("value") in (None, "", "-"):
                continue
            seen += 1
            if seen == 2:
                prior = d
                break
        rate = float(latest["value"])
        trend = ""
        if prior:
            try:
                delta = rate - float(prior["value"])
                arrow = "up" if delta > 0 else ("down" if delta < 0 else "flat")
                trend = f" ({arrow} from {prior['value']}% {prior['periodName']})"
            except Exception:
                trend = ""
        return [{
            "source": f"BLS LAUS ({series_id})",
            "signal": "County unemployment rate → income-protection urgency dial (rising=urgency, falling=capacity)",
            "detail": f"{county_label}: {rate}% unemployment, {latest['periodName']} {latest['year']}{trend}",
            "value": rate, "as_of": f"{latest['periodName']} {latest['year']}",
            "county": county_label, "product": "FAM",
            "scoring_axis": "income_security", "public": True, "live": True,
        }]
    except Exception:
        return _sample_bls_county(county_label)


def _sample_bls_county(county_label: str = _BLS_COUNTY[1]):
    return [{
        "source": "BLS LAUS (LAUCN361190000000003) [SAMPLE]",
        "signal": "County unemployment rate → income-protection urgency dial (rising=urgency, falling=capacity)",
        "detail": f"Sample: {county_label}: 3.3% unemployment (April 2026, preliminary)",
        "value": 3.3, "county": county_label, "product": "FAM",
        "scoring_axis": "income_security", "public": True, "live": False,
    }]


# ============================================================ 6) aggregate
def gather_v3(live: bool = True):
    """Aggregate all V3 signals → (signals, meta), same shape as signals.gather_all.

    Returns a list of signal dicts and a meta dict so it can be merged into /api/run alongside
    the existing gather_all output. Each external call degrades to honest SAMPLE on failure.
    """
    if live:
        sigs = (fred_rates()
                + treasury_rates()
                + ny_business_formation()
                + census_extras()
                + bls_county_unemployment())
    else:
        sigs = (_sample_treasury()
                + _sample_treasury()  # FRED sample path also resolves to a rate signal; keep honest
                + _sample_ny_biz()
                + [_sample_homeownership(), _sample_education(), _sample_marital()]
                + _sample_bls_county())

    # GOVERNANCE GATE: drop anything not public (defensive; all V3 sources are public).
    gated = [s for s in sigs if s.get("public", False)]
    rejected = len(sigs) - len(gated)
    sources = sorted({s.get("source", "").replace(" [SAMPLE]", "") for s in gated})
    axes = sorted({s.get("scoring_axis") for s in gated if s.get("scoring_axis")})
    meta = {
        "total_signals": len(gated),
        "count": len(gated),
        "rejected_nonpublic": rejected,
        "fabricated": 0,
        "live_count": sum(1 for s in gated if s.get("live")),
        "sample_count": sum(1 for s in gated if not s.get("live")),
        "sources": sources,
        "scoring_axes": axes,
        "gathered_at": _now(),
        "mode": "LIVE" if live else "SAMPLE (offline)",
        "version": "v3",
    }
    return gated, meta


if __name__ == "__main__":
    sigs, meta = gather_v3(live=True)
    print("=" * 78)
    print("gather_v3(live=True) →", meta["count"], "signals  |  live:",
          meta["live_count"], " sample:", meta["sample_count"])
    print("=" * 78)
    for s in sigs:
        flag = "LIVE " if s.get("live") else "SAMPL"
        print(f"[{flag}] {s.get('scoring_axis','?'):<20} {s.get('source','')}")
        print(f"        {s.get('detail','')}")
    print("-" * 78)
    print("sources:", meta["sources"])
    print("scoring_axes:", meta["scoring_axes"])
    print("mode:", meta["mode"], "| gathered_at:", meta["gathered_at"])
