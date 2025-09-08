# vLLM In-Process Hook Wiring Guide

This guide shows maintainers how to wire KV‑OptKit in-process hooks into a vLLM runtime so that telemetry and Engine Activity reflect real events (no dev hooks needed).

## What you’ll wire

- **Request lifecycle**: `on_request_start`, `on_request_update`, `on_request_finish`
- **Memory/page events**: `on_block_alloc`, `on_block_free`, `on_page_move`
- **Precise rollback (optional)**: `record_undo_add_back(gb)` for exact deltas used during rollback

APIs live here:
- `kvopt/integrations/vllm/hooks.py` — wrapper class `VLLMHooks`
- `kvopt/adapters/vllm_adapter.py` — adapter, `VLLMAdapter.current()`, `record_undo_add_back()`

## A. ASGI middleware around vLLM OpenAI server (request lifecycle)

```python
# run_vllm_with_kvopt.py
import uvicorn
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from vllm.entrypoints.openai.api_server import app as vllm_app

from kvopt.integrations.vllm.hooks import VLLMHooks
from kvopt.adapters.vllm_adapter import VLLMAdapter

adapter = VLLMAdapter.current() or VLLMAdapter(config={})
hooks = VLLMHooks(adapter)

class KVOptLifecycleMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = f"req-{id(request)}"
        is_completion = request.url.path in ("/v1/completions", "/v1/chat/completions")
        try:
            if is_completion:
                prompt_tokens = 0
                try:
                    body = await request.json()
                    prompt = body.get("prompt") or (body.get("messages") or [])
                    prompt_tokens = len(str(prompt).split())
                except Exception:
                    pass
                hooks.on_request_start(req_id, prompt_tokens)
            resp: Response = await call_next(request)
            return resp
        finally:
            if is_completion:
                hooks.on_request_finish(req_id)

vllm_app.add_middleware(KVOptLifecycleMiddleware)

if __name__ == "__main__":
    uvicorn.run(vllm_app, host="0.0.0.0", port=8000, log_level="info")
```

## B. Memory/block events (allocator/BlockManager)

```python
# Inside your allocator or BlockManager
from kvopt.integrations.vllm.hooks import VLLMHooks
from kvopt.adapters.vllm_adapter import VLLMAdapter

_hooks = None

def _hooks_init():
    global _hooks
    if _hooks is None:
        ad = VLLMAdapter.current()
        if ad:
            _hooks = VLLMHooks(ad)

def on_block_allocated(req_id: str, num_bytes: int):
    _hooks_init()
    if _hooks:
        _hooks.on_block_alloc(req_id, num_bytes)

def on_block_freed(req_id: str, num_bytes: int):
    _hooks_init()
    if _hooks:
        _hooks.on_block_free(req_id, num_bytes)

def on_page_moved(req_id: str, num_bytes: int, src_tier: str, dst_tier: str):
    _hooks_init()
    if _hooks:
        _hooks.on_page_move(req_id, num_bytes, src_tier, dst_tier)
```

## C. Precise rollbacks (optional)

```python
from kvopt.adapters.vllm_adapter import VLLMAdapter

ad = VLLMAdapter.current()
if ad:
    ad.record_undo_add_back(gb=0.125)  # add back 0.125 GB on rollback
```

## Validation checklist

- **QuickView → Engine Activity** updates:
  - moves increments; alloc/free/moved bytes reflect your events
- **Prometheus**: `/metrics` shows counters rising
  - `kvopt_engine_alloc_bytes_total`, `kvopt_engine_free_bytes_total`
  - `kvopt_engine_page_moves_total`, `kvopt_engine_page_moved_bytes_total`
- **Telemetry Parity (GPU)**:
  - `python scripts/telemetry_parity.py --server http://localhost:9001 --device 0 --tolerance 0.05`
  - expect ≤ 5% deltas

## Pitfalls

- Only call hooks on success paths (avoid double counting).
- Avoid double-calling at multiple wrapper layers.
- Maintain stable `req_id` mapping when batching changes structure.
- Coalesce token updates in high‑QPS paths (e.g., every N tokens or X ms).
