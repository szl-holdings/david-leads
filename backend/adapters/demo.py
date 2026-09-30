# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — david-leads vertical
"""Synthetic demo dataset adapter — clearly labeled, offline by construction.

The dataset exists so the vertical runs end-to-end with no network and no
licensed data. Every record carries synthetic=true and SYNTHETIC_DEMO signal
provenance; the scorer admits such signals only on records labeled synthetic,
and every resulting response declares that the organization is not real.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..models import AdapterStatus, LeadRecord, TruthState

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "demo_leads.json"


class DemoAdapter:
    name = "demo_synthetic"
    kind = "DEMO"

    def _load(self) -> tuple[list[LeadRecord], str | None]:
        try:
            raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return [], f"dataset file missing: {DATA_FILE}"
        except json.JSONDecodeError as exc:
            return [], f"dataset file does not parse: {exc}"
        records = [LeadRecord(**row) for row in raw.get("leads", [])]
        unlabeled = [r.id for r in records if not r.synthetic]
        if unlabeled:
            # Zero-Bandaid: an unlabeled record in a synthetic dataset is a
            # provenance defect. Refuse the file rather than guess.
            return [], f"records without synthetic=true in a synthetic dataset: {unlabeled}"
        return records, None

    def status(self) -> AdapterStatus:
        records, error = self._load()
        if error:
            return AdapterStatus(
                name=self.name, kind=self.kind, truth_state=TruthState.UNAVAILABLE,
                detail=error, requires=["backend/data/demo_leads.json present, parseable, all synthetic"],
                records_available=None,
            )
        return AdapterStatus(
            name=self.name, kind=self.kind, truth_state=TruthState.VERIFIED,
            detail=(
                "Synthetic demonstration dataset loaded. Every record is labeled "
                "synthetic; no real organization or public record is represented."
            ),
            requires=[],
            records_available=len(records),
        )

    def fetch(self) -> list[LeadRecord]:
        records, _ = self._load()
        return records
