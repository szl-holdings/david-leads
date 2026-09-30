# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — david-leads vertical
"""Receipt per scoring decision — the SZL doctrine primitive this vertical is built on.

Pattern reuse: estate szl-receipt approach as implemented in app/receipts.py —
canonical JSON payload, DSSE-v1 pre-authentication encoding (spec ASCII-decimal
form, cosign verify-blob compatible), ECDSA-P256 signature when a key is
configured, and an honest UNSIGNED hash-chained receipt when it is not.

Honesty contract:
- No signing key (env SZL_COSIGN_PRIVATE_PEM) or no optional `cryptography`
  package  =>  signature_status "UNSIGNED (hash-chained, honest)". The absence
  of a signature is disclosed, never papered over, and a signature is never
  fabricated.
- Law 5: signature != truth. A valid signature proves integrity of this
  receipt, not correctness of the score it carries. Verifier output says so.
- Law 3: every receipt payload carries is_service_account=false. v0 has no
  identity provider, so the operator is disclosed as UNAUTHENTICATED rather
  than impersonated.
- Flight-Recorder discipline: the hash chain tip is process memory. That is
  LOCAL durability only; receipts are not a durable archive (local != remote).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

KEYID = "szl-david-leads-v0"
PAYLOAD_TYPE = "application/vnd.szl.lead-score-receipt+json"

_GENESIS = "0" * 64
_chain_tip = {"hash": _GENESIS}  # process-memory chain tip; LOCAL durability only


def _canon(obj: Any) -> bytes:
    """Canonical JSON: sorted keys, tight separators. Stable across processes."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _pae(payload_type: str, body: bytes) -> bytes:
    """DSSE-v1 Pre-Authentication Encoding (ASCII-decimal length form).

    Byte-compatible with the estate david-leads app/receipts.py encoding so a
    receipt minted here verifies with the same PAE rule there and vice versa.
    """
    return b"DSSEv1 %d %s %d %s" % (len(payload_type), payload_type.encode(), len(body), body)


def _try_sign(pae: bytes) -> Optional[dict[str, Any]]:
    """ECDSA-P256 over the PAE. Returns None — honestly — when signing is impossible."""
    pem = os.environ.get("SZL_COSIGN_PRIVATE_PEM")
    if not pem:
        return None
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        key = serialization.load_pem_private_key(pem.encode(), password=None)
        sig = key.sign(pae, ec.ECDSA(hashes.SHA256()))
        return {"keyid": KEYID, "sig": base64.b64encode(sig).decode()}
    except Exception:
        # A misconfigured key must not mint a broken "signed" receipt.
        return None


def make_receipt(payload_core: dict[str, Any], truth_state: str) -> dict[str, Any]:
    """Mint a hash-chained receipt for one scoring decision.

    payload_core is the scoring outcome (lead, axes, signals, denials). This
    function adds doctrine fields, hashes, optionally signs, and advances the
    process-local chain. It never raises on signing problems; it discloses.
    """
    body = dict(payload_core)
    body.update(
        {
            "receipt_kind": "lead-scoring-decision",
            "truth_state": truth_state,
            "is_service_account": False,  # Law 3 — structurally present
            "operator_identity": "UNAUTHENTICATED (local v0; no identity provider configured)",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prev_receipt_hash": _chain_tip["hash"],
            "doctrine": "SZL governed-AI: default-deny evidence policy, zero-bandaid disclosure",
        }
    )
    body_bytes = _canon(body)
    body_hash = hashlib.sha256(body_bytes).hexdigest()
    signature = _try_sign(_pae(PAYLOAD_TYPE, body_bytes))
    receipt = {
        "receipt_id": "rcpt_" + body_hash[:16],
        "payload_type": PAYLOAD_TYPE,
        "payload": body,
        "payload_sha256": body_hash,
        "signed": signature is not None,
        "signature": signature,  # None when no key — an honest UNSIGNED receipt
        "signature_status": (
            "DSSE-ECDSA-P256 SIGNED" if signature else "UNSIGNED (hash-chained, honest)"
        ),
        "truth_state": truth_state,
        "prev_receipt_hash": body["prev_receipt_hash"],
        "durability": "PROCESS_MEMORY",
    }
    _chain_tip["hash"] = body_hash
    return receipt


