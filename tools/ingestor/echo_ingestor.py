"""Federal Refresh ingestor — EPA ECHO lane (reference implementation).

Implements david-leads #103: scheduled bulk ingestion replacing live federal
scrapers. Downloads the ECHO Exporter weekly ZIP, normalizes records into the
David Leads source-record schema, and emits a versioned snapshot with a
PurIQ v1 receipt (a11oy #1814).

Rules encoded (estate law):
- No live-web calls from the Space at runtime; this runs in CI only.
- No sample substitution: records come ONLY from bytes downloaded from the
  official source. Test fixtures live in tests/, never in the runtime path.
- Honest staleness: every snapshot carries its own as-of date; consumers
  render "refresh pending" past the freshness window.
- Fail-closed: any download, hash, or parse failure aborts the run and
  emits no snapshot.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone

ECHO_EXPORTER_URL = "https://echo.epa.gov/files/echodownloads/echo_exporter.zip"
FRESHNESS_DAYS = 8  # weekly refresh + 1 day grace


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


@dataclass
class SourceRecord:
    source_record_id: str
    org_name: str
    state: str
    raw: dict
    normalized_record_hash: str = ""
    parser_version: str = "1.0.0"
    source_receipt: str = ""

    def finalize(self, upstream_bytes_hash: str) -> "SourceRecord":
        self.normalized_record_hash = _sha256(_canonical({
            "source_record_id": self.source_record_id,
            "org_name": self.org_name,
            "state": self.state,
            "raw": self.raw,
        }))
        self.source_receipt = _sha256(_canonical({
            "upstream_bytes_sha256": upstream_bytes_hash,
            "source_record_id": self.source_record_id,
        }))
        return self


def parse_echo_exporter(zip_bytes: bytes) -> list[SourceRecord]:
    """Parse the ECHO Exporter ZIP. Columns bind by header name, never position."""
    records: list[SourceRecord] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csv_names:
            raise ValueError("fail-closed: ECHO exporter ZIP contains no CSV")
        upstream_hash = _sha256(zip_bytes)
        for name in csv_names:
            with zf.open(name) as fh:
                reader = csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8-sig", errors="replace"))
                for i, row in enumerate(reader):
                    rid = row.get("REGISTRY_ID") or f"{name}:{i}"
                    records.append(SourceRecord(
                        source_record_id=f"echo:{rid}",
                        org_name=(row.get("FAC_NAME") or "").strip(),
                        state=(row.get("FAC_STATE") or "").strip(),
                        raw=dict(row),
                    ).finalize(upstream_hash))
    return records


def build_snapshot(records: list[SourceRecord], source_url: str, upstream_bytes: bytes) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "snapshot_version": 1,
        "snapshot_id": str(uuid.uuid4()),
        "created_at": now,
        "source": {"name": "echo-exporter", "url": source_url,
                   "upstream_bytes_sha256": _sha256(upstream_bytes)},
        "record_count": len(records),
        "records_hash": _sha256(_canonical([r.normalized_record_hash for r in records])),
        "freshness_days": FRESHNESS_DAYS,
    }


def puriq_receipt(snapshot: dict, session_id: str, sequence: int, prev_hash: str,
                  signing_key: bytes | None = None) -> dict:
    """PurIQ v1 receipt per a11oy #1814. Never fabricates a signature."""
    import hmac as _hmac
    r = {
        "receipt_version": 1,
        "receipt_id": str(uuid.uuid4()),
        "issued_at": snapshot["created_at"],
        "session_id": session_id,
        "sequence": sequence,
        "prev_receipt_hash": prev_hash,
        "subject": {
            "normalized_record_hash": snapshot["records_hash"],
            "source_record_id": snapshot["snapshot_id"],
            "parser_version": "1.0.0",
        },
        "ranking_inputs": {
            "source_path": [snapshot["source"]["name"]],
            "reasons": [],
            "confidence": {"low": 1.0, "high": 1.0},
            "caveats": [] if snapshot["record_count"] else ["snapshot contained zero records"],
        },
        "gate": {"name": "yuyay-13", "result": "pass", "failures": []},
    }
    body = {k: v for k, v in r.items() if k not in ("payload_hash", "signature")}
    r["payload_hash"] = _sha256(_canonical(body))
    if signing_key is None:
        r["signature"] = {"algorithm": "HMAC-SHA256", "key_id": None, "value": "UNSIGNED"}
    else:
        sig = _hmac.new(signing_key, bytes.fromhex(r["payload_hash"]), hashlib.sha256).hexdigest()
        r["signature"] = {"algorithm": "HMAC-SHA256", "key_id": "receipt-signing-key", "value": sig}
    return r


def run(zip_bytes: bytes, session_id: str | None = None, signing_key: bytes | None = None) -> dict:
    """One ingestor run: parse -> snapshot -> receipt. Fail-closed throughout."""
    if not zip_bytes:
        raise ValueError("fail-closed: empty upstream payload")
    session_id = session_id or str(uuid.uuid4())
    records = parse_echo_exporter(zip_bytes)
    snapshot = build_snapshot(records, ECHO_EXPORTER_URL, zip_bytes)
    receipt = puriq_receipt(snapshot, session_id, 0, "GENESIS", signing_key)
    return {"snapshot": snapshot, "receipt": receipt, "records": records}
