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
import pathlib
import re
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

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
_PERSISTENCE_PROBE_LOCK = threading.Lock()
_PERSISTENCE_READY_PATH: str | None = None
_PERSISTENCE_RETRY_SECONDS = max(
    5,
    int(os.environ.get("DAVID_DATABASE_RETRY_SECONDS", "15")),
)
_PERSISTENCE_LOCK = threading.Lock()
_LAST_PERSISTENCE_ATTEMPT = 0.0
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
    global _PERSISTENCE_DIAGNOSTIC, _PERSISTENCE_HEALTH, _PERSISTENCE_READY_PATH
    if _DATABASE_URL:
        _recover_postgres_if_due()
        return _PERSISTENCE_HEALTH
    if not _PATH or not os.path.isabs(_PATH):
        return "NOT_CONFIGURED"

    with _PERSISTENCE_PROBE_LOCK:
        path = os.path.abspath(_PATH)
        directory = os.path.dirname(path)
        if not os.path.isdir(directory) or (
            os.path.exists(path) and not os.path.isfile(path)
        ):
            _PERSISTENCE_HEALTH = "FILE_UNAVAILABLE"
            _PERSISTENCE_DIAGNOSTIC = "FILE_PATH_UNAVAILABLE"
            _PERSISTENCE_READY_PATH = None
            return "FILE_UNAVAILABLE"
        if _PERSISTENCE_HEALTH == "FILE_READY" and _PERSISTENCE_READY_PATH == path:
            return "FILE_BACKED"

        temporary: str | None = None
        try:
            original = pathlib.Path(path).read_bytes() if os.path.exists(path) else b"{}"
            fd, temporary = tempfile.mkstemp(
                prefix=".dealdesk-readiness-",
                suffix=".tmp",
                dir=directory,
            )
            with os.fdopen(fd, "wb") as handle:
                handle.write(original)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            temporary = None
            if pathlib.Path(path).read_bytes() != original:
                _PERSISTENCE_HEALTH = "FILE_UNAVAILABLE"
                _PERSISTENCE_DIAGNOSTIC = "FILE_PROBE_MISMATCH"
                return "FILE_UNAVAILABLE"
            _PERSISTENCE_HEALTH = "FILE_READY"
            _PERSISTENCE_DIAGNOSTIC = "OK"
            _PERSISTENCE_READY_PATH = path
            return "FILE_BACKED"
        except OSError:
            _PERSISTENCE_HEALTH = "FILE_UNAVAILABLE"
            _PERSISTENCE_DIAGNOSTIC = "FILE_PROBE_FAILED"
            _PERSISTENCE_READY_PATH = None
            return "FILE_UNAVAILABLE"
        finally:
            if temporary and os.path.exists(temporary):
                try:
                    os.unlink(temporary)
                except OSError:
                    pass


def persistence_ready() -> bool:
    return persistence_state() in {"FILE_BACKED", "POSTGRES_READY"}


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


def subject_ids(record: dict[str, Any]) -> tuple[str, ...]:
    """Stable business aliases used to carry suppression across new signals."""
    official_keys = (
        "license_number",
        "usdot_number",
        "uei",
        "cage_code",
        "entity_number",
    )
    identities = [
        {"official": f"{key}:{_clean(record.get(key), 160).lower()}"}
        for key in official_keys
        if _clean(record.get(key), 160)
    ]
    name = _clean(record.get("name"), 240).lower()
    state = _clean(record.get("state"), 16).upper()
    if name:
        identities.append({"name": name, "state": state})
    aliases: list[str] = []
    for identity in identities or [{"opportunity": opportunity_id(record)}]:
        raw = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        aliases.append("subj_" + hashlib.sha256(raw).hexdigest()[:24])
    return tuple(dict.fromkeys(aliases))


def subject_id(record: dict[str, Any]) -> str:
    """Primary stable identity; volatile dates and source URLs are excluded."""
    return subject_ids(record)[0]


def _active_suppression(record: dict[str, Any]) -> dict[str, Any] | None:
    stable_ids = set(subject_ids(record))
    for saved in _STATE.values():
        suppression = saved.get("suppression")
        if not isinstance(suppression, dict) or suppression.get("active") is not True:
            continue
        suppressed_ids = set(suppression.get("subject_ids") or ())
        if suppression.get("subject_id"):
            suppressed_ids.add(str(suppression["subject_id"]))
        if stable_ids.intersection(suppressed_ids):
            return suppression
    return None


def _db_connect():
    if not _DATABASE_URL:
        raise RuntimeError("database persistence is not configured")
    if psycopg is None:
        raise RuntimeError("psycopg is required when DAVID_DATABASE_URL is configured")
    return psycopg.connect(_DATABASE_URL, connect_timeout=8)


class PersistenceUnavailable(RuntimeError):
    """Sanitized persistence failure safe to expose as a service-unavailable error."""


def _ensure_database_schema(connection: Any) -> None:
    """Create only the fixed, idempotent tables this service owns."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS david_dealdesk_state (
                opportunity_id text PRIMARY KEY,
                payload jsonb NOT NULL,
                version bigint NOT NULL DEFAULT 1,
                updated_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS david_dealdesk_events (
                event_id text PRIMARY KEY,
                opportunity_id text NOT NULL,
                event_type text NOT NULL,
                actor text NOT NULL,
                payload jsonb NOT NULL,
                created_at timestamptz NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS david_dealdesk_events_opportunity_created_idx
            ON david_dealdesk_events (opportunity_id, created_at)
            """
        )


