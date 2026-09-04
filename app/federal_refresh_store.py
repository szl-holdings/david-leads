"""Federal Refresh dataset-backed store for the David Leads Space.

Reads the latest verified snapshot from SZLHOLDINGS/david-leads-data instead of
calling live federal sources at runtime (david-leads #103, PRs #104/#105).

Estate-law properties:
- Verification before service: every snapshot is checked with the same rules
  as tools.ingestor.verify_snapshot (per-record content hash, chain, receipt,
  gate, staleness). A snapshot that fails verification is never served.
- Honest staleness: when no verified fresh snapshot exists, the store reports
  STALE/EMPTY and the UI renders its existing placeholder — never fabricated
  or sample data.
- No live-web fallback: this module reads the HF Dataset only. There is no
  code path from here to the federal sources.

Interface mirrors the lane-fetch shape used in app/frontier_sources.py:
    fetch_* (states: list[str], limit: int) -> list[dict]
Here: fetch_snapshot_organizations(states, limit) -> StoreResult
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

DATASET_ID = "SZLHOLDINGS/david-leads-data"


class StoreState(str, Enum):
    FRESH = "fresh"            # verified snapshot within freshness window
    STALE = "stale"            # verified but past freshness window
    UNVERIFIED = "unverified"  # failed verification — never served
    EMPTY = "empty"            # no snapshot available


@dataclass
class StoreResult:
    state: StoreState
    records: list[dict] = field(default_factory=list)
    snapshot_id: str | None = None
    created_at: str | None = None
    receipt: dict | None = None
    message: str = ""


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _record_hash(r: dict) -> str:
    return hashlib.sha256(_canonical({
        "source_record_id": r["source_record_id"],
        "org_name": r["org_name"],
        "state": r["state"],
        "raw": r["raw"],
    })).hexdigest()


def verify_snapshot_payload(snapshot: dict, receipt: dict, records: list[dict],
                            now: datetime | None = None) -> tuple[bool, str]:
    """Same six checks as tools.ingestor.verify_snapshot, in-process."""
    now = now or datetime.now(timezone.utc)
    for i, r in enumerate(records):
        if _record_hash(r) != r.get("normalized_record_hash"):
            return False, f"record {i} content hash mismatch"
    records_hash = hashlib.sha256(_canonical([r["normalized_record_hash"] for r in records])).hexdigest()
    if records_hash != snapshot.get("records_hash"):
        return False, "records_hash mismatch"
    body = {k: v for k, v in receipt.items() if k not in ("payload_hash", "signature")}
    if hashlib.sha256(_canonical(body)).hexdigest() != receipt.get("payload_hash"):
        return False, "receipt payload_hash mismatch"
    sig = receipt.get("signature", {})
    if sig.get("value") != "UNSIGNED" and sig.get("key_id") is None:
        return False, "signed receipt missing key_id"
    if receipt.get("gate", {}).get("result") != "pass":
        return False, "receipt on gate failure"
    created = datetime.strptime(snapshot["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    if (now - created).total_seconds() / 86400 > snapshot.get("freshness_days", 8):
        return False, "stale"
    return True, "ok"


class FederalRefreshStore:
    """Dataset-backed store. `loader` is injected for testability; production
    uses load_latest_from_hub()."""

    def __init__(self, loader, now=None):
        self._loader = loader
        self._now = now or (lambda: datetime.now(timezone.utc))

    def load_latest_from_hub(self) -> dict | None:
        """Production loader: fetch latest.json + dated snapshot from the HF Dataset.
        Returns None when the dataset or pointer is unavailable (honest EMPTY)."""
        try:
            from huggingface_hub import hf_hub_download
            pointer_path = hf_hub_download(DATASET_ID, "latest.json", repo_type="dataset")
            pointer = json.loads(open(pointer_path).read())
            base = pointer["path"]
            out = {}
            for name in ("snapshot.json", "receipt.json", "records.jsonl"):
                p = hf_hub_download(DATASET_ID, f"{base}/{name}", repo_type="dataset")
                out[name] = open(p, "rb").read()
            return {
                "snapshot": json.loads(out["snapshot.json"]),
                "receipt": json.loads(out["receipt.json"]),
                "records": [json.loads(l) for l in out["records.jsonl"].decode().splitlines() if l],
            }
        except Exception:
            return None

    def fetch_snapshot_organizations(self, states: list[str] | None = None,
                                     limit: int = 50) -> StoreResult:
        bundle = self._loader()
        if bundle is None:
            return StoreResult(StoreState.EMPTY, message="no snapshot available; refresh pending")
        ok, why = verify_snapshot_payload(bundle["snapshot"], bundle["receipt"],
                                          bundle["records"], now=self._now())
        if not ok:
            if why == "stale":
                return StoreResult(StoreState.STALE,
                                   snapshot_id=bundle["snapshot"]["snapshot_id"],
                                   created_at=bundle["snapshot"]["created_at"],
                                   receipt=bundle["receipt"],
                                   message=f"data as of {bundle['snapshot']['created_at']}, refresh pending")
            return StoreResult(StoreState.UNVERIFIED,
                               snapshot_id=bundle["snapshot"].get("snapshot_id"),
                               message=f"snapshot failed verification: {why}")
        records = bundle["records"]
        if states:
            wanted = {s.upper() for s in states}
            records = [r for r in records if (r.get("state") or "").upper() in wanted]
        return StoreResult(StoreState.FRESH,
                           records=records[:limit],
                           snapshot_id=bundle["snapshot"]["snapshot_id"],
                           created_at=bundle["snapshot"]["created_at"],
                           receipt=bundle["receipt"])
