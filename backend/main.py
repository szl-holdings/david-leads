# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — david-leads vertical
"""david-leads v0 — public insurance-intelligence vertical.

FastAPI service: honest source states, a clearly-labeled synthetic demo
dataset for offline runs, transparent Lambda-spine scoring, and a
tamper-evident receipt (DSSE/ECDSA-P256 when keyed, honestly UNSIGNED when
not) on every scoring decision — including decisions to emit no score.

Run:  uvicorn backend.main:app --port 8000
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, receipts, scoring
from .adapters import ALL_ADAPTERS, get as get_adapter
from .models import (
    ScoreRequest,
    ScoreResponse,
    TruthState,
    VerifyRequest,
    VerifyResponse,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="david-leads",
    version=__version__,
    description=(
        "Public-record-driven insurance lead intelligence. Every scoring "
        "decision carries a receipt with a declared truth_state. Licensed "
        "commercial sources report UNAVAILABLE until licensed; synthetic demo "
        "records are labeled and can never ground a VERIFIED claim."
    ),
)


@app.get("/healthz")
def healthz() -> dict:
    """Liveness with a declared truth state — not a bare 200."""
    return {
        "status": "ok",
        "service": "david-leads",
        "version": __version__,
        "truth_state": TruthState.VERIFIED.value,
        "detail": "process up; see /v1/sources for per-source truth states",
    }


@app.get("/v1/sources")
def sources() -> dict:
    """Honest state of every ingestion adapter, licensed or not."""
    statuses = [a.status() for a in ALL_ADAPTERS]
    return {
        "adapters": [s.model_dump() for s in statuses],
        "doctrine": "UNAVAILABLE is an audited state; no source fabricates records to look alive.",
    }


@app.get("/v1/leads")
def leads() -> dict:
    """The synthetic demo dataset, labeled as such in both directions."""
    demo = get_adapter("demo_synthetic")
    records = demo.fetch() if demo else []
    status = demo.status() if demo else None
    return {
        "dataset": "synthetic-demo-v1",
        "synthetic": True,
        "adapter_state": status.model_dump() if status else None,
        "leads": [r.model_dump(mode="json") for r in records],
    }


@app.post("/v1/score", response_model=ScoreResponse)
def score(req: ScoreRequest) -> dict:
    """Score one lead and return the decision with its receipt.

    Exactly one of lead_id (a stored demo record) or an inline lead is
    required. A lead with no admitted evidence returns score=null with
    truth_state=INCOMPLETE and a receipt for that refusal.
    """
    if bool(req.lead_id) == bool(req.lead):
        raise HTTPException(status_code=422, detail="provide exactly one of lead_id or lead")
    if req.lead_id:
        demo = get_adapter("demo_synthetic")
        record = next((r for r in demo.fetch() if r.id == req.lead_id), None) if demo else None
        if record is None:
            raise HTTPException(
                status_code=404,
                detail=f"no demo lead with id {req.lead_id!r}; the demo set never substitutes "
                       "a stand-in record (Zero-Bandaid)",
            )
    else:
        record = req.lead
    return scoring.score_lead(record)


@app.post("/v1/receipts/verify", response_model=VerifyResponse)
def verify(req: VerifyRequest) -> dict:
    """Offline receipt verification: hash re-derivation, ECDSA check when a
    public key is configured, and explicit chain-link state."""
    return receipts.verify_receipt(req.receipt, req.previous_receipt)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
