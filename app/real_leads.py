# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads · Real Callable Leads (compliant, public records)
"""
real_leads.py — REAL, callable B2B prospects pulled LIVE from public state portals.

HARD DOCTRINE (SZL governed-AI · honest by design):
  * PUBLIC data only. B2B public business/license records ONLY — new business owners and
    newly-licensed professionals from official state open-data portals.
  * NEVER private individuals' personal cell/home numbers. NEVER social-media scraping.
    NEVER fabricated names or numbers.
  * Every real record carries its public source citation + a signed receipt (public signals,
    fabricated=0). David does his own compliant outreach (no auto-dialing).
  * If a portal is unreachable, that source degrades to a clearly-labelled [SAMPLE] — never faked.

Sources (no API key required):
  * DE Division of Revenue — Business Licenses : data.delaware.gov resource 5zy2-grhr
  * CT Dept. of Consumer Protection — Licenses  : data.ct.gov     resource ngch-56tr
  * CT Secretary of State — Business Filings     : data.ct.gov     resource ah3s-bes7
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from . import receipts as rc

UA = {"User-Agent": "SZL-David-Leads research@szlholdings.com"}
TIMEOUT = 12  # seconds — short, per doctrine

# ---- source citations (public, official) ----------------------------------------------------
SRC_DE_BIZ = {
    "label": "DE Division of Revenue — Business Licenses",
    "url": "https://data.delaware.gov/resource/5zy2-grhr.json",
    "portal": "https://data.delaware.gov/Government-and-Finance/Active-and-Inactive-Business-License-List/5zy2-grhr",
}
SRC_CT_LIC = {
    "label": "CT Dept. of Consumer Protection — Professional Licenses",
    "url": "https://data.ct.gov/resource/ngch-56tr.json",
    "portal": "https://data.ct.gov/Business/Active-Engineers/ngch-56tr",
}
SRC_CT_ENT = {
    "label": "CT Secretary of State — Business Filings",
    "url": "https://data.ct.gov/resource/ah3s-bes7.json",
    "portal": "https://data.ct.gov/Business/Business-Filings/ah3s-bes7",
}
SRC_NY_CORP = {
    "label": "NY Dept. of State — Active Corporations",
    "url": "https://data.ny.gov/resource/n9v6-gdp6.json",
    "portal": "https://data.ny.gov/Government-Finance/Active-Corporations-Beginning-1800/n9v6-gdp6",
}
SRC_NJ_BIZ = {
    "label": "NJ Dept. of Children & Families — Licensed Child Care Centers",
    "url": "https://data.nj.gov/resource/cru5-4rmm.json",
    "portal": "https://data.nj.gov/Reference-Data/Licensed-Child-Care-Centers/cru5-4rmm",
}
SRC_PA_BIZ = {
    "label": "PA Dept. of State — Registered Business Entities",
    "url": "https://data.pa.gov/resource/xvd7-5r2c.json",
    "portal": "https://data.pa.gov/Government-That-Works/Registered-Business-Entities/xvd7-5r2c",
}
SRC_MD_BIZ = {
    "label": "MD Dept. of Agriculture — Licensed Plant/Pesticide Facilities",
    "url": "https://opendata.maryland.gov/resource/cygz-kinv.json",
    "portal": "https://opendata.maryland.gov/resource/cygz-kinv",
}


# ============================================================================================
# data cleaning — strip HTML entities, collapse whitespace, smart title-case, drop garbage
# ============================================================================================
# tokens that must stay upper-case when we title-case an ALL-CAPS public-record name
_KEEP_UPPER = {
    "LLC", "L.L.C.", "INC", "INC.", "LLP", "LP", "PC", "PLLC", "PA", "DBA", "USA",
    "II", "III", "IV", "CT", "DE", "NY", "NJ", "PA", "MA", "RI", "MD", "VA",
    "HVAC", "LLC.", "CO", "CO.", "&",
}


def _clean_text(s: Any) -> str:
    """Unescape HTML entities (&QUOT; &AMP; &#39; …), collapse whitespace, trim."""
    if s is None:
        return ""
    t = str(s)
    # Socrata sometimes emits upper-cased entity names like &QUOT; — normalise case for unescape
    t = re.sub(r"&[A-Za-z]+;", lambda m: m.group(0).lower(), t)
    t = html.unescape(t)
    t = t.replace(" ", " ")
    # cut field-bleed: dirty source rows sometimes leak the next CSV column in via a stray quote
    # (e.g. 'Bichara","0...') — keep only the text before the first double-quote.
    if '"' in t:
        t = t.split('"', 1)[0]
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"[\s,;|]+$", "", t).strip()  # drop trailing separators left by the cut
    return t


