"""vLLM integration adapter stubs.

These are placeholders to illustrate how KV-OptKit plugins could be wired into
vLLM. They do not perform real integration yet.
"""
from typing import Any, Dict, List

from kvopt.plugins.lmcache_plugin import LMCachePlugin
from kvopt.plugins.kivi_plugin import KIVIPlugin


class VLLMLMCacheAdapter:
    """Stub adapter to connect LMCachePlugin to a vLLM-like interface."""

    def __init__(self, plugin: LMCachePlugin):
        self.plugin = plugin

    def on_prefill(self, sequence_id: str, tokens: List[int]) -> Dict[str, Any]:
        """Called before model prefill to attempt KV reuse."""
        return self.plugin.check_cache(sequence_id, tokens)

    def on_store(self, sequence_id: str, tokens: List[int], kv_data: Dict[str, Any]) -> None:
        """Called after prefill/decoding to store KV for reuse."""
        self.plugin.update_cache(sequence_id, tokens, kv_data)


class VLLMKIVIAdapter:
    """Stub adapter to apply KIVI quantization on KV blocks in a vLLM-like flow."""

    def __init__(self, plugin: KIVIPlugin):
        self.plugin = plugin

    def quantize_block(self, kv_data: Dict[str, Any], layer_idx: int, token_pos: int) -> Dict[str, Any]:
        return self.plugin.quantize(kv_data, layer_idx=layer_idx, token_pos=token_pos)

    def dequantize_block(self, kv_data: Dict[str, Any], layer_idx: int, token_pos: int) -> Dict[str, Any]:
        return self.plugin.dequantize(kv_data, layer_idx=layer_idx, token_pos=token_pos)
