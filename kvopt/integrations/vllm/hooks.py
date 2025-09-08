"""
In-process vLLM integration stub for KV-OptKit.

This module demonstrates how an embedding within a vLLM runtime could call back
into the KV-OptKit vLLM adapter to provide accurate sequence/block events.

Note: This file intentionally does NOT import vLLM to avoid a hard dependency.
It shows the shape of the integration and where to call the adapter hooks.
"""
from __future__ import annotations
from typing import Any, Optional

from ...adapters.vllm_adapter import VLLMAdapter


class VLLMHooks:
    """A light wrapper that engine code can use to notify KV-OptKit.

    Typical usage from inside the vLLM runtime (pseudocode):

        adapter = VLLMAdapter.current()
        hooks = VLLMHooks(adapter)
        engine.register_allocation_callback(hooks.on_block_alloc)
        engine.register_free_callback(hooks.on_block_free)
        engine.register_page_move_callback(hooks.on_page_move)
        engine.register_request_lifecycle(
            on_start=hooks.on_request_start,
            on_update=hooks.on_request_update,
            on_finish=hooks.on_request_finish,
        )

    The adapter will aggregate events and expose them via /telemetry and
    /sequences endpoints.
    """

    def __init__(self, adapter: Optional[VLLMAdapter] = None):
        # If not provided, try to get the process-global instance if such accessor exists
        self.adapter = adapter or getattr(VLLMAdapter, "_instance", None)
        if not self.adapter:
            raise RuntimeError("VLLMAdapter is not initialized")

    # --- Request lifecycle ---
    def on_request_start(self, request_id: str, prompt_token_count: int) -> None:
        self.adapter.track_request_start(request_id, int(prompt_token_count))

    def on_request_update(self, request_id: str, delta_tokens: int) -> None:
        self.adapter.track_request_update(request_id, int(delta_tokens))

    def on_request_finish(self, request_id: str) -> None:
        self.adapter.track_request_finish(request_id)

    # --- Memory/block events ---
    def on_block_alloc(self, request_id: str, bytes_alloc: int) -> None:
        self.adapter.on_block_alloc(request_id, int(bytes_alloc))

    def on_block_free(self, request_id: str, bytes_free: int) -> None:
        self.adapter.on_block_free(request_id, int(bytes_free))

    def on_page_move(self, request_id: str, bytes_moved: int, src_tier: str, dst_tier: str) -> None:
        self.adapter.on_page_move(request_id, int(bytes_moved), str(src_tier), str(dst_tier))