def _smart_title(name: str) -> str:
    """Title-case an ALL-CAPS public-record name while preserving LLC/INC/etc.
    Leave already-mixed-case names (real estate portals often store proper case) untouched."""
    n = _clean_text(name)
    if not n:
        return ""
    # only re-case names that are essentially all-caps (public license registries store CAPS)
    letters = [c for c in n if c.isalpha()]
    if letters and not all(c.isupper() for c in letters):
        return n  # already mixed-case — trust the source
    out = []
    for word in n.split(" "):
        up = word.upper().strip(".,")
        if up in _KEEP_UPPER:
            out.append(word.upper())
        elif "-" in word:
            out.append("-".join(p.capitalize() for p in word.split("-")))
        else:
            out.append(word.capitalize())
    return " ".join(out)


_GARBAGE = {"", "n/a", "na", "none", "null", "unknown", "test", "."}


def _is_garbage_name(name: str) -> bool:
    n = (name or "").strip().lower()
    if n in _GARBAGE:
        return True
    if not re.search(r"[a-z]", n):  # no letters at all (pure digits / punctuation)
        return True
    return False


def _looks_like_account_id(name: str) -> bool:
    """CT entity 'name' is often an internal account id (e.g. '0001781691' or 'BF-0014183096')."""
    n = (name or "").strip()
    return bool(re.fullmatch(r"[A-Z]{0,3}[-\s]?\d{6,}", n))


# ============================================================================================
# HTTP
# ============================================================================================
def _get(url: str) -> Any:
    req = urllib.request.Request(url, headers=UA, method="GET")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()


def _date10(s: Any) -> str:
    """Return YYYY-MM-DD only if it's a plausible real date (2015-01-01 .. today).
    DE/CT portals sometimes store future validity/expiration dates in these fields;
    showing '2092-07-11' as a filing date is misleading, so we drop implausible dates
    rather than display a wrong one (honest by design — never show a misleading date)."""
    if not s:
        return ""
    d = str(s)[:10]
    try:
        dt = datetime.strptime(d, "%Y-%m-%d").date()
    except Exception:
        return ""
    today = datetime.now(timezone.utc).date()
    if dt < datetime(2015, 1, 1).date() or dt > today:
        return ""
    return d


# ============================================================================================
# classify_prospect — public record -> NYL product angle + why  (pure)
# ============================================================================================
_BIZ_ANGLES = {
    "default": {
        "product_angle": "Key-person life + buy-sell funding",
        "product": "BIZ",
        "why": "A newly-licensed/registered business owner rarely has key-person coverage or a "
               "funded buy-sell — protect the owner, partners, and business continuity.",
    },
    "professional": {
        "product_angle": "Business-continuation + disability overhead expense",
        "product": "BIZ",
        "why": "Professional-services firms depend on the principal — DI overhead-expense and a "
               "continuation plan keep the practice running if the owner is out.",
    },
    "dealer": {
        "product_angle": "Key-person + group benefits",
        "product": "BIZ",
        "why": "Dealers/retailers with employees are prime for key-person cover and group benefits "
               "to retain staff.",
    },
}
_LICENSEE_ANGLE = {
    "product_angle": "Starter life (term) + individual disability income",
    "product": "FAM",
    "why": "A newly-licensed professional is early-career with rising income — lock in low-cost "
           "term and own-occupation DI now while young and healthy.",
}
_ENTITY_ANGLE = {
    "product_angle": "Business-formation review: key-person / buy-sell",
    "product": "BIZ",
    "why": "A brand-new entity formation is the moment to put owner protection and a buy-sell in "
           "place before the business has dependents on its cash flow.",
}

_PROF_KEYWORDS = ("service", "professional", "consult", "legal", "account", "medical", "care",
                  "real estate", "apprais", "engineer", "architect", "dental", "therap")
_DEALER_KEYWORDS = ("dealer", "retail", "wholesale", "mercantile", "restaurant", "contractor")


def classify_prospect(record: dict[str, Any]) -> dict[str, Any]:
    """Map a real public record to an insurance product angle. Pure, never fabricates."""
    rtype = record.get("type")
    if rtype == "licensee":
        return dict(_LICENSEE_ANGLE)
    if rtype == "entity":
        return dict(_ENTITY_ANGLE)
    # business
    cat = (record.get("category") or "").lower()
    if any(k in cat for k in _DEALER_KEYWORDS):
        return dict(_BIZ_ANGLES["dealer"])
    if any(k in cat for k in _PROF_KEYWORDS):
        return dict(_BIZ_ANGLES["professional"])
    return dict(_BIZ_ANGLES["default"])


