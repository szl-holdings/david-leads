"""Transactional streaming CLI for the EPA ECHO Federal Refresh."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

from tools.ingestor.echo_ingestor import (
    IngestionStats,
    RecordRootAccumulator,
    build_snapshot_from_metrics,
    canonical_json,
    file_sha256,
    iter_operational_echo_records,
    puriq_receipt,
    serialize_record,
)

PRODUCTION_MINIMUM_RECORDS = 1_000


def _write_json(path: Path, value: object) -> None:
    payload = json.dumps(
        value, indent=2, sort_keys=True, ensure_ascii=False
    ).encode("utf-8") + b"\n"
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def ingest_zip(
    zip_path: Path,
    out_dir: Path,
    *,
    source_revision: str,
    session_id: str | None = None,
    created_at: str | None = None,
    minimum_records: int = 1,
) -> dict[str, object]:
    """Write and self-verify one bundle atomically, leaving no partial output."""

    zip_path = zip_path.resolve(strict=True)
    out_dir = out_dir.resolve()
    if out_dir.exists():
        raise FileExistsError(f"fail-closed: output already exists: {out_dir}")
    if minimum_records <= 0:
        raise ValueError("fail-closed: minimum record threshold must be positive")
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{out_dir.name}-", dir=str(out_dir.parent)))
    try:
        upstream_hash = file_sha256(zip_path)
        stats = IngestionStats()
        record_root = RecordRootAccumulator()
        records_file_hash = hashlib.sha256()
        records_path = staging / "records.jsonl"

        with records_path.open("xb") as output:
            for record in iter_operational_echo_records(
                zip_path,
                upstream_hash=upstream_hash,
                stats=stats,
            ):
                encoded = canonical_json(serialize_record(record)) + b"\n"
                output.write(encoded)
                records_file_hash.update(encoded)
                record_root.add(record.normalized_record_hash)
            output.flush()
            os.fsync(output.fileno())

        if stats.rows_admitted < minimum_records:
            raise ValueError(
                "fail-closed: admitted record count "
                f"{stats.rows_admitted} is below required floor {minimum_records}"
            )

        snapshot = build_snapshot_from_metrics(
            record_count=stats.rows_admitted,
            records_root_sha256=record_root.hexdigest(),
            records_file_sha256=records_file_hash.hexdigest(),
            upstream_hash=upstream_hash,
            upstream_size_bytes=zip_path.stat().st_size,
            stats=stats,
            source_revision=source_revision,
            created_at=created_at,
        )
        receipt = puriq_receipt(
            snapshot,
            session_id or str(uuid.uuid4()),
            0,
            "GENESIS",
        )
        _write_json(staging / "snapshot.json", snapshot)
        _write_json(staging / "receipt.json", receipt)

        # Import here to keep the primitive module dependency one-way.
        from tools.ingestor.verify_snapshot import verify

        if verify(staging, require_fresh=True) != 0:
            raise ValueError("fail-closed: generated bundle did not self-verify")
        os.replace(staging, out_dir)
        return {"snapshot": snapshot, "receipt": receipt}
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True, help="Downloaded ECHO Exporter ZIP")
    parser.add_argument("--out", required=True, help="New output directory")
    parser.add_argument(
        "--source-revision",
        required=True,
        help="Exact 40-character Git SHA of the parser source",
    )
    parser.add_argument(
        "--minimum-records",
        type=int,
        default=PRODUCTION_MINIMUM_RECORDS,
        help="Fail when the admitted cardinality is unexpectedly low",
    )
    args = parser.parse_args()

    result = ingest_zip(
        Path(args.zip),
        Path(args.out),
        source_revision=args.source_revision,
        minimum_records=args.minimum_records,
    )
    snapshot = result["snapshot"]
    receipt = result["receipt"]
    print(
        f"snapshot_id={snapshot['snapshot_id']} "
        f"records={snapshot['record_count']} "
        f"records_file_sha256={snapshot['records_file_sha256']} "
        f"receipt_state={receipt['signature']['value']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
