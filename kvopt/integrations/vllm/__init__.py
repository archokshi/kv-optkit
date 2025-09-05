"""vLLM integration stubs for KV-OptKit.

These adapters are placeholders to wire LMCachePlugin and KIVIPlugin later.
They expose minimal method signatures to be used by a future vLLM hook.
"""
from .adapters import VLLMLMCacheAdapter, VLLMKIVIAdapter

__all__ = [
    "VLLMLMCacheAdapter",
    "VLLMKIVIAdapter",
]