# ============================================================================================
# fetchers — each returns {source, citation_url, mode, records:[...]}; honest [SAMPLE] on failure
# ============================================================================================
def fetch_de_businesses(limit: int = 15) -> dict[str, Any]:
    """DE business licenses issued in the last 180 days that carry a public address."""
    since = _iso_days_ago(180)
    where = f"current_license_valid_from > '{since}T00:00:00' AND address_1 IS NOT NULL"
    url = (SRC_DE_BIZ["url"] + "?" + urllib.parse.urlencode({
        "$where": where,
        "$order": "current_license_valid_from DESC",
        "$limit": str(limit),
    }))
    try:
        rows = _get(url)
        out = []
        for r in rows:
            name = _smart_title(r.get("business_name") or r.get("trade_name") or "")
            if _is_garbage_name(name):
                continue
            addr = _clean_text(r.get("address_1"))
            out.append({
                "type": "business",
                "name": name,
                "category": _smart_title(r.get("category") or "") or "Business",
                "address": addr,
                "city": _smart_title(r.get("city") or ""),
                "state": (r.get("state") or "").upper()[:20],
                "zip": _clean_text(r.get("zip")),
                "license_or_issue_date": _date10(r.get("current_license_valid_from")),
                "public": True,
            })
        if out:
            return {"source": SRC_DE_BIZ["label"], "citation": SRC_DE_BIZ,
                    "mode": "LIVE", "records": out[:limit]}
    except Exception:
        pass
    return {"source": SRC_DE_BIZ["label"], "citation": SRC_DE_BIZ,
            "mode": "SAMPLE", "records": _sample_de()}


def fetch_ct_licenses(limit: int = 15) -> dict[str, Any]:
    """CT active professional licenses, most-recently issued first."""
    where = "active='1' AND issuedate IS NOT NULL"
    url = (SRC_CT_LIC["url"] + "?" + urllib.parse.urlencode({
        "$where": where,
        "$order": "issuedate DESC",
        "$limit": str(limit * 2),  # over-fetch; we prioritise agent-relevant credentials
    }))
    try:
        rows = _get(url)
        out = []
        for r in rows:
            name = _smart_title(r.get("name") or "")
            if _is_garbage_name(name) or _looks_like_account_id(name):
                continue
            cred = _clean_text(r.get("credential") or "")
            out.append({
                "type": "licensee",
                "name": name,
                "credential": cred or "Professional license",
                "status": _clean_text(r.get("status") or "ACTIVE").title(),
                "address": _clean_text(r.get("address")),
                "city": _smart_title(r.get("city") or ""),
                "state": (r.get("state") or "CT").upper()[:4],
                "zip": _clean_text(r.get("zip")),
                "license_or_issue_date": _date10(r.get("issuedate")),
                "public": True,
                "_relevant": any(k in cred.lower() for k in _PROF_KEYWORDS),
            })
        if out:
            # prioritise agent-relevant credentials (real estate / professional services), keep order otherwise
            out.sort(key=lambda x: (not x.get("_relevant", False),))
            for x in out:
                x.pop("_relevant", None)
            return {"source": SRC_CT_LIC["label"], "citation": SRC_CT_LIC,
                    "mode": "LIVE", "records": out[:limit]}
    except Exception:
        pass
    return {"source": SRC_CT_LIC["label"], "citation": SRC_CT_LIC,
            "mode": "SAMPLE", "records": _sample_ct_lic()}


