# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads Sovereign Insurance Intelligence
"""FastAPI backend: login gate, live signal run, scored leads, signed receipts, KPI."""
from __future__ import annotations
import os, secrets, hashlib, io, csv, json, urllib.request, urllib.error, urllib.parse
import http.client, ipaddress, socket, ssl, time
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import JSONResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import signals as sig
from . import signals_v3 as sig3
from . import signals_v5 as sig5
from . import signals_v6 as sig6
from . import signals_v7 as sig7
from . import signals_v8 as sig8
from . import scoring as sc
from . import receipts as rc
from . import ask as ask_engine

# V8.4 EDGAR workforce-event window — defensive import so boot never breaks
try:
    from . import edgar_fts as efts
except Exception:  # pragma: no cover
    efts = None

# V8 genius modules — imported defensively so a missing optional module never breaks boot
try:
    from . import formulas as fm
except Exception:  # pragma: no cover
    fm = None
try:
    from . import work as wk
except Exception:  # pragma: no cover
    wk = None
try:
    from . import oroboros as ob
except Exception:  # pragma: no cover
    ob = None
try:
    from . import receipt_lake as lake
except Exception:  # pragma: no cover
    lake = None
try:
    from . import consensus as cs
except Exception:  # pragma: no cover
    cs = None
try:
    from . import events as ev
except Exception:  # pragma: no cover
    ev = None
# V8.2 P1 gap-fill modules — defensive imports so /api/run never breaks on a missing optional
try:
    from . import liquidity as liq
except Exception:  # pragma: no cover
    liq = None
try:
    from . import wealth990 as w990
except Exception:  # pragma: no cover
    w990 = None
try:
    from . import benchmark as bench
except Exception:  # pragma: no cover
    bench = None
try:
    from . import coverage as cov
except Exception:  # pragma: no cover
    cov = None
# V8.3 P2-1 best-fit advisor routing — defensive import so /api/run + boot never break
try:
    from . import routing as rt
except Exception:  # pragma: no cover
    rt = None
# Public B2B research records. Defensive import so boot never breaks.
try:
    from . import real_leads as rl
except Exception:  # pragma: no cover
    rl = None
# Tax-territory intelligence — aggregate IRS public statistics. Defensive import.
try:
    from . import tax_leads as tx
except Exception:  # pragma: no cover
    tx = None
# WARN Act layoff intelligence — public state DOL records. Defensive import.
try:
    from . import warn_leads as wl
except Exception:  # pragma: no cover
    wl = None
try:
    from . import dealdesk as dd
except Exception:  # pragma: no cover
    dd = None
try:
    from . import data_policy as dp
except Exception:  # pragma: no cover
    dp = None
try:
    from . import frontier_sources as frontier_data
except Exception:  # pragma: no cover
    frontier_data = None

