"""
KIVI Quantization Plugin for KV-OptKit

Implements KIVI (Kernel-Inspired Vector Quantization) for efficient KV cache compression.
"""
import logging
import numpy as np
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass
from ..plugins import QuantizationPlugin, PluginConfig, PluginType

logger = logging.getLogger(__name__)

@dataclass
class KIVIConfig(PluginConfig):
    """Configuration for KIVI quantization plugin."""
    bitwidth: int = 2
    group_size: int = 64
    min_layer: int = 0
    max_layer: Optional[int] = None
    min_tokens: int = 8192
    enabled: bool = True
    plugin_type: PluginType = PluginType.QUANTIZATION
    
    def dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "name": getattr(self, 'name', 'kivi'),
            "enabled": self.enabled,
            "priority": getattr(self, 'priority', 100),
            "plugin_type": self.plugin_type.value,
            "bitwidth": self.bitwidth,
            "group_size": self.group_size,
            "min_layer": self.min_layer,
            "max_layer": self.max_layer,
            "min_tokens": self.min_tokens
        }
    
    def model_dump(self) -> Dict[str, Any]:
        """Pydantic v2 compatibility alias."""
        return self.dict()

class KIVIPlugin(QuantizationPlugin):
    """KIVI (Kernel-Inspired Vector Quantization) plugin for KV cache."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.quantized_blocks: Dict[Tuple[int, int], Dict[str, Any]] = {}
        self.quantized_count: int = 0
        self.total_savings: float = 0.0
    
    def validate_config(self, config: Dict[str, Any]) -> KIVIConfig:
        """Validate and convert KIVI configuration."""
        return KIVIConfig(
            name=config.get("name", "kivi"),
            enabled=config.get("enabled", True),
            priority=config.get("priority", 100),
            plugin_type=PluginType.QUANTIZATION,
            bitwidth=config.get("bitwidth", 2),
            group_size=config.get("group_size", 64),
            min_layer=config.get("min_layer", 0),
            max_layer=config.get("max_layer"),
            min_tokens=config.get("min_tokens", 8192)
        )
    
    def on_startup(self):
        """Initialize the KIVI plugin."""
        logger.info(
            f"KIVI Plugin initialized - {self.config.bitwidth}-bit quantization, "
            f"group size: {self.config.group_size}"
        )
    
    def on_shutdown(self):
        """Clean up resources."""
        self.quantized_blocks.clear()
        logger.info("KIVI Plugin shutdown")
    
    def _should_quantize(self, layer_idx: int, token_pos: int) -> bool:
        """Determine if a given layer/token position should be quantized."""
        if not self.config.enabled:
            return False
        if layer_idx < self.config.min_layer:
            return False
        if self.config.max_layer is not None and layer_idx > self.config.max_layer:
            return False
        if token_pos < self.config.min_tokens:
            return False
        return True
    
    def quantize(self, kv_data: Dict, layer_idx: int, token_pos: int) -> Dict:
        """Quantize KV cache data using KIVI algorithm."""
        if not self._should_quantize(layer_idx, token_pos):
            logger.debug(f"Skipping quantization for layer {layer_idx}, token_pos {token_pos} - min_tokens={self.config.min_tokens}")
            return kv_data

        logger.debug(f"Quantizing layer {layer_idx}, token_pos {token_pos} with {self.config.bitwidth}-bit quantization")

        try:
            # Get the original size (support numpy arrays directly)
            original_size = sum(v.nbytes for v in kv_data.values() if hasattr(v, 'nbytes'))

            # Apply quantization to each tensor in the KV cache
            quantized = {}
            max_q = (1 << self.config.bitwidth) - 1
            for k, v in kv_data.items():
                # Accept either numpy arrays or torch tensors
                if hasattr(v, 'nbytes'):
                    arr = v  # numpy ndarray
                elif hasattr(v, 'numpy'):
                    arr = v.numpy()
                else:
                    quantized[k] = v
                    continue

                # Simple per-tensor min-max quantization (demo-only)
                arr_min = float(arr.min())
                arr_max = float(arr.max())
                # Avoid zero division
                scale = (arr_max - arr_min) / max(1, max_q)
                if scale == 0:
                    scale = 1e-8
                zero_point = arr_min

                q = np.round((arr - zero_point) / scale)
                q = np.clip(q, 0, max_q)
                q_dtype = np.uint8 if self.config.bitwidth <= 8 else np.uint16
                quantized_arr = q.astype(q_dtype)

                # Store quantization parameters and metadata
                quantized[k] = {
                    'data': quantized_arr,
                    'scale': np.float32(scale),
                    'zero_point': np.float32(zero_point),
                    'dtype': str(arr.dtype),
                    'shape': tuple(arr.shape),
                    'bitwidth': int(self.config.bitwidth),
                }

            # Calculate and log compression ratio (based on bitwidth, not byte dtype)
            def quantized_size_bytes(entry: Dict) -> int:
                data = entry['data']
                bitwidth = entry.get('bitwidth', 8)
                numel = int(np.prod(data.shape))
                data_bytes = (numel * bitwidth + 7) // 8
                overhead = 8 + 32  # scale/zero_point + metadata approx
                return data_bytes + overhead

            compressed_size = sum(
                quantized_size_bytes(v) for v in quantized.values() if isinstance(v, dict)
            )

            if original_size > 0 and compressed_size > 0:
                compression_ratio = original_size / compressed_size
                self.total_savings += max(0, (original_size - compressed_size))
                logger.debug(
                    f"Quantized layer {layer_idx} @ {token_pos}: "
                    f"{original_size/1024:.1f}KB -> {compressed_size/1024:.1f}KB "
                    f"({compression_ratio:.2f}x)"
                )

            # Track this block for dequantization
            self.quantized_blocks[(layer_idx, token_pos)] = {
                'quantized': quantized,
                'original_size': original_size,
                'compressed_size': compressed_size,
            }
            self.quantized_count += 1

            return quantized  # Return the quantized data

        except Exception as e:
            logger.error(f"Quantization failed: {e}")
            return kv_data
    
    def dequantize(self, kv_data: Dict, layer_idx: int, token_pos: int) -> Dict:
        """Dequantize KV cache data."""
        block_key = (layer_idx, token_pos)
        if block_key not in self.quantized_blocks:
            return kv_data
        
        try:
            quantized = self.quantized_blocks[block_key]['quantized']
            dequantized = {}
            
            for k, v in quantized.items():
                if isinstance(v, dict):
                    # Validate required fields
                    required = ('data', 'scale', 'zero_point', 'shape')
                    if not all(field in v for field in required):
                        logger.debug(f"Dequantize skip key {k}: missing fields in quantized entry")
                        return kv_data

                    scale = v['scale']
                    zero_point = v['zero_point']
                    quantized_arr = v['data']
                    shape = tuple(v['shape'])

                    # Basic type checks
                    if not hasattr(quantized_arr, 'astype'):
                        logger.debug(f"Dequantize skip key {k}: 'data' is not array-like")
                        return kv_data

                    # Apply dequantization
                    dequantized_arr = quantized_arr.astype(np.float32) * float(scale) + float(zero_point)
                    try:
                        dequantized_arr = dequantized_arr.reshape(shape)
                    except Exception:
                        logger.debug(f"Dequantize reshape mismatch for key {k}: expected shape {shape}")
                        return kv_data
                    dequantized[k] = dequantized_arr
                else:
                    # Non-quantized entry: pass through
                    dequantized[k] = v
            
            return dequantized
            
        except Exception as e:
            logger.error(f"Dequantization failed: {e}")
            return kv_data
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get plugin metrics."""
        return {
            "quantized_count": self.quantized_count,
            "quantized_blocks": len(self.quantized_blocks),
            "memory_saved_mb": self.total_savings / (1024**2),
            "total_savings_gb": self.total_savings / (1024**3),
            "enabled": self.config.enabled
        }

# Aliases for compatibility
KiviPlugin = KIVIPlugin