def fetch_ct_new_entities(limit: int = 15) -> dict[str, Any]:
    """CT new business formations (Certificate of Organization/Incorporation), newest first.
    The public 'name' field is an internal account id, so these are flagged 'entity id only'."""
    url = (SRC_CT_ENT["url"] + "?" + urllib.parse.urlencode({
        "$order": "create_dt DESC",
        "$limit": "200",
    }))
    try:
        rows = _get(url)
        out = []
        for r in rows:
            ftype = _clean_text(r.get("filing_type") or r.get("type") or "")
            fl = ftype.lower()
            # NEW formations only — exclude annual reports, dissolutions, amendments
            if not any(k in fl for k in ("organization", "incorporation", "formation", "registration")):
                continue
            raw_name = _clean_text(r.get("name") or "")
            acct = _looks_like_account_id(raw_name)
            name = raw_name if not _is_garbage_name(raw_name) else (raw_name or "CT entity")
            out.append({
                "type": "entity",
                "name": name or "CT entity",
                "category": ftype or "New business formation",
                "address": "",
                "city": "",
                "state": "CT",
                "zip": "",
                "license_or_issue_date": _date10(r.get("filing_date") or r.get("create_dt")),
                "public": True,
                "_account_id": acct,
            })
            if len(out) >= limit:
                break
        if out:
            return {"source": SRC_CT_ENT["label"], "citation": SRC_CT_ENT,
                    "mode": "LIVE", "records": out[:limit]}
    except Exception:
        pass
    return {"source": SRC_CT_ENT["label"], "citation": SRC_CT_ENT,
            "mode": "SAMPLE", "records": _sample_ct_ent()}


def fetch_ny_corporations(limit: int = 15) -> dict[str, Any]:
    """NY corporations filed in the last 365 days that carry a public process-service address."""
    since = _iso_days_ago(365)
    where = (f"initial_dos_filing_date > '{since}T00:00:00' "
             "AND dos_process_address_1 IS NOT NULL AND current_entity_name IS NOT NULL")
    url = (SRC_NY_CORP["url"] + "?" + urllib.parse.urlencode({
        "$where": where,
        "$order": "initial_dos_filing_date DESC",
        "$limit": str(limit),
    }))
    try:
        rows = _get(url)
        out = []
        for r in rows:
            name = _smart_title(r.get("current_entity_name") or "")
            if _is_garbage_name(name):
                continue
            out.append({
                "type": "business",
                "name": name,
                "category": _smart_title(r.get("entity_type") or "") or "Corporation",
                "address": _clean_text(r.get("dos_process_address_1")),
                "city": _smart_title(r.get("dos_process_city") or ""),
                "state": (r.get("dos_process_state") or "NY").upper()[:4],
                "zip": _clean_text(r.get("dos_process_zip")),
                "license_or_issue_date": _date10(r.get("initial_dos_filing_date")),
                "public": True,
            })
        if out:
            return {"source": SRC_NY_CORP["label"], "citation": SRC_NY_CORP,
                    "mode": "LIVE", "records": out[:limit]}
    except Exception:
        pass
    return {"source": SRC_NY_CORP["label"], "citation": SRC_NY_CORP,
            "mode": "SAMPLE", "records": _sample_generic("NY", "Coastal Holdings Corp")}


def fetch_nj_businesses(limit: int = 15) -> dict[str, Any]:
    """NJ licensed child-care centers (small businesses) with a public business address."""
    url = (SRC_NJ_BIZ["url"] + "?" + urllib.parse.urlencode({
        "$where": "center IS NOT NULL AND addr1 IS NOT NULL",
        "$order": "center ASC",
        "$limit": str(limit),
    }))
    try:
        rows = _get(url)
        out = []
        for r in rows:
            name = _smart_title(r.get("center") or "")
            if _is_garbage_name(name):
                continue
            out.append({
                "type": "business",
                "name": name,
                "category": "Licensed Child Care Center",
                "address": _clean_text(r.get("addr1")),
                "city": _smart_title(r.get("city") or ""),
                "state": "NJ",
                "zip": _clean_text(r.get("zip")),
                "license_or_issue_date": "",  # this registry exposes no clean filing date
                "public": True,
            })
        if out:
            return {"source": SRC_NJ_BIZ["label"], "citation": SRC_NJ_BIZ,
                    "mode": "LIVE", "records": out[:limit]}
    except Exception:
        pass
    return {"source": SRC_NJ_BIZ["label"], "citation": SRC_NJ_BIZ,
            "mode": "SAMPLE", "records": _sample_generic("NJ", "Garden State Learning Center")}


