# SPDX-License-Identifier: Apache-2.0
"""Machine-readable public-data and outreach policy for David Leads.

This module is deliberately conservative. Public visibility does not by itself
make a source lawful to scrape, enrich, resell, or use for automated outreach.
"""
from __future__ import annotations

from datetime import date


POLICY_VERSION = "2026-08-28"

SOURCE_CLASSES = [
    {
        "id": "official-open-data",
        "label": "Official open data / public API",
        "ingestion": "ALLOWED_WITH_CONTROLS",
        "examples": [
            "DOL Form 5500",
            "FMCSA Company Census",
            "USAspending",
            "EPA ECHO",
            "SEC EDGAR",
            "U.S. Census",
            "state open-data portals",
        ],
        "controls": [
            "Use documented endpoints and identify the application.",
            "Respect rate limits, terms, dataset licenses, and retention requirements.",
            "Store source URL, observed timestamp, query, and truth label with every signal.",
            "Re-check the current record before outreach; a filing is a signal, not present-tense truth.",
            "Bind normalized records to parser version, source record ID, hash, and receipt.",
        ],
    },
    {
        "id": "official-registry",
        "label": "Official registry without a documented bulk API",
        "ingestion": "MANUAL_OR_LICENSED_ONLY",
        "examples": ["state licensing lookup", "state corporate search", "county clerk search"],
        "controls": [
            "Prefer an official export or licensed API.",
            "Do not bypass access controls, CAPTCHAs, or anti-bot measures.",
            "Record the registry terms and the human verification date.",
        ],
    },
    {
        "id": "business-web",
        "label": "Public business website",
        "ingestion": "LIMITED_RESEARCH",
        "examples": ["company contact page", "company newsroom", "company RSS feed"],
        "controls": [
            "Use business contact information only.",
            "Honor robots.txt and site terms; cache lightly and rate-limit.",
            "Do not infer sensitive traits or collect personal contact details.",
        ],
    },
    {
        "id": "social-platform",
        "label": "Social network / professional profile",
        "ingestion": "NO_UNAPPROVED_SCRAPING",
        "examples": ["LinkedIn", "Facebook", "Instagram", "X"],
        "controls": [
            "Do not scrape profiles or copy member data into lead records.",
            "Use approved APIs, first-party lead forms, ads, or human research only.",
            "Do not use social data to infer health, finances, family status, or other sensitive traits.",
        ],
    },
    {
        "id": "consumer-report",
        "label": "Consumer report / data-broker enrichment",
        "ingestion": "PROHIBITED_BY_DEFAULT",
        "examples": ["credit data", "people-search data", "purchased personal profiles"],
        "controls": [
            "Do not ingest without written counsel and compliance approval.",
            "Never use David Leads for underwriting, eligibility, pricing, or adverse action.",
            "Complete data-broker-status and FCRA reviews before any proposed use.",
        ],
    },
]

OUTREACH_GATES = [
    {
        "id": "public-business-record",
        "label": "Public business or license record",
        "decision": "RESEARCH_REQUIRED",
        "requirements": [
            "Verify the current official record and business identity.",
            "Find a business contact channel from the business itself.",
            "Check federal and state calling/texting/email rules at execution time.",
            "Check internal and company-specific suppression lists.",
            "Use manual, truthful outreach; no auto-dialing or prerecorded/AI voice.",
        ],
    },
    {
        "id": "first-party-opt-in",
        "label": "First-party express opt-in",
        "decision": "ELIGIBLE_AFTER_VERIFICATION",
        "requirements": [
            "Retain the exact consent language, scope, timestamp, source, and receipt.",
            "Confirm the requested channel and that consent has not been revoked.",
            "Honor quiet hours, suppression requests, and applicable state rules.",
        ],
    },
    {
        "id": "sample-or-modeled",
        "label": "Sample, aggregate, or modeled record",
        "decision": "DO_NOT_CONTACT",
        "requirements": [
            "Use for product demonstration or territory planning only.",
            "Never export or present a modeled persona as a real person.",
        ],
    },
]

OFFICIAL_GUIDANCE = [
    {
        "label": "FTC Telemarketing Sales Rule compliance",
        "url": "https://www.ftc.gov/business-guidance/resources/complying-telemarketing-sales-rule",
    },
    {
        "label": "FTC CAN-SPAM compliance guide",
        "url": "https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business",
    },
    {
        "label": "FCC unwanted calls and texts guidance",
        "url": "https://www.fcc.gov/consumers/guides/stop-unwanted-robocalls-and-texts",
    },
    {
        "label": "California DROP / Delete Act",
        "url": "https://privacy.ca.gov/drop/",
    },
    {
        "label": "EPA ECHO web services and data-use guidance",
        "url": "https://echo.epa.gov/tools/web-services",
    },
    {
        "label": "LinkedIn User Agreement",
        "url": "https://www.linkedin.com/legal/user-agreement",
    },
]