def _classify_database_error(exc: Exception) -> str:
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    if psycopg is None or "psycopg is required" in message:
        return "DRIVER_UNAVAILABLE"
    if "does not exist" in message or "undefinedtable" in name:
        return "SCHEMA_UNAVAILABLE"
    if "password authentication failed" in message or "invalidpassword" in name:
        return "AUTHENTICATION_FAILED"
    if "name or service not known" in message or "could not translate host" in message:
        return "DNS_UNAVAILABLE"
    if "timeout" in name or "timeout" in message:
        return "CONNECTION_TIMEOUT"
    return "CONNECTION_UNAVAILABLE"


def _read_database_rows(connection: Any) -> list[tuple[Any, Any]]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT opportunity_id, payload FROM david_dealdesk_state")
        return list(cursor.fetchall())


def _load() -> None:
    global _LAST_PERSISTENCE_ATTEMPT
    global _PERSISTENCE_DIAGNOSTIC
    global _PERSISTENCE_HEALTH
    if _DATABASE_URL:
        _LAST_PERSISTENCE_ATTEMPT = time.monotonic()
        try:
            with _db_connect() as connection:
                try:
                    rows = _read_database_rows(connection)
                except Exception as exc:
                    if _classify_database_error(exc) != "SCHEMA_UNAVAILABLE":
                        raise
                    connection.rollback()
                    _ensure_database_schema(connection)
                    rows = _read_database_rows(connection)
                for oid, payload in rows:
                    if isinstance(payload, str):
                        payload = json.loads(payload)
                    if isinstance(payload, dict):
                        _STATE[str(oid)] = payload
            _PERSISTENCE_HEALTH = "POSTGRES_READY"
            _PERSISTENCE_DIAGNOSTIC = "OK"
        except Exception as exc:
            _STATE.clear()
            _PERSISTENCE_HEALTH = "POSTGRES_UNAVAILABLE"
            _PERSISTENCE_DIAGNOSTIC = _classify_database_error(exc)
        return
    if not _PATH or not os.path.exists(_PATH):
        return
    try:
        with open(_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            _STATE.update({str(k): v for k, v in data.items() if isinstance(v, dict)})
        _PERSISTENCE_HEALTH = "FILE_READABLE"
        if persistence_state() != "FILE_BACKED":
            _STATE.clear()
    except Exception:
        _STATE.clear()
        _PERSISTENCE_HEALTH = "FILE_UNAVAILABLE"
        _PERSISTENCE_DIAGNOSTIC = "FILE_LOAD_FAILED"


def _recover_postgres_if_due() -> None:
    if not _DATABASE_URL or _PERSISTENCE_HEALTH == "POSTGRES_READY":
        return
    if time.monotonic() - _LAST_PERSISTENCE_ATTEMPT < _PERSISTENCE_RETRY_SECONDS:
        return
    if not _PERSISTENCE_LOCK.acquire(blocking=False):
        return
    try:
        if (
            _PERSISTENCE_HEALTH != "POSTGRES_READY"
            and time.monotonic() - _LAST_PERSISTENCE_ATTEMPT
            >= _PERSISTENCE_RETRY_SECONDS
        ):
            _load()
    finally:
        _PERSISTENCE_LOCK.release()


def _persist(
    state: dict[str, dict[str, Any]] | None = None,
    event: dict[str, Any] | None = None,
) -> None:
    global _PERSISTENCE_DIAGNOSTIC, _PERSISTENCE_HEALTH, _PERSISTENCE_READY_PATH
    snapshot = _STATE if state is None else state
    if _DATABASE_URL:
        try:
            with _db_connect() as connection:
                with connection.cursor() as cursor:
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
        except Exception as exc:
            _PERSISTENCE_HEALTH = "POSTGRES_UNAVAILABLE"
            _PERSISTENCE_DIAGNOSTIC = _classify_database_error(exc)
            raise PersistenceUnavailable("deal-desk persistence is unavailable") from None
        _PERSISTENCE_HEALTH = "POSTGRES_READY"
        _PERSISTENCE_DIAGNOSTIC = "OK"
        return
    if not _PATH:
        return
    temporary: str | None = None
    try:
        directory = os.path.dirname(os.path.abspath(_PATH))
        os.makedirs(directory, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix="dealdesk-",
            suffix=".json",
            dir=directory,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, _PATH)
        _PERSISTENCE_HEALTH = "FILE_READY"
        _PERSISTENCE_DIAGNOSTIC = "OK"
        _PERSISTENCE_READY_PATH = os.path.abspath(_PATH)
    except Exception:
        _PERSISTENCE_HEALTH = "FILE_UNAVAILABLE"
        _PERSISTENCE_DIAGNOSTIC = "FILE_WRITE_FAILED"
        _PERSISTENCE_READY_PATH = None
        raise PersistenceUnavailable("deal-desk persistence is unavailable") from None
    finally:
        if temporary and os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                pass


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
    _KNOWN[oid] = dict(record)
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
    cleared_channel = next(
        (
            item
            for item in saved.get("channels") or []
            if clearance and item.get("channel_id") == clearance.get("channel_id")
        ),
        None,
    )
    phone_call_ready = bool(
        call_ready
        and isinstance(cleared_channel, dict)
        and cleared_channel.get("type") == "BUSINESS_PHONE"
    )
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
        "phone_call_ready": phone_call_ready,
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
            "phone_call_ready": sum(
                1 for item in opportunities if item["phone_call_ready"]
            ),
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
        "next_action": (
            "Open the governed call sheet and place one manual business call"
            if channel.get("type") == "BUSINESS_PHONE"
            else "Use only the cleared business channel; a phone call sheet remains locked"
        ),
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
            "phone_call_ready": item.get("phone_call_ready"),
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
