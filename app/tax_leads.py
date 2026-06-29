# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads · Tax-Territory Intelligence (aggregate IRS public data)
"""
tax_leads.py — TERRITORY intelligence from aggregate IRS public statistics.

HARD DOCTRINE (SZL governed-AI · honest by design):
  * PUBLIC, AGGREGATE data only. This layer answers "WHERE should David prospect?",
    never "WHO" — it surfaces affluent ZIPs and money-in-motion counties from
    IRS Statistics-of-Income tables. It names NO individuals. That is the compliant
    use of tax data: aggregate territory targeting, not personal targeting.
  * NEVER fabricated. Every block carries the IRS source citation + a signed receipt.
  * If irs.gov is unreachable the layer degrades to a clearly-labelled [SAMPLE] —
    a tiny bundled illustrative set, never presented as live.

Sources (no API key required):
  * IRS SOI — Individual Income Tax by ZIP : irs.gov/pub/irs-soi/21zpallagi.csv
      agi_stub == 6  -> $200,000+ AGI bracket (the affluence dial)
  * IRS SOI — County-to-County Migration   : irs.gov/pub/irs-soi/countyinflow2122.csv
      AGI carried in by movers -> "money-in-motion" relocation territory
"""
from __future__ import annotations

import csv
import io
import re
import urllib.request
from datetime import datetime, timezone
from typing import Any

from . import receipts as rc

UA = {"User-Agent": "SZL-David-Leads research@szlholdings.com"}
TIMEOUT = 20  # seconds — IRS CSVs are large; cached after first load

# ---- source citations (public, official) ----------------------------------------------------
# ZIP income files fall back across tax years if the newest is briefly unavailable.
SRC_ZIP = {
    "label": "IRS SOI — Individual Income Tax Statistics by ZIP Code (TY2021)",
    "urls": [
        "https://www.irs.gov/pub/irs-soi/21zpallagi.csv",
        "https://www.irs.gov/pub/irs-soi/22zpallagi.csv",
        "https://www.irs.gov/pub/irs-soi/20zpallagi.csv",
    ],
    "portal": "https://www.irs.gov/statistics/soi-tax-stats-individual-income-tax-statistics-zip-code-data-soi",
}
SRC_INFLOW = {
    "label": "IRS SOI — County-to-County Migration, inflow (2021→2022)",
    "urls": [
        "https://www.irs.gov/pub/irs-soi/countyinflow2122.csv",
        "https://www.irs.gov/pub/irs-soi/countyinflow2223.csv",
    ],
    "portal": "https://www.irs.gov/statistics/soi-tax-stats-migration-data",
}

# Atlantic-seaboard scope (David's market). Parsed once into the cache, then filtered per request.
_SEABOARD = {"NY", "NJ", "CT", "PA", "MD", "DE", "MA", "RI", "VA", "NH", "ME",
             "DC", "NC", "SC", "GA", "FL"}
# destination state in the migration file is FIPS-only -> map back to abbreviation
_FIPS_TO_ABBR = {
    "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "23": "ME",
    "24": "MD", "25": "MA", "33": "NH", "34": "NJ", "36": "NY", "37": "NC",
    "42": "PA", "44": "RI", "45": "SC", "51": "VA",
}

# in-process cache (IRS SOI tables are annual) -------------------------------------------------
_CACHE: dict[str, Any] = {"zip": None, "inflow": None}

# NYL product-angle text (territory-level, not individuals) ------------------------------------
ANGLE_AFFLUENT = "Estate planning, premium-financed life, annuity — affluent-ZIP prospecting territory"
ANGLE_MONEY_IN_MOTION = "Money-in-motion: new-resident estate / coverage review (relocation trigger)"


def _open(urls: list[str]):
    """Yield a decoded line iterator for the first reachable URL; raise if all fail."""
    last = None
    for url in urls:
        try:
            req = urllib.request.Request(url, headers=UA, method="GET")
            resp = urllib.request.urlopen(req, timeout=TIMEOUT)
            return url, io.TextIOWrapper(resp, encoding="utf-8", errors="replace")
        except Exception as e:  # pragma: no cover - network dependent
            last = e
            continue
    raise RuntimeError(f"all IRS endpoints unreachable: {last}")


def _to_float(s: Any) -> float:
    try:
        return float(s)
    except Exception:
        return 0.0


