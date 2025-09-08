from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

# Development-only router to trigger adapter hook callbacks via HTTP.
# Enabled only when KVOPT_DEV=1 in server startup (see kvopt/server/main.py).

router = APIRouter(prefix="/dev/hooks", tags=["dev-hooks"])


def _get_adapter():
    from kvopt.server import main as server_main
    return getattr(server_main, "_adapter", None)


class AllocPayload(BaseModel):
    sequence_id: str = Field(...)
    bytes: int = Field(..., ge=0)


class FreePayload(BaseModel):
    sequence_id: str = Field(...)
    bytes: int = Field(..., ge=0)


class MovePayload(BaseModel):
    sequence_id: str = Field(...)
    bytes: int = Field(..., ge=0)
    src: str = Field(...)
    dst: str = Field(...)


@router.post("/alloc")
def alloc(payload: AllocPayload):
    ad = _get_adapter()
    if not ad:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    if hasattr(ad, "on_block_alloc"):
        ad.on_block_alloc(payload.sequence_id, int(payload.bytes))
        return {"ok": True}
    return {"ok": True, "note": "adapter missing on_block_alloc; no-op"}


@router.post("/free")
def free(payload: FreePayload):
    ad = _get_adapter()
    if not ad:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    if hasattr(ad, "on_block_free"):
        ad.on_block_free(payload.sequence_id, int(payload.bytes))
        return {"ok": True}
    return {"ok": True, "note": "adapter missing on_block_free; no-op"}


@router.post("/move")
def move(payload: MovePayload):
    ad = _get_adapter()
    if not ad:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    if hasattr(ad, "on_page_move"):
        ad.on_page_move(payload.sequence_id, int(payload.bytes), payload.src, payload.dst)
        return {"ok": True}
    return {"ok": True, "note": "adapter missing on_page_move; no-op"}
