# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads V8.2 · P1-E coverage-gap identifier
"""
coverage.py — pure-function "Likely gap" identifier (Salesforce FSC coverage-gap detection,
EZLynx renewal cross-sell, lighter-weight + rules-based).

Given an event_type and the prospect's OPTIONAL held_policies (default: none known), compute
the single most-likely coverage gap to lead the conversation with. No network, no fabrication
— if nothing applies and policies are unknown, returns a generic coverage-review prompt.
"""
from __future__ import annotations

from typing import Any, Iterable

# event_type -> (gap label, the held-policy keyword that would CLOSE this gap, recommended product)
_GAP_RULES: dict[str, tuple[str, tuple[str, ...], str]] = {
    "business_formation":       ("key-person gap", ("key-person", "key_person", "keyperson", "buy-sell", "buy_sell"),
                                 "Key-person life + buy-sell funding"),
    "home_purchase":            ("mortgage-protection gap", ("mortgage", "mortgage-protection", "mortgage_protection"),
                                 "Mortgage-protection term tied to the loan balance"),
    "new_baby":                 ("education-funding gap", ("education", "529", "college", "education_funding"),
                                 "Education-funding strategy + family term coverage"),
    "near_retirement":          ("income/LTC gap", ("annuity", "ltc", "long-term-care", "long_term_care"),
                                 "Annuity + long-term-care review"),
    "promotion":                ("income-protection gap", ("disability", "di", "income-protection"),
                                 "Disability-income to protect peak earnings"),
    "new_professional_license": ("starter-coverage gap", ("term", "disability", "di"),
                                 "Starter term + disability income"),
    "address_change":           ("beneficiary/coverage-refresh gap", ("review", "refresh"),
                                 "Coverage refresh + beneficiary review"),
}


def _has_policy(held: Iterable[str] | None, keywords: tuple[str, ...]) -> bool:
    if not held:
        return False
    blob = " ".join(str(h).lower() for h in held)
    return any(k in blob for k in keywords)


def likely_gap(event_type: str, held_policies: Iterable[str] | None = None) -> dict[str, Any]:
    """Compute the likely coverage gap for an event_type given optional held policies."""
    rule = _GAP_RULES.get(event_type or "")
    if rule is None:
        return {
            "has_gap": True,
            "label": "coverage-review opportunity",
            "recommended": "General coverage review",
            "basis": "no event-specific rule; defaulting to a coverage review",
            "held_policies_known": bool(held_policies),
            "advisory": True,
        }
    label, close_keywords, recommended = rule
    closed = _has_policy(held_policies, close_keywords)
    return {
        "has_gap": not closed,
        "label": ("covered: " + label.replace(" gap", "")) if closed else label,
        "recommended": recommended,
        "basis": ("held policy appears to close this gap" if closed
                  else "no closing policy supplied (default: gap likely open)"),
        "held_policies_known": bool(held_policies),
        "advisory": True,
    }
