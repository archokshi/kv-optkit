#!/usr/bin/env python3
"""
KV-OptKit Sidecar Proxy

A small FastAPI service that proxies requests to an upstream vLLM server
(OpenAI-compatible endpoints) and emits KV-OptKit sequence lifecycle events
(/sequences/start, /sequences/update, /sequences/finish) so KV-OptKit can
track real sequences without in-process hooks.

Environment variables:
  UPSTREAM_VLLM_URL   (default: http://localhost:8000)
  KVOPT_URL           (default: http://localhost:9001)
  PROXY_PORT          (default: 9010)

Supported endpoints (non-streaming):
  - POST /v1/completions
  - POST /v1/chat/completions

Notes:
- Token counting is best-effort unless the upstream returns usage.completion_tokens.
- For streaming, extend this proxy to parse SSE chunks and issue /sequences/update
  periodically with delta tokens.
"""
import os
import time
import uuid
from typing import Any, Dict

import uvicorn
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
import httpx

UPSTREAM_VLLM_URL = os.getenv("UPSTREAM_VLLM_URL", "http://localhost:8000").rstrip("/")
KVOPT_URL = os.getenv("KVOPT_URL", "http://localhost:9001").rstrip("/")
PROXY_PORT = int(os.getenv("PROXY_PORT", "9010"))

app = FastAPI(title="KV-OptKit Sidecar Proxy")
client = httpx.AsyncClient(timeout=30)


def _gen_request_id() -> str:
    return f"req-{int(time.time()*1000)}-{uuid.uuid4().hex[:8]}"


def _count_prompt_tokens(body: Dict[str, Any]) -> int:
    # Prefer explicit tokenized input if present; otherwise approximate by whitespace
    if isinstance(body.get("prompt"), str):
        return len((body.get("prompt") or "").split())
    if isinstance(body.get("input"), str):
        return len((body.get("input") or "").split())
    # chat format: array of messages
    msgs = body.get("messages")
    if isinstance(msgs, list):
        s = " ".join([m.get("content", "") for m in msgs if isinstance(m, dict)])
        return len(s.split())
    return int(body.get("prompt_tokens", 0) or 0)


def _count_generated_tokens(resp_json: Dict[str, Any]) -> int:
    # OpenAI-like usage preferred
    usage = resp_json.get("usage") or {}
    if "completion_tokens" in usage:
        try:
            return int(usage["completion_tokens"])  # type: ignore[arg-type]
        except Exception:
            pass
    # Fallbacks
    try:
        # /v1/completions: choices[0].text
        if isinstance(resp_json.get("choices"), list) and resp_json["choices"]:
            text = resp_json["choices"][0].get("text", "")
            if text:
                return len(str(text).split())
    except Exception:
        pass
    try:
        # /v1/chat/completions: choices[0].message.content
        if isinstance(resp_json.get("choices"), list) and resp_json["choices"]:
            content = (((resp_json["choices"][0] or {}).get("message") or {}).get("content"))
            if content:
                return len(str(content).split())
    except Exception:
        pass
    return 0


async def _seq_start(seq_id: str, total_tokens: int) -> None:
    try:
        await client.post(f"{KVOPT_URL}/sequences/start", json={
            "sequence_id": seq_id,
            "total_tokens": int(max(0, total_tokens)),
        })
    except Exception:
        pass


async def _seq_update(seq_id: str, delta_tokens: int) -> None:
    try:
        if delta_tokens:
            await client.post(f"{KVOPT_URL}/sequences/update", json={
                "sequence_id": seq_id,
                "delta_tokens": int(delta_tokens),
            })
    except Exception:
        pass


async def _seq_finish(seq_id: str) -> None:
    try:
        await client.post(f"{KVOPT_URL}/sequences/finish", json={
            "sequence_id": seq_id,
        })
    except Exception:
        pass


@app.post("/v1/completions")
async def completions(request: Request):
    body = await request.json()
    seq_id = body.get("request_id") or _gen_request_id()
    prompt_tokens = _count_prompt_tokens(body)

    # Notify start
    await _seq_start(seq_id, prompt_tokens)

    # If streaming requested, proxy SSE and emit updates incrementally
    if bool(body.get("stream")):
        async def _stream_generator():
            nonlocal body, seq_id
            try:
                async with client.stream("POST", f"{UPSTREAM_VLLM_URL}/v1/completions", json=body) as upstream:
                    acc_text = ""
                    async for chunk in upstream.aiter_bytes():
                        # Forward to client
                        yield chunk
                        # Heuristic: count words delta in the SSE data payload
                        try:
                            s = chunk.decode("utf-8", errors="ignore")
                            acc_text += s
                            # crude split on whitespace; update when buffer grows
                            words = len(acc_text.split())
                            if words > 0:
                                await _seq_update(seq_id, max(0, words))
                                acc_text = ""
                        except Exception:
                            pass
            except Exception as e:
                # End sequence on stream error
                await _seq_finish(seq_id)
                raise HTTPException(status_code=502, detail=f"Upstream stream error: {e}")
            # Finish at end of stream
            await _seq_finish(seq_id)

        return StreamingResponse(_stream_generator(), media_type="text/event-stream")

    # Non-streaming: Forward to upstream vLLM
    try:
        upstream = await client.post(f"{UPSTREAM_VLLM_URL}/v1/completions", json=body)
    except Exception as e:
        await _seq_finish(seq_id)
        raise HTTPException(status_code=502, detail=f"Upstream error: {e}")

    data = {}
    try:
        data = upstream.json()
    except Exception:
        pass

    # Notify update and finish
    generated = _count_generated_tokens(data)
    if generated:
        await _seq_update(seq_id, generated)
    await _seq_finish(seq_id)

    return JSONResponse(content=data, status_code=upstream.status_code, headers=dict(upstream.headers))


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    seq_id = body.get("request_id") or _gen_request_id()
    prompt_tokens = _count_prompt_tokens(body)

    await _seq_start(seq_id, prompt_tokens)
    # Streaming path for chat
    if bool(body.get("stream")):
        async def _stream_generator():
            nonlocal body, seq_id
            try:
                async with client.stream("POST", f"{UPSTREAM_VLLM_URL}/v1/chat/completions", json=body) as upstream:
                    acc_text = ""
                    async for chunk in upstream.aiter_bytes():
                        yield chunk
                        try:
                            s = chunk.decode("utf-8", errors="ignore")
                            acc_text += s
                            words = len(acc_text.split())
                            if words > 0:
                                await _seq_update(seq_id, max(0, words))
                                acc_text = ""
                        except Exception:
                            pass
            except Exception as e:
                await _seq_finish(seq_id)
                raise HTTPException(status_code=502, detail=f"Upstream stream error: {e}")
            await _seq_finish(seq_id)

        return StreamingResponse(_stream_generator(), media_type="text/event-stream")

    try:
        upstream = await client.post(f"{UPSTREAM_VLLM_URL}/v1/chat/completions", json=body)
    except Exception as e:
        await _seq_finish(seq_id)
        raise HTTPException(status_code=502, detail=f"Upstream error: {e}")

    data = {}
    try:
        data = upstream.json()
    except Exception:
        pass

    generated = _count_generated_tokens(data)
    if generated:
        await _seq_update(seq_id, generated)
    await _seq_finish(seq_id)

    return JSONResponse(content=data, status_code=upstream.status_code, headers=dict(upstream.headers))


if __name__ == "__main__":
    uvicorn.run("kvopt_sidecar_proxy:app", host="0.0.0.0", port=PROXY_PORT, reload=False)
