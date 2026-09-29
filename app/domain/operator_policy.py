"""Server-owned operator scope for the evidence workflow; no contact authority."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .david_reference import Hold, aware, digest, parse_stamp

ACTIONS = frozenset({"read", "admit", "brief", "review", "clearance", "manual_task", "correct", "suppress", "outcome"})
PURPOSE = "organization_research"


@dataclass(frozen=True)
class OperatorContext:
    username: str
    tenant: str
    actions: frozenset[str]
    policy_revision: str
    policy_digest: str
    expires_at: datetime

    def require(self, action: str, now: datetime) -> None:
        if action not in self.actions or aware(now) >= aware(self.expires_at):
            raise Hold("OPERATOR_SCOPE_DENIED_OR_EXPIRED")


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise Hold("OPERATOR_POLICY_INVALID")
        result[key] = value
    return result


def load_operator_context(path: str | None, username: str, session_expiry: datetime,
                          now: datetime) -> OperatorContext:
    """Read only the explicitly configured policy file, independently of browser input.

    Deployment operators install this policy through their approved private config
    flow. Repository examples grant nothing. Reading a policy never grants source
    rights, verifies a professional license, or permits contacting anyone.
    """
    secret_value = os.environ.get("DAVID_OPERATOR_POLICY_JSON", "") if not path else ""
    if not path and not secret_value:
        raise Hold("OPERATOR_POLICY_NOT_CONFIGURED")
    source = Path(path) if path else None
    if source is not None and (not source.is_absolute() or source.is_symlink()):
        raise Hold("OPERATOR_POLICY_PATH_MUST_BE_ABSOLUTE")
    try:
        if source is None:
            raw = secret_value.encode("utf-8")
        else:
            with source.open("rb") as handle:
                raw = handle.read(65537)
        if len(raw) > 65536:
            raise Hold("OPERATOR_POLICY_INVALID")
        policy = json.loads(raw, object_pairs_hook=_pairs)
        if type(policy) is not dict or set(policy) != {
            "schema", "revision", "review_reference", "expires_at", "operators"
        } or policy["schema"] != "szl.david.operator-policy/v1":
            raise Hold("OPERATOR_POLICY_INVALID")
        for key in ("revision", "review_reference"):
            if type(policy[key]) is not str or not 1 <= len(policy[key].strip()) <= 256:
                raise Hold("OPERATOR_POLICY_INVALID")
        if type(policy["expires_at"]) is not str:
            raise Hold("OPERATOR_POLICY_INVALID")
        expiry = parse_stamp(policy["expires_at"])
        if type(policy["operators"]) is not list or len(policy["operators"]) > 100:
            raise Hold("OPERATOR_POLICY_INVALID")
        seen = set()
        admitted = None
        for item in policy["operators"]:
            if type(item) is not dict or set(item) != {"username", "tenant", "actions", "purpose", "expires_at"}:
                raise Hold("OPERATOR_POLICY_INVALID")
            for key in ("username", "tenant"):
                if type(item[key]) is not str or not 1 <= len(item[key].strip()) <= 80:
                    raise Hold("OPERATOR_POLICY_INVALID")
            if item["username"] in seen or item["purpose"] != PURPOSE:
                raise Hold("OPERATOR_POLICY_INVALID")
            seen.add(item["username"])
            if type(item["actions"]) is not list or "read" not in item["actions"] or any(type(x) is not str or x not in ACTIONS for x in item["actions"]):
                raise Hold("OPERATOR_POLICY_INVALID")
            if type(item["expires_at"]) is not str:
                raise Hold("OPERATOR_POLICY_INVALID")
            item_expiry = parse_stamp(item["expires_at"])
            if item["username"] == username:
                admitted = OperatorContext(username, item["tenant"], frozenset(item["actions"]),
                    policy["revision"], digest(policy), min(expiry, item_expiry, aware(session_expiry)))
        if admitted is None or aware(now) >= admitted.expires_at:
            raise Hold("OPERATOR_SCOPE_DENIED_OR_EXPIRED")
        return admitted
    except Hold:
        raise
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, RecursionError):
        raise Hold("OPERATOR_POLICY_INVALID") from None
