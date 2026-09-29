"""Bounded DOL filing parser; excluded raw columns never leave this stage."""
from __future__ import annotations
import csv
import hashlib
import hmac
import io
import re
import uuid
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import date
from tools.ingestor.echo_ingestor import SourceRecord, _canonical, _sha256, build_snapshot, puriq_receipt

DOL_5500_BULK_URL = "https://www.dol.gov/agencies/ebsa/about-ebsa/our-activities/public-disclosure/foia/form-5500-datasets"
DOL_PARSER_VERSION = "2.0.0"
MAX_INPUT_BYTES = 128 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_ROWS = 100_000
SAFE_FIELDS = frozenset({"form_year", "plan_year_begin", "plan_year_end", "amended_filing", "participant_count", "reported_life_benefit"})

@dataclass(frozen=True)
class ParseResult:
    records: list[SourceRecord]
    rows_seen: int
    rejected_rows: int
    quarantined_rows: int
    quarantine_reasons: dict[str, int]

def _payloads(payload: bytes) -> list[bytes]:
    if not payload or len(payload) > MAX_INPUT_BYTES:
        raise ValueError("DOL_INPUT_SIZE")
    if payload[:2] != b"PK":
        return [payload]
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        members = archive.infolist()
        if len(members) > 32:
            raise ValueError("DOL_ARCHIVE_MEMBERS")
        if any(m.flag_bits & 1 or m.file_size > MAX_EXPANDED_BYTES or m.file_size > max(m.compress_size, 1) * 200 for m in members):
            raise ValueError("DOL_ARCHIVE_BUDGET")
        if sum(m.file_size for m in members) > MAX_EXPANDED_BYTES:
            raise ValueError("DOL_ARCHIVE_BUDGET")
        data = [m for m in members if m.filename.lower().endswith((".csv", ".txt"))]
        chosen = [m for m in data if "5500" in m.filename.lower()] or data
        if len(chosen) != 1:
            raise ValueError("DOL_LAYOUT_AMBIGUOUS")
        with archive.open(chosen[0]) as stream:
            result = stream.read(MAX_EXPANDED_BYTES + 1)
        if len(result) > MAX_EXPANDED_BYTES:
            raise ValueError("DOL_ARCHIVE_BUDGET")
        return [result]

def _date(value: str) -> str:
    if re.fullmatch(r"\d{8}", value):
        value = f"{value[:4]}-{value[4:6]}-{value[6:]}"
    elif re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):
        value = f"{value[6:]}-{value[:2]}-{value[3:5]}"
    return date.fromisoformat(value).isoformat()

