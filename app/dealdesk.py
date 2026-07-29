# SPDX-License-Identifier: Apache-2.0
"""Evidence-backed broker workflow for entity-level public B2B records.

Public records create research tasks. They never create contact permission.
Every call-ready packet is bound to a business-published channel, current
suppression checks, an identified operator, a jurisdiction, and an expiry.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

if os.name == "nt":
    import msvcrt
else:  # pragma: no cover - exercised by Linux production and CI
    import fcntl

try:  # Optional locally; required when DAVID_DATABASE_URL is configured.
    import psycopg
except Exception:  # pragma: no cover - exercised in the production image
    psycopg = None


STAGES = (
    "REVIEW",
    "RESEARCH",
    "READY",
    "CONTACTED",
    "MEETING",
    "PROPOSAL",
    "WON",
    "LOST",
    "BLOCKED",
)
TRANSITIONS = {
    "REVIEW": {"RESEARCH", "BLOCKED"},
    "RESEARCH": {"READY", "BLOCKED"},
    "READY": {"CONTACTED", "RESEARCH", "BLOCKED"},
    "CONTACTED": {"MEETING", "READY", "LOST", "BLOCKED"},
    "MEETING": {"PROPOSAL", "LOST", "BLOCKED"},
    "PROPOSAL": {"WON", "LOST", "BLOCKED"},
    "WON": set(),
    "LOST": {"RESEARCH"},
    "BLOCKED": {"RESEARCH"},
}
CONTACT_STAGES = {"READY", "CONTACTED", "MEETING", "PROPOSAL", "WON"}
ALLOWED_CHANNEL_TYPES = {"BUSINESS_PHONE", "BUSINESS_EMAIL", "WEBSITE", "WEBSITE_FORM"}
ALLOWED_PUBLISHER_CLASS = "FIRST_PARTY_BUSINESS_WEBSITE"
DISPOSITIONS = {
    "NO_ANSWER",
    "LEFT_VOICEMAIL",
    "CONNECTED",
    "MEETING_BOOKED",
    "NOT_INTERESTED",
    "FOLLOW_UP",
    "DO_NOT_CALL",
    "WRONG_BUSINESS",
}
_SOCIAL_HOSTS = {
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
}
_FREE_MAIL = {
    "aol.com",
    "gmail.com",
    "hotmail.com",
    "icloud.com",
    "outlook.com",
    "proton.me",
    "protonmail.com",
    "yahoo.com",
}
_PATH = os.environ.get("DAVID_DEAL_DESK_PATH")
_DATABASE_URL = os.environ.get("DAVID_DATABASE_URL")
_STATE: dict[str, dict[str, Any]] = {}
_KNOWN: dict[str, dict[str, Any]] = {}
_SCHEMA_VERSION = 2
_SUBJECT_IDENTIFIER_KEYS = {
    "license_number": "license_number",
    "usdot_number": "usdot",
    "uei": "uei",
    "cage_code": "cage",
    "entity_number": "entity_number",
}
_AUTHORITATIVE_IDENTIFIER_SYSTEMS = {
    "cage": "cage",
    "cage code": "cage",
    "chicago business license": "chicago_license",
    "chicago license number": "chicago_license",
    "epa frs": "epa_frs",
    "epa_frs": "epa_frs",
    "entity_number": "entity_number",
    "frs": "epa_frs",
    "license_number": "license_number",
    "sam uei": "uei",
    "uei": "uei",
    "usdot": "usdot",
}
_SCHEMA_COLUMNS = {
    ("david_dealdesk_schema", "schema_name"): ("text", "NO"),
    ("david_dealdesk_schema", "schema_version"): ("int4", "NO"),
    ("david_dealdesk_schema", "applied_at"): ("timestamptz", "NO"),
    ("david_dealdesk_state", "opportunity_id"): ("text", "NO"),
    ("david_dealdesk_state", "payload"): ("jsonb", "NO"),
    ("david_dealdesk_state", "version"): ("int8", "NO"),
    ("david_dealdesk_state", "updated_at"): ("timestamptz", "NO"),
    ("david_dealdesk_events", "event_id"): ("text", "NO"),
    ("david_dealdesk_events", "opportunity_id"): ("text", "NO"),
    ("david_dealdesk_events", "event_type"): ("text", "NO"),
    ("david_dealdesk_events", "actor"): ("text", "NO"),
    ("david_dealdesk_events", "payload"): ("jsonb", "NO"),
    ("david_dealdesk_events", "created_at"): ("timestamptz", "NO"),
}
_SCHEMA_PRIMARY_KEYS = {
    "david_dealdesk_schema": ("schema_name",),
    "david_dealdesk_state": ("opportunity_id",),
    "david_dealdesk_events": ("event_id",),
}
_SCHEMA_CONSTRAINTS = {
    (
        "david_dealdesk_schema",
        "c",
        "CHECK (schema_version > 0)",
    ),
    (
        "david_dealdesk_schema",
        "p",
        "PRIMARY KEY (schema_name)",
    ),
    (
        "david_dealdesk_state",
        "c",
        "CHECK (version > 0)",
    ),
    (
        "david_dealdesk_state",
        "p",
        "PRIMARY KEY (opportunity_id)",
    ),
    (
        "david_dealdesk_events",
        "p",
        "PRIMARY KEY (event_id)",
    ),
}
_SCHEMA_EVENTS_INDEX = (
    True,
    True,
    False,
    True,
    True,
    2,
    2,
    "btree",
    "opportunity_id",
    "created_at",
)
_PERSISTENCE_LOCK = threading.Lock()
_LAST_PROBE_AT = 0.0
_READY_PROBE_INTERVAL_SECONDS = 10.0
_FAILED_PROBE_INTERVAL_SECONDS = 3.0
_PERSISTENCE_DIAGNOSTIC = "NOT_CONFIGURED"
_PERSISTENCE_HEALTH = (
    "POSTGRES_CONFIGURED"
    if _DATABASE_URL
    else "FILE_CONFIGURED"
    if (_PATH and os.path.isabs(_PATH))
    else "NOT_CONFIGURED"
)


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def persistence_configured() -> bool:
    return bool(_DATABASE_URL or (_PATH and os.path.isabs(_PATH)))


def persistence_state() -> str:
    if _DATABASE_URL:
        _refresh_postgres_health()
        return _PERSISTENCE_HEALTH
    if _PATH and os.path.isabs(_PATH):
        _refresh_file_health()
        return _PERSISTENCE_HEALTH
    return "NOT_CONFIGURED"


def persistence_ready() -> bool:
    return persistence_state() in {"FILE_READY", "POSTGRES_READY"}


def persistence_diagnostic() -> str:
    """Return a non-secret operational diagnostic suitable for health probes."""
    persistence_state()
    return _PERSISTENCE_DIAGNOSTIC


def _now() -> str:
    return _now_dt().isoformat()


def _clean(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _event_id(event: dict[str, Any]) -> str:
    raw = json.dumps(event, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "evt_" + hashlib.sha256(raw).hexdigest()[:24]


def opportunity_id(record: dict[str, Any]) -> str:
    identity = {
        "name": (record.get("name") or "").strip().lower(),
        "state": (record.get("state") or "").strip().upper(),
        "zip": (record.get("zip") or "").strip(),
        "date": (record.get("license_or_issue_date") or "").strip(),
        "source": ((record.get("citation") or {}).get("url") or "").strip(),
    }
    raw = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "opp_" + hashlib.sha256(raw).hexdigest()[:16]


def _official_identifiers(record: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """Normalize only identifier systems emitted by governed source producers."""
    identifiers = [
        (system, _clean(record.get(key), 160))
        for key, system in _SUBJECT_IDENTIFIER_KEYS.items()
        if _clean(record.get(key), 160)
    ]
    emitted = record.get("authoritative_entity_ids")
    if isinstance(emitted, list):
        for item in emitted:
            if not isinstance(item, dict):
                continue
            system = _AUTHORITATIVE_IDENTIFIER_SYSTEMS.get(
                _clean(item.get("system"), 80).lower()
            )
            value = _clean(item.get("value"), 160)
            if system and value:
                identifiers.append((system, value))
    credential = _clean(record.get("credential"), 200)
    match = re.fullmatch(r"(USDOT|UEI|CAGE|FRS)\s+(.+)", credential, re.IGNORECASE)
    if match:
        system = _AUTHORITATIVE_IDENTIFIER_SYSTEMS[match.group(1).lower()]
        identifiers.append((system, _clean(match.group(2), 160)))
    return tuple(
        dict.fromkeys(
            (system, value.lower())
            for system, value in identifiers
            if value
        )
    )


def _subject_alias(identity: dict[str, str]) -> str:
    raw = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "subj_" + hashlib.sha256(raw).hexdigest()[:24]


def subject_ids(record: dict[str, Any]) -> tuple[str, ...]:
    """Stable business aliases used for irreversible contact suppression."""
    identities = [
        {"official": f"{system}:{value}"}
        for system, value in _official_identifiers(record)
    ]
    name = _clean(record.get("name"), 240).lower()
    state = _clean(record.get("state"), 16).upper()
    if name:
        identities.append({"name": name, "state": state})
    # Public source records must not be able to select another opportunity's
    # suppression alias by supplying an `opportunity_id` field. Always derive
    # the fallback scope from the governed opportunity contract.
    identities = identities or [{"opportunity": opportunity_id(record)}]
    return tuple(dict.fromkeys(_subject_alias(identity) for identity in identities))


def subject_id(record: dict[str, Any]) -> str:
    """Primary stable identity; volatile trigger dates and URLs are excluded."""
    return subject_ids(record)[0]


def _subject_identity(record: dict[str, Any]) -> dict[str, Any] | None:
    """Return the bounded identity fields required for durable suppression."""
    identity: dict[str, Any] = {}
    official = _official_identifiers(record)
    if official:
        identity["authoritative_entity_ids"] = [
            {"system": system, "value": value}
            for system, value in official
        ]
    name = _clean(record.get("name"), 240)
    if name:
        identity["name"] = name
        identity["state"] = _clean(record.get("state"), 16).upper()
    scoped_opportunity = _clean(record.get("opportunity_id"), 160)
    if not identity and scoped_opportunity:
        identity["opportunity_id"] = scoped_opportunity
    return identity or None


def _backfill_legacy_suppressions(
    state: dict[str, dict[str, Any]],
    known_records: dict[str, dict[str, Any]] | None = None,
) -> bool:
    """Upgrade legacy DNC rows only when a real business identity is available."""
    changed = False
    known_records = known_records or {}
    for oid, saved in state.items():
        if not isinstance(saved, dict) or saved.get("last_disposition") != "DO_NOT_CALL":
            continue
        suppression = saved.get("suppression")
        identity = saved.get("subject_identity")
        if not isinstance(identity, dict):
            identity = _subject_identity(known_records.get(oid) or saved)
        else:
            identity = _subject_identity(identity)
        if not identity:
            # Older payloads did not retain source identity. Never manufacture
            # one empty alias shared by every legacy DNC row; backfill when the
            # exact source opportunity is observed again.
            continue
        if identity.get("opportunity_id"):
            aliases = (
                _subject_alias(
                    {"opportunity": _clean(identity["opportunity_id"], 160)}
                ),
            )
        else:
            aliases = subject_ids(identity)
        if isinstance(suppression, dict) and suppression.get("active") is True:
            normalized = {
                **suppression,
                "subject_id": aliases[0],
                "subject_ids": list(aliases),
            }
            if (
                normalized != suppression
                or saved.get("subject_identity") != identity
            ):
                saved["stage"] = "BLOCKED"
                saved["next_action"] = "Suppressed: do not contact"
                saved["subject_identity"] = identity
                saved["suppression"] = normalized
                changed = True
            continue
        clearance = saved.get("clearance")
        revoked_at = (
            clearance.get("revoked_at")
            if isinstance(clearance, dict)
            else None
        )
        saved["stage"] = "BLOCKED"
        saved["next_action"] = "Suppressed: do not contact"
        saved["subject_identity"] = identity
        saved["suppression"] = {
            "subject_id": aliases[0],
            "subject_ids": list(aliases),
            "type": "DO_NOT_CALL",
            "active": True,
            "recorded_at": revoked_at or "UNAVAILABLE",
            "actor": "legacy-persistence-backfill",
        }
        changed = True
    return changed


def _legacy_unnamed_subject_id(record: dict[str, Any]) -> str | None:
    """Return the pre-scoping alias only for an exact unnamed opportunity."""
    if _clean(record.get("name"), 240) or _official_identifiers(record):
        return None
    identity = {
        "name": "",
        "state": _clean(record.get("state"), 16).upper(),
    }
    raw = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "subj_" + hashlib.sha256(raw).hexdigest()[:24]


def _backfill_legacy_suppression(record: dict[str, Any]) -> bool:
    """Persist an idempotent, auditable suppression for an observed legacy row."""
    oid = opportunity_id(record)
    saved = _STATE.get(oid)
    if not isinstance(saved, dict):
        return False
    suppression = saved.get("suppression")
    is_active = (
        isinstance(suppression, dict)
        and suppression.get("active") is True
    )
    if saved.get("last_disposition") != "DO_NOT_CALL" and not is_active:
        return False

    existing_ids: list[str] = []
    if isinstance(suppression, dict):
        existing_ids.extend(
            str(item)
            for item in suppression.get("subject_ids") or ()
            if item
        )
        if suppression.get("subject_id"):
            existing_ids.append(str(suppression["subject_id"]))
    aliases = tuple(dict.fromkeys((*existing_ids, *subject_ids(record))))
    identity = _subject_identity(record)
    clearance = saved.get("clearance")
    if isinstance(clearance, dict) and not clearance.get("revoked_at"):
        clearance = {**clearance, "revoked_at": _now()}

    normalized_suppression = {
        **(suppression if isinstance(suppression, dict) else {}),
        "subject_id": aliases[0],
        "subject_ids": list(aliases),
        "type": "DO_NOT_CALL",
        "active": True,
        "recorded_at": (
            suppression.get("recorded_at")
            if isinstance(suppression, dict) and suppression.get("recorded_at")
            else saved.get("updated_at") or "UNAVAILABLE"
        ),
        "actor": (
            suppression.get("actor")
            if isinstance(suppression, dict) and suppression.get("actor")
            else "legacy-persistence-backfill"
        ),
    }
    candidate = {
        **saved,
        "stage": "BLOCKED",
        "next_action": "Suppressed: do not contact",
        "suppression": normalized_suppression,
    }
    if identity:
        candidate["subject_identity"] = identity
    if isinstance(clearance, dict):
        candidate["clearance"] = clearance
    if candidate == saved:
        return False

    _commit(
        oid,
        candidate,
        {
            "at": _now(),
            "opportunity_id": oid,
            "type": "LEGACY_DO_NOT_CALL_BACKFILLED",
            "actor": "system",
        },
    )
    return True


def _active_suppression(record: dict[str, Any]) -> dict[str, Any] | None:
    stable_ids = set(subject_ids(record))
    current_opportunity_id = opportunity_id(record)
    legacy_id = _legacy_unnamed_subject_id(record)
    for saved_opportunity_id, saved in _STATE.items():
        suppression = saved.get("suppression")
        if not isinstance(suppression, dict) or suppression.get("active") is not True:
            if (
                saved_opportunity_id == current_opportunity_id
                and saved.get("last_disposition") == "DO_NOT_CALL"
            ):
                aliases = subject_ids(record)
                return {
                    "subject_id": aliases[0],
                    "subject_ids": list(aliases),
                    "type": "DO_NOT_CALL",
                    "active": True,
                    "recorded_at": saved.get("updated_at") or "UNAVAILABLE",
                    "actor": "legacy-persistence-backfill",
                }
            continue
        suppressed_ids = set(suppression.get("subject_ids") or ())
        if suppression.get("subject_id"):
            suppressed_ids.add(str(suppression["subject_id"]))
        if stable_ids.intersection(suppressed_ids):
            return suppression
        if (
            legacy_id
            and saved_opportunity_id == current_opportunity_id
            and legacy_id in suppressed_ids
        ):
            return suppression
    return None


def _db_connect():
    if not _DATABASE_URL:
        raise RuntimeError("database persistence is not configured")
    if psycopg is None:
        raise RuntimeError("psycopg is required when DAVID_DATABASE_URL is configured")
    return psycopg.connect(_DATABASE_URL, connect_timeout=4)


class PersistenceUnavailable(RuntimeError):
    """Sanitized persistence failure safe to return without connection details."""


class _DatabaseSchemaUnavailable(RuntimeError):
    pass


class _DatabaseSchemaIncompatible(RuntimeError):
    pass


class _LegacySuppressionIdentityRequired(RuntimeError):
    pass


def _assert_no_unresolved_legacy_suppressions(
    state: dict[str, dict[str, Any]],
) -> None:
    for saved in state.values():
        if not isinstance(saved, dict) or saved.get("last_disposition") != "DO_NOT_CALL":
            continue
        suppression = saved.get("suppression")
        identity = saved.get("subject_identity")
        if (
            isinstance(suppression, dict)
            and suppression.get("active") is True
            and isinstance(identity, dict)
            and _subject_identity(identity)
        ):
            continue
        raise _LegacySuppressionIdentityRequired(
            "legacy do-not-call identity requires governed backfill"
        )


def _assert_schema_contract(cursor: Any) -> None:
    cursor.execute(
        "SELECT schema_version FROM david_dealdesk_schema WHERE schema_name = %s",
        ("dealdesk",),
    )
    row = cursor.fetchone()
    if row != (_SCHEMA_VERSION,):
        raise _DatabaseSchemaIncompatible(
            "unsupported deal-desk schema version"
        )
    cursor.execute(
        """
        SELECT table_name, column_name, udt_name, is_nullable
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name IN (%s, %s, %s)
        ORDER BY table_name, ordinal_position
        """,
        tuple(sorted(_SCHEMA_PRIMARY_KEYS)),
    )
    observed_columns = {
        (str(table), str(column)): (str(data_type), str(nullable))
        for table, column, data_type, nullable in cursor.fetchall()
    }
    if set(_SCHEMA_PRIMARY_KEYS) - {
        table for table, _column in observed_columns
    }:
        raise _DatabaseSchemaUnavailable(
            "database schema is missing required service tables"
        )
    if observed_columns != _SCHEMA_COLUMNS:
        raise _DatabaseSchemaIncompatible(
            "database schema columns are incompatible with this service"
        )

    cursor.execute(
        """
        SELECT
            table_relation.relname,
            table_attribute.attname,
            key_column.ordinality
        FROM pg_catalog.pg_index AS index_meta
        JOIN pg_catalog.pg_class AS table_relation
          ON table_relation.oid = index_meta.indrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = table_relation.relnamespace
        JOIN LATERAL unnest(index_meta.indkey)
          WITH ORDINALITY AS key_column(attribute_number, ordinality)
          ON true
        JOIN pg_catalog.pg_attribute AS table_attribute
          ON table_attribute.attrelid = table_relation.oid
         AND table_attribute.attnum = key_column.attribute_number
        WHERE namespace.nspname = current_schema()
          AND index_meta.indisprimary
          AND table_relation.relname IN (%s, %s, %s)
        ORDER BY table_relation.relname, key_column.ordinality
        """,
        tuple(sorted(_SCHEMA_PRIMARY_KEYS)),
    )
    observed_primary_keys: dict[str, list[tuple[int, str]]] = {}
    for table, column, position in cursor.fetchall():
        observed_primary_keys.setdefault(str(table), []).append(
            (int(position), str(column))
        )
    normalized_primary_keys = {
        table: tuple(column for _position, column in sorted(columns))
        for table, columns in observed_primary_keys.items()
    }
    if normalized_primary_keys != _SCHEMA_PRIMARY_KEYS:
        raise _DatabaseSchemaIncompatible(
            "database schema primary keys are incompatible with this service"
        )

    cursor.execute(
        """
        SELECT
            table_relation.relname,
            constraint_meta.contype,
            pg_get_constraintdef(constraint_meta.oid, true)
        FROM pg_catalog.pg_constraint AS constraint_meta
        JOIN pg_catalog.pg_class AS table_relation
          ON table_relation.oid = constraint_meta.conrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = table_relation.relnamespace
        WHERE namespace.nspname = current_schema()
          AND table_relation.relname IN (%s, %s, %s)
        ORDER BY table_relation.relname, constraint_meta.contype,
                 constraint_meta.conname
        """,
        tuple(sorted(_SCHEMA_PRIMARY_KEYS)),
    )
    observed_constraints = {
        (str(table), str(constraint_type), str(definition))
        for table, constraint_type, definition in cursor.fetchall()
    }
    if observed_constraints != _SCHEMA_CONSTRAINTS:
        raise _DatabaseSchemaIncompatible(
            "database schema constraints are incompatible with this service"
        )

    cursor.execute(
        """
        SELECT
            index_meta.indisvalid,
            index_meta.indisready,
            index_meta.indisunique,
            index_meta.indpred IS NULL,
            index_meta.indexprs IS NULL,
            index_meta.indnkeyatts,
            index_meta.indnatts,
            access_method.amname,
            pg_get_indexdef(index_meta.indexrelid, 1, true),
            pg_get_indexdef(index_meta.indexrelid, 2, true)
        FROM pg_catalog.pg_index AS index_meta
        JOIN pg_catalog.pg_class AS index_relation
          ON index_relation.oid = index_meta.indexrelid
        JOIN pg_catalog.pg_class AS table_relation
          ON table_relation.oid = index_meta.indrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = table_relation.relnamespace
        JOIN pg_catalog.pg_am AS access_method
          ON access_method.oid = index_relation.relam
        WHERE namespace.nspname = current_schema()
          AND table_relation.relname = %s
          AND index_relation.relname = %s
        """,
        (
            "david_dealdesk_events",
            "david_dealdesk_events_opportunity_created_idx",
        ),
    )
    index_rows = list(cursor.fetchall())
    if not index_rows:
        raise _DatabaseSchemaUnavailable(
            "database schema is missing the required events index"
        )
    if len(index_rows) != 1 or tuple(index_rows[0]) != _SCHEMA_EVENTS_INDEX:
        raise _DatabaseSchemaIncompatible(
            "database events index is incompatible with this service"
        )


def _database_snapshot() -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    with _db_connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '4000ms'")
            _assert_schema_contract(cursor)
            cursor.execute("SELECT opportunity_id, payload FROM david_dealdesk_state")
            for oid, payload in cursor.fetchall():
                if isinstance(payload, str):
                    payload = json.loads(payload)
                if isinstance(payload, dict):
                    loaded[str(oid)] = payload
    return loaded


def _mark_postgres_unavailable(
    *,
    error: Exception | None = None,
    retry_immediately: bool = False,
) -> None:
    global _LAST_PROBE_AT, _PERSISTENCE_DIAGNOSTIC, _PERSISTENCE_HEALTH
    _PERSISTENCE_HEALTH = "POSTGRES_UNAVAILABLE"
    _PERSISTENCE_DIAGNOSTIC = (
        _classify_database_error(error) if error is not None else "CONNECTION_UNAVAILABLE"
    )
    _LAST_PROBE_AT = 0.0 if retry_immediately else time.monotonic()


def _refresh_postgres_health(*, force: bool = False) -> None:
    global _LAST_PROBE_AT, _PERSISTENCE_DIAGNOSTIC, _PERSISTENCE_HEALTH
    now = time.monotonic()
    interval = (
        _READY_PROBE_INTERVAL_SECONDS
        if _PERSISTENCE_HEALTH == "POSTGRES_READY"
        else _FAILED_PROBE_INTERVAL_SECONDS
    )
    if not force and _LAST_PROBE_AT and now - _LAST_PROBE_AT < interval:
        return
    if not _PERSISTENCE_LOCK.acquire(blocking=False):
        return
    try:
        now = time.monotonic()
        if not force and _LAST_PROBE_AT and now - _LAST_PROBE_AT < interval:
            return
        try:
            if _PERSISTENCE_HEALTH == "POSTGRES_READY":
                with _db_connect() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL statement_timeout = '4000ms'")
                        _assert_schema_contract(cursor)
            else:
                recovered = _database_snapshot()
                backfilled = _backfill_legacy_suppressions(recovered)
                _assert_no_unresolved_legacy_suppressions(recovered)
                if backfilled:
                    _persist(recovered)
                _STATE.clear()
                _STATE.update(recovered)
            _PERSISTENCE_HEALTH = "POSTGRES_READY"
            _PERSISTENCE_DIAGNOSTIC = "OK"
            _LAST_PROBE_AT = time.monotonic()
        except Exception as exc:
            _mark_postgres_unavailable(error=exc)
    finally:
        _PERSISTENCE_LOCK.release()


def _probe_file_store() -> dict[str, dict[str, Any]]:
    if not _PATH or not os.path.isabs(_PATH):
        raise PersistenceUnavailable("file persistence is not configured")
    directory = os.path.dirname(_PATH)
    if not os.path.isdir(directory) or (os.path.exists(_PATH) and not os.path.isfile(_PATH)):
        raise PersistenceUnavailable("file persistence path is unavailable")
    with _file_store_lock():
        original = b"{}"
        if os.path.exists(_PATH):
            with open(_PATH, "rb") as handle:
                original = handle.read()
        persisted = json.loads(original)
        if not isinstance(persisted, dict):
            raise PersistenceUnavailable("file persistence payload is invalid")
        fd, temporary = tempfile.mkstemp(
            prefix="dealdesk-probe-",
            suffix=".tmp",
            dir=directory,
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(original)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, _PATH)
            with open(_PATH, "rb") as handle:
                if handle.read() != original:
                    raise PersistenceUnavailable("file persistence probe is invalid")
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return {
        str(key): value
        for key, value in persisted.items()
        if isinstance(value, dict)
    }


@contextmanager
def _file_store_lock():
    if not _PATH:
        raise PersistenceUnavailable("file persistence is not configured")
    lock_path = _PATH + ".lock"
    deadline = time.monotonic() + 2.0
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    while not acquired:
        try:
            if os.name == "nt":
                if os.fstat(descriptor).st_size == 0:
                    os.write(descriptor, b"\0")
                    os.fsync(descriptor)
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:  # pragma: no cover - exercised by Linux production and CI
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError:
            if time.monotonic() >= deadline:
                os.close(descriptor)
                raise PersistenceUnavailable("file persistence lock is unavailable") from None
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            if os.name == "nt":
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:  # pragma: no cover - exercised by Linux production and CI
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _refresh_file_health() -> None:
    global _PERSISTENCE_DIAGNOSTIC, _PERSISTENCE_HEALTH
    try:
        loaded = _probe_file_store()
        backfilled = _backfill_legacy_suppressions(loaded)
        _assert_no_unresolved_legacy_suppressions(loaded)
        if backfilled:
            _persist(loaded)
        _STATE.clear()
        _STATE.update(loaded)
        _PERSISTENCE_HEALTH = "FILE_READY"
        _PERSISTENCE_DIAGNOSTIC = "OK"
    except _LegacySuppressionIdentityRequired:
        _PERSISTENCE_HEALTH = "FILE_UNAVAILABLE"
        _PERSISTENCE_DIAGNOSTIC = "LEGACY_DNC_IDENTITY_REQUIRED"
    except Exception:
        _PERSISTENCE_HEALTH = "FILE_UNAVAILABLE"
        _PERSISTENCE_DIAGNOSTIC = "FILE_UNAVAILABLE"


def _classify_database_error(exc: Exception) -> str:
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    if isinstance(exc, _DatabaseSchemaUnavailable):
        return "SCHEMA_UNAVAILABLE"
    if isinstance(exc, _DatabaseSchemaIncompatible):
        return "SCHEMA_INCOMPATIBLE"
    if isinstance(exc, _LegacySuppressionIdentityRequired):
        return "LEGACY_DNC_IDENTITY_REQUIRED"
    if psycopg is None or "psycopg is required" in message:
        return "DRIVER_UNAVAILABLE"
    if "does not exist" in message or "undefinedtable" in name:
        return "SCHEMA_UNAVAILABLE"
    if (
        "undefinedcolumn" in name
        or "datatypemismatch" in name
        or "no unique or exclusion constraint" in message
    ):
        return "SCHEMA_INCOMPATIBLE"
    if "password authentication failed" in message or "invalidpassword" in name:
        return "AUTHENTICATION_FAILED"
    if "name or service not known" in message or "could not translate host" in message:
        return "DNS_UNAVAILABLE"
    if "timeout" in name or "timeout" in message:
        return "CONNECTION_TIMEOUT"
    return "CONNECTION_UNAVAILABLE"


def _load() -> None:
    global _LAST_PROBE_AT, _PERSISTENCE_DIAGNOSTIC, _PERSISTENCE_HEALTH
    if _DATABASE_URL:
        last_error = None
        for attempt in range(3):
            try:
                loaded = _database_snapshot()
                backfilled = _backfill_legacy_suppressions(loaded)
                _assert_no_unresolved_legacy_suppressions(loaded)
                _STATE.clear()
                _STATE.update(loaded)
                if backfilled:
                    _persist(_STATE)
                _PERSISTENCE_HEALTH = "POSTGRES_READY"
                _PERSISTENCE_DIAGNOSTIC = "OK"
                _LAST_PROBE_AT = time.monotonic()
                return
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.25 * (attempt + 1))
        _STATE.clear()
        _mark_postgres_unavailable(error=last_error, retry_immediately=True)
        return
    if not _PATH or not os.path.isabs(_PATH):
        return
    try:
        loaded = _probe_file_store()
        _STATE.clear()
        _STATE.update(loaded)
        if _backfill_legacy_suppressions(_STATE):
            _persist(_STATE)
        _assert_no_unresolved_legacy_suppressions(_STATE)
        _PERSISTENCE_HEALTH = "FILE_READY"
        _PERSISTENCE_DIAGNOSTIC = "OK"
    except _LegacySuppressionIdentityRequired:
        _STATE.clear()
        _PERSISTENCE_HEALTH = "FILE_UNAVAILABLE"
        _PERSISTENCE_DIAGNOSTIC = "LEGACY_DNC_IDENTITY_REQUIRED"
    except Exception:
        _STATE.clear()
        _PERSISTENCE_HEALTH = "FILE_UNAVAILABLE"
        _PERSISTENCE_DIAGNOSTIC = "FILE_UNAVAILABLE"


def _persist(
    state: dict[str, dict[str, Any]] | None = None,
    event: dict[str, Any] | None = None,
) -> None:
    global _PERSISTENCE_DIAGNOSTIC, _PERSISTENCE_HEALTH
    snapshot = _STATE if state is None else state
    _assert_no_unresolved_legacy_suppressions(snapshot)
    if _DATABASE_URL:
        try:
            with _db_connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL statement_timeout = '4000ms'")
                    _assert_schema_contract(cursor)
                    for oid, payload in snapshot.items():
                        cursor.execute(
                            """
                            INSERT INTO david_dealdesk_state
                                (opportunity_id, payload, version, updated_at)
                            VALUES (%s, %s::jsonb, 1, now())
                            ON CONFLICT (opportunity_id) DO UPDATE SET
                                payload = EXCLUDED.payload,
                                version = david_dealdesk_state.version + 1,
                                updated_at = now()
                            """,
                            (oid, json.dumps(payload, sort_keys=True)),
                        )
                    if event:
                        cursor.execute(
                            """
                            INSERT INTO david_dealdesk_events
                                (event_id, opportunity_id, event_type, actor, payload, created_at)
                            VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                            ON CONFLICT (event_id) DO NOTHING
                            """,
                            (
                                event["event_id"],
                                event["opportunity_id"],
                                event["type"],
                                event.get("actor") or "unknown",
                                json.dumps(event, sort_keys=True),
                                event["at"],
                            ),
                        )
            _PERSISTENCE_HEALTH = "POSTGRES_READY"
            _PERSISTENCE_DIAGNOSTIC = "OK"
        except Exception as exc:
            _mark_postgres_unavailable(error=exc)
            raise PersistenceUnavailable("deal-desk persistence is unavailable") from None
        return
    if not _PATH:
        return
    directory = os.path.dirname(os.path.abspath(_PATH))
    try:
        with _file_store_lock():
            fd, temporary = tempfile.mkstemp(
                prefix="dealdesk-",
                suffix=".json",
                dir=directory,
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(snapshot, handle, indent=2, sort_keys=True)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, _PATH)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        _PERSISTENCE_HEALTH = "FILE_READY"
        _PERSISTENCE_DIAGNOSTIC = "OK"
    except Exception:
        _PERSISTENCE_HEALTH = "FILE_UNAVAILABLE"
        _PERSISTENCE_DIAGNOSTIC = "FILE_UNAVAILABLE"
        raise PersistenceUnavailable("deal-desk persistence is unavailable") from None


_load()


def _priority(record: dict[str, Any]) -> int:
    """Evidence-completeness priority, never an underwriting or conversion score."""
    score = 15
    if record.get("contact_quality") == "business address (public)":
        score += 10
    observed = record.get("license_or_issue_date")
    if observed:
        score += 15
        try:
            age_days = max(
                0,
                (_now_dt().date() - datetime.fromisoformat(str(observed)[:10]).date()).days,
            )
            score += max(0, 10 - min(age_days, 180) // 18)
        except ValueError:
            pass
    if (record.get("citation") or {}).get("url"):
        score += 20
    if record.get("receipt_id"):
        score += 15
    if record.get("type") in {"business", "licensee", "carrier", "federal_award", "facility"}:
        score += 5
    if record.get("contact_quality") != "[SAMPLE]":
        score += 10
    return min(score, 100)


def _default_gate(record: dict[str, Any]) -> tuple[str, list[str]]:
    quality = record.get("contact_quality")
    if quality == "[SAMPLE]" or str(record.get("name", "")).startswith("[SAMPLE]"):
        return "DO_NOT_CONTACT_SAMPLE", ["Sample records are demonstration-only."]
    if quality == "entity id only":
        return "BLOCKED_NO_BUSINESS_CHANNEL", [
            "Verify a named business and official business contact channel first."
        ]
    return "RESEARCH_REQUIRED", [
        "Verify the current official record.",
        "Record a channel published on the business's own HTTPS website.",
        "Check internal, federal, and applicable state suppression rules.",
        "Record a time-limited outreach clearance before contact.",
    ]


def _contact_gate(record: dict[str, Any]) -> tuple[str, list[str]]:
    if _active_suppression(record):
        return "DO_NOT_CONTACT_SUPPRESSED", [
            "A prior do-not-call request permanently suppresses this business identity."
        ]
    return _default_gate(record)


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _current_clearance(saved: dict[str, Any]) -> dict[str, Any] | None:
    clearance = saved.get("clearance")
    if not isinstance(clearance, dict) or clearance.get("revoked_at"):
        return None
    expiry = _parse_time(clearance.get("expires_at"))
    channel_id = clearance.get("channel_id")
    channels = saved.get("channels") or []
    if (
        expiry is None
        or expiry <= _now_dt()
        or not any(item.get("channel_id") == channel_id for item in channels)
    ):
        return None
    required = (
        clearance.get("federal_dnc_checked"),
        clearance.get("state_dnc_checked"),
        clearance.get("opt_out_checked"),
        clearance.get("rules_reviewed"),
    )
    return clearance if all(value is True for value in required) else None


def enrich(record: dict[str, Any]) -> dict[str, Any]:
    oid = opportunity_id(record)
    _KNOWN[oid] = {**record, "opportunity_id": oid}
    if (
        not _backfill_legacy_suppression(record)
        and _backfill_legacy_suppressions(_STATE, {oid: record})
    ):
        _persist(_STATE)
    gate, checklist = _contact_gate(record)
    saved = _STATE.get(oid, {})
    clearance = _current_clearance(saved)
    blocked = gate.startswith(("DO_NOT_CONTACT", "BLOCKED"))
    if blocked and clearance:
        candidate = {
            **saved,
            "clearance": {**clearance, "revoked_at": _now()},
            "stage": "BLOCKED",
            "next_action": "Suppressed: do not contact",
        }
        event = {
            "at": _now(),
            "opportunity_id": oid,
            "type": "DEFAULT_CONTACT_BLOCK_APPLIED",
            "actor": "system",
        }
        _commit(oid, candidate, event)
        saved = candidate
        clearance = None
    call_ready = bool(clearance and saved.get("stage") in CONTACT_STAGES and not blocked)
    if call_ready:
        gate = "TIME_LIMITED_CLEARANCE"
    elif isinstance(saved.get("clearance"), dict) and not blocked:
        gate = "CLEARANCE_EXPIRED_OR_REVOKED"
    stage = saved.get("stage") or ("BLOCKED" if blocked else "REVIEW")
    if gate == "DO_NOT_CONTACT_SUPPRESSED":
        stage = "BLOCKED"
    elif stage in CONTACT_STAGES and not call_ready:
        stage = "RESEARCH"
    next_action = (
        "Suppressed: do not contact"
        if gate == "DO_NOT_CONTACT_SUPPRESSED"
        else saved.get("next_action")
        or record.get("recommended_next_action")
        or (
            "Use for demonstration only"
            if gate.startswith("DO_NOT_CONTACT")
            else "Verify the source and find the official business contact channel"
        )
    )
    return {
        **record,
        "opportunity_id": oid,
        "subject_id": subject_id(record),
        "priority": _priority(record),
        "stage": stage,
        "next_action": next_action,
        "contact_gate": gate,
        "call_ready": call_ready,
        "clearance_checklist": checklist,
        "clearance": clearance,
        "channels": list(saved.get("channels") or []),
        "owner": saved.get("owner") or "Unassigned",
        "last_note": saved.get("last_note") or "",
        "updated_at": saved.get("updated_at"),
        "history": list(saved.get("history") or []),
        "truth_label": "LIVE" if record.get("contact_quality") != "[SAMPLE]" else "EXAMPLE",
    }


def board(records: list[dict[str, Any]]) -> dict[str, Any]:
    opportunities = [enrich(record) for record in records]
    opportunities.sort(
        key=lambda item: (
            item.get("call_ready") is True,
            item.get("priority", 0),
            item.get("license_or_issue_date") or "",
        ),
        reverse=True,
    )
    stage_counts = {stage: 0 for stage in STAGES}
    for item in opportunities:
        stage_counts[item["stage"]] = stage_counts.get(item["stage"], 0) + 1
    return {
        "opportunities": opportunities,
        "summary": {
            "total": len(opportunities),
            "live": sum(1 for item in opportunities if item["truth_label"] == "LIVE"),
            "examples": sum(1 for item in opportunities if item["truth_label"] == "EXAMPLE"),
            "call_ready": sum(1 for item in opportunities if item["call_ready"]),
            "needs_research": sum(1 for item in opportunities if not item["call_ready"]),
            "stage_counts": stage_counts,
        },
        "persistence": persistence_state(),
        "doctrine": (
            "Public B2B records are research signals, not permission to contact. "
            "Only a current evidence-backed clearance unlocks a call sheet."
        ),
    }


def _saved(oid: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if oid not in _KNOWN:
        raise KeyError("unknown opportunity; refresh the opportunity desk first")
    return _KNOWN[oid], dict(_STATE.get(oid) or {})


def _commit(oid: str, candidate: dict[str, Any], event: dict[str, Any]) -> None:
    identity = _subject_identity(_KNOWN.get(oid) or {})
    if identity:
        candidate["subject_identity"] = identity
    event = {**event, "event_id": _event_id(event)}
    history = list(candidate.get("history") or [])
    history.append(event)
    candidate["history"] = history[-100:]
    candidate["updated_at"] = event["at"]
    snapshot = {**_STATE, oid: candidate}
    _persist(snapshot, event)
    _STATE[oid] = candidate


def _channel_value(channel_type: str, value: str) -> str:
    value = _clean(value, 200)
    if channel_type == "BUSINESS_PHONE":
        digits = re.sub(r"\D", "", value)
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        if len(digits) != 10:
            raise ValueError("business phone must contain a 10-digit US number")
        return f"+1{digits}"
    if channel_type == "BUSINESS_EMAIL":
        match = re.fullmatch(r"[^@\s]+@([^@\s]+)", value.lower())
        if not match or match.group(1) in _FREE_MAIL:
            raise ValueError("use a role or business-domain email, not a personal/free-mail address")
        return value.lower()
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("website channels must be valid HTTPS URLs")
    return value


def _source_host(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if parsed.scheme != "https" or not host:
        raise ValueError("source_url must be a valid HTTPS business website")
    if host in _SOCIAL_HOSTS or any(host.endswith("." + social) for social in _SOCIAL_HOSTS):
        raise ValueError("social-profile scraping or copied social contact data is not allowed")
    return host


def record_research(
    oid: str,
    *,
    actor: str,
    channel_type: str,
    channel_value: str,
    source_url: str,
    publisher_class: str,
    note: str = "",
) -> dict[str, Any]:
    record, previous = _saved(oid)
    gate, _ = _contact_gate(record)
    if gate.startswith(("DO_NOT_CONTACT", "BLOCKED")):
        raise ValueError("this record cannot be researched for outreach")
    current_stage = previous.get("stage") or "REVIEW"
    if current_stage != "RESEARCH" and "RESEARCH" not in TRANSITIONS.get(current_stage, set()):
        raise ValueError(f"research cannot reopen the workflow from {current_stage}")
    actor = _clean(actor, 80)
    normalized_type = _clean(channel_type, 30).upper()
    if not actor:
        raise ValueError("actor is required")
    if normalized_type not in ALLOWED_CHANNEL_TYPES:
        raise ValueError(f"channel_type must be one of {sorted(ALLOWED_CHANNEL_TYPES)}")
    if publisher_class != ALLOWED_PUBLISHER_CLASS:
        raise ValueError("only a first-party business website can publish a contact channel")
    source_host = _source_host(source_url)
    normalized_value = _channel_value(normalized_type, channel_value)
    if normalized_type in {"WEBSITE", "WEBSITE_FORM"}:
        channel_host = _source_host(normalized_value)
        if channel_host != source_host and not channel_host.endswith("." + source_host):
            raise ValueError("website channel must belong to the cited business website")
    observed_at = _now()
    identity = f"{oid}|{normalized_type}|{normalized_value}|{source_url}|{observed_at}"
    channel = {
        "channel_id": "chn_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20],
        "type": normalized_type,
        "value": normalized_value,
        "source_url": source_url,
        "source_host": source_host,
        "publisher_class": ALLOWED_PUBLISHER_CLASS,
        "observed_at": observed_at,
        "actor": actor,
        "note": _clean(note, 500),
    }
    channels = list(previous.get("channels") or [])
    channels.append(channel)
    candidate = {
        **previous,
        "stage": "RESEARCH",
        "channels": channels[-20:],
        "clearance": None,
        "last_note": channel["note"],
        "next_action": "Complete suppression checks and record a time-limited clearance",
        "owner": previous.get("owner") or actor,
    }
    event = {
        "at": observed_at,
        "opportunity_id": oid,
        "type": "BUSINESS_CHANNEL_RECORDED",
        "actor": actor,
        "channel_id": channel["channel_id"],
        "source_url": source_url,
    }
    _commit(oid, candidate, event)
    return enrich(record)


def record_clearance(
    oid: str,
    *,
    actor: str,
    channel_id: str,
    business_purpose: str,
    talk_track_version: str,
    broker_jurisdiction: str,
    license_scope: str,
    federal_dnc_checked: bool,
    state_dnc_checked: bool,
    opt_out_checked: bool,
    rules_reviewed: bool,
    expires_hours: int = 24,
) -> dict[str, Any]:
    record, previous = _saved(oid)
    gate, _ = _contact_gate(record)
    if gate.startswith(("DO_NOT_CONTACT", "BLOCKED")):
        raise ValueError("this record cannot be cleared for contact")
    if (previous.get("stage") or "REVIEW") != "RESEARCH":
        raise ValueError("clearance can only be issued from the RESEARCH stage")
    actor = _clean(actor, 80)
    business_purpose = _clean(business_purpose, 240)
    talk_track_version = _clean(talk_track_version, 80)
    jurisdiction = _clean(broker_jurisdiction, 40).upper()
    license_scope = _clean(license_scope, 160)
    channels = list(previous.get("channels") or [])
    channel = next((item for item in channels if item.get("channel_id") == channel_id), None)
    if not channel:
        raise ValueError("clearance must reference a recorded business-published channel")
    if channel.get("type") != "BUSINESS_PHONE":
        raise ValueError("call clearance requires a recorded business phone")
    if not all((actor, business_purpose, talk_track_version, jurisdiction, license_scope)):
        raise ValueError("actor, business purpose, talk track, jurisdiction, and license scope are required")
    checks = (federal_dnc_checked, state_dnc_checked, opt_out_checked, rules_reviewed)
    if not all(value is True for value in checks):
        raise ValueError("every suppression and applicable-rules check must be affirmatively recorded")
    hours = max(1, min(int(expires_hours), 24))
    issued_at = _now_dt()
    clearance_core = {
        "opportunity_id": oid,
        "channel_id": channel_id,
        "actor": actor,
        "business_purpose": business_purpose,
        "talk_track_version": talk_track_version,
        "broker_jurisdiction": jurisdiction,
        "license_scope": license_scope,
        "federal_dnc_checked": True,
        "state_dnc_checked": True,
        "opt_out_checked": True,
        "rules_reviewed": True,
        "issued_at": issued_at.isoformat(),
        "expires_at": (issued_at + timedelta(hours=hours)).isoformat(),
        "revoked_at": None,
    }
    receipt_raw = json.dumps(clearance_core, sort_keys=True, separators=(",", ":")).encode("utf-8")
    clearance = {
        **clearance_core,
        "clearance_receipt": "clr_" + hashlib.sha256(receipt_raw).hexdigest()[:24],
    }
    candidate = {
        **previous,
        "stage": "READY",
        "clearance": clearance,
        "next_action": "Open the governed call sheet and place one manual business call",
        "last_note": f"Time-limited clearance recorded for {jurisdiction}",
        "owner": previous.get("owner") or actor,
    }
    event = {
        "at": issued_at.isoformat(),
        "opportunity_id": oid,
        "type": "OUTREACH_CLEARANCE_RECORDED",
        "actor": actor,
        "clearance_receipt": clearance["clearance_receipt"],
        "channel_id": channel_id,
        "expires_at": clearance["expires_at"],
    }
    _commit(oid, candidate, event)
    return enrich(record)


def update(
    oid: str,
    *,
    stage: str,
    next_action: str | None = None,
    note: str | None = None,
    owner: str | None = None,
    actor: str = "David",
) -> dict[str, Any]:
    record, previous = _saved(oid)
    normalized_stage = _clean(stage, 24).upper()
    if normalized_stage not in STAGES:
        raise ValueError(f"stage must be one of {STAGES}")
    gate, _ = _contact_gate(record)
    if gate.startswith(("DO_NOT_CONTACT", "BLOCKED")) and normalized_stage != "BLOCKED":
        raise ValueError("a suppressed record cannot be reopened for outreach")
    current = previous.get("stage") or "REVIEW"
    if normalized_stage != current and normalized_stage not in TRANSITIONS.get(current, set()):
        raise ValueError(f"invalid transition: {current} -> {normalized_stage}")
    if normalized_stage == "READY":
        raise ValueError("READY can only be entered by recording evidence-backed clearance")
    clearance = _current_clearance(previous)
    if normalized_stage in CONTACT_STAGES and clearance is None:
        raise ValueError("a current evidence-backed outreach clearance is required")
    clean_note = _clean(note, 500)
    clean_action = _clean(next_action, 240)
    clean_owner = _clean(owner, 80)
    candidate = {
        **previous,
        "stage": normalized_stage,
        "next_action": clean_action or previous.get("next_action") or "",
        "last_note": clean_note,
        "owner": clean_owner or previous.get("owner") or "Unassigned",
    }
    if normalized_stage in {"RESEARCH", "BLOCKED", "LOST"}:
        prior_clearance = candidate.get("clearance")
        if isinstance(prior_clearance, dict) and not prior_clearance.get("revoked_at"):
            candidate["clearance"] = {**prior_clearance, "revoked_at": _now()}
    event = {
        "at": _now(),
        "opportunity_id": oid,
        "type": "STAGE_CHANGED",
        "actor": _clean(actor, 80) or "David",
        "from": current,
        "to": normalized_stage,
        "note": clean_note,
    }
    _commit(oid, candidate, event)
    return enrich(record)


def call_sheet(oid: str) -> dict[str, Any]:
    record, saved = _saved(oid)
    opportunity = enrich(record)
    if not opportunity["call_ready"]:
        raise ValueError("call sheet is locked until a current evidence-backed clearance exists")
    clearance = _current_clearance(saved)
    channel = next(
        item for item in saved.get("channels") or []
        if item.get("channel_id") == clearance.get("channel_id")
    )
    if channel.get("type") != "BUSINESS_PHONE":
        raise ValueError("a call sheet requires clearance for a recorded business phone")
    return {
        "opportunity_id": oid,
        "generated_at": _now(),
        "clearance_receipt": clearance["clearance_receipt"],
        "clearance_expires_at": clearance["expires_at"],
        "operator": clearance["actor"],
        "business": {
            "name": record.get("name"),
            "location": ", ".join(
                str(record.get(key) or "") for key in ("city", "state") if record.get(key)
            ),
            "official_signal": record.get("signal_summary") or record.get("why"),
            "source": record.get("citation"),
            "limitations": record.get("limitations") or [],
        },
        "business_channel": channel,
        "purpose": clearance["business_purpose"],
        "license_scope": clearance["license_scope"],
        "jurisdiction": clearance["broker_jurisdiction"],
        "talk_track": {
            "version": clearance["talk_track_version"],
            "opening": (
                f"Hello, this is {clearance['actor']}. I am calling on a manual business basis "
                f"about {clearance['business_purpose']}. Is now an appropriate time?"
            ),
            "discovery_questions": [
                "What changed operationally in the last 90 days?",
                "Which owner, workforce, or continuity risk is most important this quarter?",
                "Who is the appropriate licensed decision-maker for a coverage review?",
            ],
            "prohibited_claims": [
                "Do not imply the public signal proves a coverage gap, violation, or insurability.",
                "Do not quote, bind, advise, or solicit outside the recorded license scope.",
                "Do not use autodialing, prerecorded voice, AI voice, or automated texting.",
            ],
        },
    }


def record_disposition(
    oid: str,
    *,
    actor: str,
    disposition: str,
    note: str = "",
    follow_up_at: str | None = None,
) -> dict[str, Any]:
    record, previous = _saved(oid)
    normalized = _clean(disposition, 40).upper()
    if normalized not in DISPOSITIONS:
        raise ValueError(f"disposition must be one of {sorted(DISPOSITIONS)}")
    if normalized not in {"DO_NOT_CALL", "WRONG_BUSINESS"} and _current_clearance(previous) is None:
        raise ValueError("a current clearance is required to record a contact disposition")
    if (
        normalized not in {"DO_NOT_CALL", "WRONG_BUSINESS"}
        and previous.get("stage") not in {"READY", "CONTACTED"}
    ):
        raise ValueError("contact dispositions can only be recorded from READY or CONTACTED")
    event_at = _now()
    candidate = {
        **previous,
        "last_note": _clean(note, 500),
        "last_disposition": normalized,
        "next_action": _clean(follow_up_at, 80) if follow_up_at else "",
    }
    if normalized == "DO_NOT_CALL":
        candidate["stage"] = "BLOCKED"
        candidate["suppression"] = {
            "subject_id": subject_id(record),
            "subject_ids": list(subject_ids(record)),
            "type": "DO_NOT_CALL",
            "active": True,
            "recorded_at": event_at,
            "actor": _clean(actor, 80) or "David",
        }
        candidate["next_action"] = "Suppressed: do not contact"
    elif normalized == "MEETING_BOOKED":
        candidate["stage"] = "MEETING"
    elif normalized in {"NOT_INTERESTED", "WRONG_BUSINESS"}:
        candidate["stage"] = "LOST"
    elif normalized in {"CONNECTED", "LEFT_VOICEMAIL", "NO_ANSWER", "FOLLOW_UP"}:
        candidate["stage"] = "CONTACTED"
    if normalized in {"DO_NOT_CALL", "NOT_INTERESTED", "WRONG_BUSINESS"}:
        clearance = candidate.get("clearance")
        if isinstance(clearance, dict) and not clearance.get("revoked_at"):
            candidate["clearance"] = {**clearance, "revoked_at": event_at}
    event = {
        "at": event_at,
        "opportunity_id": oid,
        "type": "CONTACT_DISPOSITION_RECORDED",
        "actor": _clean(actor, 80) or "David",
        "disposition": normalized,
        "note": candidate["last_note"],
        "follow_up_at": follow_up_at,
    }
    _commit(oid, candidate, event)
    return enrich(record)


def export_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for oid, record in _KNOWN.items():
        item = enrich(record)
        clearance = item.get("clearance")
        channel = None
        if clearance:
            channel = next(
                (
                    candidate for candidate in item.get("channels") or []
                    if candidate.get("channel_id") == clearance.get("channel_id")
                ),
                None,
            )
        rows.append({
            "opportunity_id": oid,
            "business_name": item.get("name"),
            "state": item.get("state"),
            "source_frontier": item.get("source_frontier"),
            "observed_trigger": item.get("observed_trigger"),
            "trigger_date": item.get("trigger_date") or item.get("license_or_issue_date"),
            "stage": item.get("stage"),
            "priority": item.get("priority"),
            "contact_gate": item.get("contact_gate"),
            "call_ready": item.get("call_ready"),
            "next_action": item.get("next_action"),
            "source_url": (item.get("citation") or {}).get("url"),
            "business_channel_type": (channel or {}).get("type"),
            "business_channel": (channel or {}).get("value"),
            "clearance_expires_at": (clearance or {}).get("expires_at"),
            "not_for_underwriting": True,
        })
    return rows


def reset_for_tests() -> None:
    _STATE.clear()
    _KNOWN.clear()
