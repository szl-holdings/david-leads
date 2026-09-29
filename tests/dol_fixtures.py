"""Synthetic fixtures: no actual organization records or production rights."""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from tools.ingestor.dol_5500_ingestor import run_dol_5500

KEY = b"synthetic-test-signing-key-32-bytes-only"
REVISION = "a" * 40
NOW = datetime.now(timezone.utc).replace(microsecond=0)
PAYLOAD = b"ACK_ID|SPONSOR_DFE_PN|SPONS_DFE_MAIL_US_STATE|FORM_YEAR|PLAN_YEAR_BEGIN_DATE|PLAN_YEAR_END_DATE|AMENDED_IND|SPONSOR_DFE_EIN|SIGNER_NAME|TOT_PARTCP_BOY_CNT\nSYNTHETIC-A1|Synthetic Review Fixture Corp|NY|2025|20250101|20251231|1|EXCLUDED-EIN|EXCLUDED-PERSON|12\n"

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

def fixture():
    value = run_dol_5500(PAYLOAD, session_id="synthetic", signing_key=KEY)
    value["records"] = [asdict(record) for record in value["records"]]
    return value

def bundle_files(value, *, resign=True):
    snapshot, receipt = value["snapshot"], value["receipt"]
    if resign:
        receipt["subject"]["snapshot_sha256"] = hashlib.sha256(canonical(snapshot)).hexdigest()
        receipt["issued_at"] = snapshot["created_at"]
        body = {k:v for k,v in receipt.items() if k not in {"payload_hash", "signature"}}
        receipt["payload_hash"] = hashlib.sha256(canonical(body)).hexdigest()
        receipt["signature"]["value"] = hmac.new(KEY, bytes.fromhex(receipt["payload_hash"]), hashlib.sha256).hexdigest()
    base = f"snapshots/dol-5500-bulk/{snapshot['created_at'][:10]}/{snapshot['snapshot_id']}"
    payloads = {"snapshot.json": canonical(snapshot), "receipt.json": canonical(receipt),
                "records.jsonl": b"\n".join(canonical(record) for record in value["records"])}
    pointer = {"snapshot_id":snapshot["snapshot_id"], "created_at":snapshot["created_at"],"lane":"dol-5500-bulk", "path":base,
               "files_sha256":{key:hashlib.sha256(data).hexdigest() for key,data in payloads.items()}}
    return {"latest/dol-5500-bulk.json":canonical(pointer), **{f"{base}/{key}":data for key,data in payloads.items()}}

def policy(value, *, display="DENY"):
    from app.domain.source_admission import SOURCE_ID, FIELDS
    return {"schema":"szl.david.dol-admission/v1", "source_id":SOURCE_ID,"policy_revision":"synthetic-review-v1",
            "review_reference":"synthetic-fixture-only", "expires_at":(NOW+timedelta(days=20)).isoformat(),
            "rights":{"collect":"ALLOW","research":"ALLOW","public_display":display,"redistribute":"DENY","train":"DENY"},
            "allowed_fields":sorted(FIELDS),"purpose":"organization_research","jurisdictions":["NY"],"snapshot_revision":REVISION,
            "classifications":{"dol-5500:SYNTHETIC-A1":{"classification":"VERIFIED_LEGAL_ORGANIZATION",
            "review_reference":"synthetic-organization-review","record_hash":value["records"][0]["normalized_record_hash"],
            "expires_at":(NOW+timedelta(days=10)).isoformat()}}}
