# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — david-leads vertical
"""Live-capable public-record adapters (no license required, network optional).

These sources are genuinely public: USAspending (federal contract awards),
SEC EDGAR full-text search (registrant filings), and EPA ECHO (facility
enforcement/compliance records). v0 wires reachability + a minimal fetch for
each; deep entity resolution stays in the legacy app/ frontier adapters.

Offline discipline: network access is OPT-IN (DAVID_LEADS_LIVE=1) so the
service runs deterministically offline. With live mode off, each adapter
reports UNKNOWN (reachable state not evaluated) rather than pretending either
health or data. With live mode on, a failed request reports UNAVAILABLE with
the error class — never a substituted or invented record (Zero-Bandaid).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

import requests

from ..models import AdapterStatus, LeadRecord, Signal, SourceClass, TruthState

TIMEOUT_S = 8.0
USER_AGENT = "szl-david-leads/0.1 (public-record research; contact: repo owner)"


def _live() -> bool:
    return os.environ.get("DAVID_LEADS_LIVE", "").strip() == "1"


class PublicSourceAdapter:
    """Base for no-key public HTTP sources. Subclasses declare an endpoint and
    a parser; failures degrade to honest states, never to fabricated rows."""

    name = "public_base"
    kind = "PUBLIC"
    endpoint = ""
    description = ""

    def _get_json(self, url: str, params: Optional[dict] = None) -> tuple[Optional[Any], Optional[str]]:
        try:
            resp = requests.get(
                url, params=params, timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT}
            )
        except requests.RequestException as exc:
            return None, f"request failed: {type(exc).__name__}"
        if resp.status_code != 200:
            return None, f"HTTP {resp.status_code}"
        try:
            return resp.json(), None
        except ValueError:
            return None, "response was not JSON"

    def status(self) -> AdapterStatus:
        if not _live():
            return AdapterStatus(
                name=self.name, kind=self.kind, truth_state=TruthState.UNKNOWN,
                detail=(
                    f"{self.description} Live fetch is opt-in and currently off; "
                    "reachable state not evaluated. Set DAVID_LEADS_LIVE=1 to enable."
                ),
                requires=["DAVID_LEADS_LIVE=1", "network egress"],
                records_available=None,
            )
        _, error = self._get_json(self.endpoint, params=self._probe_params())
        if error:
            return AdapterStatus(
                name=self.name, kind=self.kind, truth_state=TruthState.UNAVAILABLE,
                detail=f"{self.description} Probe failed: {error}.",
                requires=["network egress"], records_available=None,
            )
        return AdapterStatus(
            name=self.name, kind=self.kind, truth_state=TruthState.VERIFIED,
            detail=f"{self.description} Probe succeeded; source reachable.",
            requires=["network egress"], records_available=None,
        )

    def _probe_params(self) -> Optional[dict]:
        return None

    def fetch(self) -> list[LeadRecord]:
        return []  # base class yields nothing; subclasses implement real parses


class USAspendingAdapter(PublicSourceAdapter):
    """Federal contract-award activity for a recipient organization."""

    name = "usaspending"
    endpoint = "https://api.usaspending.gov/api/v2/references/toptier_agencies/"
    description = "USAspending federal award records (public, no key)."

    def fetch(self) -> list[LeadRecord]:
        """v0: reachability only. Award-search parsing lands with the entity-
        resolution milestone; until then this adapter honestly yields no leads
        rather than partial, unattributed rows."""
        return []


class SECEdgarAdapter(PublicSourceAdapter):
    """SEC EDGAR registrant filing activity (public, no key).

    Probe target is the EDGAR full-text search API (efts.sec.gov), the same
    lane the legacy app/edgar_fts.py adapter uses. Note: www.sec.gov document
    endpoints 403 from many datacenter egress IPs under SEC fair-access rules;
    the adapter reports exactly what the probe sees rather than assuming reach.
    """

    name = "sec_edgar"
    endpoint = "https://efts.sec.gov/LATEST/search-index"
    description = "SEC EDGAR full-text registrant filings (public, no key; fair-access UA required)."

    def _probe_params(self) -> Optional[dict]:
        return {"q": '"8-K"', "dateRange": "custom"}

    def fetch(self) -> list[LeadRecord]:
        return []  # v0: reachability only, same honesty rule as USAspending


class EPAEchoAdapter(PublicSourceAdapter):
    """EPA ECHO facility compliance/monitoring activity (public, no key)."""

    name = "epa_echo"
    endpoint = "https://echodata.epa.gov/echo/dfr_rest_services.get_facility_info"
    description = "EPA ECHO facility records (public, no key)."

    def _probe_params(self) -> Optional[dict]:
        return {"output": "JSON", "p_fn": "110000000000"}  # fixed well-known FRS prefix probe

    def fetch(self) -> list[LeadRecord]:
        return []  # v0: reachability only


def synthetic_signal(source: str, text: str, evidence_ref: str) -> Signal:
    """Helper for tests: build an honestly-labeled synthetic signal."""
    now = datetime.now(timezone.utc)
    return Signal(
        source=source, source_class=SourceClass.SYNTHETIC_DEMO, signal=text,
        observed_at=now, retrieved_at=now, evidence_ref=evidence_ref,
    )
