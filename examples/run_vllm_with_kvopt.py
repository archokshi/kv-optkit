"""
Example: Run vLLM OpenAI server with KV-OptKit lifecycle middleware.

This demonstrates in-process wiring for request start/finish. For token updates
and memory/page events, wire the hooks inside vLLM internals as shown in
`docs/maintainers/vllm-hooks.md` (sections B and C).

Usage (developer machine):
    # In one terminal, optionally run KV-OptKit server separately
    #   $env:KVOPT_ADAPTER="vllm"; $env:KVOPT_PORT="9001"; python -m kvopt.server.main

    # In another terminal, run this example to launch vLLM OpenAI server (port 8000)
    # with the KV-OptKit lifecycle middleware attached
    python examples/run_vllm_with_kvopt.py

Then open QuickView at http://localhost:9001/ and drive requests to
http://localhost:8000/ (or via the sidecar). See Engine Activity and telemetry.
"""
from __future__ import annotations

import uvicorn
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

try:
    from vllm.entrypoints.openai.api_server import app as vllm_app
except Exception as e:  # pragma: no cover
    raise SystemExit(
        "vLLM is not installed or import failed. Install vllm first to run this example."
    ) from e

from kvopt.integrations.vllm.hooks import VLLMHooks
from kvopt.adapters.vllm_adapter import VLLMAdapter


def _get_hooks() -> VLLMHooks:
    # Get the live adapter; if KV-OptKit is not running in this process, you can
    # still construct a local adapter instance for dev-only visualization.
    adapter = VLLMAdapter.current() or VLLMAdapter(config={})
    return VLLMHooks(adapter)


class KVOptLifecycleMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        hooks = _get_hooks()
        req_id = f"req-{id(request)}"
        path = request.url.path
        is_completion = path in ("/v1/completions", "/v1/chat/completions")
        try:
            if is_completion:
                prompt_tokens = 0
                try:
                    body = await request.json()
                    prompt = body.get("prompt") or (body.get("messages") or [])
                    prompt_tokens = len(str(prompt).split())
                except Exception:
                    pass
                hooks.on_request_start(req_id, int(prompt_tokens))
            resp: Response = await call_next(request)
            return resp
        finally:
            if is_completion:
                hooks.on_request_finish(req_id)


# Attach middleware to the vLLM ASGI app
vllm_app.add_middleware(KVOptLifecycleMiddleware)


if __name__ == "__main__":
    uvicorn.run(vllm_app, host="0.0.0.0", port=8000, log_level="info")
