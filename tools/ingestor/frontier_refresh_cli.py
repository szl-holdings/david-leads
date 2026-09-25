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
from functools import partial

from app import federal_snapshot as snapshots

DEFAULT_STATES = snapshots.TARGET_STATES
SCHEDULED_USASPENDING_TIMEOUT = 60


def _collect_with_retry(collector, state, *, lane=None, report=None):
    """Bounded transport retries; bot blocks and contract failures stop immediately."""
    for attempt in range(3):
        started = time.monotonic()
        try:
            result = collector([state], limit=50)
        except Exception as exc:
            retryable = (
                exc.code in {429, 500, 502, 503, 504}
                if isinstance(exc, urllib.error.HTTPError)
                else isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError))
            )
            retry = retryable and attempt < 2
            if report:
                # Never record exception text, URLs, headers, or provider bodies.
                report({"event": "COLLECTION_ATTEMPT", "lane": lane, "state": state,
                        "attempt": attempt + 1, "attempt_limit": 3,
                        "outcome": "RETRY" if retry else "FAILED",
                        "error_class": type(exc).__name__,
                        "http_status": exc.code if isinstance(exc, urllib.error.HTTPError) else None,
                        "elapsed_ms": round((time.monotonic() - started) * 1000),
                        "retry_delay_seconds": 2 ** attempt if retry else 0})
            if not retry:
                raise
            time.sleep(2 ** attempt)
        else:
            if report:
                report({"event": "COLLECTION_ATTEMPT", "lane": lane, "state": state,
                        "attempt": attempt + 1, "attempt_limit": 3, "outcome": "RETURNED",
                        "elapsed_ms": round((time.monotonic() - started) * 1000)})
            return result


def collect_bundle(lane: str, source_revision: str, *, states=None,
                   per_state_limit: int = 20, collector: Callable | None = None,
                   created_at: str | None = None, report: Callable | None = None) -> dict:
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
                     "usaspending": partial(frontier_sources.collect_usaspending_live,
                                            request_timeout=SCHEDULED_USASPENDING_TIMEOUT)}[lane]
    records = []
    coverage = {"requested_states": requested, "completed_states": [],
                "state_record_counts": {}, "per_state_limit": per_state_limit,
                "status": "COMPLETE", "selection": "BOUNDED_ADAPTER_RESULTS_NOT_EXHAUSTIVE",
                "query_windows": {}, "admission_counts": {}}
    for state in requested:
        result = _collect_with_retry(collector, state, lane=lane, report=report)
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
        if report:
            report({"event": "STATE_VALIDATED", "lane": lane, "state": state,
                    **coverage["admission_counts"][state]})
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
                                per_state_limit=args.per_state_limit,
                                report=lambda event: print(json.dumps(event, sort_keys=True),
                                                           file=sys.stderr, flush=True))
        snapshots.write_bundle(bundle, args.out)
    except Exception as exc:
        # Providers can include arbitrary response bodies in errors; log only class.
        print(f"FEDERAL_REFRESH_FAILED_CLOSED lane={args.lane} error={type(exc).__name__}", file=sys.stderr)
        return 1
    snapshot = bundle["snapshot"]
    print(json.dumps({"state": "LOCAL_VERIFIED", "lane": args.lane,
                      "snapshot_id": snapshot["snapshot_id"], "record_count": snapshot["record_count"],
                      "coverage": snapshot["coverage"], "receipt_state": "PAYLOAD_VERIFIED_UNSIGNED"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
