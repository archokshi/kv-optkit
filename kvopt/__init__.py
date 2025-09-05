"""
KV-OptKit: Optimization layer for LLM inference with KV-cache management.

This package provides tools for optimizing KV-cache memory usage in LLM inference,
including policy-based eviction, offloading, and tiered storage strategies.
"""

__version__ = "0.4.1"

# Import key components for easier access
from .config import Config
from .adapters.sim_adapter import SimAdapter
from .adapters.vllm_adapter import VLLMAdapter
from .agent.policy import PolicyEngine

__all__ = [
    'Config',
    'SimAdapter',
    'VLLMAdapter',
    'PolicyEngine',
]