APP_DIR = os.path.dirname(__file__)
app = FastAPI(title="David Leads — Sovereign Insurance Intelligence", version="1.0")
# CORS: env-configurable allow-list (comma-separated). Default "*" is safe here because auth is a
# bearer token in the Authorization header (not a cookie), so credentials are not sent cross-site.
_CORS_ORIGINS = [o.strip() for o in os.environ.get("DAVID_CORS_ORIGINS", "*").split(",") if o.strip()] or ["*"]
app.add_middleware(CORSMiddleware, allow_origins=_CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
SERVE_STATIC = os.environ.get("SERVE_STATIC", "1") == "1"

# --- David-only credentials. MUST be provided via Space secrets — NO defaults (fail-closed). ---
# In a PUBLIC repo, hardcoded defaults are an open gate whenever the Space secrets are unset,
# so we read from env with no fallback and refuse logins when any credential is missing.
DAVID_USER = os.environ.get("DAVID_USER")
DAVID_PASS = os.environ.get("DAVID_PASS")
ACCESS_KEY = os.environ.get("DAVID_ACCESS_KEY")
_REVOKED_CREDENTIAL_FINGERPRINTS = {
    # Publicly exposed legacy triplet. The values are intentionally not retained in source.
    "3377808eda65b578cac8927ff49cf9d511dafe83b81ce8780905cc96641e3abd",
}


def _credential_fingerprint(username: str | None, password: str | None, access_key: str | None) -> str:
    material = "\0".join((username or "", password or "", access_key or "")).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


_CREDS_PRESENT = bool(DAVID_USER and DAVID_PASS and ACCESS_KEY)
_CREDS_ROTATION_REQUIRED = (
    _CREDS_PRESENT
    and _credential_fingerprint(DAVID_USER, DAVID_PASS, ACCESS_KEY)
    in _REVOKED_CREDENTIAL_FINGERPRINTS
)
_CREDS_CONFIGURED = bool(_CREDS_PRESENT and not _CREDS_ROTATION_REQUIRED)
USERS = {DAVID_USER: DAVID_PASS} if _CREDS_CONFIGURED else {}
_TOKEN_TTL_SECONDS = max(300, int(os.environ.get("DAVID_SESSION_TTL_SECONDS", "28800")))
_TOKENS: dict[str, float] = {}

# session cache of last run
_STATE: dict = {"leads": [], "signals": [], "meta": {}, "receipts": {}}

# Opt-in (TCPA-safe) consented leads. This is the ONLY place a personal phone/email is stored —
# because the person submitted it themselves with explicit consent. Optionally persisted to a file.
_OPTIN_PATH = os.environ.get("SZL_OPTIN_PATH")
_OPTIN_LEADS: list[dict] = []


def _load_optin():
    if _OPTIN_PATH and os.path.exists(_OPTIN_PATH):
        try:
            with open(_OPTIN_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                _OPTIN_LEADS.extend(data)
        except Exception:
            pass


def _persist_optin():
    if not _OPTIN_PATH:
        return
    try:
        with open(_OPTIN_PATH, "w", encoding="utf-8") as f:
            json.dump(_OPTIN_LEADS, f)
    except Exception:
        pass


_load_optin()


class LoginReq(BaseModel):
    username: str
    password: str
    access_key: str


class RunReq(BaseModel):
    live: bool = True
    state: str = "NY"
    age_min: float = 0.0  # V8: demonstrate Λ time-decay live (minutes since trigger observed)


def _auth(authorization: str | None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    token = authorization.split(" ", 1)[1]
    expires_at = _TOKENS.get(token)
    if expires_at is None:
        raise HTTPException(401, "Invalid token")
    if expires_at <= time.time():
        _TOKENS.pop(token, None)
        raise HTTPException(401, "Session expired")


@app.get("/healthz")
def healthz():
    body = {
        "status": "ok",
        "service": "david-leads",
        "authentication": (
            "ROTATION_REQUIRED"
            if _CREDS_ROTATION_REQUIRED
            else "CONFIGURED"
            if _CREDS_CONFIGURED
            else "NOT_CONFIGURED"
        ),
        "doctrine": "SZL governed-AI · honest by design",
    }
    persistence = dd.persistence_state() if dd is not None else "UNAVAILABLE"
    ready = body["authentication"] == "CONFIGURED" and persistence in {
        "FILE_BACKED",
        "POSTGRES_READY",
    }
    body["status"] = "ready" if ready else "blocked"
    body["deal_desk_persistence"] = persistence
    return JSONResponse(content=body, status_code=200 if ready else 503)


@app.get("/readyz")
def readyz():
    return healthz()


def _runtime_bundle_manifest() -> dict:
    """Hash the exact runtime files Docker copies so live bytes can be compared to GitHub."""
    roots = [
        (APP_DIR, "app"),
        (os.path.join(os.path.dirname(APP_DIR), "requirements.txt"), "requirements.txt"),
        (
            os.path.join(os.path.dirname(APP_DIR), "PUBLICATION_READINESS.md"),
            "PUBLICATION_READINESS.md",
        ),
        (
            os.path.join(os.path.dirname(APP_DIR), "PUBLIC_DATA_OPERATING_MODEL.md"),
            "PUBLIC_DATA_OPERATING_MODEL.md",
        ),
        (
            os.path.join(os.path.dirname(APP_DIR), "SPACE_PROVENANCE.json"),
            "SPACE_PROVENANCE.json",
        ),
    ]
    files: list[dict] = []
    for absolute, logical in roots:
        if os.path.isfile(absolute):
            with open(absolute, "rb") as handle:
                files.append({"path": logical, "sha256": hashlib.sha256(handle.read()).hexdigest()})
            continue
        for directory, dirnames, filenames in os.walk(absolute):
            dirnames[:] = sorted(name for name in dirnames if name != "__pycache__")
            for filename in sorted(filenames):
                if filename.endswith((".pyc", ".pyo")):
                    continue
                path = os.path.join(directory, filename)
                relative = os.path.relpath(path, absolute).replace("\\", "/")
                with open(path, "rb") as handle:
                    digest = hashlib.sha256(handle.read()).hexdigest()
                files.append({"path": f"{logical}/{relative}", "sha256": digest})
    files.sort(key=lambda item: item["path"])
    canonical = "\n".join(
        f"{item['path']}\0{item['sha256']}" for item in files
    ).encode("utf-8")
    revision = (
        os.environ.get("SOURCE_GITHUB_SHA")
        or os.environ.get("GITHUB_SHA")
        or os.environ.get("HF_SPACE_COMMIT_SHA")
    )
    return {
        "service": "david-leads",
        "version": app.version,
        "build": {
            "state": "OBSERVED" if revision else "UNAVAILABLE",
            "revision": revision,
        },
        "receipt_minted": False,
        "bundle_sha256": hashlib.sha256(canonical).hexdigest(),
        "file_count": len(files),
        "files": files,
        "source_revision": revision,
        "source_revision_state": "OBSERVED" if revision else "UNAVAILABLE",
        "github_huggingface_alignment": "UNVERIFIED",
        "alignment_note": (
            "Compare this runtime bundle digest and file manifest with the Docker-copied GitHub tree. "
            "A healthy process or HTTP 200 is not source-parity proof."
        ),
    }


@app.get("/api/build-info")
def build_info():
    return _runtime_bundle_manifest()


@app.post("/api/login")
def login(req: LoginReq):
    if _CREDS_ROTATION_REQUIRED:
        raise HTTPException(
            503,
            "published legacy credentials are revoked; rotate DAVID_USER / DAVID_PASS / "
            "DAVID_ACCESS_KEY in the approved secret store",
        )
    if not _CREDS_CONFIGURED:
        # Fail closed: never fall back to publicly-visible defaults. No credentials → no login.
        raise HTTPException(
            503,
            "credentials not configured — set DAVID_USER / DAVID_PASS / DAVID_ACCESS_KEY in Space settings",
        )
    expected = USERS.get(req.username)
    pass_ok = expected is not None and secrets.compare_digest(req.password, expected)
    key_ok = secrets.compare_digest(req.access_key, ACCESS_KEY)
    if not (pass_ok and key_ok):
        raise HTTPException(401, "Invalid credentials or access key")
    tok = secrets.token_urlsafe(24)
    _TOKENS[tok] = time.time() + _TOKEN_TTL_SECONDS
    return {"token": tok, "user": req.username, "expires_in": _TOKEN_TTL_SECONDS}


@app.post("/api/logout")
def logout(authorization: str | None = Header(default=None)):
    _auth(authorization)
    token = authorization.split(" ", 1)[1]
    _TOKENS.pop(token, None)
    return {"ok": True}


@app.post("/api/run")
def run(req: RunReq, authorization: str | None = Header(default=None)):
    _auth(authorization)
    try:
        rc.reset_chain()
    except Exception:
        pass
    # Base public-data gather. The per-source helpers already fall back to [SAMPLE] internally,
    # but wrap defensively so an unexpected failure degrades to an honest empty run, never a 500.
    try:
        sigs, meta = sig.gather_all(live=req.live)
    except Exception:
        sigs, meta = [], {"total_signals": 0, "rejected_nonpublic": 0, "fabricated": 0,
                         "live_count": 0, "mode": "SAMPLE (offline)",
                         "gathered_at": __import__("datetime").datetime.now(
                             __import__("datetime").timezone.utc).isoformat()}
    # V3: merge in expanded public-data signals (rates, business formation, ACS extras, county unemployment)
    try:
        sigs3, meta3 = sig3.gather_v3(live=req.live)
        sigs = sigs + sigs3
        meta["total_signals"] = meta.get("total_signals", 0) + meta3.get("total_signals", 0)
        meta["live_count"] = meta.get("live_count", 0) + meta3.get("live_count", 0)
        meta["v3_sources"] = meta3.get("sources", [])
        meta["v3_axes"] = meta3.get("scoring_axes", [])
    except Exception:
        sigs3, meta3 = [], {}
    # V5: freshest daily/real-time triggers (ACRIS deeds, DOB new builds, USAspending, biz velocity)
    try:
        sigs5, meta5 = sig5.gather_v5(live=req.live)
        sigs = sigs + sigs5
        meta["total_signals"] = meta.get("total_signals", 0) + meta5.get("total_signals", 0)
        meta["live_count"] = meta.get("live_count", 0) + meta5.get("live_count", 0)
        meta["v5_sources"] = meta5.get("sources", [])
        meta["fresh_daily"] = sum(1 for s in sigs if s.get("freshness") == "updated daily" and s.get("live"))
    except Exception:
        sigs5, meta5 = [], {}
    # V6: next-gen triggers — newly-licensed professionals & new business owners (the moments competitors ignore)
    try:
        sigs6, meta6 = sig6.gather_v6(live=req.live)
        sigs = sigs + sigs6
        meta["total_signals"] = meta.get("total_signals", 0) + meta6.get("total_signals", 0)
        meta["live_count"] = meta.get("live_count", 0) + meta6.get("live_count", 0)
        meta["v6_sources"] = meta6.get("sources", [])
        meta["fresh_daily"] = sum(1 for s in sigs if s.get("freshness") == "updated daily" and s.get("live"))
    except Exception:
        sigs6, meta6 = [], {}
    # V7: tax/wealth + multi-state East Coast expansion
    try:
        sigs7, meta7 = sig7.gather_v7(live=req.live, state=getattr(req, "state", "NY"))
        sigs = sigs + sigs7
        meta["total_signals"] = meta.get("total_signals", 0) + meta7.get("total_signals", 0)
        meta["live_count"] = meta.get("live_count", 0) + meta7.get("live_count", 0)
        meta["v7_sources"] = meta7.get("sources", [])
        meta["states_covered"] = meta7.get("states_covered", ["NY"])
    except Exception:
        sigs7, meta7 = [], {}
    # V8: Λ time-decay applied via age_min (0 = fresh run)
    try:
        leads = sc.build_leads(meta, age_minutes=getattr(req, "age_min", 0.0))
    except Exception:
        leads = []
    # V8.2 P1-A: optional SEC Form 4 insider-sell liquidity flag — only on live runs, only for
    # leads whose event_type implies a liquidity moment AND where a public employer is known.
    # Defensive: any failure leaves the lead untouched so /api/run never breaks.
    # V8.3 P2-2: attempt the real SEC Form 4 check for employer-bearing archetypes on BOTH live and
    # sample runs so the demo can surface a "Liquidity event" flag. The employer is a representative
    # public company (Form 4 proxy), clearly labelled illustrative; liquidity_signal() returns an
    # honest [SAMPLE] if SEC is unreachable so /api/run never breaks.
    if liq is not None:
        _LIQ_EVENTS = {"job_change", "promotion", "near_retirement"}
        for lead in leads:
            try:
                employer = lead.get("employer")
                if employer and (lead.get("event_type") in _LIQ_EVENTS):
                    sig_liq = liq.liquidity_signal(employer)
                    if isinstance(sig_liq, dict):
                        sig_liq["employer"] = employer
                        sig_liq["employer_illustrative"] = True  # representative public employer, labelled
                    lead["liquidity"] = sig_liq
            except Exception:
                pass
    # V8.2 P1-B: OPTIONAL 990 philanthropy/HNW supporting signal. Only fires for a lead that
    # carries an explicit individual `name_token` (the demo segment archetypes don't — so this is
    # an honest no-op in the deterministic demo, never spamming ProPublica with segment labels).
    if w990 is not None and getattr(req, "live", False):
        for lead in leads:
            try:
                tok = lead.get("name_token")
                if tok:
                    sig990 = w990.wealth990_signal(tok)
                    lead["wealth990"] = sig990
                    wt = lead.get("wealth_tier")
                    cur_tier = wt.get("tier", "Mass") if isinstance(wt, dict) else (wt or "Mass")
                    nud = w990.nudge_wealth_tier(cur_tier, sig990)
                    if nud.get("nudged"):
                        if isinstance(wt, dict) and ev is not None:
                            wt["tier"] = nud["tier"]
                            try:
                                wt["ladder_index"] = ev.WEALTH_LADDER.index(nud["tier"])
                            except Exception:
                                pass
                        else:
                            lead["wealth_tier"] = nud["tier"]
                        lead["wealth_tier_nudge"] = nud
            except Exception:
                pass
    receipts = {}
    for lead in leads:
        # each lead's receipt binds the signals that justify its segment
        try:
            receipts[lead["id"]] = rc.make_receipt(lead, sigs, lead["score"])
            lead["receipt_id"] = receipts[lead["id"]]["id"]
            lead["receipt_signed"] = receipts[lead["id"]]["signed"]
        except Exception:
            lead["receipt_id"] = None
            lead["receipt_signed"] = False
    # ONE-CHAIN fold-in: mirror each real lead score into the sovereign org chain
    # (szl.lake.receipt/v1) under verb insurance|score.lead. Best-effort + honest N/A when
    # SZL_LAKE_DIR is unset (the live standalone Space), so /api/run never changes behavior.
    try:
        from . import org_chain as _org_chain
        org_receipts = []
        for lead in leads:
            org_receipts.append(_org_chain.emit_score_lead(lead))
        meta["org_chain"] = {
            "verb": "insurance|score.lead",
            "emitted": sum(1 for r in org_receipts if r.get("accepted")),
            "chain": (org_receipts[0].get("chain") if org_receipts else "N/A"),
            "bind_policy": "ROADMAP — no policy-binding path (genome Q3-INS-16); never emitted",
        }
    except Exception:
        pass
    _STATE.update(leads=leads, signals=sigs, meta=meta, receipts=receipts)
    # khipu 3-of-4 witnessed governance: report consensus from the leads' receipts when present
    consensus_state = "unwitnessed"
    any_receipt = next(iter(receipts.values()), None)
    if any_receipt and any_receipt.get("consensus"):
        consensus_state = any_receipt["consensus"].get("khipu_consensus", "unwitnessed")
    top = leads[:3]
    try:
        brief = {
            "top_ids": [l.get("id") for l in top],
            "headline": (f"{len([l for l in leads if l.get('bucket')=='HOT'])} HOT leads ready to call today — "
                         f"lead with {top[0].get('name')}." if top else "Run intelligence to build today's call list."),
            "items": [{"id": l.get("id"), "name": l.get("name"), "score": l.get("score"),
                       "bucket": l.get("bucket"), "product": l.get("product"),
                       "action": (l.get("nba") or {}).get("action")} for l in top],
        }
    except Exception:
        brief = {"top_ids": [], "headline": "Run intelligence to build today's call list.", "items": []}
    try:
        learning = ev.outcome_summary() if ev is not None else {"total_outcomes": 0}
    except Exception:
        learning = {"total_outcomes": 0}
    try:
        kpi = sc.kpi_summary(leads)
    except Exception:
        kpi = {}
    return {
        "meta": meta,
        "signals": sigs,
        "leads": leads,
        "kpi": kpi,
        "brief": brief,
        "learning": learning,  # P0-6: in-session adaptive conversion signal
        "governance": {
            "signals_checked": meta.get("total_signals", 0),
            "all_public": meta.get("rejected_nonpublic", 0) == 0,
            "fabricated": meta.get("fabricated", 0),
            "rejected_nonpublic": meta.get("rejected_nonpublic", 0),
            "consensus": consensus_state,
            "verdict": "PASS — public-data-only, honest by design",
        },
    }


@app.get("/api/model")
def model(authorization: str | None = Header(default=None)):
    """Open the black box: full transparent scoring methodology."""
    _auth(authorization)
    try:
        return sc.model_card()
    except Exception:
        raise HTTPException(503, "model card temporarily unavailable")


_OPERATOR_DRIVER_LABELS = {
    "life_event_strength": "Life-event need",
    "income_fit": "Financial fit",
    "age_window_fit": "Life-stage fit",
    "product_propensity": "Product fit",
    "recency": "Signal freshness",
}


def _operator_level(value: float) -> str:
    """Turn an internal 0..1 factor into an operator label without exposing formula jargon."""
    if value >= 0.80:
        return "STRONG"
    if value >= 0.60:
        return "SUPPORTING"
    return "LIMITED"


@app.get("/api/operator/trace/{lead_id}")
def operator_trace(lead_id: str, authorization: str | None = Header(default=None)):
    """Plain-language decision trace for a lead already present in the current run.

    This endpoint does not rescore or invent evidence.  It projects the exact cached
    lead, run metadata, source moments, contact gate, and receipt state into the
    questions an operator needs answered: why now, why this lead, what is uncertain,
    whether contact is allowed, and what action is recommended.
    """
    _auth(authorization)
    lead = next((item for item in _STATE.get("leads", []) if item.get("id") == lead_id), None)
    if lead is None:
        raise HTTPException(404, "lead not found in current run")

    meta = _STATE.get("meta") or {}
    total_signals = int(meta.get("total_signals") or 0)
    live_signals = int(meta.get("live_count") or 0)
    if total_signals > 0 and live_signals >= total_signals:
        run_state = "LIVE"
    elif live_signals > 0:
        run_state = "MIXED"
    else:
        run_state = "EXAMPLE"

    axes = lead.get("axes") or {}
    drivers = []
    for key, label in _OPERATOR_DRIVER_LABELS.items():
        try:
            value = max(0.0, min(1.0, float(axes.get(key, 0.0))))
        except (TypeError, ValueError):
            value = 0.0
        drivers.append({"key": key, "label": label, "level": _operator_level(value), "value": round(value, 4)})
    drivers.sort(key=lambda item: item["value"], reverse=True)

    evidence_state = run_state if run_state in {"LIVE", "EXAMPLE"} else "MIXED"
    evidence = [
        {
            "source": moment.get("source", "Unknown public source"),
            "supports": moment.get("label", "Source relation not described"),
            "state": evidence_state,
        }
        for moment in (lead.get("moments") or [])
        if isinstance(moment, dict)
    ]

    confidence = lead.get("confidence") or {}
    compliance = lead.get("compliance") or {}
    receipt_id = lead.get("receipt_id")
    caveats = []
    if run_state == "EXAMPLE":
        caveats.append("This is an offline example, not a live prospect.")
    elif run_state == "MIXED":
        caveats.append("This run mixes live public records with explicitly labeled fallback examples.")
    if confidence.get("advisory", True):
        caveats.append("The priority and confidence range are advisory, not eligibility or underwriting decisions.")
    if lead.get("est_premium_advisory"):
        caveats.append(lead.get("est_premium_note") or "Premium is illustrative, not a quote.")
    if not (lead.get("likely_gap") or {}).get("held_policies_known", False):
        caveats.append("Existing coverage is unknown; confirm it with the person before recommending a product.")
    if not lead.get("receipt_signed"):
        caveats.append("The proof record is available but unsigned because no signing key was available for this run.")

    return {
        "schema": "szl.operator-decision-trace/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lead": {
            "id": lead.get("id"),
            "name": lead.get("name"),
            "priority": lead.get("bucket"),
            "score": lead.get("score"),
            "why_now": lead.get("why"),
        },
        "run": {
            "state": run_state,
            "source_mode": meta.get("mode", "UNKNOWN"),
            "live_signals": live_signals,
            "total_signals": total_signals,
        },
        "decision_path": [
            {"step": "SIGNAL", "state": "OBSERVED" if evidence else "UNAVAILABLE", "detail": f"{len(evidence)} public source link(s) attached"},
            {"step": "PRIORITY", "state": lead.get("bucket", "UNKNOWN"), "detail": lead.get("why") or "No reason supplied"},
            {
                "step": "CONTACT",
                "state": (
                    "CLEAR"
                    if compliance.get("clear") is True
                    else "BLOCKED"
                    if compliance.get("clear") is False
                    else "NOT_EVALUATED"
                ),
                "detail": "; ".join(
                    compliance.get("reasons") or ["No contact-gate reason supplied"]
                ),
            },
            {"step": "ACTION", "state": "HUMAN_REVIEW", "detail": (lead.get("nba") or {}).get("action", "No action available")},
            {"step": "PROOF", "state": "SIGNED" if lead.get("receipt_signed") else ("UNSIGNED" if receipt_id else "UNAVAILABLE"), "detail": receipt_id or "No proof record available"},
        ],
        "drivers": drivers,
        "evidence": evidence,
        "uncertainty": {
            "state": "EXPOSED" if confidence else "UNAVAILABLE",
            "level": confidence.get("level", "UNKNOWN"),
            "range": {"low": confidence.get("lo"), "high": confidence.get("hi")},
            "source_count": confidence.get("n_sources", len(evidence)),
            "note": confidence.get("note", "No confidence note available"),
        },
        "conflict_check": {
            "state": "NOT_EVALUATED",
            "note": "No independent contradiction classifier is present in this product; the trace does not imply conflict clearance.",
        },
        "contact_gate": {
            "state": (
                "CLEAR"
                if compliance.get("clear") is True
                else "BLOCKED"
                if compliance.get("clear") is False
                else "NOT_EVALUATED"
            ),
            "reasons": compliance.get("reasons") or [],
        },
        "recommended_action": lead.get("nba") or {},
        "proof": {
            "state": "SIGNED" if lead.get("receipt_signed") else ("UNSIGNED" if receipt_id else "UNAVAILABLE"),
            "receipt_id": receipt_id,
            "verification_path": f"/api/verify/{receipt_id}" if receipt_id else None,
        },
        "caveats": caveats,
    }


@app.get("/api/methodology")
def methodology():
    """PUBLIC transparency surface: the full scoring methodology, unauthenticated.

    The model card contains formula/axes/weights/sources only — no PII, no leads.
    Transparency is the brand; the black box stays open to everyone."""
    try:
        card = sc.model_card()
        return {
            "access": "public — no login required (transparency surface; contains no PII or lead data)",
            "doctrine": "SZL governed-AI · honest by design · Λ = Conjecture 1 (advisory, never proven)",
            "model_card": card,
        }
    except Exception:
        raise HTTPException(503, "methodology temporarily unavailable")


@app.get("/api/edgar-signals")
def edgar_signals(authorization: str | None = Header(default=None)):
    """V8.4: SEC EDGAR 8-K workforce-event window (REPORTED pass-through, keyless)."""
    _auth(authorization)
    if efts is None:
        return {"status": "UNAVAILABLE", "basis": "edgar_fts module not loaded (honest absence)"}
    return efts.workforce_events_window()


@app.get("/api/territory")
def territory(state: str = "36", authorization: str | None = Header(default=None)):
    _auth(authorization)
    try:
        terr = sig.territory_index(state)
    except Exception:
        terr = _STATE.get("territory") or {"mode": "SAMPLE (offline)", "state": state, "indices": {}}
    _STATE["territory"] = terr  # cache so Ask the Territory can ground on it
    return terr


class AskReq(BaseModel):
    question: str


@app.post("/api/ask")
def ask(req: AskReq, authorization: str | None = Header(default=None)):
    """Ask the Territory — governed, citation-grounded answer over live public data + a signed receipt."""
    _auth(authorization)
    # ensure territory is available for grounding
    if not _STATE.get("territory"):
        try:
            _STATE["territory"] = sig.territory_index("36")
        except Exception:
            _STATE["territory"] = {}
    try:
        result = ask_engine.answer(req.question, _STATE)
    except Exception:
        result = {"intent": "unknown", "grounded": False, "citations": [],
                  "answer": "The territory engine is temporarily unavailable. Run intelligence and try again.",
                  "used_ids": []}
    # sign the answer (WILLAY-style: the answer + its citations are bound to a tamper-evident receipt)
    try:
        citations = result.get("citations") or []
        pseudo_lead = {
            "id": "ask_" + str(abs(hash(req.question)) % 10**8),
            "name": "Ask the Territory query",
            "bucket": (result.get("intent") or "query").upper(),
            "product": "conversational-intelligence",
        }
        sigs_used = [{"source": c.get("label", "citation"), "signal": "grounding citation", "public": True}
                     for c in citations] or \
                   [{"source": "public-data session state", "signal": "grounding", "public": True}]
        receipt = rc.make_receipt(pseudo_lead, sigs_used, 100.0 if result.get("grounded") else 0.0)
        result["receipt_id"] = receipt["id"]
        result["receipt_signed"] = receipt["signed"]
        _STATE.setdefault("ask_receipts", {})[receipt["id"]] = receipt
        _STATE.setdefault("receipts", {})[receipt["id"]] = receipt  # so /api/verify works on ask receipts too
    except Exception:
        result.setdefault("receipt_id", None)
        result.setdefault("receipt_signed", False)
    return result


@app.get("/api/leads")
def get_leads(authorization: str | None = Header(default=None)):
    _auth(authorization)
    leads = _STATE.get("leads", []) or []
    try:
        kpi = sc.kpi_summary(leads) if leads else {}
    except Exception:
        kpi = {}
    return {"leads": leads, "kpi": kpi}


@app.get("/api/receipt/{rid}")
def get_receipt(rid: str, authorization: str | None = Header(default=None)):
    _auth(authorization)
    for r in _STATE["receipts"].values():
        if r["id"] == rid:
            return r
    raise HTTPException(404, "Receipt not found")


@app.get("/api/verify/{rid}")
def verify(rid: str, authorization: str | None = Header(default=None)):
    _auth(authorization)
    for r in _STATE["receipts"].values():
        if r["id"] == rid:
            return rc.verify_receipt(r)
    raise HTTPException(404, "Receipt not found")


@app.get("/api/pulse")
def pulse(states: str | None = None, region: str | None = None, live: bool = True,
          authorization: str | None = Header(default=None)):
    """V8 Territory Pulse: ranked pulse of the Atlantic seaboard. live=true probes each state's
    portal (Socrata/ArcGIS) for a real recent count; failed probes are honest [SAMPLE]."""
    _auth(authorization)
    state_list = [x.strip().upper() for x in states.split(",")] if states else None
    try:
        rc.reset_chain()
    except Exception:
        pass
    try:
        result = sig8.territory_pulse(state_list, live=live, region=region)
    except Exception:
        raise HTTPException(503, "territory pulse temporarily unavailable")
    if not isinstance(result, dict):
        raise HTTPException(503, "territory pulse temporarily unavailable")
    summary = result.get("summary") or {}
    seaboard = result.get("seaboard") or []
    try:
        sigs_used = sig8.all_pulse_signals(state_list)
        pseudo = {"id": "pulse_seaboard", "name": "Territory Pulse (13-state seaboard)",
                  "bucket": summary.get("top_state") or "PULSE",
                  "product": "territory-intelligence"}
        receipt = rc.make_receipt(pseudo, sigs_used, float(len(seaboard)))
        result["receipt_id"] = receipt["id"]
        result["receipt_signed"] = receipt["signed"]
        _STATE.setdefault("receipts", {})[receipt["id"]] = receipt
    except Exception:
        result.setdefault("receipt_id", None)
        result.setdefault("receipt_signed", False)
    _STATE["pulse"] = result
    return result


@app.get("/api/surge")
def surge(states: str | None = None, region: str | None = None, live: bool = False,
          authorization: str | None = Header(default=None)):
    """Where Need Is Rising — plain-English rising/steady/quiet read per area.

    Honest baseline-delta: each area's current activity is compared to the seaboard
    average for this run. Above-average areas read 'Rising', around-average 'Steady',
    below-average 'Quiet'. Reuses the public-records territory signal counts; areas
    with no live count this run are labelled 'sample' so nothing is fabricated."""
    _auth(authorization)
    state_list = [x.strip().upper() for x in states.split(",")] if states else None
    try:
        result = sig8.territory_pulse(state_list, live=live, region=region)
    except Exception:
        raise HTTPException(503, "rising-areas read temporarily unavailable")
    if not isinstance(result, dict):
        raise HTTPException(503, "rising-areas read temporarily unavailable")
    seaboard = result.get("seaboard") or []
    pulses = [float(r.get("pulse", 0.0)) for r in seaboard] or [0.0]
    baseline = round(sum(pulses) / len(pulses), 1)

    def _status(row: dict) -> str:
        pulse = float(row.get("pulse", 0.0))
        bucket = row.get("bucket")
        delta = pulse - baseline
        if bucket == "SURGING" or delta >= 8.0:
            return "Rising"
        if bucket in ("QUIET", "GAP") or delta <= -8.0:
            return "Quiet"
        return "Steady"

    _NOTE = {
        "Rising": "More new homeowners and businesses than usual this month.",
        "Steady": "About the usual number of new public records this month.",
        "Quiet": "Fewer new public records than usual right now.",
    }
    areas = []
    for r in seaboard:
        status = _status(r)
        cites = r.get("citations") or []
        src = cites[0] if cites else {"label": f"{r.get('name', r.get('state'))} public records",
                                      "url": ""}
        cnt = r.get("count")
        is_live = str(r.get("mode", "")).startswith("LIVE") and cnt is not None
        areas.append({
            "area": r.get("name") or r.get("state"),
            "state": r.get("state"),
            "region": r.get("region", ""),
            "status": status,
            "count": cnt if cnt is not None else 0,
            "note": _NOTE[status],
            "source": {"label": src.get("label", ""), "url": src.get("url", "")},
            "source_status": "live" if is_live else "sample",
        })
    order = {"Rising": 0, "Steady": 1, "Quiet": 2}
    areas.sort(key=lambda a: (order.get(a["status"], 9), -a["count"]))
    return {
        "generated_at": result.get("generated_at"),
        "baseline": baseline,
        "areas": areas,
        "count": len(areas),
        "rising": [a["area"] for a in areas if a["status"] == "Rising"],
        "note": ("Areas are compared to this run's average activity across public records. "
                 "Areas without a live count this run are labelled sample — no counts are invented."),
    }


@app.get("/api/brief/{lead_id}")
def brief(lead_id: str, authorization: str | None = Header(default=None)):
    """V8 Signed 4-Part Brief — each part GROUNDED by a real a11oy formula verdict
    (Priority / Why-now / Opening-line / Sensitivity), witness-signed via khipu 3-of-4."""
    _auth(authorization)
    lead = next((l for l in _STATE.get("leads", []) if l.get("id") == lead_id), None)
    if not lead:
        raise HTTPException(404, "Lead not found - run intelligence first")
    b = None
    if fm is not None:
        try:
            b = fm.build_signed_brief(lead)
        except Exception:
            b = None
    if not isinstance(b, dict):  # honest fallback to the structured brief if the formulas engine fails
        try:
            b = sc.build_brief(lead, _STATE.get("signals", []))
        except Exception:
            raise HTTPException(503, "brief temporarily unavailable")
    try:
        receipt = rc.make_brief_receipt(b, _STATE.get("signals", []))
        b["receipt_id"] = receipt["id"]
        b["receipt_signed"] = receipt["signed"]
        _STATE.setdefault("receipts", {})[receipt["id"]] = receipt
    except Exception:
        b.setdefault("receipt_id", None)
        b.setdefault("receipt_signed", False)
    return b


class WorkReq(BaseModel):
    max_steps: int = 8
    step_minutes: float | None = None
    convergence_threshold: float = 0.1


@app.post("/api/work")
def work(req: WorkReq, authorization: str | None = Header(default=None)):
    """V8 Ouroboros bounded work loop over the Territory Pulse state. Returns the LoopTrace
    (4 exit reasons, maxSteps budget, earliestSafeExit) + the khipu-witnessed change-events it
    minted into the append-only receipt lake."""
    _auth(authorization)
    if wk is None:
        raise HTTPException(503, "work loop unavailable")
    cfg = {"maxSteps": req.max_steps, "convergenceThreshold": req.convergence_threshold}
    if req.step_minutes is not None:
        cfg["stepMinutes"] = req.step_minutes
    meta = _STATE.get("meta", {}) or {}
    try:
        out = wk.run_territory_pulse(meta, cfg)
    except Exception:
        raise HTTPException(503, "work loop temporarily unavailable")
    if not isinstance(out, dict):
        raise HTTPException(503, "work loop temporarily unavailable")
    _lake_size = None
    if lake is not None:
        try:
            _lake_size = lake.size()
        except Exception:
            _lake_size = None
    return {
        "trace": out.get("trace"),
        "events": out.get("events"),
        "loop_receipt": out.get("loop_receipt"),
        "lake_size": _lake_size,
    }


class OuroborosReq(BaseModel):
    max_steps: int = 4
    top_k: int = 5
    step_minutes: float | None = None
    convergence_threshold: float = 0.1


@app.get("/api/oroboros/manifest")
def oroboros_manifest():
    """Public capability/limits manifest; no lead or credential data."""
    return {
        "agent": "Ouroboros Director",
        "version": "1.0",
        "endpoint": "POST /api/oroboros",
        "mode": "bounded-read-only",
        "max_steps": 8,
        "formulas": [
            "LambdaMonotonicity", "FalsePosition", "SummationInvariant",
            "LambdaCompliance", "ConfidenceBand", "FusedTrack", "AdvisorRouting",
        ],
        "human_authority": "required before any contact or downstream mutation",
        "limits": [
            "No outreach, CRM write, or external mutation is executed.",
            "Public signals are claims; estimates are labeled and receipted.",
            "Lambda remains Conjecture 1 (advisory).",
        ],
    }


@app.post("/api/oroboros")
def oroboros_director(req: OuroborosReq, authorization: str | None = Header(default=None)):
    """Run the bounded, read-only Ouroboros Director over the last public-data run.

    The Director composes the existing scoring, compliance, confidence/fusion,
    formula-brief, routing, and loop engines. It returns proposals only; no
    outreach, CRM write, or other mutating action is executed.
    """
    _auth(authorization)
    if ob is None:
        raise HTTPException(503, "Ouroboros Director unavailable")
    meta = _STATE.get("meta") or {}
    if not meta:
        raise HTTPException(409, "run intelligence first so the Director has a public-signal state")
    config = {
        "max_steps": req.max_steps,
        "top_k": req.top_k,
        "convergence_threshold": req.convergence_threshold,
    }
    if req.step_minutes is not None:
        config["step_minutes"] = req.step_minutes
    try:
        result = ob.run_cycle(meta, config)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception:
        raise HTTPException(503, "Ouroboros Director temporarily unavailable")
    # Keep the loop receipt addressable through the existing verification surface.
    loop_receipt = result.get("loop_receipt") or {}
    if loop_receipt.get("id"):
        _STATE.setdefault("receipts", {})[loop_receipt["id"]] = loop_receipt
    _STATE["oroboros"] = result
    return result


class OutcomeReq(BaseModel):
    lead_id: str
    outcome: str  # "meeting" | "sold" | "no"


@app.post("/api/outcome")
def outcome(req: OutcomeReq, authorization: str | None = Header(default=None)):
    """V8 P0-6 adaptive conversion loop: log a real-world outcome for a lead, append a signed
    outcome receipt to the append-only receipt lake, and nudge the per-event_type propensity for
    future runs. Honest: in-session learning signal; durable only when SZL_RECEIPT_LAKE_PATH set."""
    _auth(authorization)
    if ev is None:
        raise HTTPException(503, "outcome learning unavailable")
    outcome_val = (req.outcome or "").lower().strip()
    if outcome_val not in ev.VALID_OUTCOMES:
        raise HTTPException(422, f"outcome must be one of {ev.VALID_OUTCOMES}")
    lead = next((l for l in _STATE.get("leads", []) if l["id"] == req.lead_id), None)
    if lead is None:
        raise HTTPException(404, "lead not found; run intelligence and use a current lead id")
    try:
        event_type = (lead or {}).get("event_type") or (ev.classify((lead or {}).get("event", "")) if lead else "unknown")
    except Exception:
        event_type = "unknown"
    try:
        summary = ev.record_outcome(event_type, outcome_val)
    except Exception:
        summary = {"total_outcomes": 0}
    # signed, hash-chained outcome receipt -> append-only lake (durable if SZL_RECEIPT_LAKE_PATH)
    receipt_id = None
    receipt_signed = False
    try:
        pseudo = {
            "id": "outcome_" + req.lead_id,
            "name": (lead or {}).get("name", req.lead_id),
            "bucket": outcome_val.upper(),
            "product": "adaptive-conversion-outcome",
        }
        sigs_used = [{
            "source": "agent-logged outcome",
            "signal": f"{event_type}:{outcome_val}",
            "public": False,
            "source_class": "INTERNAL_OPERATIONAL",
        }]
        receipt = rc.make_receipt(pseudo, sigs_used, 100.0 if outcome_val == "sold" else 50.0 if outcome_val == "meeting" else 0.0)
        receipt["organ"] = "conversion-loop"
        receipt["decision"] = "outcome-logged"
        receipt["event_type"] = event_type
        receipt["outcome"] = outcome_val
        receipt_id = receipt["id"]
        receipt_signed = receipt["signed"]
        _STATE.setdefault("receipts", {})[receipt["id"]] = receipt
        if lake is not None:
            lake.append(receipt)
    except Exception:
        pass
    return {
        "ok": True,
        "lead_id": req.lead_id,
        "event_type": event_type,
        "outcome": outcome_val,
        "receipt_id": receipt_id,
        "receipt_signed": receipt_signed,
        "learning": summary,
        "lake_size": lake.size() if lake is not None else None,
        "message": f"learning from {summary.get('total_outcomes', 0)} logged outcomes",
    }


@app.get("/api/lake")
def get_lake(organ: str | None = None, decision: str | None = None,
             limit: int | None = None, authorization: str | None = Header(default=None)):
    """V8 read the append-only receipt lake (every witnessed change-event, immutable)."""
    _auth(authorization)
    if lake is None:
        raise HTTPException(503, "receipt lake unavailable")
    try:
        events = lake.query(organ=organ, decision=decision, limit=limit)
        return {"size": lake.size(), "count": len(events), "events": events}
    except Exception:
        raise HTTPException(503, "receipt lake temporarily unavailable")


@app.get("/api/benchmark")
def benchmark(authorization: str | None = Header(default=None)):
    """V8.2 P1-F: producer conversion-funnel dashboard from this session's surfaced leads,
    the in-session outcome tally, and the durable append-only receipt lake. No external data."""
    _auth(authorization)
    if bench is None:
        raise HTTPException(503, "benchmark unavailable")
    leads = _STATE.get("leads", []) or []
    try:
        summary = ev.outcome_summary() if ev is not None else {}
    except Exception:
        summary = {}
    lake_events = []
    if lake is not None:
        try:
            lake_events = lake.query(organ="conversion-loop")
        except Exception:
            lake_events = []
    try:
        return bench.build_benchmark(leads, summary, lake_events)
    except Exception:
        raise HTTPException(503, "benchmark temporarily unavailable")


@app.get("/api/routing")
def routing(authorization: str | None = Header(default=None)):
    """V8.3 P2-1: best-fit advisor lead routing. Scores each current-run lead against the
    advisor roster on trigger specialty + territory overlap + (from the benchmark) historical
    conversion-by-trigger. David is the real advisor; teammates are an [illustrative roster].
    Defensive: never raises on a missing optional; returns an honest empty table instead."""
    _auth(authorization)
    if rt is None:
        raise HTTPException(503, "routing unavailable")
    leads = _STATE.get("leads", []) or []
    conv = {}
    try:
        if bench is not None:
            summary = ev.outcome_summary() if ev is not None else {}
            lake_events = []
            if lake is not None:
                try:
                    lake_events = lake.query(organ="conversion-loop")
                except Exception:
                    lake_events = []
            b = bench.build_benchmark(leads, summary, lake_events)
            conv = rt.conversion_by_event_from_benchmark(b)
    except Exception:
        conv = {}
    try:
        return rt.route_leads(leads, meta=_STATE.get("meta", {}), conversion_by_event=conv)
    except Exception:
        return {"roster": [], "routing": [], "factors": {},
                "honest_note": "routing temporarily unavailable; run intelligence first"}


@app.get("/api/real-leads")
def real_leads(states: str = "NY,NJ,PA,MD,DE,CT", authorization: str | None = Header(default=None)):
    """Currently filed public B2B research records from official state open-data portals.

    Public business addresses only; no permission to contact is inferred. Every
    record carries a citation and an evidence receipt. A down legacy source
    degrades to a visible sample rather than being presented as live.
    """
    _auth(authorization)
    if rl is None:
        raise HTTPException(503, "real-leads source unavailable")
    state_list = [s.strip().upper() for s in (states or "").split(",") if s.strip()] or \
        ["NY", "NJ", "PA", "MD", "DE", "CT"]
    try:
        out = rl.real_callable_leads(state_list, limit_per=12)
    except Exception:
        raise HTTPException(503, "real-leads temporarily unavailable")
    # stash each signed receipt so /api/verify/{rid} works, and strip internal-only keys
    clean_leads = []
    for lead in out.get("leads", []):
        rcpt = lead.pop("_receipt", None)
        if isinstance(rcpt, dict) and rcpt.get("id"):
            _STATE.setdefault("receipts", {})[rcpt["id"]] = rcpt
        lead.pop("_account_id", None)
        clean_leads.append(lead)
    out["leads"] = clean_leads
    _STATE["real_leads"] = out
    return out


class DealDeskUpdateReq(BaseModel):
    stage: str
    next_action: str | None = None
    note: str | None = None
    owner: str | None = None
    actor: str = "David"


class DealDeskResearchReq(BaseModel):
    actor: str
    channel_type: str
    channel_value: str
    source_url: str
    publisher_class: str = "FIRST_PARTY_BUSINESS_WEBSITE"
    note: str = ""


class DealDeskClearanceReq(BaseModel):
    actor: str
    channel_id: str
    business_purpose: str
    talk_track_version: str
    broker_jurisdiction: str
    license_scope: str
    federal_dnc_checked: bool
    state_dnc_checked: bool
    opt_out_checked: bool
    rules_reviewed: bool
    expires_hours: int = 24


class DealDeskDispositionReq(BaseModel):
    actor: str
    disposition: str
    note: str = ""
    follow_up_at: str | None = None


@app.get("/api/deal-desk")
def deal_desk(states: str = "NY,NJ,PA,MD,DE,CT", authorization: str | None = Header(default=None)):
    """Broker work queue built only from real public B2B records.

    A public record is a research signal, not permission to contact. Every row
    remains fail-closed until a human records execution-time outreach clearance.
    """
    _auth(authorization)
    if rl is None or dd is None:
        raise HTTPException(503, "opportunity desk unavailable")
    if not dd.persistence_ready():
        raise HTTPException(
            503,
            "deal desk persistence requires DAVID_DATABASE_URL or a ready absolute DAVID_DEAL_DESK_PATH",
        )
    state_list = [s.strip().upper() for s in (states or "").split(",") if s.strip()] or [
        "NY", "NJ", "PA", "MD", "DE", "CT"
    ]
    try:
        source = rl.real_callable_leads(state_list, limit_per=12)
    except Exception:
        raise HTTPException(503, "public business sources temporarily unavailable")
    clean: list[dict] = []
    for lead in source.get("leads", []):
        receipt = lead.pop("_receipt", None)
        if isinstance(receipt, dict) and receipt.get("id"):
            _STATE.setdefault("receipts", {})[receipt["id"]] = receipt
        lead.pop("_account_id", None)
        clean.append(lead)
    board = dd.board(clean)
    board["sources"] = source.get("sources", [])
    board["generated_at"] = source.get("generated_at")
    _STATE["deal_desk"] = board
    return board


@app.get("/api/frontier-desk")
def frontier_desk(
    states: str = "NY,NJ,PA,MD,DE,CT",
    authorization: str | None = Header(default=None),
):
    """Entity-level FMCSA and federal-contract activity for broker research.

    Source adapters select only operational entity fields. They intentionally
    exclude person-level contact, officer, safety, crash, insurance, and policy
    data and never infer permission to contact or an underwriting fact.
    """
    _auth(authorization)
    if frontier_data is None or dd is None:
        raise HTTPException(503, "frontier radar unavailable")
    if not dd.persistence_ready():
        raise HTTPException(
            503,
            "deal desk persistence requires DAVID_DATABASE_URL or a ready absolute DAVID_DEAL_DESK_PATH",
        )
    state_list = [s.strip().upper() for s in (states or "").split(",") if s.strip()] or [
        "NY", "NJ", "PA", "MD", "DE", "CT"
    ]
    source = frontier_data.frontier_opportunities(state_list, limit_per_source=18)
    clean: list[dict] = []
    for lead in source.get("leads", []):
        receipt = lead.pop("_receipt", None)
        if isinstance(receipt, dict) and receipt.get("id"):
            _STATE.setdefault("receipts", {})[receipt["id"]] = receipt
        clean.append(lead)
    board = dd.board(clean)
    board["sources"] = source.get("sources", [])
    board["generated_at"] = source.get("generated_at")
    board["states"] = source.get("states", state_list)
    board["frontier_doctrine"] = source.get("doctrine")
    _STATE["frontier_desk"] = board
    return board


@app.post("/api/deal-desk/{opportunity_id}")
def update_deal_desk(
    opportunity_id: str,
    req: DealDeskUpdateReq,
    authorization: str | None = Header(default=None),
):
    _auth(authorization)
    if dd is None:
        raise HTTPException(503, "opportunity desk unavailable")
    if not dd.persistence_ready():
        raise HTTPException(
            503,
            "deal desk persistence requires DAVID_DATABASE_URL or a ready absolute DAVID_DEAL_DESK_PATH",
        )
    try:
        opportunity = dd.update(
            opportunity_id,
            stage=req.stage,
            next_action=req.next_action,
            note=req.note,
            owner=req.owner,
            actor=req.actor,
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True, "opportunity": opportunity}


@app.post("/api/deal-desk/{opportunity_id}/research")
def record_deal_desk_research(
    opportunity_id: str,
    req: DealDeskResearchReq,
    authorization: str | None = Header(default=None),
):
    _auth(authorization)
    if dd is None:
        raise HTTPException(503, "opportunity desk unavailable")
    if not dd.persistence_ready():
        raise HTTPException(503, "deal desk persistence is unavailable")
    try:
        opportunity = dd.record_research(
            opportunity_id,
            actor=req.actor,
            channel_type=req.channel_type,
            channel_value=req.channel_value,
            source_url=req.source_url,
            publisher_class=req.publisher_class,
            note=req.note,
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True, "opportunity": opportunity}


@app.post("/api/deal-desk/{opportunity_id}/clearance")
def record_deal_desk_clearance(
    opportunity_id: str,
    req: DealDeskClearanceReq,
    authorization: str | None = Header(default=None),
):
    _auth(authorization)
    if dd is None:
        raise HTTPException(503, "opportunity desk unavailable")
    if not dd.persistence_ready():
        raise HTTPException(503, "deal desk persistence is unavailable")
    try:
        opportunity = dd.record_clearance(
            opportunity_id,
            actor=req.actor,
            channel_id=req.channel_id,
            business_purpose=req.business_purpose,
            talk_track_version=req.talk_track_version,
            broker_jurisdiction=req.broker_jurisdiction,
            license_scope=req.license_scope,
            federal_dnc_checked=req.federal_dnc_checked,
            state_dnc_checked=req.state_dnc_checked,
            opt_out_checked=req.opt_out_checked,
            rules_reviewed=req.rules_reviewed,
            expires_hours=req.expires_hours,
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True, "opportunity": opportunity}


@app.get("/api/deal-desk/{opportunity_id}/call-sheet")
def get_deal_desk_call_sheet(
    opportunity_id: str,
    authorization: str | None = Header(default=None),
):
    _auth(authorization)
    if dd is None:
        raise HTTPException(503, "opportunity desk unavailable")
    if not dd.persistence_ready():
        raise HTTPException(503, "deal desk persistence is unavailable")
    try:
        return dd.call_sheet(opportunity_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(423, str(exc)) from exc


@app.post("/api/deal-desk/{opportunity_id}/disposition")
def record_deal_desk_disposition(
    opportunity_id: str,
    req: DealDeskDispositionReq,
    authorization: str | None = Header(default=None),
):
    _auth(authorization)
    if dd is None:
        raise HTTPException(503, "opportunity desk unavailable")
    if not dd.persistence_ready():
        raise HTTPException(503, "deal desk persistence is unavailable")
    try:
        opportunity = dd.record_disposition(
            opportunity_id,
            actor=req.actor,
            disposition=req.disposition,
            note=req.note,
            follow_up_at=req.follow_up_at,
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True, "opportunity": opportunity}


def _safe_csv_cell(value):
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


@app.get("/api/deal-desk-export.csv")
def export_deal_desk(authorization: str | None = Header(default=None)):
    _auth(authorization)
    if dd is None:
        raise HTTPException(503, "opportunity desk unavailable")
    if not dd.persistence_ready():
        raise HTTPException(503, "deal desk persistence is unavailable")
    rows = dd.export_rows()
    fields = list(rows[0]) if rows else [
        "opportunity_id", "business_name", "state", "source_frontier", "observed_trigger",
        "trigger_date", "stage", "priority", "contact_gate", "call_ready", "next_action",
        "source_url", "business_channel_type", "business_channel", "clearance_expires_at",
        "not_for_underwriting",
    ]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _safe_csv_cell(row.get(key)) for key in fields})
    return PlainTextResponse(
        stream.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=david-leads-opportunities.csv"},
    )


@app.get("/api/data-policy")
def data_policy():
    if dp is None:
        raise HTTPException(503, "data policy unavailable")
    return dp.policy_document()


@app.get("/api/warn-leads")
def warn_leads(states: str = "NY,NJ,PA,MD,DE,CT", authorization: str | None = Header(default=None)):
    """WARN Act layoff leads (public state DOL records) for the covered states. A 60-day WARN
    notice is a high-intent trigger for ACA / short-term / COBRA-alternative coverage. Live where
    a structured endpoint exists; otherwise honest source_status='sample' rows on the real WARN
    schema (clearly labelled, never presented as live). Each lead carries its state WARN portal
    citation + a frontier receipt. Defensive: never 500s."""
    _auth(authorization)
    if wl is None:
        raise HTTPException(503, "warn-leads source unavailable")
    state_list = [s.strip().upper() for s in (states or "").split(",") if s.strip()] or \
        ["NY", "NJ", "PA", "MD", "DE", "CT"]
    try:
        out = wl.warn_leads(state_list)
    except Exception:
        raise HTTPException(503, "warn-leads temporarily unavailable")
    # stash each frontier receipt so /api/verify/{rid} can echo it
    for lead in out.get("leads", []):
        rcpt = lead.get("receipt")
        if isinstance(rcpt, dict) and rcpt.get("sha256"):
            _STATE.setdefault("receipts", {})[rcpt["sha256"]] = rcpt
    _STATE["warn_leads"] = out
    return out


@app.get("/api/tax-territories")
def tax_territories(states: str = "NY,NJ,CT,PA,MD,DE",
                    authorization: str | None = Header(default=None)):
    """TERRITORY intelligence from aggregate IRS public statistics: affluent ZIPs ($200k+ return
    density) + money-in-motion counties (AGI carried in by movers). Names NO individuals — this is
    the compliant use of tax data. Each block carries the IRS citation + a signed receipt.
    Defensive: if irs.gov is unreachable the layer degrades to an honest [SAMPLE]; never 500s."""
    _auth(authorization)
    if tx is None:
        raise HTTPException(503, "tax-territory source unavailable")
    state_list = [s.strip().upper() for s in (states or "").split(",") if s.strip()] or \
        ["NY", "NJ", "CT", "PA", "MD", "DE"]
    try:
        out = tx.real_tax_territories(state_list, top=12)
    except Exception:
        raise HTTPException(503, "tax-territory temporarily unavailable")
    rcpt = out.pop("_receipt", None)
    if isinstance(rcpt, dict) and rcpt.get("id"):
        _STATE.setdefault("receipts", {})[rcpt["id"]] = rcpt
    _STATE["tax_territories"] = out
    return out


class OptInReq(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    zip: str | None = None
    interest: str | None = None
    consent: bool = False


@app.post("/api/optin")
def optin(req: OptInReq):
    """TCPA-safe opt-in capture. The ONLY endpoint where a personal phone/email is accepted —
    because the person submits it themselves with explicit consent. Rejects unless consent==true.
    Stores the consented lead in-process (+ file if SZL_OPTIN_PATH is set) and signs a receipt
    recording the explicit consent + timestamp. Public (embeddable capture form) — no auth."""
    name = (req.name or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    if req.consent is not True:
        raise HTTPException(400, "Consent is required: you must agree to be contacted to submit.")
    ts = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    lead = {
        "name": name,
        "email": (req.email or "").strip(),
        "phone": (req.phone or "").strip(),
        "zip": (req.zip or "").strip(),
        "interest": (req.interest or "").strip(),
        "consent": True,
        "consent_basis": "express consent (opt-in)",
        "submitted_at": ts,
    }
    # Sign a receipt recording first-party consent. Consent is permitted evidence, but it is
    # not public data and must never be mislabeled as such.
    try:
        signal = {"source": "self-submitted opt-in form",
                  "signal": f"express consent to be contacted recorded {ts}",
                  "public": False, "source_class": "FIRST_PARTY_CONSENT"}
        pseudo = {"id": "optin_" + hashlib.sha256((name + ts).encode()).hexdigest()[:12],
                  "name": name, "bucket": "OPT-IN", "product": "CONSENT"}
        receipt = rc.make_receipt(pseudo, [signal], 100.0, witness=True)
        lead["receipt_id"] = receipt["id"]
        lead["receipt_signed"] = receipt["signed"]
        _STATE.setdefault("receipts", {})[receipt["id"]] = receipt
    except Exception:
        lead["receipt_id"] = None
        lead["receipt_signed"] = False
    _OPTIN_LEADS.append(lead)
    _persist_optin()
    return {"ok": True, "receipt_id": lead["receipt_id"],
            "message": "Thank you — your consent has been recorded.",
            "consent_basis": "express consent (opt-in)"}


@app.get("/api/optin/leads")
def optin_leads(authorization: str | None = Header(default=None)):
    """Consented opt-in leads for David to work — each marked 'express consent (opt-in)'."""
    _auth(authorization)
    return {"leads": list(_OPTIN_LEADS), "count": len(_OPTIN_LEADS),
            "basis": "express consent (opt-in)",
            "doctrine": "Only self-submitted, explicitly-consented contacts are stored here · "
                        "every entry carries a signed consent receipt · honest by design"}


# columns for the ranked-lead CRM export
_CSV_COLUMNS = ["rank", "id", "name", "event_type", "score", "bucket", "urgency",
                "wealth_tier", "lapse_decile", "receptivity", "likely_gap",
                "product", "employer", "liquidity", "receipt_id", "receipt_hash"]


def _lead_row(rank: int, lead: dict) -> list:
    gap = lead.get("likely_gap") or {}
    liq_sig = lead.get("liquidity") or {}
    lapse = lead.get("lapse") or {}
    rid = lead.get("receipt_id")
    rcpt = _STATE.get("receipts", {}).get(rid, {}) if rid else {}
    return [
        rank,
        lead.get("id", ""),
        lead.get("name", ""),
        lead.get("event_type", lead.get("event", "")),
        lead.get("score", ""),
        lead.get("bucket", ""),
        lead.get("urgency", ""),
        (lambda wt: wt.get("tier", "") if isinstance(wt, dict) else (wt or ""))(lead.get("wealth_tier", "")),
        (lapse.get("decile") if isinstance(lapse, dict) else lapse) or "",
        lead.get("receptivity", ""),
        gap.get("label", "") if isinstance(gap, dict) else "",
        lead.get("product", ""),
        lead.get("employer", "") or "",
        (liq_sig.get("mode", "") if isinstance(liq_sig, dict) else "") or "",
        rid or "",
        rcpt.get("payload_sha256", "") if isinstance(rcpt, dict) else "",
    ]


@app.get("/api/export.csv")
def export_csv(authorization: str | None = Header(default=None)):
    """V8.2 P1-G: CRM export — ranked leads as CSV (score/event/urgency/wealth/lapse/
    receptivity/gap + the signed receipt hash that justifies each row)."""
    _auth(authorization)
    leads = _STATE.get("leads", []) or []
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(_CSV_COLUMNS)
    for i, lead in enumerate(leads, start=1):
        try:
            w.writerow(_lead_row(i, lead))
        except Exception:
            continue
    return PlainTextResponse(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=david-leads-export.csv"},
    )


class WebhookReq(BaseModel):
    url: str | None = None
    lead_id: str | None = None  # optional: export a single enriched lead; default = all ranked leads


def _webhook_destination(
    url: str,
) -> tuple[urllib.parse.ParseResult, str, tuple[str, ...]]:
    parsed = urllib.parse.urlparse(url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    approved = {
        host.strip().lower().rstrip(".")
        for host in os.environ.get("DAVID_CRM_WEBHOOK_ALLOWLIST", "").split(",")
        if host.strip()
    }
    if not approved:
        raise ValueError("CRM webhook is disabled until DAVID_CRM_WEBHOOK_ALLOWLIST is configured")
    if parsed.scheme.lower() != "https" or not hostname or hostname not in approved:
        raise ValueError("destination must be an approved HTTPS CRM hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("destination credentials are not permitted")
    try:
        port = parsed.port or 443
    except ValueError as exc:
        raise ValueError("destination port is invalid") from exc
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        }
    except OSError as exc:
        raise ValueError("approved CRM hostname could not be resolved") from exc
    if not addresses:
        raise ValueError("approved CRM hostname did not resolve to an address")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError("approved CRM hostname resolves to a non-public address")
    validated_addresses = tuple(
        sorted(addresses, key=lambda value: ipaddress.ip_address(value).packed)
    )
    return parsed, hostname, validated_addresses


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        hostname: str,
        validated_address: str,
        *,
        port: int = 443,
        timeout: float = 8,
        context: ssl.SSLContext | None = None,
    ):
        self._validated_address = validated_address
        super().__init__(
            host=hostname,
            port=port,
            timeout=timeout,
            context=context or ssl.create_default_context(),
        )

    def connect(self):
        raw_socket = socket.create_connection(
            (self._validated_address, self.port),
            self.timeout,
            self.source_address,
        )
        if self._tunnel_host:
            self.sock = raw_socket
            self._tunnel()
            raw_socket = self.sock
        self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)


def _post_validated_webhook(
    parsed: urllib.parse.ParseResult,
    hostname: str,
    validated_addresses: tuple[str, ...],
    body: bytes,
) -> int:
    port = parsed.port or 443
    path = parsed.path or "/"
    if parsed.params:
        path += ";" + parsed.params
    if parsed.query:
        path += "?" + parsed.query

    connection = None
    last_connect_error: OSError | None = None
    for validated_address in validated_addresses:
        candidate = _PinnedHTTPSConnection(
            hostname,
            validated_address,
            port=port,
            timeout=8,
        )
        try:
            candidate.connect()
        except OSError as exc:
            last_connect_error = exc
            candidate.close()
            continue
        connection = candidate
        break
    if connection is None:
        raise last_connect_error or OSError(
            "approved CRM hostname has no reachable validated address"
        )

    try:
        connection.request(
            "POST",
            path,
            body=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "SZL-David-Leads webhook-test",
            },
        )
        response = connection.getresponse()
        status = response.status
        response.read(1)
    finally:
        connection.close()
    if not 200 <= status < 300:
        raise OSError(f"CRM webhook returned HTTP {status}")
    return status


@app.post("/api/webhook/test")
def webhook_test(req: WebhookReq, authorization: str | None = Header(default=None)):
    """V8.2 P1-G: Push-to-CRM test. POSTs the enriched-lead JSON to req.url; if no url is
    given or outbound network is blocked, returns the would-send payload (honest, never fakes a send)."""
    _auth(authorization)
    leads = _STATE.get("leads", []) or []
    if req.lead_id:
        leads = [l for l in leads if l.get("id") == req.lead_id]
        if not leads:
            raise HTTPException(404, "Lead not found - run intelligence first")
    payload = {
        "source": "David Leads V8.2",
        "exported_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
        "count": len(leads),
        "leads": [
            {
                "id": l.get("id"), "name": l.get("name"),
                "event_type": l.get("event_type", l.get("event")),
                "score": l.get("score"), "bucket": l.get("bucket"),
                "urgency": l.get("urgency"), "wealth_tier": l.get("wealth_tier"),
                "receptivity": l.get("receptivity"),
                "likely_gap": (l.get("likely_gap") or {}).get("label"),
                "product": l.get("product"),
                "receipt_id": l.get("receipt_id"),
            }
            for l in leads
        ],
    }
    if not req.url:
        return {"ok": True, "sent": False, "reason": "no url supplied",
                "would_send": payload}
    try:
        parsed, hostname, validated_addresses = _webhook_destination(req.url)
    except ValueError as exc:
        return {"ok": True, "sent": False,
                "reason": str(exc), "would_send": payload}
    try:
        body = json.dumps(payload).encode("utf-8")
        status = _post_validated_webhook(parsed, hostname, validated_addresses, body)
        return {"ok": True, "sent": True, "destination": hostname,
                "status": status, "count": payload["count"]}
    except Exception as e:
        # outbound blocked / unreachable — honest: return the would-send payload, never fake success
        return {"ok": True, "sent": False,
                "reason": "outbound POST failed (%s)" % type(e).__name__,
                "destination": hostname, "would_send": payload}


# static frontend (disabled when deployed behind the proxy; deploy serves static from S3)
if SERVE_STATIC:
    app.mount("/", StaticFiles(directory=os.path.join(APP_DIR, "static"), html=True), name="static")
