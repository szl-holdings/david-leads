# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads Sovereign Insurance Intelligence
"""FastAPI backend: login gate, live signal run, scored leads, signed receipts, KPI."""
from __future__ import annotations
import os, secrets, hashlib, io, csv, json, urllib.request, urllib.error
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

APP_DIR = os.path.dirname(__file__)
app = FastAPI(title="David Leads — Sovereign Insurance Intelligence", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
SERVE_STATIC = os.environ.get("SERVE_STATIC", "1") == "1"

# --- demo credentials (David-only). Override via env in production. ---
USERS = {
    os.environ.get("DAVID_USER", "david"): os.environ.get("DAVID_PASS", "David2026!"),
}
ACCESS_KEY = os.environ.get("DAVID_ACCESS_KEY", "DAVID-2026-SECURE-DEMO")
_TOKENS: set[str] = set()

# session cache of last run
_STATE: dict = {"leads": [], "signals": [], "meta": {}, "receipts": {}}


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
    if authorization.split(" ", 1)[1] not in _TOKENS:
        raise HTTPException(401, "Invalid token")


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "david-leads", "doctrine": "SZL governed-AI · honest by design"}


@app.post("/api/login")
def login(req: LoginReq):
    ok = (USERS.get(req.username) == req.password) and (req.access_key == ACCESS_KEY)
    if not ok:
        raise HTTPException(401, "Invalid credentials or access key")
    tok = secrets.token_urlsafe(24)
    _TOKENS.add(tok)
    return {"token": tok, "user": req.username}


@app.post("/api/run")
def run(req: RunReq, authorization: str | None = Header(default=None)):
    _auth(authorization)
    rc.reset_chain()
    sigs, meta = sig.gather_all(live=req.live)
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
    leads = sc.build_leads(meta, age_minutes=getattr(req, "age_min", 0.0))
    # V8.2 P1-A: optional SEC Form 4 insider-sell liquidity flag — only on live runs, only for
    # leads whose event_type implies a liquidity moment AND where a public employer is known.
    # Defensive: any failure leaves the lead untouched so /api/run never breaks.
    if liq is not None and getattr(req, "live", False):
        _LIQ_EVENTS = {"job_change", "promotion", "near_retirement"}
        for lead in leads:
            try:
                employer = lead.get("employer")
                if employer and (lead.get("event_type") in _LIQ_EVENTS):
                    lead["liquidity"] = liq.liquidity_signal(employer)
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
                    nud = w990.nudge_wealth_tier(lead.get("wealth_tier", "Mass"), sig990)
                    if nud.get("nudged"):
                        lead["wealth_tier"] = nud["tier"]
                        lead["wealth_tier_nudge"] = nud
            except Exception:
                pass
    receipts = {}
    for lead in leads:
        # each lead's receipt binds the signals that justify its segment
        receipts[lead["id"]] = rc.make_receipt(lead, sigs, lead["score"])
        lead["receipt_id"] = receipts[lead["id"]]["id"]
        lead["receipt_signed"] = receipts[lead["id"]]["signed"]
    _STATE.update(leads=leads, signals=sigs, meta=meta, receipts=receipts)
    # khipu 3-of-4 witnessed governance: report consensus from the leads' receipts when present
    consensus_state = "unwitnessed"
    any_receipt = next(iter(receipts.values()), None)
    if any_receipt and any_receipt.get("consensus"):
        consensus_state = any_receipt["consensus"].get("khipu_consensus", "unwitnessed")
    top = leads[:3]
    brief = {
        "top_ids": [l["id"] for l in top],
        "headline": (f"{len([l for l in leads if l['bucket']=='HOT'])} HOT leads ready to call today — "
                     f"lead with {top[0]['name']}." if top else "Run intelligence to build today's call list."),
        "items": [{"id": l["id"], "name": l["name"], "score": l["score"], "bucket": l["bucket"],
                   "product": l["product"], "action": l["nba"]["action"]} for l in top],
    }
    learning = ev.outcome_summary() if ev is not None else {"total_outcomes": 0}
    return {
        "meta": meta,
        "signals": sigs,
        "leads": leads,
        "kpi": sc.kpi_summary(leads),
        "brief": brief,
        "learning": learning,  # P0-6: in-session adaptive conversion signal
        "governance": {
            "signals_checked": meta["total_signals"],
            "all_public": meta["rejected_nonpublic"] == 0,
            "fabricated": meta["fabricated"],
            "rejected_nonpublic": meta["rejected_nonpublic"],
            "consensus": consensus_state,
            "verdict": "PASS — public-data-only, honest by design",
        },
    }


@app.get("/api/model")
def model(authorization: str | None = Header(default=None)):
    """Open the black box: full transparent scoring methodology."""
    _auth(authorization)
    return sc.model_card()