# ============================================================================================
# IRS SOI — affluent ZIPs ($200k+ return density)
# ============================================================================================
def _load_zip_affluence() -> dict[str, Any]:
    """Stream the IRS income-by-ZIP CSV once, keeping only seaboard ZIPs. Cache the result.
    Per ZIP: count of $200k+ returns (agi_stub 6, N1), total returns, and $200k+ AGI mass."""
    if _CACHE["zip"] is not None:
        return _CACHE["zip"]
    try:
        used_url, lines = _open(SRC_ZIP["urls"])
        agg: dict[tuple, dict[str, float]] = {}
        with lines:
            rd = csv.DictReader(lines)
            for row in rd:
                st = (row.get("STATE") or "").strip().upper()
                if st not in _SEABOARD:
                    continue
                zc = (row.get("zipcode") or "").strip()
                if not zc or zc in ("00000", "99999") or len(zc) < 5:
                    continue
                try:
                    stub = int(row.get("agi_stub") or 0)
                except Exception:
                    continue
                n1 = _to_float(row.get("N1"))
                d = agg.setdefault((st, zc), {"hi": 0.0, "tot": 0.0, "agi6": 0.0})
                d["tot"] += n1
                if stub == 6:  # $200,000+
                    d["hi"] += n1
                    d["agi6"] += _to_float(row.get("A00100"))  # AGI in $000s
        _CACHE["zip"] = {"mode": "LIVE", "url": used_url, "agg": agg}
    except Exception:
        _CACHE["zip"] = {"mode": "SAMPLE", "url": SRC_ZIP["urls"][0], "agg": _sample_zip_agg()}
    return _CACHE["zip"]


def affluent_zips(states: list[str], top: int = 12) -> tuple[list[dict[str, Any]], str]:
    """Rank affluent ZIPs in the requested states by $200k+ return count (with share)."""
    data = _load_zip_affluence()
    agg = data["agg"]
    want = {s.strip().upper() for s in states}
    rows = []
    for (st, zc), d in agg.items():
        if st not in want or d["hi"] <= 0:
            continue
        share = (d["hi"] / d["tot"] * 100.0) if d["tot"] else 0.0
        rows.append({
            "zip": zc,
            "state": st,
            "high_income_returns": int(round(d["hi"])),       # households with $200k+ AGI
            "total_returns": int(round(d["tot"])),
            "affluent_share": round(share, 1),                 # % of ZIP's returns that are $200k+
            "high_income_agi_000": int(round(d["agi6"])),      # aggregate $200k+ AGI ($ thousands)
            "angle": ANGLE_AFFLUENT,
            "citation": {"label": SRC_ZIP["label"], "url": SRC_ZIP["portal"]},
        })
    # rank by count of affluent households, then by share
    rows.sort(key=lambda r: (r["high_income_returns"], r["affluent_share"]), reverse=True)
    return rows[:top], data["mode"]


# ============================================================================================
# IRS SOI — county migration inflow (money-in-motion)
# ============================================================================================
def _load_inflow() -> dict[str, Any]:
    """Stream the IRS county-inflow CSV once, keeping seaboard destination counties. Cache it.
    The destination county is FIPS-only; its name lives in the 'Total Migration-US and Foreign'
    summary row's y1_countyname field, so we read those rows for per-county total inflow."""
    if _CACHE["inflow"] is not None:
        return _CACHE["inflow"]
    try:
        used_url, lines = _open(SRC_INFLOW["urls"])
        rows: list[dict[str, Any]] = []
        with lines:
            rd = csv.DictReader(lines)
            for row in rd:
                fips = str(row.get("y2_statefips") or "").strip().zfill(2)
                st = _FIPS_TO_ABBR.get(fips)
                if not st:
                    continue
                cn = (row.get("y1_countyname") or "")
                if "Total Migration-US and Foreign" not in cn:
                    continue
                n1 = int(_to_float(row.get("n1")))
                agi = int(_to_float(row.get("agi")))  # $000s carried in by all movers
                if n1 <= 0 or agi <= 0:
                    continue
                name = re.sub(r"\s+Total Migration.*$", "", cn).strip()
                rows.append({"state": st, "county": name, "returns_inflow": n1,
                             "individuals_inflow": int(_to_float(row.get("n2"))),
                             "agi_inflow_000": agi})
        _CACHE["inflow"] = {"mode": "LIVE", "url": used_url, "rows": rows}
    except Exception:
        _CACHE["inflow"] = {"mode": "SAMPLE", "url": SRC_INFLOW["urls"][0], "rows": _sample_inflow_rows()}
    return _CACHE["inflow"]