def fetch_pa_businesses(limit: int = 15) -> dict[str, Any]:
    """PA registered business entities, most-recently created first, with a public address."""
    since = _iso_days_ago(365)
    where = (f"creationdate > '{since}T00:00:00' "
             "AND business_name IS NOT NULL AND address_line1 IS NOT NULL")
    url = (SRC_PA_BIZ["url"] + "?" + urllib.parse.urlencode({
        "$where": where,
        "$order": "creationdate DESC",
        "$limit": str(limit),
    }))
    try:
        rows = _get(url)
        out = []
        for r in rows:
            name = _smart_title(r.get("business_name") or "")
            if _is_garbage_name(name):
                continue
            out.append({
                "type": "business",
                "name": name,
                "category": _smart_title(r.get("typeofbusinessregistration") or "") or "Business",
                "address": _clean_text(r.get("address_line1")),
                "city": _smart_title(r.get("city") or ""),
                "state": (r.get("state") or "PA").upper()[:4],
                "zip": _clean_text(r.get("zip")),
                "license_or_issue_date": _date10(r.get("creationdate")),
                "public": True,
            })
        if out:
            return {"source": SRC_PA_BIZ["label"], "citation": SRC_PA_BIZ,
                    "mode": "LIVE", "records": out[:limit]}
    except Exception:
        pass
    return {"source": SRC_PA_BIZ["label"], "citation": SRC_PA_BIZ,
            "mode": "SAMPLE", "records": _sample_generic("PA", "Keystone Contractors Llc")}


def fetch_md_businesses(limit: int = 15) -> dict[str, Any]:
    """MD active licensed plant/pesticide-handling firms with a public business address.
    This portal's CDN rejects SoQL $where filters, so we over-fetch and filter client-side."""
    url = (SRC_MD_BIZ["url"] + "?" + urllib.parse.urlencode({"$limit": str(limit * 5)}))
    try:
        rows = _get(url)
        out = []
        for r in rows:
            if (r.get("bus_status") or "").upper() != "A" or not r.get("arc_street"):
                continue
            name = _smart_title(r.get("firmname") or "")
            if _is_garbage_name(name):
                continue
            out.append({
                "type": "business",
                "name": name,
                "category": "Licensed Facility",
                "address": _clean_text(r.get("arc_street")),
                "city": _smart_title(r.get("arc_city") or ""),
                "state": (r.get("arc_state") or "MD").upper()[:4],
                "zip": _clean_text(r.get("arc_zip")),
                "license_or_issue_date": "",  # this registry exposes no clean issue date
                "public": True,
            })
            if len(out) >= limit:
                break
        if out:
            return {"source": SRC_MD_BIZ["label"], "citation": SRC_MD_BIZ,
                    "mode": "LIVE", "records": out[:limit]}
    except Exception:
        pass
    return {"source": SRC_MD_BIZ["label"], "citation": SRC_MD_BIZ,
            "mode": "SAMPLE", "records": _sample_generic("MD", "Chesapeake Industries Inc")}


# ============================================================================================
# honest [SAMPLE] fallbacks — clearly labelled, public-shaped, never presented as live
# ============================================================================================
def _sample_de() -> list[dict[str, Any]]:
    return [{
        "type": "business", "name": "[SAMPLE] Coastal Services Llc",
        "category": "General Services", "address": "100 Market St", "city": "Wilmington",
        "state": "DE", "zip": "19801", "license_or_issue_date": _iso_days_ago(20),
        "public": True, "_sample": True,
    }]


def _sample_ct_lic() -> list[dict[str, Any]]:
    return [{
        "type": "licensee", "name": "[SAMPLE] J. Rivera", "credential": "Real Estate Broker",
        "status": "Active", "address": "25 Main St", "city": "Hartford", "state": "CT",
        "zip": "06103", "license_or_issue_date": _iso_days_ago(15), "public": True, "_sample": True,
    }]


def _sample_ct_ent() -> list[dict[str, Any]]:
    return [{
        "type": "entity", "name": "[SAMPLE] entity id 00000000", "category": "Certificate of Organization",
        "address": "", "city": "", "state": "CT", "zip": "",
        "license_or_issue_date": _iso_days_ago(3), "public": True, "_account_id": True, "_sample": True,
    }]


def _sample_generic(state: str, name: str) -> list[dict[str, Any]]:
    return [{
        "type": "business", "name": f"[SAMPLE] {name}", "category": "Business",
        "address": "100 Main St", "city": "Capital City", "state": state, "zip": "00000",
        "license_or_issue_date": _iso_days_ago(20), "public": True, "_sample": True,
    }]


# ============================================================================================
# aggregate — merge, clean, de-dupe, classify, attach contact_quality + citation + receipt
# ============================================================================================
_STATE_FETCHERS = {
    "DE": [("de_biz", fetch_de_businesses)],
    "CT": [("ct_lic", fetch_ct_licenses), ("ct_ent", fetch_ct_new_entities)],
    "NY": [("ny_corp", fetch_ny_corporations)],
    "NJ": [("nj_biz", fetch_nj_businesses)],
    "PA": [("pa_biz", fetch_pa_businesses)],
    "MD": [("md_biz", fetch_md_businesses)],
}


