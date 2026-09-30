# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — david-leads vertical
"""Licensed commercial data sources — honestly UNAVAILABLE in this deployment.

Verisk, LexisNexis Risk Solutions, Zesty.ai, and Cape Analytics sell
property/claims/loss-history intelligence under commercial license. This
deployment holds no license and no credentials, so each adapter reports
UNAVAILABLE with what would be required. That is the vertical's stated
differentiator made structural: where a black-box incumbent would still emit a
score, this service refuses to let unlicensed data influence one (Default
DENY in the scoring policy) and says so on the receipt.
"""
from __future__ import annotations

import os

from ..models import AdapterStatus, LeadRecord, TruthState


class LicensedAdapter:
    """Base for license-gated sources. UNAVAILABLE unless its license env var
    is configured; this build ships no licensed integration, so even with a
    variable set the adapter stays UNAVAILABLE until a real integration lands
    (Zero-Bandaid: a configured key is not evidence of a working source)."""

    name = "licensed_base"
    kind = "LICENSED"
    vendor = ""
    product = ""
    license_env = ""
    what_it_would_add = ""

    def status(self) -> AdapterStatus:
        configured = bool(os.environ.get(self.license_env, "").strip())
        if configured:
            detail = (
                f"{self.vendor} {self.product}: credentials present in {self.license_env}, "
                "but no licensed integration is implemented in v0. State stays UNAVAILABLE "
                "rather than pretending the feed works."
            )
        else:
            detail = (
                f"{self.vendor} {self.product}: licensed commercial source; no license or "
                f"credentials configured ({self.license_env} unset). {self.what_it_would_add}"
            )
        return AdapterStatus(
            name=self.name, kind=self.kind, truth_state=TruthState.UNAVAILABLE,
            detail=detail,
            requires=[f"commercial license from {self.vendor}", f"{self.license_env} credentials",
                      "licensed integration implementation"],
            records_available=None,
        )

    def fetch(self) -> list[LeadRecord]:
        return []  # unlicensed source yields nothing — by policy, not by bug


class VeriskAdapter(LicensedAdapter):
    name = "verisk"
    vendor = "Verisk"
    product = "ISO / A-PLUS loss history"
    license_env = "VERISK_API_KEY"
    what_it_would_add = "Property and auto claims/loss-history attributes per risk."


class LexisNexisRiskAdapter(LicensedAdapter):
    name = "lexisnexis_risk"
    vendor = "LexisNexis Risk Solutions"
    product = "C.L.U.E. / risk insights"
    license_env = "LEXISNEXIS_RISK_API_KEY"
    what_it_would_add = "Contributory claims history and entity risk attributes."


class ZestyAIAdapter(LicensedAdapter):
    name = "zesty_ai"
    vendor = "Zesty.ai"
    product = "property risk analytics"
    license_env = "ZESTY_API_KEY"
    what_it_would_add = "Aerial-imagery-derived property condition and peril scores."


class CapeAnalyticsAdapter(LicensedAdapter):
    name = "cape_analytics"
    vendor = "Cape Analytics"
    product = "property intelligence"
    license_env = "CAPE_API_KEY"
    what_it_would_add = "Geospatial property attributes (roof, condition, hazards)."
