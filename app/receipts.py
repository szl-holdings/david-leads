# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads
"""
Tamper-evident source and guarded-workflow receipts.

If a signing key is present (env SZL_COSIGN_PRIVATE_PEM), the module produces an
ECDSA-P256 DSSE-style signature over the canonical payload. Without that key it emits a
clearly labeled UNSIGNED, hash-linked receipt; it never fabricates a signature.

A receipt binds the normalized payload and its declared predecessor hash. The chain tip and
public receipt cache are process memory unless a separate durable store is explicitly configured;
verification without the predecessor checks only the declared link, not historical continuity.
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
    # DSSE Pre-Authentication Encoding — ASCII-decimal DSSE-v1 form (cosign
    # verify-blob compatible), shared byte-for-byte with app/consensus.py and
    # khipu-consensus. NOTE: this DIVERGES from szl-receipt's struct-packed PAE;
    # do NOT delegate to szl-receipt without a coordinated re-sign, or existing
    # lead receipts stop verifying. Locked by tests/test_receipt_bus_parity.py.
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


_PERMITTED_SOURCE_CLASSES = {"PUBLIC", "FIRST_PARTY_CONSENT", "INTERNAL_OPERATIONAL"}


def _normalize_signals(signals: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized = []
    for signal in signals or []:
        public = signal.get("public") is True
        raw_source_class = signal.get("source_class")
        source_class = (
            str(raw_source_class).strip().upper()
            if raw_source_class
            else ("PUBLIC" if public else "UNCLASSIFIED")
        )
        normalized.append({
            "source": signal["source"],
            "signal": signal.get("signal", ""),
            "public": public,
            "source_class": source_class,
            "fabricated": bool(signal.get("fabricated", False)),
        })
    return normalized


def _source_classes(signals: list[dict[str, Any]]) -> list[str]:
    return sorted({signal["source_class"] for signal in signals})


def _sources_permitted(source_classes: list[str]) -> bool:
    return bool(source_classes) and all(
        source_class in _PERMITTED_SOURCE_CLASSES for source_class in source_classes
    )


def make_receipt(lead: dict[str, Any], signals: list[dict[str, Any]], score: float,
                 witness: bool = True) -> dict[str, Any]:
    """Build a tamper-evident receipt for a single scored lead.

    When witness=True, attach a 3-of-4 khipu multi-party consensus block over the payload."""
    ts = datetime.now(timezone.utc).isoformat()
    normalized_signals = _normalize_signals(signals)
    source_classes = _source_classes(normalized_signals)
    body = {
        "lead_id": lead["id"],
        "lead_name": lead["name"],
        "score": round(float(score), 2),
        "bucket": lead["bucket"],
        "product": lead["product"],
        "signals_used": normalized_signals,
        "source_classes": source_classes,
        "all_sources_permitted": _sources_permitted(source_classes),
        "all_signals_public": all(s["public"] for s in normalized_signals),
        "fabricated_signals": sum(1 for s in normalized_signals if s["fabricated"]),
        "timestamp": ts,
        "prev_receipt_hash": _chain_tip["hash"],
        "doctrine": "SZL governed-AI · source-classified · honest by design",
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
    normalized_signals = _normalize_signals(signals or [])
    source_classes = _source_classes(normalized_signals)
    body = {
        "kind": "signed-4-part-brief",
        "lead_id": brief["lead_id"],
        "lead_name": brief.get("lead_name", ""),
        "score": round(float(brief.get("score", 0.0)), 2),
        "bucket": brief.get("bucket", ""),
        "freshness_state": brief.get("freshness_state", ""),
        "parts": [{"key": pt["key"], "body": pt["body"]} for pt in brief.get("parts", [])],
        "citations": sorted(set(cite_sources)),
        "signals_used": normalized_signals,
        "source_classes": source_classes,
        "all_sources_permitted": _sources_permitted(source_classes),
        "all_signals_public": all(
            signal["public"] for signal in normalized_signals
        ),
        "fabricated_signals": sum(
            1 for signal in normalized_signals if signal["fabricated"]
        ),
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


def verify_receipt(
    receipt: dict[str, Any],
    previous_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify payload, signature, and any supplied predecessor as distinct states."""
    body_bytes = _canon(receipt["payload"])
    recomputed = hashlib.sha256(body_bytes).hexdigest()
    hash_ok = recomputed == receipt["payload_sha256"]
    payload = receipt["payload"]
    normalized_signals = _normalize_signals(payload.get("signals_used") or [])
    source_classes = _source_classes(normalized_signals)
    sources_permitted = _sources_permitted(source_classes)
    declared_source_classes = payload.get("source_classes")
    source_summary_consistent = (
        declared_source_classes is None
        or sorted({str(value).strip().upper() for value in declared_source_classes})
        == source_classes
    )
    permission_summary_consistent = (
        payload.get("all_sources_permitted") is None
        or payload.get("all_sources_permitted") is sources_permitted
    )
    previous_hash = payload.get("prev_receipt_hash")
    pointer_valid = (
        isinstance(previous_hash, str)
        and len(previous_hash) == 64
        and all(character in "0123456789abcdef" for character in previous_hash)
    )
    checks = [
        {"check": "Payload hash re-derives (tamper-evident)", "pass": hash_ok},
        {"check": "Source-class summary matches bound signals", "pass": source_summary_consistent},
        {"check": "Evidence source classes are permitted", "pass": sources_permitted},
        {"check": "Permission summary matches source classes", "pass": permission_summary_consistent},
        {"check": "Zero fabricated signals declared", "pass": payload["fabricated_signals"] == 0},
        {"check": "Predecessor pointer is structurally valid", "pass": pointer_valid},
    ]
    if not pointer_valid:
        chain_state = "FAILED"
    elif previous_hash == _GENESIS:
        chain_state = "GENESIS_DECLARED"
    elif previous_receipt is None:
        chain_state = "UNVERIFIED_PREDECESSOR"
    else:
        previous_body = previous_receipt.get("payload")
        previous_declared = previous_receipt.get("payload_sha256")
        previous_recomputed = (
            hashlib.sha256(_canon(previous_body)).hexdigest()
            if isinstance(previous_body, dict)
            else None
        )
        predecessor_ok = (
            previous_recomputed is not None
            and previous_recomputed == previous_declared
            and previous_hash == previous_recomputed
        )
        checks.append({
            "check": "Supplied predecessor re-derives and matches pointer",
            "pass": predecessor_ok,
        })
        chain_state = "VERIFIED" if predecessor_ok else "FAILED"
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

    integrity_ok = all(
        check["pass"] for check in checks if "signature" not in check["check"].lower()
    )
    signed = bool(receipt.get("signature"))
    if not integrity_ok or (signed and sig_ok is not True):
        verdict = "FAILED"
    elif signed:
        verdict = "SIGNATURE_VERIFIED"
    else:
        verdict = "HASH_INTEGRITY_VERIFIED"
    consensus = receipt.get("consensus")
    if isinstance(consensus, dict):
        signing_mode = str(consensus.get("signing_mode") or "UNAVAILABLE")
        witness = {
            "state": (
                "THRESHOLD_REACHED"
                if consensus.get("signed") is True
                else "UNSIGNED_OR_UNAVAILABLE"
            ),
            "consensus": consensus.get("khipu_consensus"),
            "signing_mode": signing_mode,
            "durability": (
                "PROCESS_EPHEMERAL"
                if "ephemeral" in signing_mode.lower()
                else "DECLARED_BY_RECEIPT"
            ),
        }
    else:
        witness = {
            "state": "UNAVAILABLE",
            "consensus": None,
            "signing_mode": "UNAVAILABLE",
            "durability": "UNAVAILABLE",
        }
    return {
        "receipt_id": receipt["id"],
        "verdict": verdict,
        "integrity_state": "VERIFIED" if integrity_ok else "FAILED",
        "signature_state": "VERIFIED" if sig_ok is True else "FAILED" if signed else "UNSIGNED",
        "chain_state": chain_state,
        "source_classes": source_classes,
        "claim_scope": (
            "INTEGRITY_SIGNATURE_AND_CHAIN"
            if chain_state == "VERIFIED" and sig_ok is True
            else "INTEGRITY_AND_PROVENANCE_METADATA_ONLY"
        ),
        "witness": witness,
        "checks": checks,
        "recomputed_hash": recomputed,
    }


def reset_chain():
    _chain_tip["hash"] = _GENESIS
