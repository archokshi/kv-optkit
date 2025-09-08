"""
Adapters for different KV cache implementations with a central registry.
"""
from typing import Dict, Type, Any

from .base import Adapter
from .sim_adapter import SimAdapter
from .vllm_adapter import VLLMAdapter
from .tgi_adapter import TGIAdapter
from .trtllm_adapter import TRTLLMAdapter
from .deepspeed_adapter import DeepSpeedMIIAdapter

# Adapter registry maps canonical type names to classes
ADAPTER_REGISTRY: Dict[str, Type[Adapter]] = {
    "sim": SimAdapter,
    "vllm": VLLMAdapter,
    "tgi": TGIAdapter,
    "trtllm": TRTLLMAdapter,
    "deepspeed": DeepSpeedMIIAdapter,
}


def get_adapter_class(name: str) -> Type[Adapter]:
    key = (name or "").lower()
    if key not in ADAPTER_REGISTRY:
        raise ValueError(f"Unknown adapter type '{name}'. Known: {sorted(ADAPTER_REGISTRY.keys())}")
    return ADAPTER_REGISTRY[key]


def create_adapter(name: str, config: Dict[str, Any]) -> Adapter:
    cls = get_adapter_class(name)
    return cls(config)


__all__ = [
    'SimAdapter', 'VLLMAdapter', 'TGIAdapter', 'TRTLLMAdapter', 'DeepSpeedMIIAdapter',
    'ADAPTER_REGISTRY', 'get_adapter_class', 'create_adapter',
]
