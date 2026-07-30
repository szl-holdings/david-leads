# SPDX-License-Identifier: Apache-2.0
"""Organization-level benefit-plan timing from official DOL Form 5500 files.

The adapter reads only the bulk disclosure fields required to identify a plan
sponsor, understand the covered benefit categories, and calculate the next
anniversary of the reported plan or policy period. It never retains EINs,
signers, preparers, administrators, phone numbers, commissions, or person-level
addresses.
"""
from __future__ import annotations

import csv
import io
import os
import re
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable


PORTAL = (
    "https://www.dol.gov/agencies/ebsa/about-ebsa/our-activities/"
    "public-disclosure/foia/form-5500-datasets"
)
_BASE = "https://askebsa.dol.gov/FOIA%20Files/{year}/Latest/"
_MAX_DOWNLOAD = 80_000_000
_CACHE_TTL = timedelta(hours=12)
_FILE_CACHE: dict[tuple[int, str], tuple[datetime, bytes]] = {}
_EIN_TEXT = re.compile(
    r"\s*(?:\(|\[)?\bEIN\b\s*(?:[:#-]\s*)?\d{2}-?\d{7}(?:\)|\])?",
    re.IGNORECASE,
)

_BENEFIT_FIELDS = {
    "WLFR_BNFT_HEALTH_IND": "Medical",
    "WLFR_BNFT_DENTAL_IND": "Dental",
    "WLFR_BNFT_VISION_IND": "Vision",
    "WLFR_BNFT_LIFE_INSUR_IND": "Life",
    "WLFR_BNFT_TEMP_DISAB_IND": "Short-term disability",
    "WLFR_BNFT_LONG_TERM_DISAB_IND": "Long-term disability",
    "WLFR_BNFT_DRUG_IND": "Prescription",
    "WLFR_BNFT_STOP_LOSS_IND": "Stop-loss",
    "WLFR_BNFT_HMO_IND": "HMO",
    "WLFR_BNFT_PPO_IND": "PPO",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _filing_year() -> int:
    configured = os.environ.get("DOL_FORM5500_YEAR", "").strip()
    if configured.isdigit():
        return int(configured)
    return _now().year - 1


def _download(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "SZL-David-Leads/1.3 research@szlholdings.com"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(_MAX_DOWNLOAD + 1)
    if len(data) > _MAX_DOWNLOAD:
        raise ValueError("DOL_FILE_TOO_LARGE")
    return data


def _file(year: int, filename: str, loader: Callable[[str], bytes]) -> bytes:
    key = (year, filename)
    cached = _FILE_CACHE.get(key)
    if cached and cached[0] > _now():
        return cached[1]
    url = _BASE.format(year=year) + filename
    data = loader(url)
    _FILE_CACHE[key] = (_now() + _CACHE_TTL, data)
    return data


def _rows(data: bytes) -> csv.DictReader:
    archive = zipfile.ZipFile(io.BytesIO(data))
    members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
    if len(members) != 1:
        archive.close()
        raise ValueError("DOL_ARCHIVE_SHAPE_CHANGED")
    stream = archive.open(members[0])
    text = io.TextIOWrapper(stream, encoding="utf-8-sig", errors="replace", newline="")
    reader = csv.DictReader(text)
    # Keep the archive and streams reachable for the lifetime of the iterator.
    reader._david_resources = (archive, stream, text)  # type: ignore[attr-defined]
    return reader


def _clean(value: Any, limit: int = 180) -> str:
    return " ".join(str(value or "").split())[:limit]


def _organization_text(value: Any, limit: int = 180) -> str:
    return _clean(_EIN_TEXT.sub("", str(value or "")).strip(" ,;-"), limit)


def _count(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _iso_date(value: Any) -> str:
    text = _clean(value, 20)
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return ""


def _next_anniversary(value: str, today: date) -> date | None:
    if not value:
        return None
    try:
        observed = date.fromisoformat(value)
        candidate = observed.replace(year=today.year)
    except ValueError:
        return None
    if candidate < today:
        try:
            candidate = candidate.replace(year=today.year + 1)
        except ValueError:
            candidate = date(today.year + 1, 2, 28)
    return candidate


def _zip(value: Any) -> str:
    digits = "".join(char for char in _clean(value, 12) if char.isdigit())
    return digits[:5]


def _benefit_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    benefits: list[str] = []
    carriers: list[str] = []
    policy_end = ""
    plan_end = ""
    for row in rows:
        for field, label in _BENEFIT_FIELDS.items():
            if row.get(field) == "1" and label not in benefits:
                benefits.append(label)
        carrier = (
            _clean(row.get("INS_CARRIER_NAME"), 120)
            if row.get("WLFR_BNFT_LIFE_INSUR_IND") == "1"
            else ""
        )
        if carrier and carrier not in carriers:
            carriers.append(carrier)
        candidate_policy_end = _iso_date(row.get("INS_POLICY_TO_DATE"))
        candidate_plan_end = _iso_date(row.get("SCH_A_PLAN_YEAR_END_DATE"))
        policy_end = max(policy_end, candidate_policy_end)
        plan_end = max(plan_end, candidate_plan_end)
    return {
        "benefits": benefits[:8],
        "carriers": carriers[:3],
        "policy_end": policy_end,
        "plan_end": plan_end,
    }


def collect(
    states: list[str],
    limit: int = 18,
    *,
    loader: Callable[[str], bytes] = _download,
    today: date | None = None,
    year: int | None = None,
) -> dict[str, Any]:
    """Return live organization-level benefit timing observations."""
    filing_year = year or _filing_year()
    state_set = {str(state).upper() for state in states}
    today = today or _now().date()
    main_name = f"F_5500_{filing_year}_Latest.zip"
    schedule_name = f"F_SCH_A_{filing_year}_Latest.zip"
    main = _rows(_file(filing_year, main_name, loader))

    sponsors: dict[str, dict[str, str]] = {}
    for row in main:
        state = _clean(row.get("SPONS_DFE_LOC_US_STATE"), 2).upper()
        ack_id = _clean(row.get("ACK_ID"), 50)
        sponsor = _organization_text(row.get("SPONSOR_DFE_NAME"), 160)
        if (
            state not in state_set
            or not ack_id
            or not sponsor
            or row.get("SCH_A_ATTACHED_IND") != "1"
            or row.get("FILING_STATUS") != "FILING_RECEIVED"
        ):
            continue
        participants = max(
            _count(row.get("TOT_ACTIVE_PARTCP_CNT")),
            _count(row.get("TOT_PARTCP_BOY_CNT")),
        )
        if participants < 10 or participants > 5_000:
            continue
        sponsors[ack_id] = {
            "ack_id": ack_id,
            "name": sponsor,
            "plan_name": _organization_text(row.get("PLAN_NAME"), 180),
            "city": _clean(row.get("SPONS_DFE_LOC_US_CITY"), 80),
            "state": state,
            "zip": _zip(row.get("SPONS_DFE_LOC_US_ZIP")),
            "participants": str(participants),
            "received": _iso_date(row.get("DATE_RECEIVED")),
        }

    schedules: dict[str, list[dict[str, str]]] = defaultdict(list)
    if sponsors:
        schedule = _rows(_file(filing_year, schedule_name, loader))
        for row in schedule:
            ack_id = _clean(row.get("ACK_ID"), 50)
            if ack_id in sponsors:
                schedules[ack_id].append(row)

    records: list[dict[str, Any]] = []
    for ack_id, sponsor in sponsors.items():
        summary = _benefit_summary(schedules.get(ack_id, []))
        anniversary_basis = summary["policy_end"] or summary["plan_end"]
        anniversary = _next_anniversary(anniversary_basis, today)
        if not anniversary:
            continue
        days_to_anniversary = (anniversary - today).days
        benefits = summary["benefits"]
        if "Life" not in benefits:
            continue
        participants = int(sponsor["participants"])
        timing_band = (
            "0-90 days"
            if days_to_anniversary <= 90
            else ("91-180 days" if days_to_anniversary <= 180 else "181-365 days")
        )
        product_fit = [
            "Life insurance review",
            "Business protection research",
            "Executive benefits research",
        ]
        signal = (
            f"DOL received this {filing_year} Form 5500 filing on "
            f"{sponsor['received'] or 'a date not supplied'}; its Schedule A reports "
            f"{participants:,} participants and a plan or policy period ending "
            f"{anniversary_basis}."
        )
        records.append({
            "name": sponsor["name"],
            "dba": "",
            "type": "benefit_plan",
            "city": sponsor["city"],
            "state": sponsor["state"],
            "zip": sponsor["zip"],
            "address": "",
            "status": "FILING_RECEIVED",
            "credential": f"DOL filing {ack_id}",
            "license_or_issue_date": sponsor["received"],
            "trigger_date": sponsor["received"],
            "category": "Benefit plan filing",
            "source_frontier": "BENEFIT_PLAN_TIMING",
            "source_class": "OFFICIAL_PUBLIC_FILING",
            "source_state": "LIVE",
            "source_record_id": ack_id,
            "authoritative_entity_ids": [{
                "system": "DOL Form 5500 ACK ID",
                "value": ack_id,
            }],
            "observed_trigger": "Reported group-life plan anniversary watch",
            "signal_summary": signal,
            "why": (
                f"A reported benefit-plan anniversary is {days_to_anniversary} days away. "
                "That is a research timing hypothesis, not proof of a renewal, buying "
                "intent, dissatisfaction, eligibility, or insurability."
            ),
            "purpose": "Commercial life and business-protection research",
            "product": "Life & business protection",
            "product_angle": ", ".join(product_fit),
            "product_fit": product_fit,
            "timing": {
                "label": timing_band,
                "next_anniversary": anniversary.isoformat(),
                "days_to_anniversary": days_to_anniversary,
                "basis": "reported plan or policy period end",
                "hypothesis_only": True,
            },
            "operational_snapshot": {
                "participants_reported": participants,
                "benefit_categories": benefits,
                "reported_carriers": summary["carriers"],
                "plan_name": sponsor["plan_name"],
            },
            "evidence": {
                "strength": "DIRECT_FILING",
                "source_count": 1,
                "fit_basis": "Schedule A life-benefit indicator",
                "observed_fields": [
                    "plan sponsor",
                    "participant count",
                    "plan or policy period",
                    "benefit categories",
                ],
            },
            "recommended_next_action": (
                "Open the DOL filing, confirm the sponsor and plan period, then research "
                "the organization's own website and document product fit before any "
                "contact-clearance work."
            ),
            "citation": {
                "label": "U.S. Department of Labor Form 5500 datasets",
                "url": PORTAL,
            },
            "source_record": {
                "label": f"DOL Form 5500 bulk disclosure ({filing_year})",
                "url": PORTAL,
            },
            "contact_quality": "organization location (public)",
            "limitations": [
                "The anniversary is calculated from a previously reported plan or policy period.",
                "The filing does not prove a current renewal, buying intent, or broker-of-record opportunity.",
                "Only the reported life-benefit indicator informs product fit; other benefit categories are context only.",
                "No contact permission, phone, email, EIN, signer, preparer, or commission data is collected.",
            ],
        })

    deduplicated: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        key = (record["name"].casefold(), record["state"])
        existing = deduplicated.get(key)
        if not existing or (
            record["operational_snapshot"]["participants_reported"]
            > existing["operational_snapshot"]["participants_reported"]
        ):
            deduplicated[key] = record
    records = list(deduplicated.values())

    def segment_rank(participants: int) -> int:
        if 25 <= participants <= 500:
            return 3
        if 501 <= participants <= 2_500:
            return 2
        return 1

    records.sort(
        key=lambda item: (
            int(item["timing"]["days_to_anniversary"] <= 180),
            segment_rank(item["operational_snapshot"]["participants_reported"]),
            item["operational_snapshot"]["participants_reported"],
            -item["timing"]["days_to_anniversary"],
        ),
        reverse=True,
    )
    records = records[: max(1, min(int(limit), 50))]
    return {
        "records": records,
        "source": "DOL Form 5500 benefit-plan filings",
        "source_id": "dol-form5500-benefit-timing",
        "mode": "LIVE",
        "count": len(records),
        "filing_year": filing_year,
        "query_window": {
            "anniversary_start": today.isoformat(),
            "anniversary_end": (today + timedelta(days=365)).isoformat(),
        },
        "citation": {
            "label": "U.S. Department of Labor Form 5500 datasets",
            "url": PORTAL,
        },
        "privacy": "ORGANIZATION_LIFE_PLAN_FIELDS_ONLY",
    }
