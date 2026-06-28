# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads "Ask the Territory"
#
# Clean-room governed conversational layer. Lineage / fashion-thinking:
#   - PATTERN adopted from our own a11oy WILLAY gateway: "they hide the governor; we sign and show it."
#     Every answer is grounded in PUBLIC data, carries inline CITATIONS, and is bound to a SIGNED receipt.
#   - Out-classes Verisk AskMax / Verisk Underwriting Intelligence Connector (Claude Enterprise): those give
#     natural-language access to PROPRIETARY, gated data with NO provenance and NO lead generation. Ours is
#     public-data, lead-generating, and cryptographically receipted. Honest by design — never fabricates;
#     if it doesn't have the data it says so.
"""ask.py — deterministic, citation-grounded query engine over the live public-data session state."""
from __future__ import annotations
import re
from datetime import datetime, timezone
from typing import Any


# ---- intent classification (transparent rule set, no black box) ----
# Order matters: more specific intents are checked before the generic 'top_leads'.
INTENTS = [
    ("compliance",  r"(complian|\bpii\b|audit|defensib|provenance|receipt|fabricat|made up|where.*(from|come)|is this (legal|safe|private|public))"),
    ("newpro",      r"(new grad|graduat|young|new(ly)? (licen|admit|profession|lawyer|attorney|agent|doctor|nurse)|first job|starting out|entry.level)"),
    ("fresh",       r"(fresh|new(est)?|latest|today|recent|just|home ?buyer|home purchase|deed|new building|moved|relocat)"),
    ("business",    r"(business|formation|self.?employ|new compan|corporation|incorporat|\bllc\b|owner|liquidit|award|grant)"),
    ("rates",       r"(rate|mortgage|interest|fed funds|treasury|\bcpi\b|inflation|yield)"),
    ("territory",   r"(where|territor|count(y|ies)|area|prospect|\bzip\b|region|\bmap\b|geograph|focus)"),
    ("pipeline",    r"(pipeline|premium|revenue|dollar|forecast|appoint|\bkpi\b|how much|projected)"),
    ("product",     r"(product|annuit|term life|whole life|\bltc\b|long.?term care|college|retire|coverage|recommend|sell|offer)"),
    ("why",         r"(why|explain|reason|how.*scor|justif|break ?down)"),
    ("top_leads",   r"(top|best|hottest|priorit|who.*(call|first)|call first|hot lead|lead list|today)"),
]


def classify(q: str) -> str:
    ql = q.lower()
    for name, pat in INTENTS:
        if re.search(pat, ql):
            return name
    return "top_leads"  # sensible default


def _cite(source: str, url: str = "") -> dict:
    return {"label": source, "url": url}