def verify_receipt(
    receipt: dict[str, Any], previous_receipt: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """Offline verification: payload hash, signature (if present), chain link.

    Distinct states, never collapsed: integrity, signature, and chain are
    reported separately. A missing predecessor is UNVERIFIED_PREDECESSOR, not a
    failure and not a pass.
    """
    payload = receipt.get("payload") or {}
    body_bytes = _canon(payload)
    recomputed = hashlib.sha256(body_bytes).hexdigest()
    hash_ok = recomputed == receipt.get("payload_sha256")

    checks = [{"check": "Payload hash re-derives (tamper-evident)", "pass": hash_ok}]

    prev_hash = payload.get("prev_receipt_hash")
    pointer_valid = (
        isinstance(prev_hash, str)
        and len(prev_hash) == 64
        and all(c in "0123456789abcdef" for c in prev_hash)
    )
    checks.append({"check": "Predecessor pointer is structurally valid", "pass": pointer_valid})

    if not pointer_valid:
        chain_state = "FAILED"
    elif prev_hash == _GENESIS:
        chain_state = "GENESIS_DECLARED"
    elif previous_receipt is None:
        chain_state = "UNVERIFIED_PREDECESSOR"
    else:
        prev_payload = previous_receipt.get("payload")
        prev_recomputed = (
            hashlib.sha256(_canon(prev_payload)).hexdigest()
            if isinstance(prev_payload, dict)
            else None
        )
        predecessor_ok = prev_recomputed is not None and prev_hash == prev_recomputed
        checks.append(
            {"check": "Supplied predecessor re-derives and matches pointer", "pass": predecessor_ok}
        )
        chain_state = "VERIFIED" if predecessor_ok else "FAILED"

    sig = receipt.get("signature")
    signature_state = "UNSIGNED"
    sig_ok: Optional[bool] = None
    if sig:
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import ec

            pem = os.environ.get("SZL_COSIGN_PUBLIC_PEM")
            if not pem:
                sig_ok = None
                signature_state = "UNVERIFIABLE (no SZL_COSIGN_PUBLIC_PEM configured)"
            else:
                pub = serialization.load_pem_public_key(pem.encode())
                pub.verify(
                    base64.b64decode(sig["sig"]),
                    _pae(receipt.get("payload_type", PAYLOAD_TYPE), body_bytes),
                    ec.ECDSA(hashes.SHA256()),
                )
                sig_ok = True
                signature_state = "VERIFIED"
        except Exception:
            sig_ok = False
            signature_state = "FAILED"
        if sig_ok is not None:
            checks.append({"check": "ECDSA-P256 signature verifies", "pass": sig_ok})

    integrity_ok = all(c["pass"] for c in checks if "signature" not in c["check"].lower())
    if not integrity_ok or sig_ok is False:
        verdict = "FAILED"
    elif sig_ok is True:
        verdict = "SIGNATURE_VERIFIED"
    else:
        verdict = "HASH_INTEGRITY_VERIFIED"

    return {
        "receipt_id": receipt.get("receipt_id", "UNKNOWN"),
        "verdict": verdict,
        "integrity_state": "VERIFIED" if integrity_ok else "FAILED",
        "signature_state": signature_state,
        "chain_state": chain_state,
        "checks": checks,
        "note": (
            "A valid signature proves integrity of the receipt, not correctness "
            "of the score it carries (Law 5: signature != truth)."
        ),
    }


def reset_chain() -> None:
    """Test hook: return the process-local chain to genesis."""
    _chain_tip["hash"] = _GENESIS
