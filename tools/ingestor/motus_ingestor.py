"""Federal Refresh ingestor — FMCSA MOTUS lane.

Lane 2 of david-leads #103. FMCSA migrated its public carrier data to the
MOTUS schema on the DOT Data Portal; the legacy layouts are frozen archives
and must NOT be parsed. This module parses the MOTUS Carrier extract.

Same estate-law properties as echo_ingestor (imported, not duplicated):
header-bound parsing, three-level provenance, PurIQ v1 receipt, fail-closed.
parser_version for this lane starts at 1.0.0 and bumps independently.
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

MOTUS_CARRIER_URL = "https://data.transportation.gov/api/views/motus-carrier/rows.csv"
MOTUS_PARSER_VERSION = "1.0.0"


def parse_motus_carrier(payload: bytes) -> list[SourceRecord]:
    """Parse the MOTUS Carrier extract (CSV bytes, or a ZIP containing one CSV).

    Columns bind by header name, never position. DOT_NUMBER is the identity key.
    """
    if payload[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not names:
                raise ValueError("fail-closed: MOTUS ZIP contains no CSV")
            with zf.open(names[0]) as fh:
                payload = fh.read()

    upstream_hash = _sha256(payload)
    text = payload.decode("utf-8-sig", errors="replace")
    header = text.split("\n", 1)[0].upper()
    if "DOT" not in header:
        raise ValueError("fail-closed: payload header does not look like a MOTUS carrier extract")

    records: list[SourceRecord] = []
    reader = csv.DictReader(io.StringIO(text))
    for i, row in enumerate(reader):
        row = {(k or "").strip().upper(): (v or "") for k, v in row.items()}
        dot = row.get("DOT_NUMBER") or row.get("DOTNUMBER") or row.get("DOT") or f"row:{i}"
        rec = SourceRecord(
            source_record_id=f"fmcsa-motus:{dot}",
            org_name=(row.get("LEGAL_NAME") or row.get("DBA_NAME") or "").strip(),
            state=(row.get("PHY_STATE") or row.get("STATE") or "").strip(),
            raw=dict(row),
        )
        rec.parser_version = MOTUS_PARSER_VERSION
        records.append(rec.finalize(upstream_hash))
    return records


def run_motus(payload: bytes, session_id: str | None = None, signing_key: bytes | None = None) -> dict:
    """One MOTUS lane run: parse -> snapshot -> receipt. Fail-closed throughout."""
    if not payload:
        raise ValueError("fail-closed: empty upstream payload")
    import hmac as _hmac
    import uuid as _uuid

    session_id = session_id or str(_uuid.uuid4())
    records = parse_motus_carrier(payload)
    snapshot = build_snapshot(records, MOTUS_CARRIER_URL, payload)
    snapshot["source"]["name"] = "fmcsa-motus-carrier"
    receipt = puriq_receipt(snapshot, session_id, 0, "GENESIS", signing_key)
    receipt["subject"]["parser_version"] = MOTUS_PARSER_VERSION
    body = {k: v for k, v in receipt.items() if k not in ("payload_hash", "signature")}
    receipt["payload_hash"] = _sha256(_canonical(body))
    if signing_key is None:
        receipt["signature"] = {"algorithm": "HMAC-SHA256", "key_id": None, "value": "UNSIGNED"}
    else:
        sig = _hmac.new(signing_key, bytes.fromhex(receipt["payload_hash"]), hashlib.sha256).hexdigest()
        receipt["signature"] = {"algorithm": "HMAC-SHA256", "key_id": "receipt-signing-key", "value": sig}
    return {"snapshot": snapshot, "receipt": receipt, "records": records}
