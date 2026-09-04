#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed live proof for David Leads' four federal data lanes.

This probe calls the same public, read-only endpoint as the browser. It records
only source states, counts, parser/receipt contract summaries, and hashes. It
never exports an organization record and never substitutes sample data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CANONICAL_SPACE = "https://szlholdings-david-leads.hf.space"
STATES = "NY,NJ,PA,MD,DE,CT,VA"
REQUIRED_LANES = (
    "dol-form5500-benefit-timing",
    "fmcsa-company-census",
    "usaspending-contract-activity",
    "epa-echo-monitoring-activity",
)
NON_PRODUCTION = {"SAMPLE", "EXAMPLE", "MOCK", "FIXTURE"}
USER_AGENT = "SZL-David-Leads-Live-Canary/1.0 research@szlholdings.com"


def _get_json(path: str, timeout: int = 300) -> dict[str, Any]:
    url = CANONICAL_SPACE + path
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(4_000_000)
            status = response.getcode()
    except urllib.error.HTTPError as exc:
        body = exc.read(2048).decode("utf-8", "replace")
        raise RuntimeError(f"HTTP_{exc.code}: {body[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"TRANSPORT_{type(exc.reason).__name__}") from exc
    if status != 200:
        raise RuntimeError(f"HTTP_{status}")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("NON_OBJECT_JSON")
    return value


def _as_count(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        return -1
    return count if count >= 0 else -1


def _record_contract(records: list[dict[str, Any]]) -> dict[str, Any]:
    invalid_hash = 0
    missing_source_id = 0
    missing_parser = 0
    dishonest_receipt = 0
    non_production = 0
    hashes: list[str] = []
    parser_versions: set[str] = set()
    receipt_states: set[str] = set()

    for record in records:
        mode = str(
            record.get("mode")
            or record.get("source_status")
            or record.get("truth_label")
            or ""
        ).strip().upper()
        if mode in NON_PRODUCTION or bool(record.get("_sample")):
            non_production += 1

        digest = str(record.get("normalized_record_sha256") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            invalid_hash += 1
        else:
            hashes.append(digest)
        if not str(record.get("source_record_id") or "").strip():
            missing_source_id += 1
        parser = str(record.get("parser_version") or "").strip()
        if not parser:
            missing_parser += 1
        else:
            parser_versions.add(parser)
        receipt_state = str(record.get("receipt_state") or "").strip().upper()
        if receipt_state not in {"SIGNED", "HASH_CHAINED_UNSIGNED"}:
            dishonest_receipt += 1
        elif receipt_state:
            receipt_states.add(receipt_state)

    canonical_hashes = "\n".join(sorted(hashes)).encode("utf-8")
    return {
        "records_observed": len(records),
        "records_exported": False,
        "record_hash_set_sha256": hashlib.sha256(canonical_hashes).hexdigest(),
        "parser_versions": sorted(parser_versions),
        "receipt_states": sorted(receipt_states),
        "invalid_hash": invalid_hash,
        "missing_source_record_id": missing_source_id,
        "missing_parser_version": missing_parser,
        "invalid_receipt_state": dishonest_receipt,
        "non_production_records": non_production,
        "complete": bool(records)
        and not any(
            (
                invalid_hash,
                missing_source_id,
                missing_parser,
                dishonest_receipt,
                non_production,
            )
        ),
    }


def evaluate(
    board: dict[str, Any],
    build: dict[str, Any],
    *,
    expected_revision: str = "",
) -> dict[str, Any]:
    raw_sources = board.get("sources") or []
    sources = [item for item in raw_sources if isinstance(item, dict)]
    by_id = {str(item.get("source_id") or ""): item for item in sources}
    lanes: list[dict[str, Any]] = []

    for source_id in REQUIRED_LANES:
        item = by_id.get(source_id)
        if item is None:
            lanes.append(
                {
                    "source_id": source_id,
                    "mode": "UNAVAILABLE",
                    "count": -1,
                    "reason": "SOURCE_NOT_RETURNED",
                    "operational": False,
                }
            )
            continue
        mode = str(item.get("mode") or "UNAVAILABLE").strip().upper()
        count = _as_count(item.get("count"))
        reason = str(item.get("reason") or "").strip()[:240]
        lanes.append(
            {
                "source_id": source_id,
                "mode": mode,
                "count": count,
                "reason": reason or None,
                "operational": mode == "LIVE" and count > 0,
            }
        )

    raw_records = board.get("opportunities") or board.get("leads") or []
    records = [item for item in raw_records if isinstance(item, dict)]
    record_contract = _record_contract(records)

    revision = str(
        build.get("source_revision")
        or (build.get("build") or {}).get("revision")
        or ""
    ).lower()
    release = build.get("release_receipt") or {}
    source_bound = bool(re.fullmatch(r"[0-9a-f]{40}", revision))
    if expected_revision:
        source_bound = source_bound and revision == expected_revision.lower()
    release_attested = bool(
        build.get("receipt_minted") is True
        and release.get("state") == "GITHUB_OIDC_ATTESTED"
        and release.get("source_revision") == revision
    )

    complete = bool(
        all(lane["operational"] for lane in lanes)
        and record_contract["complete"]
        and source_bound
        and release_attested
    )
    return {
        "schema": "szl.david-frontier-live-canary/v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": "/api/frontier-desk",
        "states": STATES.split(","),
        "sample_substitution": False,
        "records_exported": False,
        "required_lanes": lanes,
        "record_contract": record_contract,
        "deployment": {
            "source_revision": revision or None,
            "expected_revision": expected_revision or None,
            "source_bound": source_bound,
            "release_attested": release_attested,
        },
        "complete": complete,
    }


def run(expected_revision: str = "") -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {"states": STATES, "limit_per_source": 3},
        safe=",",
    )
    board = _get_json(f"/api/frontier-desk?{query}")
    build = _get_json("/api/build-info", timeout=60)
    return evaluate(board, build, expected_revision=expected_revision)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="david-frontier-live-canary.json")
    parser.add_argument("--expected-revision", default="")
    args = parser.parse_args(argv)
    report: dict[str, Any]
    try:
        report = run(args.expected_revision.strip())
    except Exception as exc:
        report = {
            "schema": "szl.david-frontier-live-canary/v1",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "endpoint": "/api/frontier-desk",
            "sample_substitution": False,
            "records_exported": False,
            "complete": False,
            "failure": f"{type(exc).__name__}: {str(exc)[:300]}",
        }
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    Path(args.output).write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0 if report.get("complete") is True else 1


if __name__ == "__main__":
    sys.exit(main())
