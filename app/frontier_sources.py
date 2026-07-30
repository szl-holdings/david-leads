# SPDX-License-Identifier: Apache-2.0
"""High-signal official-data frontiers for entity-level broker research.

Only fields required to identify a business event are requested. Phone numbers,
email addresses, named officers, crash/safety fields, policy identifiers, and
other person-level fields are deliberately excluded at query time.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from . import benefit_frontier
from . import receipts as rc


UA = {"User-Agent": "SZL-David-Leads/1.2 research@szlholdings.com"}
TIMEOUT = 15
DEFAULT_STATES = ("NY", "NJ", "PA", "MD", "DE", "CT")
US_STATE_CODES = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN",
    "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY",
})
_ECHO_CACHE: dict[tuple[tuple[str, ...], int], tuple[datetime, dict[str, Any]]] = {}
_CHICAGO_CACHE: dict[tuple[int, str], tuple[datetime, dict[str, Any]]] = {}
_SAM_CACHE: dict[tuple[tuple[str, ...], int, str], tuple[datetime, dict[str, Any]]] = {}

FMCSA = {
    "id": "fmcsa-company-census",
    "label": "FMCSA Company Census",
    "api": "https://data.transportation.gov/resource/az4n-8mr2.json",
    "portal": (
        "https://data.transportation.gov/Trucking-and-Motorcoaches/"
        "Company-Census-File/az4n-8mr2/about_data"
    ),
}
USASPENDING = {
    "id": "usaspending-contract-activity",
    "label": "USAspending federal contract activity",
    "api": "https://api.usaspending.gov/api/v2/search/spending_by_award/",
    "portal": "https://api.usaspending.gov/docs/intro-tutorial",
}
ECHO = {
    "id": "epa-echo-monitoring-activity",
    "label": "EPA ECHO compliance-monitoring activity",
    "api": "https://echodata.epa.gov/echo",
    "portal": "https://echo.epa.gov/tools/web-services",
}
FCC = {
    "id": "fcc-uls-organization-licenses",
    "label": "FCC ULS organization license activity",
    "api": "https://data.fcc.gov/download/pub/uls/daily",
    "portal": "https://www.fcc.gov/wireless/data/public-access-files-database-downloads",
}
CHICAGO = {
    "id": "chicago-new-business-licenses",
    "label": "Chicago new active business licenses",
    "api": "https://data.cityofchicago.org/resource/r5kz-chrr.json",
    "portal": (
        "https://data.cityofchicago.org/Community-Economic-Development/"
        "Business-Licenses/r5kz-chrr"
    ),
}
SAM = {
    "id": "sam-active-entity-updates",
    "label": "SAM.gov active entity updates",
    "api": "https://api.sam.gov/entity-information/v4/entities",
    "portal": "https://open.gsa.gov/api/entity-api/",
}
FORM5500 = {
    "id": "dol-form5500-benefit-timing",
    "label": "DOL Form 5500 benefit-plan filings",
    "api": "https://askebsa.dol.gov/FOIA%20Files/",
    "portal": benefit_frontier.PORTAL,
}

_ORG_SUFFIX = re.compile(
    r"(?:\bL\.?L\.?C\.?|\bINC(?:ORPORATED)?\.?|\bCORP(?:ORATION)?\.?|"
    r"\bCO(?:MPANY)?\.?|\bLTD\.?|\bLIMITED(?:\s+PARTNERSHIP)?|"
    r"\bL\.?L\.?P\.?|\bL\.?P\.?|\bP\.?L\.?L\.?C\.?|\bP\.?C\.?)\s*$",
    re.IGNORECASE,
)
class SourceConfigurationUnavailable(RuntimeError):
    """A source is lawful but cannot run until an external credential exists."""


FMCSA_SELECT = (
    "legal_name,dba_name,dot_number,add_date,status_code,classdef,business_org_desc,"
    "truck_units,power_units,bus_units,total_drivers,phy_street,phy_city,phy_state,phy_zip"
)
USASPENDING_FIELDS = (
    "Award ID",
    "Recipient Name",
    "Recipient UEI",
    "Recipient Location",
    "Start Date",
    "End Date",
    "Award Amount",
    "Awarding Agency",
    "Description",
    "generated_internal_id",
)
_NON_COMMERCIAL_RECIPIENTS = (
    "CITY OF ",
    "COUNTY OF ",
    "STATE OF ",
    "TOWN OF ",
    "TOWNSHIP OF ",
    "VILLAGE OF ",
    "BOROUGH OF ",
    "UNITED STATES ",
)
_NON_COMMERCIAL_TERMS = (
    " SCHOOL DISTRICT",
    " UNIVERSITY",
    " HOUSING AUTHORITY",
    " TRANSIT AUTHORITY",
    " DEPARTMENT OF ",
)
_FEDERAL_FACILITY_PREFIXES = (
    "US AIR FORCE",
    "US ARMY",
    "US COAST GUARD",
    "US DEPARTMENT",
    "US MARINE CORPS",
    "US NAVY",
    "U.S. AIR FORCE",
    "U.S. ARMY",
    "U.S. COAST GUARD",
    "U.S. DEPARTMENT",
    "U.S. MARINE CORPS",
    "U.S. NAVY",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean(value: Any, limit: int = 240) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _states(values: list[str] | tuple[str, ...] | None) -> list[str]:
    result: list[str] = []
    for value in values or DEFAULT_STATES:
        state = str(value).strip().upper()
        if state in US_STATE_CODES and state not in result:
            result.append(state)
    # The public cockpit covers 27 Eastern markets. The former 12-state cap
    # silently dropped valid selections before they reached the source APIs.
    return result[:30] or list(DEFAULT_STATES)


def _request_json(url: str, payload: dict[str, Any] | None = None) -> Any:
    body = None
    headers = dict(UA)
    method = "GET"
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read(2_000_000).decode("utf-8", "replace"))


def _request_json_headers(url: str, headers: dict[str, str]) -> Any:
    request_headers = dict(UA)
    request_headers.update(headers)
    request = urllib.request.Request(url, headers=request_headers, method="GET")
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read(2_000_000).decode("utf-8", "replace"))


def _date8(value: Any) -> str:
    try:
        return datetime.strptime(str(value), "%Y%m%d").date().isoformat()
    except (TypeError, ValueError):
        return ""


def _date_us(value: Any) -> str:
    try:
        return datetime.strptime(str(value), "%m/%d/%Y").date().isoformat()
    except (TypeError, ValueError):
        return ""


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _nonnegative_float(value: Any) -> float:
    try:
        return max(0.0, round(float(value), 2))
    except (TypeError, ValueError):
        return 0.0


def _organization_name(value: Any) -> str:
    name = _clean(value, 160)
    return name if name and _ORG_SUFFIX.search(name) else ""


def _date_iso(value: Any) -> str:
    text = _clean(value, 32)
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return ""


def _receipt(record: dict[str, Any], signal: str) -> dict[str, Any] | None:
    try:
        identity = "|".join(
            [
                record.get("name", ""),
                record.get("state", ""),
                record.get("credential", ""),
                record.get("license_or_issue_date", ""),
            ]
        )
        pseudo = {
            "id": "frontier_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12],
            "name": record["name"],
            "bucket": "RESEARCH",
            "product": "BIZ",
        }
        return rc.make_receipt(
            pseudo,
            [{
                "source": record["citation"]["label"],
                "signal": signal,
                "public": True,
                "source_class": "PUBLIC",
            }],
            0.0,
            witness=True,
        )
    except Exception:
        return None


def _attach_receipt(record: dict[str, Any], signal: str) -> dict[str, Any]:
    record["observed_at"] = _now().isoformat()
    record["parser_version"] = "frontier-sources/1.2"
    ids = record.get("authoritative_entity_ids") or []
    record["source_record_id"] = _clean(record.get("source_record_id"), 80) or (
        _clean(ids[0].get("value"), 80)
        if ids and isinstance(ids[0], dict)
        else _clean(record.get("credential"), 80)
    )
    canonical = json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    record["normalized_record_sha256"] = hashlib.sha256(canonical).hexdigest()
    bound_signal = (
        f"{signal} normalized_record_sha256={record['normalized_record_sha256']}; "
        f"source_record_id={record['source_record_id']}; "
        f"observed_at={record['observed_at']}; parser_version={record['parser_version']}."
    )
    receipt = _receipt(record, bound_signal)
    record["receipt_id"] = receipt.get("id") if receipt else None
    record["receipt_signed"] = bool(receipt and receipt.get("signed"))
    record["receipt_witnessed"] = bool(receipt and receipt.get("consensus"))
    record["receipt_state"] = (
        "SIGNED"
        if record["receipt_signed"]
        else ("HASH_CHAINED_UNSIGNED" if receipt else "UNAVAILABLE")
    )
    if receipt:
        record["_receipt"] = receipt
    else:
        record["receipt_error"] = "MINTING_FAILED"
    return record


def fetch_fmcsa(states: list[str] | None = None, limit: int = 18) -> dict[str, Any]:
    """Return recent active carrier additions without collecting contact/person fields."""
    state_list = _states(states)
    since = (_now().date() - timedelta(days=45)).strftime("%Y%m%d")
    state_sql = ",".join(f"'{state}'" for state in state_list)
    where = (
        f"status_code='A' AND add_date>='{since}' "
        f"AND phy_state in({state_sql}) AND legal_name is not null"
    )
    query = urllib.parse.urlencode({
        "$select": FMCSA_SELECT,
        "$where": where,
        "$order": "add_date DESC",
        "$limit": str(max(1, min(int(limit), 50))),
    })
    rows = _request_json(f"{FMCSA['api']}?{query}")
    if not isinstance(rows, list):
        raise ValueError("FMCSA response was not an array")

    records: list[dict[str, Any]] = []
    for row in rows:
        name = _clean(row.get("legal_name"), 140)
        dot = _clean(row.get("dot_number"), 20)
        state = _clean(row.get("phy_state"), 2).upper()
        if not name or not dot or state not in state_list:
            continue
        added = _date8(row.get("add_date"))
        power_units = _nonnegative_int(row.get("power_units"))
        drivers = _nonnegative_int(row.get("total_drivers"))
        street = _clean(row.get("phy_street"), 120)
        carrier_class = _clean(row.get("classdef"), 80) or "FMCSA carrier"
        signal = (
            f"USDOT {dot} appeared in the FMCSA Company Census addition field on "
            f"{added or 'date unavailable'}; source reported {power_units} power units "
            f"and {drivers} drivers."
        )
        record = {
            "name": name,
            "dba": _clean(row.get("dba_name"), 140),
            "type": "carrier",
            "category": f"Motor carrier · {carrier_class}",
            "credential": f"USDOT {dot}",
            "status": "ACTIVE_CODE_REPORTED",
            "address": street,
            "city": _clean(row.get("phy_city"), 80),
            "state": state,
            "zip": _clean(row.get("phy_zip"), 12)[:5],
            "license_or_issue_date": added,
            "observed_trigger": "FMCSA company census addition",
            "trigger_date": added,
            "signal_summary": signal,
            "operational_snapshot": {
                "power_units": power_units,
                "drivers": drivers,
                "trucks": _nonnegative_int(row.get("truck_units")),
                "buses": _nonnegative_int(row.get("bus_units")),
            },
            "authoritative_entity_ids": [{"system": "USDOT", "value": dot}],
            "product_angle": "Owner-continuity, disability-overhead, and workforce-benefits review",
            "product": "BIZ",
            "why": (
                "A recently added carrier entity with reported equipment or drivers can justify "
                "a licensed broker review of owner continuity and workforce needs. It does not "
                "establish a coverage gap or underwriting fact."
            ),
            "recommended_next_action": (
                "Confirm current authority in FMCSA SAFER, then locate a business-published "
                "contact channel and document the permitted product conversation."
            ),
            "contact_quality": "business address (public)" if street else "entity id only",
            "citation": {
                "label": f"FMCSA SAFER · USDOT {dot}",
                "url": (
                    "https://safer.fmcsa.dot.gov/query.asp?searchtype=ANY&"
                    f"query_type=queryCarrierSnapshot&query_param=USDOT&query_string={dot}"
                ),
            },
            "source_record": {"label": FMCSA["label"], "url": FMCSA["portal"]},
            "source_frontier": "FMCSA",
            "source_class": "OFFICIAL_OPEN_DATA",
            "purpose": "PROSPECTING_ONLY",
            "not_for_underwriting": True,
            "limitations": [
                "FMCSA status and addition fields are registry observations, not proof of authority, safety, or coverage.",
                "Phone, email, officer, crash, safety-rating, and insurance fields are not requested or stored.",
            ],
        }
        records.append(_attach_receipt(record, signal))

    return {
        "source": FMCSA["label"],
        "source_id": FMCSA["id"],
        "mode": "LIVE",
        "count": len(records),
        "records": records,
        "query_window": {"start": since, "end": _now().date().isoformat()},
        "citation": {"label": FMCSA["label"], "url": FMCSA["portal"]},
        "privacy": "ENTITY_FIELDS_ONLY",
    }


def _commercial_recipient(name: str) -> bool:
    upper = name.upper()
    if upper.startswith(_NON_COMMERCIAL_RECIPIENTS):
        return False
    return not any(term in upper for term in _NON_COMMERCIAL_TERMS)


def fetch_echo(states: list[str] | None = None, limit: int = 18) -> dict[str, Any]:
    """Return recent facility monitoring activity with adverse/risk fields omitted.

    This is a small, on-demand query against EPA's documented ECHO web service.
    Production-scale collection belongs on EPA's weekly bulk exporter instead.
    """
    state_list = _states(states)
    page_size = max(1, min(int(limit), 50))
    cache_key = (tuple(state_list), page_size)
    cached = _ECHO_CACHE.get(cache_key)
    if cached and cached[0] > _now():
        return json.loads(json.dumps(cached[1]))
    search_query = urllib.parse.urlencode({
        "output": "JSON",
        "p_st": ",".join(state_list),
        "p_act": "Y",
        "p_ysl": "W",
        "p_ysly": "1",
        "responseset": str(page_size),
    })
    search = _request_json(
        f"{ECHO['api']}/echo_rest_services.get_facilities?{search_query}"
    )
    search_result = search.get("Results") if isinstance(search, dict) else None
    qid = search_result.get("QueryID") if isinstance(search_result, dict) else None
    if not qid:
        raise ValueError("EPA ECHO search did not return a query identifier")
    result_query = urllib.parse.urlencode({
        "output": "JSON",
        "qid": str(qid),
        "pageno": "1",
        "newsort": "43",
        "descending": "Y",
        "qcolumns": "1,2,3,4,5,6,16,42,43",
    })
    response = _request_json(
        f"{ECHO['api']}/echo_rest_services.get_qid?{result_query}"
    )
    result = response.get("Results") if isinstance(response, dict) else None
    rows = result.get("Facilities", []) if isinstance(result, dict) else []
    if not isinstance(rows, list):
        raise ValueError("EPA ECHO facilities were not an array")

    records: list[dict[str, Any]] = []
    for row in rows[:page_size]:
        name = _clean(row.get("FacName"), 140)
        state = _clean(row.get("FacState"), 2).upper()
        registry_id = _clean(row.get("RegistryID"), 24)
        observed = _date_us(row.get("FacDateLastInspection"))
        if (
            not name
            or not registry_id
            or state not in state_list
            or not _commercial_recipient(name)
            or name.upper().startswith(_FEDERAL_FACILITY_PREFIXES)
            or re.match(r"^\d+\s+[A-Z]", name.upper())
        ):
            continue
        street = _clean(row.get("FacStreet"), 120)
        naics = _clean(row.get("FacNAICSCodes"), 80)
        days = _nonnegative_int(row.get("FacDaysLastInspection"))
        signal = (
            f"EPA ECHO reported compliance-monitoring activity for facility registry "
            f"{registry_id} on {observed or 'date unavailable'} ({days} days before the "
            "ECHO query)."
        )
        record = {
            "name": name,
            "type": "facility",
            "category": "EPA-regulated facility monitoring activity",
            "credential": f"FRS {registry_id}",
            "status": "MONITORING_ACTIVITY_OBSERVED",
            "address": street,
            "city": _clean(row.get("FacCity"), 80),
            "state": state,
            "zip": _clean(row.get("FacZip"), 12)[:5],
            "license_or_issue_date": observed,
            "observed_trigger": "EPA compliance-monitoring activity",
            "trigger_date": observed,
            "signal_summary": signal,
            "operational_snapshot": {"naics_codes": naics, "days_since_activity": days},
            "authoritative_entity_ids": [{"system": "EPA FRS", "value": registry_id}],
            "product_angle": "Licensed environmental, property, and operational-continuity review",
            "product": "BIZ",
            "why": (
                "A recent public monitoring event can justify a factual business review of "
                "operational change and coverage administration. It does not establish a "
                "violation, unsafe condition, loss likelihood, or insurability."
            ),
            "recommended_next_action": (
                "Open the current ECHO facility report, confirm the business identity, then "
                "research only a channel published on the business's own website."
            ),
            "contact_quality": "business address (public)" if street else "entity id only",
            "citation": {
                "label": f"EPA ECHO facility · FRS {registry_id}",
                "url": f"https://echo.epa.gov/detailed-facility-report?fid={registry_id}",
            },
            "source_record": {"label": ECHO["label"], "url": ECHO["portal"]},
            "source_frontier": "EPA_ECHO",
            "source_class": "OFFICIAL_OPEN_DATA",
            "purpose": "PROSPECTING_ONLY",
            "not_for_underwriting": True,
            "limitations": [
                "Monitoring activity is not a violation, enforcement finding, or risk score.",
                "Compliance status, penalties, demographics, and personal contact fields are not requested or stored.",
                "ECHO data can lag or be incomplete; re-open the current facility report before outreach.",
            ],
        }
        records.append(_attach_receipt(record, signal))

    output = {
        "source": ECHO["label"],
        "source_id": ECHO["id"],
        "mode": "LIVE",
        "count": len(records),
        "records": records,
        "query_window": {"lookback": "within one year, newest results first"},
        "citation": {"label": ECHO["label"], "url": ECHO["portal"]},
        "privacy": "ENTITY_AND_FACILITY_FIELDS_ONLY",
    }
    _ECHO_CACHE[cache_key] = (_now() + timedelta(minutes=15), output)
    return json.loads(json.dumps(output))
def fetch_usaspending(states: list[str] | None = None, limit: int = 18) -> dict[str, Any]:
    """Return federal contract activity as a research signal, never as a new-award claim."""
    state_list = _states(states)
    end = _now().date()
    start = end - timedelta(days=21)
    payload = {
        "filters": {
            "time_period": [{"start_date": start.isoformat(), "end_date": end.isoformat()}],
            "award_type_codes": ["A", "B", "C", "D"],
            "recipient_scope": "domestic",
            "recipient_locations": [
                {"country": "USA", "state": state} for state in state_list
            ],
            "award_amounts": [{"lower_bound": 25000, "upper_bound": 10000000}],
        },
        "fields": list(USASPENDING_FIELDS),
        "page": 1,
        "limit": max(1, min(int(limit), 50)),
        "sort": "Award Amount",
        "order": "desc",
        "subawards": False,
    }
    response = _request_json(USASPENDING["api"], payload)
    rows = response.get("results", []) if isinstance(response, dict) else []
    if not isinstance(rows, list):
        raise ValueError("USAspending results were not an array")

    records: list[dict[str, Any]] = []
    for row in rows:
        name = _clean(row.get("Recipient Name"), 140)
        location = row.get("Recipient Location") or {}
        state = _clean(location.get("state_code"), 2).upper()
        award_id = _clean(row.get("Award ID"), 80)
        generated_id = _clean(row.get("generated_internal_id"), 220)
        if (
            not name
            or not award_id
            or state not in state_list
            or not _commercial_recipient(name)
        ):
            continue
        amount = round(float(row.get("Award Amount") or 0.0), 2)
        agency = _clean(row.get("Awarding Agency"), 120) or "Federal agency"
        uei = _clean(row.get("Recipient UEI"), 24)
        street = _clean(location.get("address_line1"), 120)
        description = _clean(row.get("Description"), 280)
        award_url = (
            f"https://www.usaspending.gov/award/{urllib.parse.quote(generated_id, safe='_-.')}/latest"
            if generated_id
            else "https://www.usaspending.gov/search"
        )
        signal = (
            f"USAspending returned contract activity for award {award_id} in the "
            f"{start.isoformat()} through {end.isoformat()} query window; displayed award "
            f"amount ${amount:,.2f} and awarding agency {agency}."
        )
        ids = [{"system": "Federal Award ID", "value": award_id}]
        if uei:
            ids.insert(0, {"system": "UEI", "value": uei})
        record = {
            "name": name,
            "type": "federal_award",
            "category": f"Federal contract activity · {agency}",
            "credential": f"UEI {uei}" if uei else f"Award {award_id}",
            "status": "ACTIVITY_WINDOW_OBSERVED",
            "address": street,
            "city": _clean(location.get("city_name"), 80),
            "state": state,
            "zip": _clean(location.get("zip5"), 10),
            "license_or_issue_date": end.isoformat(),
            "observed_trigger": "Federal contract activity returned in current query window",
            "trigger_date": end.isoformat(),
            "observation_window": {"start": start.isoformat(), "end": end.isoformat()},
            "signal_summary": signal,
            "award": {
                "award_id": award_id,
                "amount": amount,
                "agency": agency,
                "description": description,
                "start_date": _clean(row.get("Start Date"), 10),
                "end_date": _clean(row.get("End Date"), 10),
            },
            "authoritative_entity_ids": ids,
            "product_angle": "Capacity, owner-continuity, and workforce-benefits review",
            "product": "BIZ",
            "why": (
                "Recent federal contract activity may change backlog, staffing, or principal "
                "dependency and can justify a licensed broker review. The activity window can "
                "include a modification to an older award, so it is not labeled a new contract."
            ),
            "recommended_next_action": (
                "Open the award history, verify the latest action and current business website, "
                "then document a business-published contact channel and permitted product fit."
            ),
            "contact_quality": "business address (public)" if street else "entity id only",
            "citation": {"label": f"USAspending · {award_id}", "url": award_url},
            "source_record": {"label": USASPENDING["label"], "url": USASPENDING["portal"]},
            "source_frontier": "FEDERAL_CONTRACT",
            "source_class": "OFFICIAL_OPEN_DATA",
            "purpose": "PROSPECTING_ONLY",
            "not_for_underwriting": True,
            "limitations": [
                "The search window may reflect an award modification, not a newly signed contract.",
                "Award amount is a federal award field, not revenue, cash flow, or insurability.",
            ],
        }
        records.append(_attach_receipt(record, signal))

    return {
        "source": USASPENDING["label"],
        "source_id": USASPENDING["id"],
        "mode": "LIVE",
        "count": len(records),
        "records": records,
        "query_window": {"start": start.isoformat(), "end": end.isoformat()},
        "citation": {"label": USASPENDING["label"], "url": USASPENDING["portal"]},
        "privacy": "ENTITY_FIELDS_ONLY",
    }


def fetch_fcc_uls(states: list[str] | None = None, limit: int = 18) -> dict[str, Any]:
    """Fail closed until the large ULS archives have a durable ingestion lane."""
    del states, limit
    raise SourceConfigurationUnavailable("FCC_DURABLE_INGEST_NOT_CONFIGURED")


def fetch_chicago_licenses(
    states: list[str] | None = None,
    limit: int = 18,
) -> dict[str, Any]:
    """Return organization-only newly issued licenses after explicit reuse approval."""
    state_list = _states(states)
    page_size = max(1, min(int(limit), 50))
    if "IL" not in state_list:
        return {
            "source": CHICAGO["label"],
            "source_id": CHICAGO["id"],
            "mode": "NOT_APPLICABLE",
            "count": 0,
            "records": [],
            "citation": {"label": CHICAGO["label"], "url": CHICAGO["portal"]},
            "privacy": "ORGANIZATION_LICENSE_FIELDS_ONLY",
            "reason": "IL_NOT_IN_SELECTED_TERRITORY",
        }

    if os.environ.get("CHICAGO_PUBLIC_DATA_APPROVED", "").strip() != "1":
        raise SourceConfigurationUnavailable(
            "CHICAGO_REUSE_APPROVAL_NOT_CONFIGURED"
        )
    app_token = os.environ.get("CHICAGO_SOCRATA_APP_TOKEN", "").strip()
    if not app_token:
        raise SourceConfigurationUnavailable(
            "CHICAGO_SOCRATA_APP_TOKEN_NOT_CONFIGURED"
        )

    since = (_now().date() - timedelta(days=45)).isoformat()
    cache_key = (page_size, since)
    cached = _CHICAGO_CACHE.get(cache_key)
    if cached and cached[0] > _now():
        return json.loads(json.dumps(cached[1]))
    fields = [
        "id",
        "license_id",
        "license_number",
        "legal_name",
        "doing_business_as_name",
        "city",
        "state",
        "zip_code",
        "license_description",
        "application_type",
        "date_issued",
        "license_status",
    ]
    query = urllib.parse.urlencode({
        "$select": ",".join(fields),
        "$where": (
            f"date_issued >= '{since}T00:00:00' AND "
            "application_type='ISSUE' AND license_status='AAI' AND state='IL'"
        ),
        "$order": "date_issued DESC,id DESC",
        "$limit": str(min(250, page_size * 8)),
    })
    try:
        rows = _request_json_headers(
            f"{CHICAGO['api']}?{query}",
            {"X-App-Token": app_token, "Accept": "application/json"},
        )
    except Exception as exc:
        raise SourceConfigurationUnavailable(
            "CHICAGO_API_REQUEST_FAILED"
        ) from exc
    if not isinstance(rows, list):
        raise ValueError("Chicago business-license response was not an array")

    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        name = _organization_name(row.get("legal_name"))
        license_id = _clean(row.get("license_id"), 32)
        license_number = _clean(row.get("license_number"), 32)
        issue_date = _date_iso(row.get("date_issued"))
        state = _clean(row.get("state"), 2).upper()
        if (
            not name
            or not license_id
            or not license_number
            or not issue_date
            or state != "IL"
            or _clean(row.get("application_type"), 16).upper() != "ISSUE"
            or _clean(row.get("license_status"), 16).upper() != "AAI"
            or license_id in seen
        ):
            continue
        seen.add(license_id)
        description = _clean(row.get("license_description"), 160)
        signal = (
            f"Chicago reported newly issued active business license "
            f"{license_number} for organization {name} on {issue_date}."
        )
        record = {
            "name": name,
            "dba": _clean(row.get("doing_business_as_name"), 140),
            "type": "city_business_license",
            "category": f"Chicago license · {description or 'business activity'}",
            "credential": f"Chicago license {license_number}",
            "status": "NEW_ACTIVE_LICENSE_REPORTED",
            "address": "",
            "city": _clean(row.get("city"), 80),
            "state": "IL",
            "zip": "",
            "license_or_issue_date": issue_date,
            "observed_trigger": "Chicago new active business license",
            "trigger_date": issue_date,
            "signal_summary": signal,
            "operational_snapshot": {
                "license_description": description,
                "application_type": "ISSUE",
                "license_status": "AAI",
            },
            "source_record_id": license_id,
            "authoritative_entity_ids": [
                {"system": "Chicago business license", "value": license_number},
            ],
            "product_angle": "New-business operations, property, liability, and continuity review",
            "product": "BIZ",
            "why": (
                "An initial active business-license record can justify entity research. "
                "It does not prove current operation, revenue, insurance need, or insurability."
            ),
            "recommended_next_action": (
                "Re-open the City record, verify the organization and status, then use "
                "only a channel published on the business's own website."
            ),
            "contact_quality": "entity id only",
            "citation": {
                "label": f"Chicago business license · {license_number}",
                "url": CHICAGO["portal"],
            },
            "source_record": {"label": CHICAGO["label"], "url": CHICAGO["portal"]},
            "source_frontier": "CHICAGO_BUSINESS_LICENSE",
            "source_class": "OFFICIAL_OPEN_DATA",
            "purpose": "PROSPECTING_ONLY",
            "not_for_underwriting": True,
            "attribution": "This product uses data made available by the City of Chicago.",
            "limitations": [
                "License issuance does not prove the business opened or remains operational.",
                "No owner dataset, personal contact, exact street address, or geolocation is joined or emitted.",
                "The record is a research trigger, not evidence of revenue, a coverage gap, or insurability.",
            ],
        }
        records.append(_attach_receipt(record, signal))
        if len(records) >= page_size:
            break

    output = {
        "source": CHICAGO["label"],
        "source_id": CHICAGO["id"],
        "mode": "LIVE",
        "count": len(records),
        "records": records,
        "query_window": {"start": since, "end": _now().date().isoformat()},
        "citation": {"label": CHICAGO["label"], "url": CHICAGO["portal"]},
        "privacy": "ORGANIZATION_LICENSE_FIELDS_ONLY",
        "attribution": "This product uses data made available by the City of Chicago.",
    }
    _CHICAGO_CACHE[cache_key] = (_now() + timedelta(minutes=15), output)
    return json.loads(json.dumps(output))


def _sam_entity_record(row: Any, state: str) -> dict[str, Any] | None:
    """Normalize an allowlisted public SAM entity record or fail it closed."""
    if not isinstance(row, dict):
        return None
    registration = row.get("entityRegistration") or {}
    core = row.get("coreData") or {}
    address = core.get("physicalAddress") or {}
    if not all(isinstance(value, dict) for value in (registration, core, address)):
        return None
    name = _organization_name(registration.get("legalBusinessName"))
    uei = _clean(registration.get("ueiSAM"), 16)
    observed_state = _clean(address.get("stateOrProvinceCode"), 2).upper()
    updated = _date_iso(registration.get("lastUpdateDate"))
    public_display = _clean(registration.get("publicDisplayFlag"), 8).upper()
    evs_source = _clean(registration.get("evsSource"), 40).upper()
    dnb_open = _clean(registration.get("dnbOpenData"), 8).upper()
    entity_type = _clean(registration.get("entityTypeCode"), 8).upper()
    if (
        not name
        or not uei
        or observed_state != state
        or public_display != "Y"
        or evs_source == "D&B"
        or dnb_open == "Y"
        or (entity_type and entity_type != "F")
        or not updated
        or updated < "2022-04-04"
    ):
        return None
    signal = (
        f"SAM.gov reported a public active registration update for UEI {uei} "
        f"on {updated}."
    )
    record = {
        "name": name,
        "dba": _clean(registration.get("dbaName"), 140),
        "type": "sam_registered_entity",
        "category": "SAM.gov active entity update",
        "credential": f"UEI {uei}",
        "status": "ACTIVE_REGISTRATION_UPDATE_REPORTED",
        "address": "",
        "city": _clean(address.get("city"), 80),
        "state": observed_state,
        "zip": "",
        "license_or_issue_date": updated,
        "observed_trigger": "SAM.gov public entity registration update",
        "trigger_date": updated,
        "signal_summary": signal,
        "operational_snapshot": {
            "registration_expiration_date": _clean(
                registration.get("registrationExpirationDate"), 16
            ),
            "purpose_of_registration": _clean(
                registration.get("purposeOfRegistrationDesc"), 100
            ),
            "evs_source": evs_source or "NOT_REPORTED",
            "entity_type_code": entity_type or "NOT_REPORTED",
        },
        "authoritative_entity_ids": [{"system": "SAM UEI", "value": uei}],
        "product_angle": "Government-contractor continuity and capacity review",
        "product": "BIZ",
        "why": (
            "A recent public registration update can justify entity research. It is "
            "not an award, revenue event, operating-status guarantee, or insurance need."
        ),
        "recommended_next_action": (
            "Re-open the public SAM record, confirm the update and entity website, "
            "then document a business-published channel and permitted conversation."
        ),
        "contact_quality": "entity id only",
        "citation": {
            "label": f"SAM.gov · UEI {uei}",
            "url": f"https://sam.gov/entity/{urllib.parse.quote(uei)}/coreData",
        },
        "source_record": {"label": SAM["label"], "url": SAM["portal"]},
        "source_frontier": "SAM_ENTITY",
        "source_class": "OFFICIAL_OPEN_DATA",
        "purpose": "PROSPECTING_ONLY",
        "not_for_underwriting": True,
        "limitations": [
            "Registration is not an award, revenue, current operation, or insurance need.",
            "Only public entityRegistration and coreData sections are requested; points of contact and CUI are excluded.",
            "D&B-sourced, D&B-open, and pre-April-2022 records are excluded from this marketing research adapter.",
        ],
    }
    return _attach_receipt(record, signal)


def fetch_sam_entities(
    states: list[str] | None = None,
    limit: int = 18,
) -> dict[str, Any]:
    """Return recent public SAM entity updates when an approved API key exists."""
    api_key = os.environ.get("SAM_GOV_API_KEY", "").strip()
    if not api_key:
        raise SourceConfigurationUnavailable("SAM_GOV_API_KEY_NOT_CONFIGURED")
    state_list = _states(states)
    page_size = max(1, min(int(limit), 30))
    since_date = _now().date() - timedelta(days=30)
    since = since_date.isoformat()
    cache_key = (tuple(state_list), page_size, since)
    cached = _SAM_CACHE.get(cache_key)
    if cached and cached[0] > _now():
        return json.loads(json.dumps(cached[1]))

    records: list[dict[str, Any]] = []
    requests_used = 0
    truncated = False
    for state in state_list:
        page = 0
        while len(records) < page_size and requests_used < 10:
            query = urllib.parse.urlencode({
                "api_key": api_key,
                "registrationStatus": "A",
                "samRegistered": "Yes",
                "sensitivity": "public",
                "includeSections": "entityRegistration,coreData",
                "physicalAddressProvinceOrStateCode": state,
                "updateDate": (
                    f"[{since_date.strftime('%m/%d/%Y')},"
                    f"{_now().date().strftime('%m/%d/%Y')}]"
                ),
                "page": str(page),
                "size": "10",
            })
            try:
                response = _request_json(f"{SAM['api']}?{query}")
            except Exception as exc:
                raise SourceConfigurationUnavailable(
                    "SAM_API_REQUEST_FAILED"
                ) from exc
            requests_used += 1
            rows = response.get("entityData", []) if isinstance(response, dict) else []
            if not isinstance(rows, list):
                raise ValueError("SAM.gov entityData was not an array")
            for row in rows:
                record = _sam_entity_record(row, state)
                if record:
                    records.append(record)
                    if len(records) >= page_size:
                        break
            if len(rows) < 10:
                break
            page += 1
        if len(records) >= page_size:
            break
    if requests_used >= 10 and len(records) < page_size:
        truncated = True

    output = {
        "source": SAM["label"],
        "source_id": SAM["id"],
        "mode": "LIVE",
        "count": len(records),
        "records": records,
        "query_window": {
            "start": since,
            "end": _now().date().isoformat(),
            "requests_used": requests_used,
            "request_budget": 10,
            "truncated": truncated,
        },
        "citation": {"label": SAM["label"], "url": SAM["portal"]},
        "privacy": "PUBLIC_ENTITY_REGISTRATION_FIELDS_ONLY",
    }
    _SAM_CACHE[cache_key] = (_now() + timedelta(hours=24), output)
    return json.loads(json.dumps(output))


def fetch_form5500(states: list[str] | None = None, limit: int = 18) -> dict[str, Any]:
    """Return organization-level plan anniversary observations from DOL filings."""
    output = benefit_frontier.collect(_states(states), limit)
    records: list[dict[str, Any]] = []
    for record in output.pop("records", []):
        records.append(_attach_receipt(record, record["signal_summary"]))
    output["records"] = records
    return output


def _entity_key(record: dict[str, Any]) -> str:
    name = _clean(record.get("name"), 180).upper()
    name = _ORG_SUFFIX.sub("", name)
    name = re.sub(r"[^A-Z0-9]+", "", name)
    return f"{record.get('state', '')}|{name}" if name else ""


def triangulate(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Annotate organization matches across independent official sources."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        key = _entity_key(record)
        if key:
            groups.setdefault(key, []).append(record)

    multi_source_accounts = 0
    for group in groups.values():
        source_names = sorted({
            _clean(item.get("source_frontier"), 60)
            for item in group
            if item.get("source_frontier")
        })
        if len(source_names) > 1:
            multi_source_accounts += 1
        signals = [{
            "source_frontier": item.get("source_frontier"),
            "observed_trigger": item.get("observed_trigger"),
            "observed_date": (
                item.get("trigger_date")
                or item.get("license_or_issue_date")
                or item.get("observed_at")
            ),
            "citation": item.get("citation"),
        } for item in group]
        for record in group:
            evidence = dict(record.get("evidence") or {})
            evidence["source_count"] = len(source_names)
            evidence["official_sources"] = source_names
            evidence["triangulation_state"] = (
                "MULTI_SOURCE" if len(source_names) > 1 else "SINGLE_SOURCE"
            )
            record["evidence"] = evidence
            record["corroborating_signals"] = signals
    return records, multi_source_accounts


def frontier_opportunities(
    states: list[str] | None = None,
    limit_per_source: int = 18,
) -> dict[str, Any]:
    """Collect independent official sources; one outage never fabricates another source."""
    state_list = _states(states)
    records: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for source, fetcher in (
        (FORM5500, fetch_form5500),
        (FMCSA, fetch_fmcsa),
        (USASPENDING, fetch_usaspending),
        (ECHO, fetch_echo),
        (FCC, fetch_fcc_uls),
        (CHICAGO, fetch_chicago_licenses),
        (SAM, fetch_sam_entities),
    ):
        try:
            result = fetcher(state_list, limit_per_source)
            records.extend(result.pop("records", []))
            sources.append(result)
        except Exception as exc:
            reason = (
                str(exc)
                if isinstance(exc, SourceConfigurationUnavailable)
                else type(exc).__name__
            )
            sources.append({
                "source": source["label"],
                "source_id": source["id"],
                "mode": "UNAVAILABLE",
                "count": 0,
                "citation": {"label": source["label"], "url": source["portal"]},
                "reason": reason,
                "privacy": "ENTITY_FIELDS_ONLY",
            })
    records, multi_source_accounts = triangulate(records)
    return {
        "leads": records,
        "sources": sources,
        "generated_at": _now().isoformat(),
        "count": len(records),
        "states": state_list,
        "multi_source_accounts": multi_source_accounts,
        "doctrine": (
            "Official entity/facility observations only. No social scraping, no person-level "
            "contact enrichment, no demographics, no underwriting use, and no contact "
            "permission inferred."
        ),
    }
