# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads · ONE-chain bridge (insurance vertical)
"""
org_chain.py — emit David Leads lead-scoring events into the sovereign org's ONE chain.

David Leads is folded into the sovereign org as the **insurance** vertical. Every real
lead score can be mirrored into the canonical org receipt chain
(`szl.lake.receipt/v1`, SHA3-256 Khipu hash-chain, append-only NDJSON — the exact envelope
produced by a11oy/szl_lake_store.py) under the verb `insurance|score.lead`.

SAFETY — this NEVER breaks the live standalone app:
  • Active ONLY when the env var SZL_LAKE_DIR points at a writable org-lake directory.
    On the live David Leads HF Space (where SZL_LAKE_DIR is unset) this is an honest no-op
    that returns {"chain": "N/A"} and writes nothing — the standalone app is untouched.
  • Every call is best-effort and exception-swallowing; a chain-write failure can never
    propagate into /api/run.

Honesty: `insurance|score.lead` is REAL (this is the live scoring path). `insurance|bind.policy`
is **ROADMAP** — David Leads has no policy-binding path (genome Q3-INS-16). We never emit a
bind.policy receipt, because there is no real binding to attest.

stdlib-only. Byte-compatible with szl_lake_store.append() so receipts written here verify in
the org lake identically.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from datetime import datetime, timezone
from typing import Any

CHAIN_HASH = "sha3_256"
SCHEMA = "szl.lake.receipt/v1"
_ORGAN_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_LOCK = threading.Lock()


def _enabled() -> bool:
    return bool(os.environ.get("SZL_LAKE_DIR"))


def _lake_dir() -> str:
    return os.path.abspath(os.environ.get("SZL_LAKE_DIR", "khipu"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("utf-8")


def _sha3(b: bytes) -> str:
    return hashlib.sha3_256(b).hexdigest()


def _organ_partitions(organ_dir: str) -> list[str]:
    if not os.path.isdir(organ_dir):
        return []
    return sorted(os.path.join(organ_dir, f) for f in os.listdir(organ_dir)
                  if f.endswith(".ndjson"))


def _chain_head(organ_dir: str) -> tuple[str | None, int, set]:
    """Replay an organ's partitions for (chain_head, max_index, seen receipt_ids)."""
    head, idx, seen = None, 0, set()
    for path in _organ_partitions(organ_dir):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        env = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    rid = env.get("receipt_id")
                    if rid:
                        seen.add(rid)
                    ci = env.get("chain_index")
                    if isinstance(ci, int) and ci > idx:
                        idx = ci
                    ch = env.get("chain_hash")
                    if ch:
                        head = ch
        except OSError:
            continue
    return head, idx, seen


def emit_score_lead(lead: dict[str, Any]) -> dict[str, Any]:
    """Mirror one insurance lead-score event into the ONE org chain (or honest N/A).

    Verb: insurance|score.lead. Returns the append result {accepted, chain_index, chain_head,
    verb, chain} or {"chain": "N/A", ...} when SZL_LAKE_DIR is unset (live Space) or on any
    error. NEVER raises — safe to call inside /api/run.
    """
    verb = "insurance|score.lead"
    if not _enabled():
        return {"chain": "N/A", "verb": verb,
                "reason": "SZL_LAKE_DIR unset — standalone app, no org-chain write"}
    organ = "insurance"
    if not _ORGAN_RE.match(organ):
        return {"chain": "N/A", "verb": verb, "reason": "invalid organ"}
    try:
        payload = {
            "lead_id": lead.get("id"),
            "score": lead.get("score"),
            "bucket": lead.get("bucket"),
            "product": lead.get("product"),
            "event_type": lead.get("event_type"),
            "receipt_id_local": lead.get("receipt_id"),
        }
        receipt = {
            "organ": organ, "verb": verb, "action": "score.lead",
            "vertical": "insurance", "decision": "ALLOW", "ts": _now_iso(),
            "payload": payload, "schema_hint": SCHEMA,
            "source": "david-leads/app/server.py:/api/run",
        }
        rid = _sha3(_canonical_json(receipt))
        ts = receipt["ts"]
        organ_dir = os.path.join(_lake_dir(), organ)
        with _LOCK:
            head, idx, seen = _chain_head(organ_dir)
            if rid in seen:
                return {"chain": SCHEMA, "verb": verb, "accepted": False,
                        "duplicate": True, "chain_index": idx, "chain_head": head}
            chain_index = idx + 1
            chain_hash = _sha3(_canonical_json({
                "prev_hash": head, "receipt_id": rid, "organ": organ,
                "ts": ts, "chain_index": chain_index,
            }))
            envelope = {
                "schema": SCHEMA, "chain_alg": CHAIN_HASH, "organ": organ,
                "receipt_id": rid, "prev_hash": head, "chain_hash": chain_hash,
                "chain_index": chain_index, "ts": ts, "ingested_at": _now_iso(),
                "energy": {"label": "UNAVAILABLE"}, "receipt": receipt,
            }
            date = ts[:10]
            os.makedirs(organ_dir, exist_ok=True)
            path = os.path.join(organ_dir, f"{date}.ndjson")
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(envelope, sort_keys=True,
                                    separators=(",", ":")) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        return {"chain": SCHEMA, "verb": verb, "accepted": True, "duplicate": False,
                "receipt_id": rid, "chain_index": chain_index, "chain_head": chain_hash}
    except Exception as e:  # never break /api/run
        return {"chain": "N/A", "verb": verb, "reason": f"org-chain emit failed: {e!r}"}
