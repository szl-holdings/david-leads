"""Federal Refresh ingestor — USAspending lane.

Lane 4 of david-leads #103. The live API is POST-based and unreliable from
datacenter IPs (probed 2026-09-04); this lane consumes the published monthly
award-data archives (files.usaspending.gov), the sanctioned bulk path.

Archives are ZIPs of delimited CSVs. Columns bind by header name, never
position. Identity key: the unique award key variants. Recipient name and
state come from the recipient fields. Lane-scoped parser_version: 1.0.0.
"""

from __future__ import annotations

import csv
import hashlib
import io
import zipfile

from tools.ingestor.echo_ingestor import (
    SourceRecord,
    _canonical,
    _sha256,
    build_snapshot,
    puriq_receipt,
)

USASPENDING_ARCHIVE_URL = "https://files.usaspending.gov/award_data_archive/"
USASPENDING_PARSER_VERSION = "1.0.0"

_AWARD_KEYS = ("CONTRACT_AWARD_UNIQUE_KEY", "ASSISTANCE_AWARD_UNIQUE_KEY",
               "UNIQUE_AWARD_KEY", "AWARD_ID", "PIID", "FAIN")
_RECIPIENT_KEYS = ("RECIPIENT_NAME", "AWARDEE_OR_RECIPIENT_LEGAL_ENTITY_NAME", "VENDOR_NAME")
_STATE_KEYS = ("RECIPIENT_STATE_CODE", "RECIPIENT_STATE", "POP_STATE_CODE", "STATE")


def _first(row: dict, keys: tuple) -> str:
    return next((row[k].strip() for k in keys if row.get(k, "").strip()), "")


def _iter_text_payloads(payload: bytes) -> list[bytes]:
    if payload[:2] == b"PK":
        out = []
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith((".csv", ".txt"))]
            if not names:
                raise ValueError("fail-closed: USAspending ZIP contains no delimited data file")
            for n in names:
                with zf.open(n) as fh:
                    out.append(fh.read())
        return out
    return [payload]


def parse_usaspending(payload: bytes) -> list[SourceRecord]:
    records: list[SourceRecord] = []
    for blob in _iter_text_payloads(payload):
        upstream_hash = _sha256(blob)
        text = blob.decode("utf-8-sig", errors="replace")
        header = text.split("\n", 1)[0].upper()
        if not any(k in header for k in ("AWARD", "PIID", "FAIN", "RECIPIENT")):
            raise ValueError("fail-closed: payload header does not look like a USAspending award extract")
        if header.count("|") > header.count(","):
            class PipeDialect(csv.excel):
                delimiter = "|"
            dialect = PipeDialect
        else:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        for i, row in enumerate(reader):
            row = {(k or "").strip().upper(): (v or "") for k, v in row.items()}
            award = _first(row, _AWARD_KEYS) or f"row:{i}"
            rec = SourceRecord(
                source_record_id=f"usaspending:{award}",
                org_name=_first(row, _RECIPIENT_KEYS),
                state=_first(row, _STATE_KEYS),
                raw=dict(row),
            )
            rec.parser_version = USASPENDING_PARSER_VERSION
            records.append(rec.finalize(upstream_hash))
    return records


def run_usaspending(payload: bytes, session_id: str | None = None, signing_key: bytes | None = None) -> dict:
    """One USAspending lane run: parse -> snapshot -> receipt. Fail-closed throughout."""
    if not payload:
        raise ValueError("fail-closed: empty upstream payload")
    import hmac as _hmac
    import uuid as _uuid

    session_id = session_id or str(_uuid.uuid4())
    records = parse_usaspending(payload)
    snapshot = build_snapshot(records, USASPENDING_ARCHIVE_URL, payload)
    snapshot["source"]["name"] = "usaspending-archive"
    receipt = puriq_receipt(snapshot, session_id, 0, "GENESIS", signing_key)
    receipt["subject"]["parser_version"] = USASPENDING_PARSER_VERSION
    body = {k: v for k, v in receipt.items() if k not in ("payload_hash", "signature")}
    receipt["payload_hash"] = _sha256(_canonical(body))
    if signing_key is None:
        receipt["signature"] = {"algorithm": "HMAC-SHA256", "key_id": None, "value": "UNSIGNED"}
    else:
        sig = _hmac.new(signing_key, bytes.fromhex(receipt["payload_hash"]), hashlib.sha256).hexdigest()
        receipt["signature"] = {"algorithm": "HMAC-SHA256", "key_id": "receipt-signing-key", "value": sig}
    return {"snapshot": snapshot, "receipt": receipt, "records": records}
