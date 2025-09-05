"""
KV-OptKit Plugins

This module provides plugin interfaces and implementations for extending KV-OptKit
functionality, including KV cache reuse and quantization.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Type, Union
from dataclasses import dataclass
from enum import Enum

class PluginType(Enum):
    """Plugin types."""
    KV_CACHE = "kv_cache"
    QUANTIZATION = "quantization"
    OTHER = "other"

@dataclass
class PluginConfig:
    """Base configuration for plugins."""
    name: str
    enabled: bool = True
    priority: int = 100  # Lower numbers execute first
    plugin_type: PluginType = PluginType.OTHER

class BasePlugin(ABC):
    """Base class for all KV-OptKit plugins."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the plugin with configuration."""
        self.config = self.validate_config(config)
        
    @abstractmethod
    def validate_config(self, config: Dict[str, Any]) -> PluginConfig:
        """Validate and convert plugin configuration."""
        pass
    
    @abstractmethod
    def on_startup(self):
        """Called when the plugin is first loaded."""
        pass
    
    @abstractmethod
    def on_shutdown(self):
        """Called when the plugin is being unloaded."""
        pass
    
    def get_metrics(self) -> Dict[str, Any]:
        """Return plugin-specific metrics."""
        return {}

class ReusePlugin(BasePlugin):
    """Base class for KV cache reuse plugins."""
    
    @abstractmethod
    def check_cache(self, sequence_id: str, tokens: list) -> Optional[dict]:
        """Check if the sequence is in the cache."""
        pass
    
    @abstractmethod
    def update_cache(self, sequence_id: str, tokens: list, kv_data: dict):
        """Update the cache with new KV data."""
        pass

class QuantizationPlugin(BasePlugin):
    """Base class for KV cache quantization plugins."""
    
    @abstractmethod
    def quantize(self, kv_data: dict, layer_idx: int, token_pos: int) -> dict:
        """Quantize KV cache data."""
        pass
    
    @abstractmethod
    def dequantize(self, kv_data: dict, layer_idx: int, token_pos: int) -> dict:
        """Dequantize KV cache data."""
        pass
