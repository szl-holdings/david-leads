"""Synthetic canonical fixtures; no actual organizations or production rights."""
from datetime import datetime, timedelta, timezone
import json
from app import federal_snapshot as snapshots
from app import dol_admission_signature as signatures
from tools.ingestor.frontier_refresh_cli import collect_bundle

KEY = b"synthetic-test-signing-key-32-bytes-only"
REVISION = "a" * 40
NOW = datetime.now(timezone.utc).replace(microsecond=0)
canonical = snapshots.canonical


def fixture():
    row = {key: "Synthetic filing observation" for key in snapshots.TEXT_FIELDS}
    row.update(name="Synthetic Review Fixture Corp", state="NY", city="ALBANY", zip="12207",
               credential="DOL ACK SYNTHETIC-A1", license_or_issue_date="2025-01-01", trigger_date="2025-01-01",
               citation={"label": "DOL Form 5500", "url": snapshots.LANES["form5500"]["url"]},
               source_record={"label": "DOL Form 5500", "url": snapshots.LANES["form5500"]["url"]},
               authoritative_entity_ids=[{"system": "DOL Form 5500 ACK ID", "value": "SYNTHETIC-A1"}],
               limitations=["Synthetic test; no contact permission."],
               operational_snapshot={"participants_reported": 12, "benefit_categories": ["Life"]},
               timing={"label": "0-90 days", "next_anniversary": (NOW + timedelta(days=40)).date().isoformat(),
                       "days_to_anniversary": 40, "basis": "Reported period", "hypothesis_only": True},
               raw={"ein": "EXCLUDED", "person": "EXCLUDED"})
    def collector(states, limit):
        return {"mode": "LIVE", "count": 1, "records": [row],
                "query_window": {"anniversary_start": NOW.date().isoformat(),
                                 "anniversary_end": (NOW + timedelta(days=365)).date().isoformat()}}
    value = collect_bundle("form5500", REVISION, states=["NY"], collector=collector,
                           created_at=NOW.strftime("%Y-%m-%dT%H:%M:%SZ"))
    value["records"] = [json.loads(line) for line in value["records_bytes"].splitlines()]
    value["admission_signature"] = signatures.sign(value["snapshot"], value["receipt"], KEY)
    return value


def bundle_files(value, *, resign=True):
    snapshot, receipt = value["snapshot"], value["receipt"]
    pointer = snapshots.pointer_for(snapshot)
    base = pointer["path"]
    signature = signatures.sign(snapshot, receipt, KEY) if resign else value["admission_signature"]
    payloads = {"snapshot.json": canonical(snapshot), "receipt.json": canonical(receipt),
                "records.jsonl": b"".join(canonical(record) + b"\n" for record in value["records"]),
                signatures.FILENAME: canonical(signature)}
    return {"latest/form5500.json": canonical(pointer), **{f"{base}/{key}": data for key, data in payloads.items()}}


def policy(value, *, display="DENY"):
    from app.domain.source_admission import SOURCE_ID, FIELDS
    return {"schema":"szl.david.dol-admission/v1", "source_id":SOURCE_ID,"policy_revision":"synthetic-review-v1",
            "review_reference":"synthetic-fixture-only", "expires_at":(NOW+timedelta(days=20)).isoformat(),
            "rights":{"collect":"ALLOW","research":"ALLOW","public_display":display,"redistribute":"DENY","train":"DENY"},
            "allowed_fields":sorted(FIELDS),"purpose":"organization_research","jurisdictions":["NY"],"snapshot_revision":REVISION,
            "classifications":{"dol-5500:SYNTHETIC-A1":{"classification":"VERIFIED_LEGAL_ORGANIZATION",
            "review_reference":"synthetic-organization-review","record_hash":value["records"][0]["normalized_record_hash"],
            "expires_at":(NOW+timedelta(days=10)).isoformat()}}}
