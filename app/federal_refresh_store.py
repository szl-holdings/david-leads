# SPDX-License-Identifier: Apache-2.0
"""Compatibility facade over the closed federal scheduled-snapshot verifier.

The retired raw-record format is deliberately unsupported. ECHO uses its own
v3 verifier in app.echo_snapshot; the other lanes use app.federal_snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from . import federal_snapshot as snapshots

DATASET_ID = snapshots.DATASET_ID


class StoreState(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    UNVERIFIED = "unverified"
    EMPTY = "empty"


@dataclass
class StoreResult:
    state: StoreState
    records: list[dict] = field(default_factory=list)
    snapshot_id: str | None = None
    created_at: str | None = None
    receipt: dict | None = None
    message: str = ""


def verify_snapshot_payload(snapshot: dict, receipt: dict, records: list[dict],
                            now: datetime | None = None) -> tuple[bool, str]:
    """Verify the complete current contract, never the deprecated raw schema."""
    try:
        payload = b"".join(snapshots.canonical(row) + b"\n" for row in records)
        snapshots.verify_bundle(snapshot, receipt, payload, now=now)
        return True, "ok"
    except snapshots.StaleSnapshot as exc:
        return False, str(exc)
    except (ValueError, TypeError, KeyError, AttributeError):
        return False, "snapshot contract or content verification failed"


class FederalRefreshStore:
    def __init__(self, loader=None, now=None, *, lane: str = "fmcsa"):
        if lane not in snapshots.LANES:
            raise snapshots.SnapshotError("unsupported scheduled snapshot lane")
        self.lane = lane
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._loader = loader or self.load_latest_from_hub

    def load_latest_from_hub(self) -> dict:
        return snapshots.load_verified(self.lane, now=self._now())

    def fetch_snapshot_organizations(self, states: list[str] | None = None,
                                     limit: int = 50) -> StoreResult:
        try:
            bundle = self._loader()
            if bundle is None:
                return StoreResult(StoreState.EMPTY, message="no snapshot available; refresh pending")
            snapshot = bundle["snapshot"]
            receipt = bundle["receipt"]
            payload = bundle.get("records_bytes")
            if payload is None:
                payload = b"".join(snapshots.canonical(row) + b"\n" for row in bundle["records"])
            verified = snapshots.verify_bundle(snapshot, receipt, payload, now=self._now())
            if snapshot["lane"] != self.lane:
                raise snapshots.SnapshotError("snapshot lane mismatch")
            wanted = {state.upper() for state in states} if states else set(snapshot["coverage"]["requested_states"])
            if not wanted <= set(snapshot["coverage"]["requested_states"]):
                raise snapshots.SnapshotError("selected state outside published coverage")
            records = [row for row in verified["records"] if row["state"] in wanted]
            return StoreResult(StoreState.FRESH, records=records[:max(1, min(int(limit), 50))],
                               snapshot_id=snapshot["snapshot_id"], created_at=snapshot["created_at"],
                               receipt=receipt)
        except snapshots.StaleSnapshot as exc:
            return StoreResult(StoreState.STALE, message=str(exc))
        except (ValueError, TypeError, KeyError, AttributeError):
            return StoreResult(StoreState.UNVERIFIED, message="snapshot failed verification; refresh pending")
        except Exception:
            return StoreResult(StoreState.EMPTY, message="snapshot unavailable; refresh pending")
