# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — david-leads vertical
"""Ingestion adapter contract.

Every adapter reports an honest AdapterStatus (VERIFIED / UNKNOWN /
UNAVAILABLE) and yields LeadRecord objects whose signals carry provenance.
No adapter fabricates records: a source that cannot be read reports its true
state and yields nothing. UNAVAILABLE is an audited answer, not an error to
hide (Zero-Bandaid).
"""
from __future__ import annotations

from typing import Protocol

from ..models import AdapterStatus, LeadRecord


class IngestionAdapter(Protocol):
    name: str
    kind: str  # DEMO | PUBLIC | LICENSED

    def status(self) -> AdapterStatus:
        """Current honest state of the source. Cheap; must not raise."""
        ...

    def fetch(self) -> list[LeadRecord]:
        """Records available right now. Empty list with an UNAVAILABLE/UNKNOWN
        status is an honest answer; an invented record is not permitted."""
        ...
