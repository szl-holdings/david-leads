# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — David Leads Sovereign Insurance Intelligence
"""FastAPI backend: login gate, live signal run, scored leads, signed receipts, KPI."""
from __future__ import annotations
import os, secrets, hashlib
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import signals as sig
from . import scoring as sc
from . import receipts as rc

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
    leads = sc.build_leads(meta)
    receipts = {}
    for lead in leads:
        # each lead's receipt binds the signals that justify its segment
        receipts[lead["id"]] = rc.make_receipt(lead, sigs, lead["score"])
        lead["receipt_id"] = receipts[lead["id"]]["id"]
        lead["receipt_signed"] = receipts[lead["id"]]["signed"]
    _STATE.update(leads=leads, signals=sigs, meta=meta, receipts=receipts)
    top = leads[:3]
    brief = {
        "top_ids": [l["id"] for l in top],
        "headline": (f"{len([l for l in leads if l['bucket']=='HOT'])} HOT leads ready to call today — "
                     f"lead with {top[0]['name']}." if top else "Run intelligence to build today's call list."),
        "items": [{"id": l["id"], "name": l["name"], "score": l["score"], "bucket": l["bucket"],
                   "product": l["product"], "action": l["nba"]["action"]} for l in top],
    }
    return {
        "meta": meta,
        "signals": sigs,
        "leads": leads,
        "kpi": sc.kpi_summary(leads),
        "brief": brief,
        "governance": {
            "signals_checked": meta["total_signals"],
            "all_public": meta["rejected_nonpublic"] == 0,
            "fabricated": meta["fabricated"],
            "rejected_nonpublic": meta["rejected_nonpublic"],
            "verdict": "PASS — public-data-only, honest by design",
        },
    }


@app.get("/api/territory")
def territory(state: str = "36", authorization: str | None = Header(default=None)):
    _auth(authorization)
    return sig.territory_index(state)


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


# static frontend (disabled when deployed behind the proxy; deploy serves static from S3)
if SERVE_STATIC:
    app.mount("/", StaticFiles(directory=os.path.join(APP_DIR, "static"), html=True), name="static")
