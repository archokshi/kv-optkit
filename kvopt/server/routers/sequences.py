from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

# This router exposes sequence lifecycle endpoints so external engines (sidecar mode)
# can notify KV-OptKit about request lifecycles without in-process hooks.
# Endpoints are adapter-agnostic and will no-op if the active adapter does not
# implement the corresponding tracking functions.

router = APIRouter(prefix="/sequences", tags=["sequences"])


class SeqStart(BaseModel):
    sequence_id: str = Field(..., description="Unique sequence/request id")
    total_tokens: int = Field(..., ge=0, description="Initial total tokens (e.g., prompt tokens)")


class SeqUpdate(BaseModel):
    sequence_id: str
    delta_tokens: int = Field(..., description="New tokens generated since last update (can be negative for truncation)")


class SeqFinish(BaseModel):
    sequence_id: str


def _get_adapter():
    # Import lazily to avoid circular imports
    from kvopt.server import main as server_main
    return getattr(server_main, "_adapter", None)


@router.post("/start")
def seq_start(payload: SeqStart):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    if hasattr(adapter, "track_request_start"):
        adapter.track_request_start(payload.sequence_id, payload.total_tokens)
        return {"ok": True}
    # Fallback: create a minimal sequence if SIM supports generic submit
    if hasattr(adapter, "submit_sequence"):
        try:
            adapter.submit_sequence(payload.sequence_id, payload.total_tokens)
            return {"ok": True, "note": "created via submit_sequence fallback"}
        except Exception:
            pass
    # Be lenient to allow CPU-only validation without hooks
    return {"ok": True, "note": "adapter does not implement sequence tracking; accepted no-op"}


@router.post("/update")
def seq_update(payload: SeqUpdate):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    if hasattr(adapter, "track_request_update"):
        adapter.track_request_update(payload.sequence_id, payload.delta_tokens)
        return {"ok": True}
    # Be lenient: accept and no-op
    return {"ok": True, "note": "adapter does not implement sequence tracking; accepted no-op"}


@router.post("/finish")
def seq_finish(payload: SeqFinish):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    if hasattr(adapter, "track_request_finish"):
        adapter.track_request_finish(payload.sequence_id)
        return {"ok": True}
    # Fallback: try SIM finish_sequence
    if hasattr(adapter, "finish_sequence"):
        try:
            ok = adapter.finish_sequence(payload.sequence_id)
            return {"ok": bool(ok), "note": "finished via finish_sequence fallback"}
        except Exception:
            pass
    return {"ok": True, "note": "adapter does not implement sequence tracking; accepted no-op"}
