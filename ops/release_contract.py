"""Offline release-contract checks; NEVER a deployment or signature verifier.

Python 3.11+, standard library only. Reads a policy, a report, and bounded local
JSON evidence artifacts. It performs no network calls, shell commands, merges,
secret reads, or writes. A complete contract remains UNVERIFIED until a trusted
external verifier authenticates its evidence and checks the actual runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

MAX_BYTES = 2 * 1024 * 1024
SHA1 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
GATE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
ENVIRONMENTS = frozenset({
    "CI_ISOLATED", "POSTGRES_RUNTIME_ROLE", "STAGING",
    "LIVE_PUBLIC", "OPERATOR_SANDBOX", "INDEPENDENT_REVIEW",
})
RUNTIME_ENVIRONMENTS = frozenset({"LIVE_PUBLIC", "OPERATOR_SANDBOX"})


class ContractError(ValueError):
    """A coded validation error; messages never interpolate input values."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ContractError(code)


def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def bad_constant(_: str) -> Any:
    raise ContractError("NONFINITE_JSON")


def finite_float(value: str) -> float:
    result = float(value)
    require(math.isfinite(result), "NONFINITE_JSON")
    return result


def parse_json(raw: bytes) -> Any:
    require(len(raw) <= MAX_BYTES, "JSON_TOO_LARGE")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=object_pairs,
                          parse_constant=bad_constant, parse_float=finite_float)
    except ContractError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise ContractError("INVALID_JSON") from None


def read_bytes(path: Path) -> bytes:
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
    except OSError:
        raise ContractError("ARTIFACT_UNREADABLE") from None
    require(len(raw) <= MAX_BYTES, "JSON_TOO_LARGE")
    return raw


def canonical_digest(value: Any) -> str:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError):
        raise ContractError("NONCANONICAL_JSON") from None
    return hashlib.sha256(raw).hexdigest()


def exact_keys(value: Any, keys: set[str], code: str) -> Mapping[str, Any]:
    require(type(value) is dict and set(value) == keys, code)
    return value


def stamp(value: Any) -> datetime:
    require(type(value) is str, "INVALID_TIMESTAMP")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ContractError("INVALID_TIMESTAMP") from None
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
            "NAIVE_TIMESTAMP")
    return parsed.astimezone(timezone.utc)


def matches(pattern: re.Pattern[str], value: Any, code: str) -> None:
    require(type(value) is str and pattern.fullmatch(value) is not None, code)


def integer(value: Any, low: int, high: int, code: str) -> None:
    require(type(value) is int and low <= value <= high, code)


def artifact_path(root: Path, relative: Any) -> Path:
    require(type(relative) is str and 0 < len(relative) <= 240,
            "INVALID_ARTIFACT_PATH")
    require("\\" not in relative and ":" not in relative,
            "INVALID_ARTIFACT_PATH")
    require(all(p not in {"", ".", ".."} for p in relative.split("/")),
            "INVALID_ARTIFACT_PATH")
    part = PurePosixPath(relative)
    require(not part.is_absolute() and part.suffix == ".json",
            "INVALID_ARTIFACT_PATH")
    try:
        require(not root.is_symlink(), "SYMLINK_ARTIFACT_ROOT")
        base = root.resolve(strict=True)
        require(base.is_dir(), "INVALID_ARTIFACT_ROOT")
        candidate = base
        for component in part.parts:
            candidate = candidate / component
            require(not candidate.is_symlink(), "SYMLINK_ARTIFACT")
        resolved = candidate.resolve(strict=True)
        require(resolved.is_relative_to(base) and resolved.is_file(),
                "ARTIFACT_OUTSIDE_ROOT")
        return resolved
    except ContractError:
        raise
    except (OSError, ValueError, RuntimeError):
        raise ContractError("ARTIFACT_UNREADABLE") from None


@dataclass(frozen=True)
class Assessment:
    state: str
    blockers: tuple[str, ...]
    checked_gates: int = 0
    cryptographic_verification: str = "NOT_PERFORMED"
    runtime_verification: str = "NOT_PERFORMED"
    promotion_authorized: bool = False