IMPLEMENTED_FRONTIERS = [
    {
        "id": "dol-form5500-benefit-timing",
        "status": "LIVE_ORGANIZATION_LIFE_PLAN_FIELDS_ONLY",
        "purpose": (
            "Reported organization benefit-plan timing for licensed broker research; "
            "anniversaries are hypotheses, never renewal or buying-intent claims."
        ),
        "included_fields": [
            "plan sponsor organization",
            "organization location",
            "participant count",
            "plan or policy period",
            "benefit categories",
        ],
        "excluded_fields": [
            "EIN",
            "signer, preparer, administrator, or named broker",
            "person-level address or contact",
            "commission",
        ],
        "contact_permission": "NEVER_INFERRED",
    },
    {
        "id": "fmcsa-company-census",
        "status": "LIVE_ENTITY_FIELDS_ONLY",
        "purpose": "Recent carrier-entity additions for owner-continuity and workforce research.",
        "admission": (
            "A recognized legal organization suffix is required; explicit individual or "
            "sole-proprietor classifications and names without that suffix fail closed."
        ),
        "included_fields": [
            "suffix-validated organization legal name and DBA",
            "USDOT identifier",
            "city, state, and ZIP",
            "reported equipment and driver counts",
        ],
        "excluded_fields": [
            "physical street address",
            "phone",
            "email",
            "named officers",
            "crash and safety fields",
            "insurance and policy fields",
        ],
        "contact_permission": "NEVER_INFERRED",
    },
    {
        "id": "usaspending-contract-activity",
        "status": "LIVE_ENTITY_FIELDS_ONLY",
        "purpose": "Recent federal contract activity for capacity and continuity research.",
        "excluded_claims": [
            "new award unless action history is verified",
            "award amount as revenue or cash flow",
            "award activity as proof of insurability or a coverage gap",
        ],
    },
    {
        "id": "epa-echo-monitoring-activity",
        "status": "LIVE_ENTITY_AND_FACILITY_FIELDS_ONLY",
        "purpose": (
            "Recent facility compliance-monitoring activity for factual, licensed "
            "environmental/property/continuity research."
        ),
        "excluded_fields": [
            "compliance status",
            "violations",
            "penalties",
            "community demographics",
            "personal contacts",
        ],
        "excluded_claims": [
            "unsafe facility",
            "legal guilt",
            "claim likelihood",
            "insurability or a coverage gap",
        ],
    },
]

DEFERRED_FRONTIERS = [
    {
        "id": "faa-aircraft-registry",
        "status": "PRIVACY_REVIEW_REQUIRED",
        "reason": (
            "The daily bulk file mixes corporate and individual ownership and now supports "
            "owner-information withholding. No ingestion until corporate-only minimization "
            "and deletion handling are approved."
        ),
    },
    {
        "id": "sam-gov-entities-opportunities",
        "status": "KEY_AND_TERMS_REVIEW_REQUIRED",
        "reason": "Use only through the documented API with an approved key and field-purpose map.",
    },
    {
        "id": "fcc-uls-organization-bulk",
        "status": "BULK_PARSER_AND_PRIVACY_TEST_REQUIRED",
        "reason": (
            "High-value organization licensing data is public, but the bulk files mix "
            "person records and require an organization-only parser, daily-delta controls, "
            "and restart-safe ingestion before production."
        ),
    },
    {
        "id": "social-profiles",
        "status": "PROHIBITED_BY_DEFAULT",
        "reason": "Use approved lead forms, ads, APIs, or human research; do not scrape member profiles.",
    },
]


def policy_document() -> dict:
    return {
        "version": POLICY_VERSION,
        "reviewed_on": str(date(2026, 8, 28)),
        "purpose": "Entity-level B2B prospecting and first-party broker workflow; not underwriting or consumer profiling.",
        "evidence_constellation": {
            "schema": "david.evidence-constellation.v1",
            "automatic_identity_links": [
                "shared UEI or SAM UEI",
                "shared USDOT",
                "shared EPA FRS ID",
                "shared SEC CIK",
            ],
            "review_required_identity_links": [
                "exact normalized legal name, state, and ZIP candidate",
                "any mixed identifier and exact-match component",
                "unresolved organization identity",
            ],
            "prohibited_identity_links": [
                "unknown identifier systems",
                "fuzzy or probabilistic links without a labeled benchmark",
            ],
            "proof_dimensions": ["authority", "freshness", "corroboration", "integrity", "identity"],
            "clock_states": ["CURRENT", "RECHECK_DUE", "STALE", "UNKNOWN"],
            "permission_default": "PUBLIC_RESEARCH_ONLY",
            "proof_grade_is_sales_probability": False,
        },
        "source_classes": SOURCE_CLASSES,
        "outreach_gates": OUTREACH_GATES,
        "implemented_frontiers": IMPLEMENTED_FRONTIERS,
        "deferred_frontiers": DEFERRED_FRONTIERS,
        "official_guidance": OFFICIAL_GUIDANCE,
        "legal_status": "OPERATIONAL_GUARDRAIL_NOT_LEGAL_ADVICE",
        "counsel_review_required_for": [
            "automated calling or texting",
            "social-platform ingestion",
            "purchased or brokered personal data",
            "consumer-level profiling",
            "cross-state outreach campaigns",
            "data-broker registration or DROP applicability",
        ],
    }
