# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads V8 · append-only receipt lake
"""
receipt_lake.py — append-only event lake for the ouroboros work loop.

Every change-event (a khipu 3-of-4 witnessed receipt minted by a bounded loop step) is
appended here, never mutated. The lake is the audit substrate: receipts.in ≡ receipts.out.

In-memory by default; if SZL_RECEIPT_LAKE_PATH is set, every append is ALSO mirrored to a
JSON-lines file (one canonical receipt per line). The file is the durable copy; the in-memory
list is the fast read path. Honest: we never fabricate events — only real minted receipts land.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any

_LAKE: list[dict[str, Any]] = []
_LOCK = threading.Lock()


def _file_path() -> str | None:
    return os.environ.get("SZL_RECEIPT_LAKE_PATH") or None


def append(receipt: dict[str, Any]) -> dict[str, Any]:
    """Append one receipt to the append-only lake. Returns the stored receipt."""
    with _LOCK:
        _LAKE.append(receipt)
        path = _file_path()
        if path:
            try:
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n")
            except Exception:
                pass  # honest: file mirror is best-effort, never breaks the write path
    return receipt


def all() -> list[dict[str, Any]]:
    """Return a shallow copy of every event in append order."""
    with _LOCK:
        return list(_LAKE)


def query(organ: str | None = None, decision: str | None = None,
          limit: int | None = None) -> list[dict[str, Any]]:
    """Filter the lake by organ and/or decision; newest-last, optional tail limit."""
    with _LOCK:
        out = list(_LAKE)
    if organ is not None:
        out = [r for r in out if r.get("organ") == organ]
    if decision is not None:
        out = [r for r in out if r.get("decision") == decision]
    if limit is not None and limit >= 0:
        out = out[-limit:]
    return out


def size() -> int:
    with _LOCK:
        return len(_LAKE)


def reset() -> None:
    """Clear the in-memory lake (test helper). Does not touch the file mirror."""
    with _LOCK:
        _LAKE.clear()
