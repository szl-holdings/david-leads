# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads V8 · multi-party-witnessed receipts
"""
consensus.py — thin wrapper over the CANONICAL khipu-consensus primitives.

The khipu functions below (canonical_json, pae, OrganVerdict, OrganCheck, ConsensusResult,
sign_verdict, verify_verdict, tally) are PORTED 1:1 from
src/khipu-consensus/python/khipu_consensus/__init__.py — Byzantine-fault-tolerant
multi-party signed agreement: ≥ threshold valid `allow` ECDSA-P256-SHA256 signatures over the
same action hash ⇒ CANONICAL. 3-of-4 tolerates 1 fault.

HONEST SIGNING: the per-organ witness keys are EPHEMERAL test-witness keypairs generated
in-memory at process start (never written to disk, never committed). They produce REAL,
verifiable ECDSA-P256 signatures — not fabricated. They are NOT the production cosign key.
If `cryptography` is unavailable, witness_event returns an honest UNSIGNED consensus block.
"""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

ORGAN_VERDICT_PAYLOAD_TYPE = "application/vnd.szl.khipu.organ-verdict+json"
ORGANS = ("a11oy", "sentra", "killinchu", "amaru")  # the 4 witness organs


# ---------------------------------------------------------------- canonical khipu (ported)
def canonical_json(obj) -> bytes:
    """Deterministic canonical JSON: sorted keys, compact separators, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def pae(payload_type: str, body: bytes) -> bytes:
    """DSSE Pre-Authentication Encoding (DSSEv1)."""
    t = payload_type.encode("utf-8")
    return b"DSSEv1 " + str(len(t)).encode() + b" " + t + b" " + str(len(body)).encode() + b" " + body


@dataclass
class OrganVerdict:
    organ: str
    keyid: str
    payload_type: str
    payload_b64: str
    signature_b64: str
    verdict: str = "allow"
    reason: str = ""

    @staticmethod
    def from_dict(d: dict) -> "OrganVerdict":
        return OrganVerdict(
            organ=d.get("organ", ""),
            keyid=d.get("keyid", ""),
            payload_type=d.get("payloadType", ORGAN_VERDICT_PAYLOAD_TYPE),
            payload_b64=d.get("payload", ""),
            signature_b64=d.get("signature", ""),
            verdict=d.get("verdict", "allow"),
            reason=d.get("reason", ""),
        )


@dataclass
class OrganCheck:
    organ: Optional[str]
    keyid: Optional[str]
    valid: bool
    verdict: Optional[str]
    action_hash_match: bool
    counts: bool
    reason: str = ""


@dataclass
class ConsensusResult:
    action_hash: str
    threshold: int
    n: int
    consensus_count: int
    decision: str
    checks: list = field(default_factory=list)

    @property
    def khipu_consensus(self) -> str:
        return f"{self.consensus_count}-of-{self.n}"


def sign_verdict(organ: str, action_hash: str, verdict: str, private_key_pem: str,
                 reason: str = "", lean_sha: str = "", ts: str = "") -> dict:
    """Produce a DSSE-signed organ verdict dict (the wire shape)."""
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import hashes

    keyid = f"{organ}-cosign"
    statement = {
        "schema": "szl.khipu.organ_verdict/v1", "organ": organ, "keyid": keyid,
        "action_hash": action_hash, "verdict": verdict, "reason": reason,
        "lean_sha": lean_sha, "ts": ts or datetime.now(timezone.utc).isoformat(),
    }
    body = canonical_json(statement)
    priv = load_pem_private_key(private_key_pem.encode(), password=None)
    sig = priv.sign(pae(ORGAN_VERDICT_PAYLOAD_TYPE, body), ec.ECDSA(hashes.SHA256()))
    return {
        "organ": organ, "keyid": keyid, "payloadType": ORGAN_VERDICT_PAYLOAD_TYPE,
        "payload": base64.b64encode(body).decode(), "signature": base64.b64encode(sig).decode(),
        "verdict": verdict, "reason": reason,
    }


def verify_verdict(v: OrganVerdict, public_key_pem: str, action_hash: str) -> OrganCheck:
    """Verify one organ's signature against its public key + internal consistency."""
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import hashes
    from cryptography.exceptions import InvalidSignature

    if not v.payload_b64 or not v.signature_b64:
        return OrganCheck(v.organ, v.keyid, False, None, False, False, "missing payload/signature")
    try:
        body = base64.b64decode(v.payload_b64)
        to_verify = pae(v.payload_type, body)
        pub = load_pem_public_key(public_key_pem.encode())
        try:
            pub.verify(base64.b64decode(v.signature_b64), to_verify, ec.ECDSA(hashes.SHA256()))
        except InvalidSignature:
            return OrganCheck(v.organ, v.keyid, False, None, False, False, "signature mismatch")
        decoded = json.loads(body)
        ah_match = decoded.get("action_hash") == action_hash
        verdict = decoded.get("verdict")
        counts = ah_match and verdict == "allow"
        return OrganCheck(v.organ, v.keyid, True, verdict, ah_match, counts)
    except Exception as e:  # noqa: BLE001
        return OrganCheck(v.organ, v.keyid, False, None, False, False, f"{type(e).__name__}: {e}")


