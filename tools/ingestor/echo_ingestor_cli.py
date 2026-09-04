"""CLI entry for the Federal Refresh ECHO ingestor (CI-only, never the Space).

Usage: python -m tools.ingestor.echo_ingestor_cli --zip <path> --out <dir>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tools.ingestor.echo_ingestor import run


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True, help="Path to downloaded ECHO Exporter ZIP")
    ap.add_argument("--out", required=True, help="Output directory for the snapshot")
    args = ap.parse_args()

    zip_bytes = Path(args.zip).read_bytes()
    result = run(zip_bytes)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "snapshot.json").write_text(json.dumps(result["snapshot"], indent=2))
    (out / "receipt.json").write_text(json.dumps(result["receipt"], indent=2))
    with (out / "records.jsonl").open("w") as fh:
        for r in result["records"]:
            fh.write(json.dumps({
                "source_record_id": r.source_record_id,
                "org_name": r.org_name,
                "state": r.state,
                "raw": r.raw,
                "normalized_record_hash": r.normalized_record_hash,
                "parser_version": r.parser_version,
                "source_receipt": r.source_receipt,
            }) + "\n")
    print(f"snapshot_id={result['snapshot']['snapshot_id']} "
          f"records={result['snapshot']['record_count']} "
          f"receipt={result['receipt']['signature']['value']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
