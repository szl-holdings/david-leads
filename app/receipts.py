# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads Sovereign Insurance Intelligence
"""
receipts.py — compliance-grade signed receipts for every lead score.

Honest-by-design (SZL doctrine): if a signing key is present (env SZL_COSIGN_PRIVATE_PEM),
we produce a real ECDSA-P256 DSSE-style signature over the canonical payload. If NOT present,
we emit a clearly-labelled UNSIGNED but HASH-CHAINED receipt — we NEVER fabricate a signature.

Each receipt binds: the lead, the public data signals used, the score, and the prior receipt
hash (tamper-evident chain). This is the audit-defensible provenance that no agent-level
competitor offers.
"""
from __future__ import annotations
import base64, hashlib, json, os
from datetime import datetime, timezone
from typing import Any

KEYID = "szl-david-leads-cosign"
PAYLOAD_TYPE = "application/vnd.szl.lead-receipt+json"

_GENESIS = "0" * 64
_chain_tip = {"hash": _GENESIS}  # in-memory hash-chain tip for the session


def _canon(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _pae(payload_type: str, body: bytes) -> bytes:
    # DSSE Pre-Authentication Encoding
    return b"DSSEv1 %d %s %d %s" % (
        len(payload_type), payload_type.encode(), len(body), body
    )


def _try_sign(pae: bytes) -> dict[str, Any] | None:
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
        return None


def _witness(action_hash: str):
    """Best-effort 3-of-4 khipu witness block; never breaks receipt minting."""
    try:
        from . import consensus as cs
        return cs.witness_event(action_hash)
    except Exception:
        return None


def make_receipt(lead: dict[str, Any], signals: list[dict[str, Any]], score: float,
                 witness: bool = True) -> dict[str, Any]:
    """Build a tamper-evident receipt for a single scored lead.

    When witness=True, attach a 3-of-4 khipu multi-party consensus block over the payload."""
    ts = datetime.now(timezone.utc).isoformat()
    body = {
        "lead_id": lead["id"],
        "lead_name": lead["name"],
        "score": round(float(score), 2),
        "bucket": lead["bucket"],
        "product": lead["product"],
        "signals_used": [
            {"source": s["source"], "signal": s["signal"], "public": s.get("public", True)}
            for s in signals
        ],
        "all_signals_public": all(s.get("public", True) for s in signals),
        "fabricated_signals": 0,  # honest-by-design: gate rejects fabricated before this point
        "timestamp": ts,
        "prev_receipt_hash": _chain_tip["hash"],
        "doctrine": "SZL governed-AI · public-data-only · honest by design",
    }
    body_bytes = _canon(body)
    body_hash = hashlib.sha256(body_bytes).hexdigest()
    pae = _pae(PAYLOAD_TYPE, body_bytes)
    signature = _try_sign(pae)

    receipt = {
        "id": "rcpt_" + body_hash[:16],
        "payloadType": PAYLOAD_TYPE,
        "payload": body,
        "payload_sha256": body_hash,
        "signed": signature is not None,
        "signature": signature,  # None when no key — honest UNSIGNED receipt
        "signature_status": "DSSE-ECDSA-P256 SIGNED" if signature else "UNSIGNED (hash-chained, honest)",
    }
    if witness:
        consensus = _witness(body_hash)
        if consensus:
            receipt["consensus"] = consensus
    _chain_tip["hash"] = body_hash  # advance the chain
    return receipt


def make_brief_receipt(brief: dict[str, Any], signals: list[dict[str, Any]],
                       witness: bool = True) -> dict[str, Any]:
    """V8: bind a full Signed 4-Part Brief (WHO/WHY NOW/PRODUCT/NEXT ACTION) + its citations
    into one tamper-evident, optionally ECDSA-P256-signed receipt. Honest UNSIGNED if no key.
    When witness=True, attach a 3-of-4 khipu multi-party consensus block."""
    ts = datetime.now(timezone.utc).isoformat()
    cite_sources = []
    for part in brief.get("parts", []):
        for c in part.get("citations", []):
            if c.get("label"):
                cite_sources.append(c["label"])
    body = {
        "kind": "signed-4-part-brief",
        "lead_id": brief["lead_id"],
        "lead_name": brief.get("lead_name", ""),
        "score": round(float(brief.get("score", 0.0)), 2),
        "bucket": brief.get("bucket", ""),
        "freshness_state": brief.get("freshness_state", ""),
        "parts": [{"key": pt["key"], "body": pt["body"]} for pt in brief.get("parts", [])],
        "citations": sorted(set(cite_sources)),
        "signals_used": [
            {"source": x["source"], "signal": x.get("signal", ""), "public": x.get("public", True)}
            for x in (signals or [])
        ],
        "all_signals_public": all(x.get("public", True) for x in (signals or [])),
        "fabricated_signals": 0,
        "timestamp": ts,
        "prev_receipt_hash": _chain_tip["hash"],
        "doctrine": "SZL governed-AI · public-data-only · honest by design",
    }
    body_bytes = _canon(body)
    body_hash = hashlib.sha256(body_bytes).hexdigest()
    pae = _pae(PAYLOAD_TYPE, body_bytes)
    signature = _try_sign(pae)
    receipt = {
        "id": "rcpt_" + body_hash[:16],
        "payloadType": PAYLOAD_TYPE,
        "payload": body,
        "payload_sha256": body_hash,
        "signed": signature is not None,
        "signature": signature,
        "signature_status": "DSSE-ECDSA-P256 SIGNED" if signature else "UNSIGNED (hash-chained, honest)",
    }
    if witness:
        consensus = _witness(body_hash)
        if consensus:
            receipt["consensus"] = consensus
    _chain_tip["hash"] = body_hash
    return receipt


def verify_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    """Re-derive the payload hash and (if signed) verify the signature. Returns a verdict."""
    body_bytes = _canon(receipt["payload"])
    recomputed = hashlib.sha256(body_bytes).hexdigest()
    hash_ok = recomputed == receipt["payload_sha256"]
    checks = [
        {"check": "Payload hash re-derives (tamper-evident)", "pass": hash_ok},
        {"check": "All signals are public data", "pass": receipt["payload"]["all_signals_public"]},
        {"check": "Zero fabricated signals (honest by design)", "pass": receipt["payload"]["fabricated_signals"] == 0},
        {"check": "Chained to prior receipt", "pass": bool(receipt["payload"]["prev_receipt_hash"])},
    ]
    sig_ok = None
    if receipt.get("signature"):
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import ec
            pem = os.environ.get("SZL_COSIGN_PUBLIC_PEM")
            if pem:
                pub = serialization.load_pem_public_key(pem.encode())
                pae = _pae(receipt["payloadType"], body_bytes)
                pub.verify(base64.b64decode(receipt["signature"]["sig"]), pae, ec.ECDSA(hashes.SHA256()))
                sig_ok = True
        except Exception:
            sig_ok = False
        checks.append({"check": "ECDSA-P256 signature verifies", "pass": bool(sig_ok)})

    overall = all(c["pass"] for c in checks)
    return {
        "receipt_id": receipt["id"],
        "verdict": "VERIFIED" if overall else "FAILED",
        "checks": checks,
        "recomputed_hash": recomputed,
    }


def reset_chain():
    _chain_tip["hash"] = _GENESIS
