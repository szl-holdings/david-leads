# SPDX-License-Identifier: Apache-2.0
"""Retired raw-file usaspending ingestor.

The earlier prototype serialized arbitrary upstream rows and did not implement
the current snapshot contract. Use the scheduled reviewed adapter projection:
python -m tools.ingestor.frontier_refresh_cli --lane usaspending --out ... --source-revision ...
"""
from __future__ import annotations

RETIRED_MESSAGE = "Legacy raw-file usaspending ingestion is retired; use frontier_refresh_cli --lane usaspending"


def parse_usaspending(payload: bytes):
    raise ValueError(RETIRED_MESSAGE)


def run_usaspending(payload: bytes, session_id=None, signing_key=None):
    raise ValueError(RETIRED_MESSAGE)
