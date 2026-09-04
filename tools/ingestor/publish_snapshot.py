"""Publish a verified snapshot to the SZLHOLDINGS/david-leads-data HF Dataset.

Snapshots are immutable: dated path snapshots/YYYY-MM-DD/ is never overwritten.
A latest.json pointer is updated after a successful upload. The HF token comes
from the HF_TOKEN environment variable and is never logged.

Usage: python -m tools.ingestor.publish_snapshot --dataset SZLHOLDINGS/david-leads-data --snapshot <dir>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, help="HF Dataset repo id, e.g. SZLHOLDINGS/david-leads-data")
    ap.add_argument("--snapshot", required=True, help="Verified snapshot directory")
    args = ap.parse_args()

    token = os.environ.get("HF_TOKEN")
    if not token:
        print("SKIP: HF_TOKEN not set; snapshot verified but not published")
        return 0

    snap_dir = Path(args.snapshot)
    snapshot = json.loads((snap_dir / "snapshot.json").read_text())
    day = snapshot["created_at"][:10]
    dated_path = f"snapshots/{day}"

    from huggingface_hub import HfApi
    api = HfApi(token=token)

    try:
        api.list_repo_tree(args.dataset, repo_type="dataset", path_in_repo=dated_path)
        print(f"FAIL: {dated_path} already exists; snapshots are immutable")
        return 1
    except Exception:
        pass  # path does not exist yet — expected

    for name in ("snapshot.json", "receipt.json", "records.jsonl"):
        api.upload_file(
            path_or_fileobj=str(snap_dir / name),
            path_in_repo=f"{dated_path}/{name}",
            repo_id=args.dataset,
            repo_type="dataset",
            commit_message=f"federal-refresh snapshot {snapshot['snapshot_id']} ({name})",
        )

    pointer = {"snapshot_id": snapshot["snapshot_id"], "created_at": snapshot["created_at"], "path": dated_path}
    api.upload_file(
        path_or_fileobj=json.dumps(pointer, indent=2).encode("utf-8"),
        path_in_repo="latest.json",
        repo_id=args.dataset,
        repo_type="dataset",
        commit_message=f"federal-refresh: latest -> {dated_path}",
    )
    print(f"OK: published {dated_path} to {args.dataset} (snapshot {snapshot['snapshot_id']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
