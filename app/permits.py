# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads V8.2 · P1-C permit-type → product-need classifier
"""
permits.py — pure-function classifier that turns the permit/construction records already
ingested by the seaboard pulse into insurance product-need categories. No network.

  residential_new_construction -> "new mortgage, likely no coverage"   (mortgage protection / term)
  commercial_addition          -> "business expansion / key-person"    (key-person / buy-sell)
  demolition_or_rebuild        -> "insurance review / disaster"         (coverage review)

classify_permit(text) maps free-text permit descriptions/types to a category by keyword.
permit_need_for_lead(lead) returns a permit_need only for leads whose event_type implies a
construction/property trigger (home_purchase, permit_filed) — otherwise None (honest).
"""
from __future__ import annotations

from typing import Any

# keyword -> category (checked in order; demolition first so "demo + rebuild" wins over "residential")
_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("demolition", "demolish", "demo ", "raze", "rebuild", "teardown", "tear-down", "fire damage", "disaster"),
     "demolition_or_rebuild"),
    (("commercial", "office", "retail", "tenant", "warehouse", "industrial", "addition", "expansion", "mixed-use"),
     "commercial_addition"),
    (("residential", "single-family", "single family", "dwelling", "new construction", "new home",
      "1-family", "2-family", "townhouse", "house"),
     "residential_new_construction"),
]

CATEGORY_NEED: dict[str, dict[str, str]] = {
    "residential_new_construction": {
        "need_category": "new mortgage, likely no coverage",
        "product_angle": "Mortgage protection / term tied to the new loan balance",
    },
    "commercial_addition": {
        "need_category": "business expansion / key-person",
        "product_angle": "Key-person life + buy-sell funding for the growing business",
    },
    "demolition_or_rebuild": {
        "need_category": "insurance review / disaster",
        "product_angle": "Coverage review after a rebuild/disaster event",
    },
}

# event_type -> default permit category (for leads that carry a property/permit trigger
# but no free-text permit description of their own).
_EVENT_DEFAULT_CATEGORY: dict[str, str] = {
    "home_purchase": "residential_new_construction",
    "permit_filed": "residential_new_construction",
    "business_formation": "commercial_addition",
}


def classify_permit(text: str) -> dict[str, Any]:
    """Classify a permit description/type string into a product-need category (pure)."""
    t = (text or "").lower()
    category = None
    for keywords, cat in _KEYWORDS:
        if any(k in t for k in keywords):
            category = cat
            break
    if category is None:
        return {"permit_type": "unclassified", "need_category": None,
                "product_angle": None, "public": True}
    need = CATEGORY_NEED[category]
    return {"permit_type": category, "public": True, **need}


def permit_need_for_lead(lead: dict[str, Any]) -> dict[str, Any] | None:
    """Return a permit_need dict for leads whose event_type implies a construction/property
    trigger; otherwise None. Prefers any free-text permit description on the lead."""
    desc = lead.get("permit_description") or lead.get("permit_type") or ""
    if desc:
        out = classify_permit(desc)
        if out.get("need_category"):
            return out
    et = lead.get("event_type") or ""
    cat = _EVENT_DEFAULT_CATEGORY.get(et)
    if not cat:
        return None
    return {"permit_type": cat, "public": True, **CATEGORY_NEED[cat]}