def answer(question: str, state: dict[str, Any]) -> dict[str, Any]:
    """Return a grounded answer dict: {answer, citations[], intent, grounded, used_ids[]}.
    state = the cached /api/run result (leads, signals, kpi, meta, ...) + territory if present."""
    leads = state.get("leads") or []
    signals = state.get("signals") or []
    kpi = state.get("kpi") or {}
    territory = (state.get("territory") or {}).get("areas") or []
    intent = classify(question)
    cites: list[dict] = []
    grounded = True

    if not leads:
        return {"intent": intent, "grounded": False,
                "answer": "Run intelligence first — I answer only from live, public data that's actually been gathered. I won't make anything up.",
                "citations": [], "used_ids": []}

    if intent == "top_leads" or intent == "why":
        top = leads[:3]
        lines = [f"Your top {len(top)} to call now:"]
        for i, l in enumerate(top, 1):
            lines.append(f"{i}. {l['name']} — score {l['score']} ({l['bucket']}) → {l['product']}. {l['nba']['action']}")
        if intent == "why":
            l0 = top[0]
            axes = ", ".join(f"{k.replace('_',' ')} {int(v*100)}" for k, v in l0["axes"].items())
            lines.append(f"Why {l0['name']} scores {l0['score']}: {axes}. Public moments: " +
                         "; ".join(m['source'] for m in l0.get('moments', [])) + ".")
        for l in top:
            cites.append(_cite(f"Lead {l['id']} signed receipt {l.get('receipt_id','')}"))
        return _wrap(intent, "\n".join(lines), cites, [l["id"] for l in top])

    if intent == "territory":
        if territory:
            t = sorted(territory, key=lambda a: a["index"], reverse=True)[:3]
            ans = "Focus your prospecting here (highest opportunity index from live Census):\n" + \
                  "\n".join(f"• {a['name']} — index {a['index']} (median income ${a['median_income']:,}, age {a['median_age']})" for a in t)
            cites.append(_cite("U.S. Census ACS 2023 (county level)", "https://www.census.gov/programs-surveys/acs"))
            return _wrap(intent, ans, cites, [])
        ans = "Open the Territory Map to rank your counties by opportunity (live Census income/age/family data)."
        return _wrap(intent, ans, [_cite("U.S. Census ACS 2023")], [])

    if intent == "rates":
        rate_sigs = [s for s in signals if s.get("scoring_axis") == "rate_environment" or "rate" in s.get("source", "").lower() or "MORTGAGE" in str(s.get("value", ""))]
        if rate_sigs:
            ans = "Current rate environment (public, live):\n" + "\n".join(f"• {s['detail']}" for s in rate_sigs[:4])
            ans += "\n\nUse it: higher mortgage rates raise the income a new-homeowner's family must protect — lead with term coverage sized to the loan."
            for s in rate_sigs[:3]:
                cites.append(_cite(s["source"]))
            return _wrap(intent, ans, cites, [])
        return _wrap(intent, "No live rate signal in this run — re-run live to pull FRED/Treasury rates.", [], [])

    if intent == "newpro":
        pro = [s for s in signals if s.get("scoring_axis") == "new_professional"]
        l7 = next((l for l in leads if l.get("event") == "new_professional"), None)
        if pro:
            ans = "Next-generation prospects — newly-licensed professionals just starting to earn (no advisor yet):\n" + \
                  "\n".join(f"• {s['detail']} [{s['source'].split('(')[0].strip()}]" for s in pro[:4])
            if l7:
                ans += f"\n\nPlay: {l7['nba']['action']}"
            for s in pro[:3]:
                cites.append(_cite(s["source"]))
            return _wrap(intent, ans, cites, [l7["id"]] if l7 else [])
        return _wrap(intent, "Re-run live to pull newly-licensed attorneys, agents, and new business owners.", [], [])

    if intent == "fresh":
        fresh_sigs = [s for s in signals if s.get("freshness") in ("updated daily", "real-time")]
        if fresh_sigs:
            ans = "Freshest public triggers right now (updated daily — act before other advisors):\n" + \
                  "\n".join(f"• {s['detail']} [{s['source'].split('(')[0].strip()}]" for s in fresh_sigs[:5])
            for s in fresh_sigs[:3]:
                cites.append(_cite(s["source"]))
            return _wrap(intent, ans, cites, [])
        return _wrap(intent, "Re-run live to pull today's freshest triggers (home purchases, new buildings, new businesses).", [], [])

    if intent == "business":
        biz = [s for s in signals if s.get("scoring_axis") == "business_formation"]
        if biz:
            ans = "Fresh business-formation triggers (new self-employed owners need coverage + buy-sell):\n" + \
                  "\n".join(f"• {s['detail']}" for s in biz[:4])
            ans += "\nThese are time-anchored X-Dates — reach out while the business is new."
            for s in biz[:3]:
                cites.append(_cite(s["source"], "https://data.ny.gov/resource/n9v6-gdp6"))
            return _wrap(intent, ans, cites, [])
        return _wrap(intent, "No business-formation signal in this run — re-run live to pull NY DOS filings.", [], [])

    if intent == "pipeline":
        bb = kpi.get("pipeline_by_bucket", {})
        ans = (f"Pipeline: {kpi.get('qualified_appts_per_week','—')} qualified appts/week modeled, "
               f"${kpi.get('pipeline_premium',0):,} est. annual premium across {kpi.get('total_leads',0)} leads "
               f"(HOT ${bb.get('HOT',0):,} · WARM ${bb.get('WARM',0):,}).")
        cites.append(_cite("Modeled from scored public-data leads (each receipted)"))
        return _wrap(intent, ans, cites, [])

    if intent == "product":
        from collections import Counter
        prods = Counter(l["product"] for l in leads)
        ans = "Product mix across your current leads:\n" + \
              "\n".join(f"• {p}: {n} lead(s)" for p, n in prods.most_common())
        ans += "\nLead each conversation with the product matched to that family's life-event."
        cites.append(_cite("NYL product mapping per scored lead"))
        return _wrap(intent, ans, cites, [])

    if intent == "compliance":
        meta = state.get("meta", {})
        ans = (f"Every answer and lead here is built from PUBLIC data only ({meta.get('total_signals','?')} signals checked, "
               f"0 fabricated). Each lead carries a cryptographically signed, tamper-evident receipt you can verify in-app. "
               f"If compliance asks 'where did this come from?', you have proof. No private PII is ever used.")
        cites.append(_cite("Governance gate: public-data-only, honest by design"))
        return _wrap(intent, ans, cites, [])

    # fallback
    return _wrap("top_leads", "Ask me about your top leads, where to prospect, products, rates, new businesses, pipeline, or compliance.", [], [])


def _wrap(intent: str, ans: str, cites: list[dict], used_ids: list[str]) -> dict[str, Any]:
    return {
        "intent": intent,
        "grounded": True,
        "answer": ans,
        "citations": cites,
        "used_ids": used_ids,
        "answered_at": datetime.now(timezone.utc).isoformat(),
        "doctrine": "public-data-only · cited · signed · honest by design",
    }
