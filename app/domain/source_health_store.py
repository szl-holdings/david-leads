"""Tenant-scoped durable source attempts; failures never reset last success."""
from dataclasses import asdict
from .david_reference import Grant, Hold, Verdict, canonical, parse_stamp, stamp
from .source_policy import SOURCE_CATALOG, SourceHealthRecord, _valid_record, record_source_attempt

_TIMES = ("last_attempt_at", "last_success_at", "snapshot_observed_at", "snapshot_expires_at")

def _encode(record):
    _valid_record(record)
    value = asdict(record)
    for key in _TIMES:
        value[key] = stamp(getattr(record, key)) if getattr(record, key) else None
    if record.grant:
        value["grant"] = {"source_id": record.grant.source_id, "policy_revision": record.grant.policy_revision,
                          "review_reference": record.grant.review_reference, "expires_at": stamp(record.grant.expires_at),
                          "rights": {key: item.value for key, item in record.grant.rights.items()},
                          "allowed_fields": sorted(record.grant.allowed_fields)}
    return canonical(value)

def _decode(value):
    try:
        value = dict(value)
        for key in _TIMES:
            value[key] = parse_stamp(value[key]) if value[key] else None
        if value["grant"]:
            grant = value["grant"]
            value["grant"] = Grant(grant["source_id"], grant["policy_revision"], grant["review_reference"],
                                   parse_stamp(grant["expires_at"]), {k: Verdict(v) for k, v in grant["rights"].items()},
                                   frozenset(grant["allowed_fields"]))
        result = SourceHealthRecord(**value)
        _valid_record(result)
        return result
    except (KeyError, TypeError, ValueError, AttributeError):
        raise Hold("SOURCE_HEALTH_STORAGE_CONTRACT") from None

class SourceHealthStore:
    def __init__(self, ledger):
        self.ledger = ledger

    def read(self, tenant: str, source_id: str) -> SourceHealthRecord:
        if source_id not in {item["id"] for item in SOURCE_CATALOG}:
            raise Hold("UNKNOWN_SOURCE")
        with self.ledger.transaction(tenant) as cursor:
            cursor.execute("SELECT record FROM source_health WHERE tenant=%s AND source_id=%s", (tenant, source_id))
            row = cursor.fetchone()
            return _decode(row[0]) if row else SourceHealthRecord(source_id)

    def record_attempt(self, tenant: str, attempt: SourceHealthRecord) -> SourceHealthRecord:
        if attempt.source_id not in {item["id"] for item in SOURCE_CATALOG}:
            raise Hold("UNKNOWN_SOURCE")
        _valid_record(attempt)
        initial = SourceHealthRecord(attempt.source_id)
        with self.ledger.transaction(tenant) as cursor:
            cursor.execute("INSERT INTO source_health(tenant,source_id,revision,record) VALUES(%s,%s,0,%s::jsonb) ON CONFLICT(tenant,source_id) DO NOTHING",
                           (tenant, attempt.source_id, _encode(initial)))
            cursor.execute("SELECT record FROM source_health WHERE tenant=%s AND source_id=%s FOR UPDATE", (tenant, attempt.source_id))
            row = cursor.fetchone()
            if row is None:
                raise Hold("SOURCE_HEALTH_STORAGE_CONTRACT")
            updated = record_source_attempt(_decode(row[0]), attempt)
            cursor.execute("UPDATE source_health SET record=%s::jsonb,revision=revision+1 WHERE tenant=%s AND source_id=%s",
                           (_encode(updated), tenant, attempt.source_id))
            return updated
