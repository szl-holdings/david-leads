# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads V8.2 · P1-B IRS Form 990 wealth/philanthropy signal
"""
wealth990.py — IRS Form 990 charitable-giving / philanthropy wealth signal via the
ProPublica Nonprofit Explorer API (public 990 filings). WealthEngine and Windfall both
use 990 giving/board data as a primary HNW indicator.

This is a SOFT, SUPPORTING signal — an inference, never an assertion. When a prospect
name token appears across nonprofit 990 filings (board roles / org name matches), it can
nudge the existing public-proxy wealth_tier UP BY AT MOST ONE TIER, clearly labelled
"990 public-record signal (inference)". Doctrine: public-data only; honest [SAMPLE]
fallback when ProPublica is unreachable — never fabricate matches.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

UA = "SZL-David-Leads research@szlholdings.com"
TIMEOUT = 12
_SEARCH_URL = "https://projects.propublica.org/nonprofits/api/v2/search.json?q={q}"

# Ordered tiers used by P0-3 wealth_tier — used here to bump up at most one step.
_TIER_ORDER = ["Mass", "Mass-Affluent", "Affluent", "HNW"]


def _get(url: str, timeout: int = TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def wealth990_signal(name: str) -> dict[str, Any]:
    """Search ProPublica Nonprofit Explorer for 990 filings matching a name token.

    Returns {matches, orgs:[{name, ein, state}], citation_url, public:True,
             mode:"LIVE"|"SAMPLE", note}. Honest [SAMPLE] when unreachable."""
    name = (name or "").strip()
    if not name:
        return _sample(name, "no name token supplied")
    q = urllib.parse.quote(name)
    citation_url = "https://projects.propublica.org/nonprofits/search?q=" + q
    try:
        data = json.loads(_get(_SEARCH_URL.format(q=q)))
        orgs_raw = data.get("organizations", []) or []
        total = int(data.get("total_results", len(orgs_raw)) or 0)
        orgs = [{"name": o.get("name", ""), "ein": o.get("ein"),
                 "state": o.get("state", "")} for o in orgs_raw[:5]]
        return {
            "matches": total,
            "orgs": orgs,
            "citation_url": citation_url,
            "public": True,
            "mode": "LIVE",
            "note": ("Appears in %d nonprofit 990 filing(s) — philanthropy/HNW inference (soft signal)." % total)
                    if total > 0 else "No nonprofit 990 filings matched this token.",
        }
    except Exception as e:
        return _sample(name, "ProPublica unreachable (%s)" % type(e).__name__)


def nudge_wealth_tier(current_tier: str, signal: dict[str, Any]) -> dict[str, Any]:
    """Bump the public-proxy wealth_tier UP BY AT MOST ONE step when a live 990 match exists.
    Returns {tier, nudged:bool, from, basis_note}. Never downgrades; never bumps on SAMPLE."""
    tier = current_tier if current_tier in _TIER_ORDER else "Mass"
    if signal.get("mode") == "LIVE" and int(signal.get("matches") or 0) > 0:
        idx = _TIER_ORDER.index(tier)
        new_idx = min(idx + 1, len(_TIER_ORDER) - 1)
        return {
            "tier": _TIER_ORDER[new_idx],
            "nudged": new_idx != idx,
            "from": tier,
            "basis_note": "990 public-record signal (inference) — %d filing match(es)" % int(signal.get("matches") or 0),
        }
    return {"tier": tier, "nudged": False, "from": tier,
            "basis_note": "no live 990 nudge (SAMPLE or no match)"}


def _sample(name: str, why: str) -> dict[str, Any]:
    return {
        "matches": None,
        "orgs": [],
        "citation_url": "https://projects.propublica.org/nonprofits/search?q=" + urllib.parse.quote(name or ""),
        "public": True,
        "mode": "SAMPLE",
        "note": "[SAMPLE] " + why + " — ProPublica Nonprofit Explorer 990 API is public; retry when reachable.",
    }
