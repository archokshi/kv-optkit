"""
MiniKV Plugin

A simplified version of the KIVI quantization plugin for KV cache compression.
This plugin provides basic quantization with minimal configuration options.
"""
import numpy as np
from typing import Dict, Any, Optional, Tuple, List
import logging
from dataclasses import dataclass

from . import BasePlugin, PluginConfig, PluginType, QuantizationPlugin

logger = logging.getLogger(__name__)

@dataclass
class MiniKVPluginConfig(PluginConfig):
    """Configuration for the MiniKV plugin."""
    plugin_type: str = PluginType.QUANTIZATION
    bitwidth: int = 2  # Default to 2-bit quantization
    layers: str = "0-31"  # Default to all layers
    older_than_tokens: int = 1024  # Only quantize tokens older than this
    min_sequence_length: int = 64  # Minimum sequence length to quantize

class MiniKVPlugin(QuantizationPlugin):
    """
    A simplified version of KIVI for KV cache quantization.
    
    This plugin implements basic quantization with minimal configuration options
    for cases where the full KIVI implementation is not needed.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the MiniKV plugin."""
        super().__init__(config)
        self.config = MiniKVPluginConfig(**config)
        self._parse_layer_spec()
        self.metrics = {
            'total_quantized': 0,
            'total_bypassed': 0,
            'compression_ratio': 1.0,
            'last_quantization_time_ms': 0.0
        }
    
    def _parse_layer_spec(self) -> None:
        """Parse the layer specification string into a list of layer indices."""
        self.layer_indices = []
        parts = self.config.layers.split(',')
        
        for part in parts:
            part = part.strip()
            if '-' in part:
                # Handle range (e.g., "0-15")
                start, end = map(int, part.split('-'))
                self.layer_indices.extend(range(start, end + 1))
            else:
                # Handle single number
                self.layer_indices.append(int(part))
    
    def should_quantize(self, sequence_length: int, token_position: int) -> bool:
        """Determine if a token should be quantized."""
        return (
            sequence_length >= self.config.min_sequence_length and
            token_position < sequence_length - self.config.older_than_tokens
        )
    
    def quantize(self, kv_cache: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        """
        Quantize the KV cache.
        
        Args:
            kv_cache: Dictionary containing 'k' and 'v' numpy arrays
            
        Returns:
            Dictionary with quantized 'k' and 'v' arrays
        """
        import time
        start_time = time.time()
        
        quantized = {}
        
        for name, tensor in kv_cache.items():
            if name not in ['k', 'v']:
                quantized[name] = tensor
                continue
                
            # Simple min-max quantization
            tensor_min = np.min(tensor)
            tensor_max = np.max(tensor)
            
            # Handle case where all values are the same
            if tensor_max == tensor_min:
                scale = 1.0
                zero_point = 0
            else:
                scale = (tensor_max - tensor_min) / (2 ** self.config.bitwidth - 1)
                zero_point = -tensor_min / scale
            
            # Quantize
            quantized_tensor = np.clip(
                np.round(tensor / scale + zero_point),
                0,
                2 ** self.config.bitwidth - 1
            ).astype(np.uint8)
            
            # Store quantization parameters for dequantization
            quantized[f"{name}_quant"] = quantized_tensor
            quantized[f"{name}_scale"] = scale
            quantized[f"{name}_zero_point"] = zero_point
            
            # Update metrics
            original_size = tensor.nbytes
            quantized_size = quantized_tensor.nbytes + 8  # +8 for scale/zero_point (simplified)
            self.metrics['compression_ratio'] = original_size / quantized_size
            self.metrics['total_quantized'] += 1
        
        self.metrics['last_quantization_time_ms'] = (time.time() - start_time) * 1000
        return quantized
    
    def dequantize(self, quantized: Dict[str, Any]) -> Dict[str, np.ndarray]:
        """
        Dequantize the KV cache.
        
        Args:
            quantized: Dictionary containing quantized tensors and parameters
            
        Returns:
            Dictionary with dequantized 'k' and 'v' arrays
        """
        dequantized = {}
        
        for name in ['k', 'v']:
            if f"{name}_quant" not in quantized:
                if name in quantized:  # Already dequantized
                    dequantized[name] = quantized[name]
                continue
                
            # Get quantization parameters
            quantized_tensor = quantized[f"{name}_quant"]
            scale = quantized[f"{name}_scale"]
            zero_point = quantized[f"{name}_zero_point"]
            
            # Dequantize
            dequantized[name] = (quantized_tensor.astype(np.float32) - zero_point) * scale
        
        return dequantized
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get plugin metrics."""
        return self.metrics
    
    def reset_metrics(self) -> None:
        """Reset plugin metrics."""
        self.metrics = {
            'total_quantized': 0,
            'total_bypassed': 0,
            'compression_ratio': 1.0,
            'last_quantization_time_ms': 0.0
        }

# Register the plugin
PluginConfig.register_plugin("minikv", MiniKVPluginConfig, MiniKVPlugin)
