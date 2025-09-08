"""
Simulator Router

Provides endpoints for interacting with the simulator adapter so that
client demos (e.g., examples/demo_trace.py) can submit, finish, and reset
sequences.
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any

from kvopt.adapters.sim_adapter import SimAdapter

router = APIRouter(prefix="/sim", tags=["simulator"])


class SubmitRequest(BaseModel):
    seq_id: str
    tokens: int


class RangeRequest(BaseModel):
    seq_id: str
    start_token: int = Field(ge=0)
    end_token: int = Field(ge=0)


class QuantizeRequest(RangeRequest):
    factor: float = Field(gt=0.0, lt=1.0)


def _get_sim_adapter():
    """Get the simulator adapter, ensuring it's the right type."""
    # Import here to avoid circular imports
    from kvopt.server.main import _adapter

    if _adapter is None:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    if not isinstance(_adapter, SimAdapter):
        raise HTTPException(status_code=400, detail="Current adapter is not the simulator")
    return _adapter


@router.post("/reset")
async def reset_simulator() -> Dict[str, Any]:
    """Reset the simulator state."""
    adapter = _get_sim_adapter()
    return adapter.reset()


@router.post("/submit")
async def submit_sequence(req: SubmitRequest) -> Dict[str, Any]:
    """Submit a sequence to the simulator."""
    adapter = _get_sim_adapter()
    try:
        ok = adapter.submit_sequence(req.seq_id, req.tokens)
        if not ok:
            raise HTTPException(status_code=400, detail=f"Sequence {req.seq_id} already exists")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("Error in /sim/submit: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/evict")
async def evict_tokens(req: RangeRequest) -> Dict[str, Any]:
    """Evict tokens from HBM for a sequence within [start_token, end_token]."""
    adapter = _get_sim_adapter()
    try:
        result = adapter.evict(req.seq_id, req.start_token, req.end_token)
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("message", "Evict failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("Error in /sim/evict: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/offload")
async def offload_tokens(req: RangeRequest) -> Dict[str, Any]:
    """Offload tokens from HBM to DDR within [start_token, end_token]."""
    adapter = _get_sim_adapter()
    try:
        result = adapter.offload(req.seq_id, req.start_token, req.end_token)
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("message", "Offload failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("Error in /sim/offload: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quantize")
async def quantize_tokens(req: QuantizeRequest) -> Dict[str, Any]:
    """Quantize tokens in HBM within [start_token, end_token] by a factor (0,1)."""
    adapter = _get_sim_adapter()
    try:
        result = adapter.quantize(req.seq_id, req.start_token, req.end_token, req.factor)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("message", "Quantize failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("Error in /sim/quantize: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dequantize")
async def dequantize_tokens(req: RangeRequest) -> Dict[str, Any]:
    """Revert quantization in HBM within [start_token, end_token] back to full precision."""
    adapter = _get_sim_adapter()
    try:
        result = adapter.dequantize(req.seq_id, req.start_token, req.end_token)
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("message", "Dequantize failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("Error in /sim/dequantize: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/finish/{seq_id}")
async def finish_sequence(seq_id: str) -> Dict[str, Any]:
    """Finish (remove) a sequence from the simulator."""
    adapter = _get_sim_adapter()
    ok = adapter.finish_sequence(seq_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Sequence {seq_id} not found")
    return {"success": True}


@router.get("/sequences")
async def list_sequences() -> Dict[str, Any]:
    """List current sequences and their segments in the simulator."""
    adapter = _get_sim_adapter()
    return {"success": True, "sequences": adapter.get_sequences()}


@router.get("/telemetry")
async def get_telemetry() -> Dict[str, Any]:
    """Return current telemetry from the simulator adapter."""
    adapter = _get_sim_adapter()
    try:
        telem = adapter.get_telemetry()
        return {"success": True, **telem}
    except Exception as e:
        logging.exception("Error in /sim/telemetry: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug")
async def debug_sim() -> Dict[str, Any]:
    """Return adapter type and simple state for diagnostics."""
    try:
        adapter = _get_sim_adapter()
        seqs = adapter.get_sequences()
        return {
            "success": True,
            "adapter_type": adapter.__class__.__name__,
            "total_sequences": len(seqs),
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        logging.exception("Error in /sim/debug: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