def parse_dol_5500_report(payload: bytes) -> ParseResult:
    accepted: dict[str, SourceRecord] = {}
    conflicts: set[str] = set()
    reasons: Counter = Counter()
    rows_seen = rejected = quarantined = 0
    for blob in _payloads(payload):
        text = blob.decode("utf-8-sig", errors="strict")
        header = text.split("\n", 1)[0]
        reader = csv.DictReader(io.StringIO(text), delimiter="|" if header.count("|") > header.count(",") else ",")
        names = [str(x).strip().upper() for x in reader.fieldnames or []]
        if len(set(names)) != len(names) or not {"ACK_ID", "SPONSOR_DFE_PN", "SPONS_DFE_MAIL_US_STATE"} <= set(names):
            raise ValueError("DOL_SCHEMA_CHANGED")
        for row in reader:
            rows_seen += 1
            if rows_seen > MAX_ROWS:
                raise ValueError("DOL_ROW_BUDGET")
            try:
                if None in row or any(v is None for v in row.values()):
                    raise ValueError("ROW_SHAPE")
                row = {k.strip().upper(): v.strip() for k, v in row.items()}
                ack, sponsor, state = row["ACK_ID"], row["SPONSOR_DFE_PN"], row["SPONS_DFE_MAIL_US_STATE"]
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,96}", ack):
                    raise ValueError("FILING_ID_MISSING_OR_INVALID")
                if not sponsor or len(sponsor) > 240 or not re.fullmatch(r"[A-Z]{2}", state):
                    raise ValueError("ORGANIZATION_FIELDS_INVALID")
                fields: dict = {}
                for source, target in (("FORM_YEAR", "form_year"), ("TOT_PARTCP_BOY_CNT", "participant_count")):
                    if row.get(source):
                        if not re.fullmatch(r"\d{1,9}", row[source]):
                            raise ValueError("NUMERIC_FIELD_INVALID")
                        fields[target] = int(row[source])
                if "form_year" in fields and not 2009 <= fields["form_year"] <= date.today().year + 1:
                    raise ValueError("FORM_YEAR_UNSUPPORTED")
                for source, target in (("PLAN_YEAR_BEGIN_DATE", "plan_year_begin"), ("PLAN_YEAR_END_DATE", "plan_year_end")):
                    if row.get(source):
                        fields[target] = _date(row[source])
                if fields.get("plan_year_begin", "") > fields.get("plan_year_end", "9999"):
                    raise ValueError("PLAN_DATE_ORDER")
                if row.get("AMENDED_IND"):
                    if row["AMENDED_IND"] not in {"0", "1", "Y", "N"}:
                        raise ValueError("AMENDMENT_FLAG_INVALID")
                    fields["amended_filing"] = row["AMENDED_IND"] in {"1", "Y"}
                if row.get("WELFARE_BENEFIT_CODE"):
                    codes = row["WELFARE_BENEFIT_CODE"].replace(" ", "").replace(",", "")
                    if not re.fullmatch(r"(?:4[A-Z]){1,20}", codes):
                        raise ValueError("BENEFIT_CODE_INVALID")
                    fields["reported_life_benefit"] = "4B" in [codes[n:n+2] for n in range(0, len(codes), 2)]
                record = SourceRecord(f"dol-5500:{ack}", sponsor, state, fields, parser_version=DOL_PARSER_VERSION).finalize(_sha256(payload))
                if ack in conflicts:
                    raise ValueError("CONFLICTING_FILING_ID")
                if ack in accepted:
                    if accepted[ack].normalized_record_hash == record.normalized_record_hash:
                        rejected += 1
                        continue
                    del accepted[ack]
                    conflicts.add(ack)
                    quarantined += 1
                    reasons["CONFLICTING_FILING_ID"] += 1
                    raise ValueError("CONFLICTING_FILING_ID")
                accepted[ack] = record
            except (ValueError, OverflowError) as exc:
                quarantined += 1
                code = str(exc)
                reasons[code if re.fullmatch(r"[A-Z_]{1,64}", code) else "FIELD_INVALID"] += 1
    return ParseResult(list(accepted.values()), rows_seen, rejected, quarantined, dict(reasons))

def parse_dol_5500(payload: bytes) -> list[SourceRecord]:
    return parse_dol_5500_report(payload).records

def run_dol_5500(payload: bytes, session_id: str | None = None, signing_key: bytes | None = None) -> dict:
    if signing_key is not None and (not isinstance(signing_key, bytes) or len(signing_key) < 32):
        raise ValueError("DOL_SIGNING_KEY_TOO_SHORT")
    report = parse_dol_5500_report(payload)
    snapshot = build_snapshot(report.records, DOL_5500_BULK_URL, payload)
    snapshot["source"]["name"] = "dol-5500-bulk"
    snapshot["parser_version"] = DOL_PARSER_VERSION
    snapshot["counts"] = {"rows_seen": report.rows_seen, "accepted": len(report.records), "rejected": report.rejected_rows, "quarantined": report.quarantined_rows}
    snapshot["completeness"] = "PARTIAL" if report.quarantined_rows else "COMPLETE"
    snapshot["quarantine_reasons"] = report.quarantine_reasons
    receipt = puriq_receipt(snapshot, session_id or str(uuid.uuid4()), 0, "GENESIS", signing_key)
    receipt["subject"]["parser_version"] = DOL_PARSER_VERSION
    receipt["subject"]["snapshot_sha256"] = _sha256(_canonical(snapshot))
    body = {k: v for k, v in receipt.items() if k not in ("payload_hash", "signature")}
    receipt["payload_hash"] = _sha256(_canonical(body))
    receipt["signature"] = {"algorithm": "HMAC-SHA256", "key_id": "receipt-signing-key" if signing_key else None,
                            "value": hmac.new(signing_key, bytes.fromhex(receipt["payload_hash"]), hashlib.sha256).hexdigest() if signing_key else "UNSIGNED"}
    return {"snapshot": snapshot, "receipt": receipt, "records": report.records}
