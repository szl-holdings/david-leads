# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads V8.4
"""
edgar_fts.py — SEC EDGAR full-text-search 8-K workforce-event window (keyless).

New frontier for the coverage/WARN story: 8-K filings whose full text matches
workforce-restructuring language, fetched from the KEYLESS SEC EDGAR full-text
search API (efts.sec.gov). Server-side stdlib urllib (CORS irrelevant).

Honest by design (SZL doctrine):
  • REPORTED pass-through only — company display name, filing date, form type and
    accession number come from SEC's own index, EXACTLY as returned. Never invented.
  • Item 2.05 ("Costs Associated with Exit or Disposal Activities") is SEC's OWN
    classification for exit/disposal (incl. workforce reduction) events — when a hit
    carries it, we surface the flag as REPORTED; when absent, item_2_05 is False,
    never guessed.
  • A filing that MATCHES the phrase is a real regulatory artifact, not a verdict
    that layoffs happened — the card says "matched phrase", nothing stronger.
  • Upstream failure → status "UNAVAILABLE" with the error class disclosed.
    No cached fabrication, no [SAMPLE] rows for this window — absent means absent.
  • SEC fair-access: declared User-Agent with contact, one phrase-pair fetch per
    cache refresh (10-min OK cache / 60s negative), well under 10 req/s.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Any, Optional

UA = {"User-Agent": "SZL Holdings david-leads research@szlholdings.com"}
TIMEOUT = 12
BASE = "https://efts.sec.gov/LATEST/search-index"

# Two disclosed workforce-event phrases. Quoted → exact-phrase FTS match.
PHRASES = ('"reduction in force"', '"workforce reduction"')
WINDOW_DAYS = 90
MAX_ROWS = 8

_CACHE: dict[str, Any] = {}
_CACHE_LOCK = threading.Lock()
OK_TTL = 600      # 10 min when upstream answered
NEG_TTL = 60      # 60 s after a failure so recovery is fast


def _fetch_phrase(phrase: str, start: str, end: str) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({
        "q": phrase, "forms": "8-K", "dateRange": "custom",
        "startdt": start, "enddt": end,
    })
    req = urllib.request.Request(f"{BASE}?{params}", headers=UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        payload = json.loads(r.read().decode())
    out: list[dict[str, Any]] = []
    for hit in (payload.get("hits", {}) or {}).get("hits", []) or []:
        src = hit.get("_source", {}) or {}
        adsh = src.get("adsh")
        if not adsh:
            continue
        cik_list = src.get("ciks") or []
        cik = cik_list[0].lstrip("0") if cik_list else None
        doc = (hit.get("_id") or "").split(":", 1)
        filename = doc[1] if len(doc) == 2 else None
        url = None
        if cik and filename:
            url = (f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                   f"{adsh.replace('-', '')}/{filename}")
        out.append({
            "company": (src.get("display_names") or [None])[0],
            "form": src.get("form"),
            "file_date": src.get("file_date"),
            "adsh": adsh,
            "item_2_05": "2.05" in (src.get("items") or []),
            "matched_phrase": phrase.strip('"'),
            "url": url,   # real EDGAR archive doc; None when SEC omits pieces — never synthesized
            "state": (src.get("biz_states") or [None])[0],
        })
    return out


def workforce_events_window() -> dict[str, Any]:
    """8-K workforce-event window: REPORTED pass-through, cached, honest UNAVAILABLE."""
    now = time.time()
    with _CACHE_LOCK:
        cached = _CACHE.get("window")
        if cached and now < cached["expires"]:
            return cached["data"]

    today = date.today()
    start = (today - timedelta(days=WINDOW_DAYS)).isoformat()
    end = today.isoformat()
    try:
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for phrase in PHRASES:
            for row in _fetch_phrase(phrase, start, end):
                if row["adsh"] not in seen:
                    seen.add(row["adsh"])
                    rows.append(row)
        rows.sort(key=lambda r: r.get("file_date") or "", reverse=True)
        data = {
            "status": "OK",
            "label": "REPORTED",
            "basis": ("SEC EDGAR full-text search (keyless, efts.sec.gov) — 8-K filings "
                      "matching disclosed workforce-event phrases in the last "
                      f"{WINDOW_DAYS} days. A phrase match is a real filing, not a "
                      "verdict; Item 2.05 flag is SEC's own classification."),
            "window": {"start": start, "end": end},
            "phrases": [p.strip('"') for p in PHRASES],
            "signals": rows[:MAX_ROWS],
            "total_matched": len(rows),
        }
        ttl = OK_TTL
    except Exception as e:  # honest UNAVAILABLE — never fabricate
        data = {
            "status": "UNAVAILABLE",
            "label": "UNAVAILABLE",
            "basis": "SEC EDGAR full-text search fetch failed — no rows shown (never fabricated).",
            "error_class": type(e).__name__,
            "window": {"start": start, "end": end},
            "signals": [],
        }
        ttl = NEG_TTL

    with _CACHE_LOCK:
        _CACHE["window"] = {"data": data, "expires": time.time() + ttl}
    return data