def money_in_motion(states: list[str], top: int = 12) -> tuple[list[dict[str, Any]], str]:
    """Top inflow counties in the requested states by AGI carried in (relocation = review trigger)."""
    data = _load_inflow()
    want = {s.strip().upper() for s in states}
    rows = []
    for r in data["rows"]:
        if r["state"] not in want:
            continue
        n1 = r["returns_inflow"]
        rows.append({
            "county": r["county"],
            "state": r["state"],
            "returns_inflow": n1,
            "individuals_inflow": r["individuals_inflow"],
            "agi_inflow_000": r["agi_inflow_000"],
            "avg_agi_per_return_000": round(r["agi_inflow_000"] / n1, 1) if n1 else 0.0,
            "angle": ANGLE_MONEY_IN_MOTION,
            "citation": {"label": SRC_INFLOW["label"], "url": SRC_INFLOW["portal"]},
        })
    rows.sort(key=lambda r: r["agi_inflow_000"], reverse=True)
    return rows[:top], data["mode"]


# ============================================================================================
# honest [SAMPLE] fallbacks — clearly labelled, IRS-shaped, never presented as live
# ============================================================================================
def _sample_zip_agg() -> dict[tuple, dict[str, float]]:
    # illustrative shape only; real numbers come from the live IRS CSV
    return {
        ("NY", "10021"): {"hi": 9000.0, "tot": 30000.0, "agi6": 11000000.0},
        ("NJ", "07078"): {"hi": 4200.0, "tot": 9000.0, "agi6": 6200000.0},
        ("CT", "06830"): {"hi": 5100.0, "tot": 12000.0, "agi6": 9800000.0},
    }


def _sample_inflow_rows() -> list[dict[str, Any]]:
    return [
        {"state": "NY", "county": "[SAMPLE] New York County", "returns_inflow": 70000,
         "individuals_inflow": 120000, "agi_inflow_000": 14000000},
        {"state": "NJ", "county": "[SAMPLE] Hudson County", "returns_inflow": 30000,
         "individuals_inflow": 50000, "agi_inflow_000": 3300000},
    ]


# ============================================================================================
# aggregate — affluent ZIPs + money-in-motion + signed receipt over the territory set
# ============================================================================================
def real_tax_territories(states: list[str] | None = None, top: int = 12) -> dict[str, Any]:
    """Build the tax-territory intelligence set (affluent ZIPs + money-in-motion counties) for
    the requested seaboard states. Aggregate IRS public statistics only — territory targeting,
    NOT named individuals. Signs one receipt over the whole territory set."""
    states = [s.strip().upper() for s in (states or ["NY", "NJ", "CT", "PA", "MD", "DE"]) if s.strip()]

    zips, zip_mode = affluent_zips(states, top=top)
    counties, mig_mode = money_in_motion(states, top=top)

    # one signed receipt over the territory set (public, aggregate signals; fabricated=0)
    receipt = None
    try:
        signals = [
            {"source": SRC_ZIP["label"],
             "signal": f"{len(zips)} affluent ZIPs ($200k+ return density) across {','.join(states)}",
             "public": True},
            {"source": SRC_INFLOW["label"],
             "signal": f"{len(counties)} money-in-motion counties by AGI inflow across {','.join(states)}",
             "public": True},
        ]
        pseudo = {
            "id": "tax_territory_" + "_".join(states).lower(),
            "name": f"Tax-territory set: {', '.join(states)}",
            "bucket": "TERRITORY",
            "product": "PROSPECTING-MAP",
        }
        receipt = rc.make_receipt(pseudo, signals, 100.0, witness=True)
    except Exception:
        receipt = None

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "states": states,
        "affluent_zips": zips,
        "money_in_motion": counties,
        "sources": [
            {"label": SRC_ZIP["label"], "url": SRC_ZIP["portal"], "mode": zip_mode},
            {"label": SRC_INFLOW["label"], "url": SRC_INFLOW["portal"], "mode": mig_mode},
        ],
        "summary": {
            "affluent_zip_count": len(zips),
            "money_in_motion_count": len(counties),
            "zip_mode": zip_mode,
            "migration_mode": mig_mode,
            "states": states,
        },
        "receipt_id": receipt["id"] if receipt else None,
        "receipt_signed": receipt["signed"] if receipt else False,
        "_receipt": receipt,
        "label": "aggregate IRS public statistics — territory targeting, not individuals",
        "doctrine": "Public aggregate IRS SOI data only · names no individuals · "
                    "every block carries an IRS citation + a signed receipt · honest by design",
    }
