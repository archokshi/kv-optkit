"""
Base adapter interface for KV cache implementations.

This module defines the base adapter interface that all KV cache adapters must implement.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Type, TypeVar, Generic

T = TypeVar('T', bound='Adapter')

class Adapter(ABC):
    """Base class for KV cache adapters."""
    _instance = None
    
    @classmethod
    def get_current(cls: Type[T]) -> T:
        """Get the current adapter instance (singleton pattern)."""
        if cls._instance is None:
            raise RuntimeError("No adapter instance has been created")
        return cls._instance

    @classmethod
    def get_current_optional(cls: Type[T]) -> Optional[T]:
        """Return current adapter if set, otherwise None.
        Useful for routes that have compatibility fallbacks in tests.
        """
        return cls._instance
    
    @abstractmethod
    def get_telemetry(self) -> Dict[str, Any]:
        """Get current system telemetry."""
        pass
    
    @abstractmethod
    def execute_action(self, action: Dict[str, Any]) -> bool:
        """Execute an optimization action."""
        pass
    
    @abstractmethod
    def get_sequences(self) -> List[Dict[str, Any]]:
        """Get information about all sequences in the KV cache."""
        pass

    # ---- EngineAdapter protocol (non-breaking defaults) ----
    def capabilities(self) -> set:
        """Return a set of supported actions, e.g., {"EVICT","OFFLOAD","QUANTIZE","REUSE"}.

        Default is empty set, meaning observe-only (L0). Implementers should override.
        """
        return set()

    def get_telemetry_schema_version(self) -> str:
        """Telemetry schema version for forward compatibility (default 'v1')."""
        return "v1"