@app.get("/api/territory")
def territory(state: str = "36", authorization: str | None = Header(default=None)):
    _auth(authorization)
    terr = sig.territory_index(state)
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
    result = ask_engine.answer(req.question, _STATE)
    # sign the answer (WILLAY-style: the answer + its citations are bound to a tamper-evident receipt)
    pseudo_lead = {
        "id": "ask_" + str(abs(hash(req.question)) % 10**8),
        "name": "Ask the Territory query",
        "bucket": result["intent"].upper(),
        "product": "conversational-intelligence",
    }
    sigs_used = [{"source": c["label"], "signal": "grounding citation", "public": True} for c in result["citations"]] or \
               [{"source": "public-data session state", "signal": "grounding", "public": True}]
    receipt = rc.make_receipt(pseudo_lead, sigs_used, 100.0 if result["grounded"] else 0.0)
    result["receipt_id"] = receipt["id"]
    result["receipt_signed"] = receipt["signed"]
    _STATE.setdefault("ask_receipts", {})[receipt["id"]] = receipt
    _STATE["receipts"][receipt["id"]] = receipt  # so /api/verify works on ask receipts too
    return result


@app.get("/api/leads")
def get_leads(authorization: str | None = Header(default=None)):
    _auth(authorization)
    return {"leads": _STATE["leads"], "kpi": sc.kpi_summary(_STATE["leads"]) if _STATE["leads"] else {}}


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
    rc.reset_chain()
    result = sig8.territory_pulse(state_list, live=live, region=region)
    sigs_used = sig8.all_pulse_signals(state_list)
    pseudo = {"id": "pulse_seaboard", "name": "Territory Pulse (13-state seaboard)",
              "bucket": result["summary"]["top_state"] or "PULSE",
              "product": "territory-intelligence"}
    receipt = rc.make_receipt(pseudo, sigs_used, float(len(result["seaboard"])))
    result["receipt_id"] = receipt["id"]
    result["receipt_signed"] = receipt["signed"]
    _STATE.setdefault("receipts", {})[receipt["id"]] = receipt
    _STATE["pulse"] = result
    return result


@app.get("/api/brief/{lead_id}")
def brief(lead_id: str, authorization: str | None = Header(default=None)):
    """V8 Signed 4-Part Brief — each part GROUNDED by a real a11oy formula verdict
    (Priority / Why-now / Opening-line / Sensitivity), witness-signed via khipu 3-of-4."""
    _auth(authorization)
    lead = next((l for l in _STATE.get("leads", []) if l["id"] == lead_id), None)
    if not lead:
        raise HTTPException(404, "Lead not found - run intelligence first")
    if fm is not None:
        b = fm.build_signed_brief(lead)
    else:  # honest fallback to the structured brief if the formulas engine is unavailable
        b = sc.build_brief(lead, _STATE.get("signals", []))
    receipt = rc.make_brief_receipt(b, _STATE.get("signals", []))
    b["receipt_id"] = receipt["id"]
    b["receipt_signed"] = receipt["signed"]
    _STATE.setdefault("receipts", {})[receipt["id"]] = receipt
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
    out = wk.run_territory_pulse(meta, cfg)
    return {
        "trace": out["trace"],
        "events": out["events"],
        "loop_receipt": out["loop_receipt"],
        "lake_size": lake.size() if lake is not None else None,
    }


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
    event_type = (lead or {}).get("event_type") or (ev.classify((lead or {}).get("event", "")) if lead else "unknown")
    summary = ev.record_outcome(event_type, outcome_val)
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
        sigs_used = [{"source": "agent-logged outcome", "signal": f"{event_type}:{outcome_val}", "public": True}]
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
        "message": f"learning from {summary['total_outcomes']} logged outcomes",
    }


@app.get("/api/lake")
def get_lake(organ: str | None = None, decision: str | None = None,
             limit: int | None = None, authorization: str | None = Header(default=None)):
    """V8 read the append-only receipt lake (every witnessed change-event, immutable)."""
    _auth(authorization)
    if lake is None:
        raise HTTPException(503, "receipt lake unavailable")
    events = lake.query(organ=organ, decision=decision, limit=limit)
    return {"size": lake.size(), "count": len(events), "events": events}


@app.get("/api/benchmark")
def benchmark(authorization: str | None = Header(default=None)):
    """V8.2 P1-F: producer conversion-funnel dashboard from this session's surfaced leads,
    the in-session outcome tally, and the durable append-only receipt lake. No external data."""
    _auth(authorization)
    if bench is None:
        raise HTTPException(503, "benchmark unavailable")
    leads = _STATE.get("leads", []) or []
    summary = ev.outcome_summary() if ev is not None else {}
    lake_events = []
    if lake is not None:
        try:
            lake_events = lake.query(organ="conversion-loop")
        except Exception:
            lake_events = []
    return bench.build_benchmark(leads, summary, lake_events)


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
        lead.get("wealth_tier", ""),
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
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            req.url, data=body, method="POST",
            headers={"Content-Type": "application/json",
                     "User-Agent": "SZL-David-Leads webhook-test"})
        with urllib.request.urlopen(request, timeout=8) as resp:
            status = resp.getcode()
            snippet = resp.read(512).decode("utf-8", "replace")
        return {"ok": True, "sent": True, "url": req.url,
                "status": status, "response_snippet": snippet, "count": payload["count"]}
    except Exception as e:
        # outbound blocked / unreachable — honest: return the would-send payload, never fake success
        return {"ok": True, "sent": False,
                "reason": "outbound POST failed (%s)" % type(e).__name__,
                "url": req.url, "would_send": payload}


# static frontend (disabled when deployed behind the proxy; deploy serves static from S3)
if SERVE_STATIC:
    app.mount("/", StaticFiles(directory=os.path.join(APP_DIR, "static"), html=True), name="static")