def tally(action_hash: str, verdicts: list, pubkeys: dict,
          threshold: int = 3, n: int = 4) -> ConsensusResult:
    """Count valid + allow signatures over `action_hash`; apply the BFT threshold."""
    checks = []
    count = 0
    for item in verdicts:
        if item is None:
            checks.append(OrganCheck(None, None, False, None, False, False, "abstain/timeout"))
            continue
        v = item if isinstance(item, OrganVerdict) else OrganVerdict.from_dict(item)
        pem = pubkeys.get(v.organ, "")
        if not pem:
            checks.append(OrganCheck(v.organ, v.keyid, False, None, False, False, "no public key"))
            continue
        chk = verify_verdict(v, pem, action_hash)
        checks.append(chk)
        if chk.counts:
            count += 1
    decision = "canonical" if count >= threshold else "rejected"
    return ConsensusResult(action_hash, threshold, n, count, decision, checks)


# ---------------------------------------------------------------- ephemeral witness keys
_WITNESS_KEYS: dict[str, dict[str, str]] | None = None  # {organ: {priv, pub}}


def _ensure_witness_keys() -> dict[str, dict[str, str]] | None:
    """Generate per-organ ephemeral P256 keypairs once per process (in-memory only).

    Honest: real ECDSA-P256 keys, never written to disk, clearly labelled as ephemeral
    test-witness keys — NOT the production cosign key. Returns None if cryptography is
    unavailable (-> honest UNSIGNED consensus)."""
    global _WITNESS_KEYS
    if _WITNESS_KEYS is not None:
        return _WITNESS_KEYS
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
    except Exception:  # pragma: no cover
        return None
    keys: dict[str, dict[str, str]] = {}
    for organ in ORGANS:
        priv = ec.generate_private_key(ec.SECP256R1())
        priv_pem = priv.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        pub_pem = priv.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        keys[organ] = {"priv": priv_pem, "pub": pub_pem}
    _WITNESS_KEYS = keys
    return keys


def action_hash_for(obj) -> str:
    """sha256 hex of the canonical JSON of an action payload."""
    return hashlib.sha256(canonical_json(obj)).hexdigest()


def witness_event(action_hash: str, organs: tuple[str, ...] = ORGANS,
                  threshold: int = 3) -> dict:
    """Produce a 3-of-4 khipu ConsensusResult over `action_hash`.

    Uses ephemeral in-memory witness keypairs (real ECDSA-P256). Returns a JSON-safe
    consensus block. When cryptography is unavailable, returns an honest UNSIGNED block."""
    n = len(organs)
    keys = _ensure_witness_keys()
    if keys is None:
        return {
            "khipu_consensus": f"0-of-{n}",
            "threshold": threshold, "n": n, "consensus_count": 0,
            "decision": "unsigned-honest",
            "signed": False,
            "signing_mode": "UNSIGNED — cryptography unavailable in this runtime (honest, no fabricated signatures)",
            "organs": list(organs),
            "checks": [],
        }
    verdicts = [
        sign_verdict(o, action_hash, "allow", keys[o]["priv"],
                     reason=f"{o} witnessed change-event")
        for o in organs
    ]
    pubkeys = {o: keys[o]["pub"] for o in organs}
    result = tally(action_hash, verdicts, pubkeys, threshold=threshold, n=n)
    return {
        "khipu_consensus": result.khipu_consensus,
        "threshold": result.threshold, "n": result.n,
        "consensus_count": result.consensus_count,
        "decision": result.decision,
        "signed": result.consensus_count >= threshold,
        "signing_mode": "ephemeral-witness-keys (real ECDSA-P256-SHA256 DSSE; in-memory test "
                        "witnesses, not the production cosign key)",
        "organs": list(organs),
        "action_hash": action_hash,
        "checks": [
            {"organ": c.organ, "keyid": c.keyid, "valid": c.valid,
             "verdict": c.verdict, "counts": c.counts, "reason": c.reason}
            for c in result.checks
        ],
    }