def _contact_quality(rec: dict[str, Any], mode: str) -> str:
    if rec.get("_sample") or mode == "SAMPLE":
        return "[SAMPLE]"
    if rec.get("type") == "entity" and rec.get("_account_id"):
        return "entity id only"
    if rec.get("address"):
        return "business address (public)"
    return "entity id only"


def _dedupe_key(rec: dict[str, Any]) -> str:
    return "|".join([
        (rec.get("name") or "").lower().strip(),
        (rec.get("city") or "").lower().strip(),
        (rec.get("license_or_issue_date") or ""),
    ])


def real_callable_leads(states: list[str] | None = None, limit_per: int = 12) -> dict[str, Any]:
    """Fetch, clean, de-dupe and attest real B2B research records.

    Each record gets an evidence receipt and public citation. The record is not
    callable until the separate deal-desk clearance contract is satisfied.
    """
    states = [s.strip().upper() for s in (states or ["DE", "CT"]) if s.strip()]
    sources: list[dict[str, Any]] = []
    leads: list[dict[str, Any]] = []
    seen: set[str] = set()
    live_count = 0
    sample_count = 0

    for st in states:
        for _key, fetcher in _STATE_FETCHERS.get(st, []):
            try:
                blk = fetcher(limit=limit_per)
            except Exception:
                continue
            mode = blk.get("mode", "SAMPLE")
            citation = blk.get("citation", {})
            sources.append({"state": st, "source": blk.get("source"),
                            "mode": mode, "citation": citation,
                            "count": len(blk.get("records", []))})
            for rec in blk.get("records", []):
                name = _clean_text(rec.get("name"))
                if _is_garbage_name(name) and not rec.get("_account_id"):
                    continue
                k = _dedupe_key(rec)
                if k in seen:
                    continue
                seen.add(k)
                angle = classify_prospect(rec)
                cq = _contact_quality(rec, mode)
                is_sample = cq == "[SAMPLE]"
                lead = {
                    "name": name,
                    "type": rec.get("type"),
                    "category": rec.get("category"),
                    "credential": rec.get("credential"),
                    "status": rec.get("status"),
                    "address": rec.get("address", ""),
                    "city": rec.get("city", ""),
                    "state": rec.get("state", st),
                    "zip": rec.get("zip", ""),
                    "license_or_issue_date": rec.get("license_or_issue_date", ""),
                    "product_angle": angle["product_angle"],
                    "product": angle["product"],
                    "why": angle["why"],
                    "contact_quality": cq,
                    "citation": {"label": citation.get("label", ""),
                                 "url": citation.get("portal") or citation.get("url", "")},
                    "source_state": st,
                }
                # signed receipt over the PUBLIC signal that justifies this real lead
                try:
                    signal = {
                        "source": citation.get("label", "public record"),
                        "signal": f"{rec.get('type')}: {name} ({rec.get('license_or_issue_date','')})",
                        "public": True,
                    }
                    pseudo = {
                        "id": "real_" + hashlib.sha256(k.encode()).hexdigest()[:12],
                        "name": name,
                        "bucket": (rec.get("type") or "lead").upper(),
                        "product": angle["product"],
                    }
                    receipt = rc.make_receipt(pseudo, [signal], 100.0, witness=True)
                    lead["receipt_id"] = receipt["id"]
                    lead["receipt_signed"] = receipt["signed"]
                    lead["_receipt"] = receipt
                except Exception:
                    lead["receipt_id"] = None
                    lead["receipt_signed"] = False
                if is_sample:
                    sample_count += 1
                else:
                    live_count += 1
                leads.append(lead)

    # Surface the most compelling real records first: a public address, then a clean
    # recent record date, then everything else. (Honest ordering, no fabricated data.)
    def _rank(l: dict[str, Any]) -> tuple:
        real_name = 0 if l.get("contact_quality") == "entity id only" else 1  # named > account-id
        has_addr = 1 if l.get("address") else 0
        has_date = 1 if l.get("license_or_issue_date") else 0
        return (real_name, has_addr, has_date, l.get("license_or_issue_date") or "")
    leads.sort(key=_rank, reverse=True)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "leads": leads,
        "summary": {
            "live_count": live_count,
            "sample_count": sample_count,
            "total": len(leads),
            "source_states": states,
        },
        "doctrine": "Public B2B business & license records only · no private personal data · "
                    "every record carries a public citation + signed receipt · honest by design",
    }
