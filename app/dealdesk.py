# SPDX-License-Identifier: Apache-2.0
"""A fail-closed, broker-oriented opportunity desk for public B2B records."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any


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
TERMINAL_STAGES = {"WON", "LOST", "BLOCKED"}
_PATH = os.environ.get("DAVID_DEAL_DESK_PATH")
_STATE: dict[str, dict[str, Any]] = {}
_KNOWN: dict[str, dict[str, Any]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _load() -> None:
    if not _PATH or not os.path.exists(_PATH):
        return
    try:
        with open(_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            _STATE.update({str(k): v for k, v in data.items() if isinstance(v, dict)})
    except Exception:
        # Corrupt/unavailable optional storage must not make outreach look cleared.
        _STATE.clear()


def _persist() -> None:
    if not _PATH:
        return
    directory = os.path.dirname(os.path.abspath(_PATH))
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="dealdesk-", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(_STATE, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, _PATH)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


_load()


def _priority(record: dict[str, Any]) -> int:
    # Evidence-completeness priority only. It is deliberately not a conversion,
    # underwriting, or contact-permission score.
    score = 15
    if record.get("contact_quality") == "business address (public)":
        score += 10
    observed = record.get("license_or_issue_date")
    if observed:
        score += 15
        try:
            age_days = max(
                0,
                (datetime.now(timezone.utc).date() - datetime.fromisoformat(str(observed)[:10]).date()).days,
            )
            score += max(0, 10 - min(age_days, 180) // 18)
        except ValueError:
            pass
    if (record.get("citation") or {}).get("url"):
        score += 20
    if record.get("receipt_id"):
        score += 15
    if record.get("type") in {"business", "licensee", "carrier", "federal_award"}:
        score += 5
    if record.get("contact_quality") != "[SAMPLE]":
        score += 10
    return min(score, 100)


def _default_gate(record: dict[str, Any]) -> tuple[str, bool, list[str]]:
    quality = record.get("contact_quality")
    if quality == "[SAMPLE]" or str(record.get("name", "")).startswith("[SAMPLE]"):
        return "DO_NOT_CONTACT_SAMPLE", False, ["Sample records are demonstration-only."]
    if quality == "entity id only":
        return "BLOCKED_NO_BUSINESS_CHANNEL", False, [
            "Verify a named business and official business contact channel first."
        ]
    return "RESEARCH_REQUIRED", False, [
        "Verify the current official record.",
        "Find a business contact channel published by the business.",
        "Check suppression lists and applicable calling, texting, and email rules.",
        "Record manual clearance before contact.",
    ]


def enrich(record: dict[str, Any]) -> dict[str, Any]:
    oid = opportunity_id(record)
    _KNOWN[oid] = dict(record)
    gate, call_ready, checklist = _default_gate(record)
    saved = _STATE.get(oid, {})
    if saved.get("clearance_confirmed") is True and saved.get("stage") not in {"BLOCKED", "LOST"}:
        gate = "MANUAL_CLEARANCE_RECORDED"
        call_ready = True
    stage = saved.get("stage") or ("BLOCKED" if gate.startswith("DO_NOT_CONTACT") else "REVIEW")
    next_action = saved.get("next_action") or record.get("recommended_next_action") or (
        "Use for demonstration only"
        if gate.startswith("DO_NOT_CONTACT")
        else "Verify the source and find the official business contact channel"
    )
    return {
        **record,
        "opportunity_id": oid,
        "priority": _priority(record),
        "stage": stage,
        "next_action": next_action,
        "contact_gate": gate,
        "call_ready": call_ready,
        "clearance_checklist": checklist,
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
            "needs_research": sum(1 for item in opportunities if item["contact_gate"] == "RESEARCH_REQUIRED"),
            "stage_counts": stage_counts,
        },
        "persistence": "FILE_BACKED" if _PATH else "IN_MEMORY",
        "doctrine": (
            "Public B2B records are research signals, not permission to contact. "
            "Manual source verification and execution-time outreach clearance are required."
        ),
    }


def update(
    oid: str,
    *,
    stage: str,
    next_action: str | None = None,
    note: str | None = None,
    owner: str | None = None,
    clearance_confirmed: bool = False,
) -> dict[str, Any]:
    if oid not in _KNOWN:
        raise KeyError("unknown opportunity; refresh the opportunity desk first")
    normalized_stage = (stage or "").strip().upper()
    if normalized_stage not in STAGES:
        raise ValueError(f"stage must be one of {STAGES}")
    record = _KNOWN[oid]
    gate, _, _ = _default_gate(record)
    if normalized_stage in {"READY", "CONTACTED", "MEETING", "PROPOSAL", "WON"}:
        if gate.startswith("DO_NOT_CONTACT") or gate.startswith("BLOCKED"):
            raise ValueError("this record cannot be cleared for contact")
        if not clearance_confirmed and _STATE.get(oid, {}).get("clearance_confirmed") is not True:
            raise ValueError("manual outreach clearance must be confirmed before advancing")
    clean_note = (note or "").strip()[:500]
    clean_action = (next_action or "").strip()[:240]
    clean_owner = (owner or "").strip()[:80]
    previous = _STATE.get(oid, {})
    history = list(previous.get("history") or [])
    event = {
        "at": _now(),
        "from": previous.get("stage") or "REVIEW",
        "to": normalized_stage,
        "note": clean_note,
    }
    history.append(event)
    _STATE[oid] = {
        "stage": normalized_stage,
        "next_action": clean_action or previous.get("next_action") or "",
        "last_note": clean_note,
        "owner": clean_owner or previous.get("owner") or "Unassigned",
        "clearance_confirmed": bool(
            clearance_confirmed or previous.get("clearance_confirmed")
        ),
        "updated_at": event["at"],
        "history": history[-50:],
    }
    _persist()
    return enrich(record)


def reset_for_tests() -> None:
    _STATE.clear()
    _KNOWN.clear()
