"""
SCP V105 — Prediction endpoints (Reality v4)

Live — admin auth required (Fix 4-a-003). Router IS registered in
api_server.py (around line 589-611) via `app.include_router(prediction_router)`.
The 5 routes below (`/v105/predictions/run-cycle`,
`/v105/predictions/pending`, `/v105/predictions/all`,
`/v105/predictions/verify`, `/v105/predictions/stats`) are LIVE and
require `Depends(verify_admin)` because `run-cycle` + `verify` are
state-changing POST endpoints that trigger the Crawl → Generate →
Predict → Verify → Learn pipeline (CPU/IO expensive — DoS amplifier
if unauthenticated). It imports `from scp.api_server import
_predictive_engine`, so the engine singleton must be initialised first
— see `_predictive_engine` initialisation in api_server.py.

[COMPLETION-FIX] Wire PredictiveOrchestrator vào API:
- POST /v105/predictions/run-cycle — chạy 1 prediction cycle
- GET  /v105/predictions/pending — list pending predictions
- GET  /v105/predictions/all — list all predictions
- POST /v105/predictions/verify — verify pending predictions
- GET  /v105/predictions/stats — prediction statistics
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from scp.api._shared import verify_admin

logger = logging.getLogger("scp.api.predictions")

router = APIRouter(prefix="/v105/predictions", tags=["predictions"])


class VerifyRequest(BaseModel):
    limit: int = Field(20, ge=1, le=100)


def _get_engine():
    """Get PredictiveOrchestrator singleton."""
    from scp.api_server import _predictive_engine
    if _predictive_engine is None:
        raise HTTPException(status_code=503, detail="PredictiveEngine not initialized")
    return _predictive_engine


@router.post("/run-cycle", dependencies=[Depends(verify_admin)])  # Fix 4-a-003: BFLA auth (state-changing)
async def run_prediction_cycle():
    """Chạy 1 cycle: Crawl → Generate → Predict → Verify → Learn."""
    engine = _get_engine()
    try:
        result = engine.run_cycle()
        return {"status": "ok", "cycle": result}
    except Exception as e:
        logger.error(f"Prediction cycle failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Prediction cycle failed — see server logs") from e


@router.get("/pending", dependencies=[Depends(verify_admin)])  # Fix 4-a-003: BFLA auth
async def get_pending_predictions(limit: int = 20):
    """List pending predictions (chưa verify)."""
    engine = _get_engine()
    preds = engine.predictor.get_pending_predictions()
    return {"pending": preds[:limit], "total": len(preds)}


@router.get("/all", dependencies=[Depends(verify_admin)])  # Fix 4-a-003: BFLA auth
async def get_all_predictions(limit: int = 100):
    """List all predictions (pending + verified)."""
    engine = _get_engine()
    preds = engine.predictor.get_all_predictions(limit=limit)
    return {"predictions": preds, "total": len(preds)}


@router.post("/verify", dependencies=[Depends(verify_admin)])  # Fix 4-a-003: BFLA auth (state-changing)
async def verify_predictions(req: VerifyRequest):
    """Verify pending predictions (nếu đến check_date)."""
    engine = _get_engine()
    try:
        results = engine.verifier.verify_pending(limit=req.limit)
        return {"verified": len(results), "results": results}
    except Exception as e:
        logger.error(f"Verify failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Verify failed — see server logs") from e


@router.get("/stats", dependencies=[Depends(verify_admin)])  # Fix 4-a-003: BFLA auth
async def prediction_stats():
    """Prediction statistics."""
    engine = _get_engine()
    all_preds = engine.predictor.get_all_predictions(limit=10000)
    pending = [p for p in all_preds if p.get("status") == "pending"]
    verified = [p for p in all_preds if p.get("status") != "pending"]
    correct = [p for p in verified if p.get("status") == "correct"]
    wrong = [p for p in verified if p.get("status") == "wrong"]
    return {
        "total": len(all_preds),
        "pending": len(pending),
        "verified": len(verified),
        "correct": len(correct),
        "wrong": len(wrong),
        "accuracy": len(correct) / len(verified) if verified else 0.0,
    }
