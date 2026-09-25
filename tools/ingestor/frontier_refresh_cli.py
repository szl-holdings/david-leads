# SPDX-License-Identifier: Apache-2.0
"""Scheduled official collection; the Space only reads the resulting dataset.

Every requested state must finish. Empty or invalid captures cannot publish.
The 27-state Eastern default is bounded discovery, never exhaustive registry coverage.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
from collections.abc import Callable

from app import federal_snapshot as snapshots

DEFAULT_STATES = snapshots.TARGET_STATES


class CollectionTransportError(RuntimeError):
    """A bounded provider transport failure with safe diagnostic fields."""

    def __init__(self, state: str, attempts: int, cause_type: str):
        super().__init__(f"{state}: {cause_type} after {attempts} attempts")
        self.state = state
        self.attempts = attempts
        self.cause_type = cause_type


def _collect_with_retry(collector, state):
    """Bounded transport retries; bot blocks and contract failures stop immediately."""
    for attempt in range(3):
        try:
            return collector([state], limit=50)
        except urllib.error.HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504}:
                raise
            if attempt == 2:
                raise CollectionTransportError(
                    state, attempt + 1, f"HTTP_{exc.code}"
                ) from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            if attempt == 2:
                raise CollectionTransportError(
                    state, attempt + 1, type(exc).__name__
                ) from exc
        time.sleep(2 ** attempt)


def collect_bundle(lane: str, source_revision: str, *, states=None,
                   per_state_limit: int = 20, collector: Callable | None = None,
                   created_at: str | None = None) -> dict:
    if lane not in snapshots.LANES:
        raise snapshots.SnapshotError("unknown federal lane")
    requested = list(DEFAULT_STATES if states is None else states)
    if (not requested or len(requested) > 27 or len(set(requested)) != len(requested)
            or any(state not in snapshots.STATES for state in requested)):
        raise snapshots.SnapshotError("states must be distinct valid two-letter state codes")
    if type(per_state_limit) is not int or not 1 <= per_state_limit <= 50:
        raise snapshots.SnapshotError("per-state limit must be between 1 and 50")
    if collector is None:
        from app import frontier_sources
        collector = {"fmcsa": frontier_sources.collect_fmcsa_live,
                     "form5500": frontier_sources.collect_form5500_live,
                     "usaspending": frontier_sources.collect_usaspending_live}[lane]
    records = []
    coverage = {"requested_states": requested, "completed_states": [],
                "state_record_counts": {}, "per_state_limit": per_state_limit,
                "status": "COMPLETE", "selection": "BOUNDED_ADAPTER_RESULTS_NOT_EXHAUSTIVE",
                "query_windows": {}, "admission_counts": {}}
    for state in requested:
        result = _collect_with_retry(collector, state)
        if not isinstance(result, dict) or result.get("mode") != "LIVE":
            raise snapshots.SnapshotError(f"{lane}/{state}: official collection did not complete")
        rows = result.get("records")
        if not isinstance(rows, list) or len(rows) > 50 or result.get("count") != len(rows):
            raise snapshots.SnapshotError(f"{lane}/{state}: invalid official result counts")
        if any(not isinstance(row, dict) or row.get("state") != state for row in rows):
            raise snapshots.SnapshotError(f"{lane}/{state}: record territory mismatch")
        admitted = [row for row in rows if snapshots.admits_organization(row)]
        # Validate all admitted rows before selection so invalid records cannot hide
        # behind the output limit. Only the explicit organization policy excludes rows.
        for row in admitted:
            snapshots.project_record(lane, row)
        chosen = admitted[:per_state_limit]
        records.extend(chosen)
        coverage["completed_states"].append(state)
        coverage["state_record_counts"][state] = len(chosen)
        coverage["query_windows"][state] = result.get("query_window")
        coverage["admission_counts"][state] = {
            "adapter_returned": len(rows), "excluded_non_organization": len(rows) - len(admitted),
            "eligible_not_selected": len(admitted) - len(chosen), "selected": len(chosen),
        }
    return snapshots.build_bundle(lane, records, source_revision, coverage, created_at)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", choices=tuple(snapshots.LANES), required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--states", nargs="+", default=list(DEFAULT_STATES))
    parser.add_argument("--per-state-limit", type=int, default=20)
    args = parser.parse_args(argv)
    try:
        bundle = collect_bundle(args.lane, args.source_revision, states=args.states,
                                per_state_limit=args.per_state_limit)
        snapshots.write_bundle(bundle, args.out)
    except Exception as exc:
        # Providers can include arbitrary response bodies in errors; log only class.
        safe_state = getattr(exc, "state", "UNAVAILABLE")
        safe_attempts = getattr(exc, "attempts", "UNAVAILABLE")
        safe_error = getattr(exc, "cause_type", type(exc).__name__)
        print(
            "FEDERAL_REFRESH_FAILED_CLOSED "
            f"lane={args.lane} state={safe_state} attempts={safe_attempts} "
            f"error={safe_error}",
            file=sys.stderr,
        )
        return 1
    snapshot = bundle["snapshot"]
    print(json.dumps({"state": "LOCAL_VERIFIED", "lane": args.lane,
                      "snapshot_id": snapshot["snapshot_id"], "record_count": snapshot["record_count"],
                      "coverage": snapshot["coverage"], "receipt_state": "PAYLOAD_VERIFIED_UNSIGNED"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
