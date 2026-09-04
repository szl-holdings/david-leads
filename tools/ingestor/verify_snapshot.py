"""Verify a Federal Refresh snapshot directory.

Checks, in order (exit non-zero with a named failure on first mismatch):
1. every record's normalized_record_hash recomputes from its own content
2. records_hash recomputed from records.jsonl equals snapshot.json.records_hash
3. receipt payload_hash recomputed from the canonical body equals receipt.json.payload_hash
4. signed receipts must carry a non-null key_id
5. gate.result must be "pass" (a receipt on a failed gate is a fail-closed violation)
6. snapshot.created_at must be within freshness_days of now

Canonical-JSON rule (must match echo_ingestor._canonical byte-for-byte):
  json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _fail(msg: str) -> int:
    print(f"FAIL: {msg}")
    return 1


def _record_hash(r: dict) -> str:
    return hashlib.sha256(_canonical({
        "source_record_id": r["source_record_id"],
        "org_name": r["org_name"],
        "state": r["state"],
        "raw": r["raw"],
    })).hexdigest()


def verify(snapshot_dir: Path, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    snapshot = json.loads((snapshot_dir / "snapshot.json").read_text())
    receipt = json.loads((snapshot_dir / "receipt.json").read_text())
    records = [json.loads(line) for line in (snapshot_dir / "records.jsonl").read_text().splitlines() if line]

    for i, r in enumerate(records):
        if _record_hash(r) != r["normalized_record_hash"]:
            return _fail(f"record {i} ({r.get('source_record_id', '?')}): normalized_record_hash does not recompute from content")

    records_hash = hashlib.sha256(_canonical([r["normalized_record_hash"] for r in records])).hexdigest()
    if records_hash != snapshot["records_hash"]:
        return _fail("records_hash mismatch")

    body = {k: v for k, v in receipt.items() if k not in ("payload_hash", "signature")}
    if hashlib.sha256(_canonical(body)).hexdigest() != receipt["payload_hash"]:
        return _fail("receipt payload_hash mismatch")

    sig = receipt["signature"]
    if sig["value"] != "UNSIGNED" and sig["key_id"] is None:
        return _fail("signed receipt missing key_id")

    if receipt["gate"]["result"] != "pass":
        return _fail("receipt emitted on gate failure (fail-closed violation)")

    created = datetime.strptime(snapshot["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    age_days = (now - created).total_seconds() / 86400
    if age_days > snapshot["freshness_days"]:
        return _fail(f"snapshot stale: {age_days:.1f}d old, freshness window {snapshot['freshness_days']}d")

    print(f"OK: snapshot {snapshot['snapshot_id']} verifies ({len(records)} records, {age_days:.1f}d old)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot_dir")
    return verify(Path(ap.parse_args().snapshot_dir))


if __name__ == "__main__":
    sys.exit(main())