def validate(policy: Any, report: Any, artifact_root: Path,
             now: datetime) -> Assessment:
    """Check shape, exact subjects, time, completeness, and local content hashes.

    The policy must be obtained from an independently trusted revision, not from
    an untrusted PR's self-approval. The artifact directory must be a frozen local
    snapshot, not an attacker-writable shared directory. This is intentionally
    NOT sufficient for /readyz, merge approval, or a SIGNED/MEASURED claim.
    """
    require(now.tzinfo is not None and now.utcoffset() is not None, "NAIVE_NOW")
    now = now.astimezone(timezone.utc)
    p = exact_keys(policy, {
        "schema", "source_repository", "source_revision", "hf_repository",
        "bundle_sha256", "gates",
    }, "INVALID_POLICY")
    require(p["schema"] == "szl.release-policy/v2", "UNKNOWN_POLICY_SCHEMA")
    matches(REPO, p["source_repository"], "INVALID_SOURCE_REPOSITORY")
    require(p["source_repository"].startswith("szl-holdings/"), "WRONG_SOURCE_ORG")
    matches(REPO, p["hf_repository"], "INVALID_HF_REPOSITORY")
    require(p["hf_repository"].startswith("SZLHOLDINGS/"), "WRONG_HF_ORG")
    matches(SHA1, p["source_revision"], "INVALID_SOURCE_REVISION")
    matches(SHA256, p["bundle_sha256"], "INVALID_BUNDLE_DIGEST")
    require(type(p["gates"]) is dict and 0 < len(p["gates"]) <= 64,
            "INVALID_REQUIRED_GATES")
    for gate, spec in p["gates"].items():
        matches(GATE, gate, "INVALID_GATE_NAME")
        s = exact_keys(spec, {"environment", "max_age_seconds"}, "INVALID_GATE_SPEC")
        require(type(s["environment"]) is str and s["environment"] in ENVIRONMENTS,
                "UNKNOWN_ENVIRONMENT")
        integer(s["max_age_seconds"], 1, 604800, "INVALID_MAX_AGE")

    r = exact_keys(report, {
        "schema", "policy_digest", "source_repository", "source_revision",
        "hf_repository", "hf_revision", "bundle_sha256", "runtime_source_revision",
        "runtime_bundle_sha256", "captured_at", "valid_until", "gates",
    }, "INVALID_REPORT")
    require(r["schema"] == "szl.release-report/v2", "UNKNOWN_REPORT_SCHEMA")
    require(r["policy_digest"] == canonical_digest(policy), "POLICY_DIGEST_MISMATCH")
    for key in ("source_repository", "source_revision", "hf_repository", "bundle_sha256"):
        require(r[key] == p[key], "RELEASE_SUBJECT_MISMATCH")
    matches(SHA1, r["hf_revision"], "INVALID_HF_REVISION")
    require(r["runtime_source_revision"] == p["source_revision"], "RUNTIME_SHA_MISMATCH")
    require(r["runtime_bundle_sha256"] == p["bundle_sha256"], "RUNTIME_BUNDLE_MISMATCH")
    captured, expiry = stamp(r["captured_at"]), stamp(r["valid_until"])
    require(captured <= now < expiry, "REPORT_EXPIRED_OR_FUTURE")
    require(type(r["gates"]) is list and len(r["gates"]) == len(p["gates"]),
            "MISSING_OR_EXTRA_GATES")
    seen: set[str] = set()
    for entry in r["gates"]:
        item = exact_keys(entry, {"gate", "artifact", "sha256"}, "INVALID_GATE_REFERENCE")
        gate = item["gate"]
        matches(GATE, gate, "INVALID_GATE_NAME")
        require(gate in p["gates"] and gate not in seen, "DUPLICATE_OR_UNKNOWN_GATE")
        seen.add(gate)
        matches(SHA256, item["sha256"], "INVALID_ARTIFACT_DIGEST")
        raw = read_bytes(artifact_path(artifact_root, item["artifact"]))
        require(hashlib.sha256(raw).hexdigest() == item["sha256"], "ARTIFACT_DIGEST_MISMATCH")
        a = exact_keys(parse_json(raw), {
            "schema", "gate", "environment", "source_revision", "bundle_sha256",
            "hf_revision", "status", "checked_count", "failed_count", "skipped_count",
            "started_at", "finished_at",
        }, "INVALID_GATE_ARTIFACT")
        require(a["schema"] == "szl.gate-result/v2", "UNKNOWN_GATE_SCHEMA")
        require(a["gate"] == gate, "GATE_ARTIFACT_MISMATCH")
        spec = p["gates"][gate]
        require(a["environment"] == spec["environment"], "ENVIRONMENT_MISMATCH")
        require(a["source_revision"] == p["source_revision"], "GATE_SHA_MISMATCH")
        require(a["bundle_sha256"] == p["bundle_sha256"], "GATE_BUNDLE_MISMATCH")
        if spec["environment"] in RUNTIME_ENVIRONMENTS:
            require(a["hf_revision"] == r["hf_revision"], "GATE_HF_MISMATCH")
        else:
            require(a["hf_revision"] is None, "NONRUNTIME_HF_BINDING")
        require(a["status"] == "PASS", "GATE_NOT_PASS")
        integer(a["checked_count"], 1, 10**8, "EMPTY_OR_INVALID_GATE")
        integer(a["failed_count"], 0, 0, "FAILED_ASSERTIONS")
        integer(a["skipped_count"], 0, 0, "SKIPPED_ASSERTIONS")
        started, finished = stamp(a["started_at"]), stamp(a["finished_at"])
        require(started <= finished <= captured, "INVALID_GATE_TIME_ORDER")
        latest = finished + timedelta(seconds=spec["max_age_seconds"])
        require(now < latest, "STALE_GATE")
        require(expiry <= latest, "REPORT_OUTLIVES_GATE")
    require(seen == set(p["gates"]), "MISSING_REQUIRED_GATE")
    return Assessment("CONTRACT_COMPLETE_UNVERIFIED", (), len(seen))


def assess(policy: Any, report: Any, artifact_root: Path,
           now: datetime) -> Assessment:
    try:
        return validate(policy, report, artifact_root, now)
    except ContractError as exc:
        return Assessment("HOLD", (str(exc),))
    except (TypeError, ValueError, KeyError, OverflowError, RecursionError):
        return Assessment("HOLD", ("MALFORMED_INPUT",))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--artifacts-root", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = assess(parse_json(read_bytes(args.policy)),
                        parse_json(read_bytes(args.report)), args.artifacts_root,
                        datetime.now(timezone.utc))
    except ContractError as exc:
        result = Assessment("HOLD", (str(exc),))
    print(json.dumps(asdict(result), sort_keys=True))
    # Exit 0 establishes local CONTRACT COMPLETENESS ONLY, never promotion authority.
    return 0 if result.state == "CONTRACT_COMPLETE_UNVERIFIED" else 2


if __name__ == "__main__":
    sys.exit(main())
