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
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from . import receipts as rc


UA = {"User-Agent": "SZL-David-Leads/1.1 research@szlholdings.com"}
TIMEOUT = 15
DEFAULT_STATES = ("NY", "NJ", "PA", "MD", "DE", "CT")
_ECHO_CACHE: dict[tuple[tuple[str, ...], int], tuple[datetime, dict[str, Any]]] = {}

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
        if re.fullmatch(r"[A-Z]{2}", state) and state not in result:
            result.append(state)
    return result[:12] or list(DEFAULT_STATES)


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
    receipt = _receipt(record, signal)
    record["receipt_id"] = receipt.get("id") if receipt else None
    record["receipt_signed"] = bool(receipt and receipt.get("signed"))
    if receipt:
        record["_receipt"] = receipt
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


def frontier_opportunities(
    states: list[str] | None = None,
    limit_per_source: int = 18,
) -> dict[str, Any]:
    """Collect independent official sources; one outage never fabricates another source."""
    state_list = _states(states)
    records: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for source, fetcher in (
        (FMCSA, fetch_fmcsa),
        (USASPENDING, fetch_usaspending),
        (ECHO, fetch_echo),
    ):
        try:
            result = fetcher(state_list, limit_per_source)
            records.extend(result.pop("records", []))
            sources.append(result)
        except Exception as exc:
            sources.append({
                "source": source["label"],
                "source_id": source["id"],
                "mode": "UNAVAILABLE",
                "count": 0,
                "citation": {"label": source["label"], "url": source["portal"]},
                "reason": type(exc).__name__,
                "privacy": "ENTITY_FIELDS_ONLY",
            })
    return {
        "leads": records,
        "sources": sources,
        "generated_at": _now().isoformat(),
        "count": len(records),
        "states": state_list,
        "doctrine": (
            "Official entity/facility observations only. No social scraping, no person-level "
            "contact enrichment, no demographics, no underwriting use, and no contact "
            "permission inferred."
        ),
    }
