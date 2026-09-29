# SPDX-License-Identifier: Apache-2.0
"""Retired raw-file form5500 ingestor.

The earlier prototype serialized arbitrary upstream rows and did not implement
the current snapshot contract. Use the scheduled reviewed adapter projection:
python -m tools.ingestor.frontier_refresh_cli --lane form5500 --out ... --source-revision ...
"""
from __future__ import annotations

RETIRED_MESSAGE = "Legacy raw-file form5500 ingestion is retired; use frontier_refresh_cli --lane form5500"


def parse_dol_5500(payload: bytes):
    raise ValueError(RETIRED_MESSAGE)


def run_dol_5500(payload: bytes, session_id=None, signing_key=None):
    raise ValueError(RETIRED_MESSAGE)
