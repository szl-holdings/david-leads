"""Federal Refresh ingestor — DOL Form 5500 bulk lane.

Lane 3 of david-leads #103. The EFAST search endpoint is Akamai bot-blocked
for datacenter IPs (probed 2026-09-04); this lane replaces it permanently with
the published Form 5500 bulk datasets. No circumvention of any kind — the bulk
files are the sanctioned consumption path.

Bulk files are annual ZIPs containing delimited text (pipe- or comma-delimited
depending on vintage). The parser sniffs the delimiter from the header line and
binds columns by name, never position. ACK_ID is the filing identity key;
SPONSOR_DFE_PN is the plan sponsor name; SPONS_DFE_MAIL_US_STATE is the state.
Lane-scoped parser_version starts at 1.0.0.
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

DOL_5500_BULK_URL = "https://www.dol.gov/agencies/ebsa/about-ebsa/our-activities/public-disclosure/foia/form-5500-datasets"
DOL_PARSER_VERSION = "1.0.0"

_SPONSOR_KEYS = ("SPONSOR_DFE_PN", "SPONSOR_NAME", "PLAN_NAME")
_STATE_KEYS = ("SPONS_DFE_MAIL_US_STATE", "SPONSOR_STATE", "STATE")


def _sniff_dialect(header_line: str):
    if header_line.count("|") > header_line.count(","):
        class PipeDialect(csv.excel):
            delimiter = "|"
        return PipeDialect
    return csv.excel


def _iter_text_payloads(payload: bytes) -> list[bytes]:
    if payload[:2] == b"PK":
        out = []
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = [n for n in zf.namelist()
                     if n.lower().endswith((".csv", ".txt")) and "5500" in n.lower()]
            if not names:
                names = [n for n in zf.namelist() if n.lower().endswith((".csv", ".txt"))]
            if not names:
                raise ValueError("fail-closed: DOL 5500 ZIP contains no delimited data file")
            for n in names:
                with zf.open(n) as fh:
                    out.append(fh.read())
        return out
    return [payload]


def parse_dol_5500(payload: bytes) -> list[SourceRecord]:
    records: list[SourceRecord] = []
    for blob in _iter_text_payloads(payload):
        upstream_hash = _sha256(blob)
        text = blob.decode("utf-8-sig", errors="replace")
        header = text.split("\n", 1)[0].upper()
        if "ACK_ID" not in header and "SPONS" not in header:
            raise ValueError("fail-closed: payload header does not look like a Form 5500 filing extract")
        reader = csv.DictReader(io.StringIO(text), dialect=_sniff_dialect(header))
        for i, row in enumerate(reader):
            row = {(k or "").strip().upper(): (v or "") for k, v in row.items()}
            ack = row.get("ACK_ID") or f"row:{i}"
            sponsor = next((row[k].strip() for k in _SPONSOR_KEYS if row.get(k, "").strip()), "")
            state = next((row[k].strip() for k in _STATE_KEYS if row.get(k, "").strip()), "")
            rec = SourceRecord(
                source_record_id=f"dol-5500:{ack}",
                org_name=sponsor,
                state=state,
                raw=dict(row),
            )
            rec.parser_version = DOL_PARSER_VERSION
            records.append(rec.finalize(upstream_hash))
    return records


def run_dol_5500(payload: bytes, session_id: str | None = None, signing_key: bytes | None = None) -> dict:
    """One DOL 5500 lane run: parse -> snapshot -> receipt. Fail-closed throughout."""
    if not payload:
        raise ValueError("fail-closed: empty upstream payload")
    import hmac as _hmac
    import uuid as _uuid

    session_id = session_id or str(_uuid.uuid4())
    records = parse_dol_5500(payload)
    snapshot = build_snapshot(records, DOL_5500_BULK_URL, payload)
    snapshot["source"]["name"] = "dol-5500-bulk"
    receipt = puriq_receipt(snapshot, session_id, 0, "GENESIS", signing_key)
    receipt["subject"]["parser_version"] = DOL_PARSER_VERSION
    body = {k: v for k, v in receipt.items() if k not in ("payload_hash", "signature")}
    receipt["payload_hash"] = _sha256(_canonical(body))
    if signing_key is None:
        receipt["signature"] = {"algorithm": "HMAC-SHA256", "key_id": None, "value": "UNSIGNED"}
    else:
        sig = _hmac.new(signing_key, bytes.fromhex(receipt["payload_hash"]), hashlib.sha256).hexdigest()
        receipt["signature"] = {"algorithm": "HMAC-SHA256", "key_id": "receipt-signing-key", "value": sig}
    return {"snapshot": snapshot, "receipt": receipt, "records": records}
