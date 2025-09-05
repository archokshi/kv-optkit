"""
KV Quantization Demo

This script demonstrates KV cache memory savings using the KIVI quantization plugin.
It shows the reduction in memory usage when applying different quantization levels.
"""
import time
import random
import numpy as np
from typing import Dict, List, Any, Tuple
import argparse
import logging
import csv
from pathlib import Path
from datetime import datetime
import sys
import os

# Add parent directory to path to allow imports
sys.path.append(str(Path(__file__).parent.parent))

# Configure logging with environment variable support
log_level = os.getenv('LOGLEVEL', 'INFO').upper()
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)
logger.setLevel(log_level)

from kvopt.plugins.kivi_plugin import KIVIPlugin, KIVIConfig
import inspect

class MockKVStore:
    """Mock KV store that simulates a high-bandwidth memory cache."""
    
    def __init__(self, num_layers: int = 32, hidden_size: int = 4096, num_heads: int = 32):
        self.num_layers = num_layers
        self.hidden_size = hidden_size
        self.num_heads = num_heads
        self.head_dim = hidden_size // num_heads
        self.kv_cache = {}
        self.quant_plugin = None
        
    def generate_kv_cache(self, seq_length: int) -> Dict[str, np.ndarray]:
        """Generate mock KV cache for a sequence."""
        # Generate random key and value tensors
        k = np.random.randn(seq_length, self.num_heads, self.head_dim).astype(np.float32)
        v = np.random.randn(seq_length, self.num_heads, self.head_dim).astype(np.float32)
        return {'k': k, 'v': v}
    
    def store_sequence(self, seq_id: str, seq_length: int, layer_idx: int = 0):
        """Store a sequence's KV cache in the store."""
        if layer_idx not in self.kv_cache:
            self.kv_cache[layer_idx] = {}
        
        self.kv_cache[layer_idx][seq_id] = self.generate_kv_cache(seq_length)
    
    def get_memory_usage(self) -> Tuple[int, Dict]:
        """Calculate memory usage in bytes and per-layer breakdown."""
        total_bytes = 0
        layer_breakdown = {}
        
        for layer_idx, layer_cache in self.kv_cache.items():
            layer_bytes = 0
            for seq_id, kv in layer_cache.items():
                # Calculate memory for both key and value tensors
                for k, v in kv.items():
                    if isinstance(v, dict) and 'data' in v:
                        # Handle quantized data using per-entry bitwidth
                        bitwidth = int(v.get('bitwidth', 8))
                        num_elements = int(v['data'].size)
                        quantized_bytes = (num_elements * bitwidth + 7) // 8  # Round up to nearest byte
                        layer_bytes += quantized_bytes
                        layer_bytes += 8  # scale and zero_point (4 bytes each)
                        layer_bytes += 32  # metadata (dtype, shape, etc.)
                    elif hasattr(v, 'nbytes'):
                        # Handle regular numpy arrays (assuming float32)
                        layer_bytes += v.nbytes
            
            layer_breakdown[layer_idx] = layer_bytes
            total_bytes += layer_bytes
            
        return total_bytes, layer_breakdown

def run_demo(
    num_sequences: int = 10,
    seq_length: int = 1024,
    num_layers: int = 32,
    bitwidths: List[int] = [16, 8, 4, 2]
):
    """Run the quantization demo."""
    logger.info(f"Starting quantization demo with {num_sequences} sequences")
    
    # Initialize mock KV store
    kv_store = MockKVStore(num_layers=num_layers)
    
    # Generate test sequences
    for i in range(num_sequences):
        seq_id = f"seq_{i:03d}"
        # Store sequence in all layers
        for layer_idx in range(num_layers):
            kv_store.store_sequence(seq_id, seq_length, layer_idx)
    
    # Get baseline memory usage
    baseline_mem, _ = kv_store.get_memory_usage()
    logger.info(f"Baseline memory usage: {baseline_mem / (1024**2):.2f} MB")
    
    results = []
    
    # Test different bitwidths
    for bitwidth in bitwidths:
        logger.info(f"\nTesting {bitwidth}-bit quantization")
        
        # Configure KIVI plugin with a dictionary
        config = {
            "name": f"kivi_{bitwidth}bit",
            "enabled": True,
            "bitwidth": bitwidth,
            "min_layer": 0,
            "max_layer": num_layers-1,
            "min_tokens": 1,  # Lower the threshold to see quantization on small examples
            "group_size": 64,
            "plugin_type": "quantization"
        }
        
        # Initialize plugin
        plugin = KIVIPlugin(config)
        plugin.on_startup()
        # Debug: verify which KIVIPlugin file is loaded
        try:
            plugin_src = inspect.getsourcefile(KIVIPlugin)
            logger.debug(f"KIVIPlugin loaded from: {plugin_src}")
        except Exception:
            pass
        
        # Store reference to the plugin in the KV store for memory calculation
        kv_store.quant_plugin = plugin
        
        # Apply quantization to all layers
        start_time = time.time()
        total_quantized = 0
        
        logger.debug(f"Applying quantization to {len(kv_store.kv_cache)} layers")
        # Accumulators for accuracy proxies
        sum_mse_k = 0.0
        sum_mse_v = 0.0
        sum_cos_k = 0.0
        sum_cos_v = 0.0
        count_acc = 0

        for layer_idx, layer_cache in kv_store.kv_cache.items():
            logger.debug(f"Processing layer {layer_idx} with {len(layer_cache)} sequences")
            for seq_id, kv in layer_cache.items():
                # Log original data shape and size
                orig_size = sum(v.nbytes if hasattr(v, 'nbytes') else len(str(v).encode()) for v in kv.values())
                logger.debug(f"  Seq {seq_id}: Original size: {orig_size} bytes")
                
                # Apply quantization with layer index and token position
                # Use seq_length as token_pos since we want to quantize all tokens
                quantized_kv = plugin.quantize(kv, layer_idx=layer_idx, token_pos=seq_length)

                # Compute accuracy proxy by dequantizing and comparing to original
                try:
                    if quantized_kv is not kv:
                        deq = plugin.dequantize(quantized_kv, layer_idx=layer_idx, token_pos=seq_length)
                        # MSE
                        mse_k = float(np.mean((deq['k'].astype(np.float32) - kv['k'].astype(np.float32)) ** 2))
                        mse_v = float(np.mean((deq['v'].astype(np.float32) - kv['v'].astype(np.float32)) ** 2))
                        # Cosine similarity
                        def cos(a: np.ndarray, b: np.ndarray) -> float:
                            a_f = a.reshape(-1).astype(np.float32)
                            b_f = b.reshape(-1).astype(np.float32)
                            denom = (np.linalg.norm(a_f) * np.linalg.norm(b_f))
                            if denom == 0:
                                return 1.0
                            return float(np.dot(a_f, b_f) / denom)
                        cos_k = cos(deq['k'], kv['k'])
                        cos_v = cos(deq['v'], kv['v'])
                        sum_mse_k += mse_k
                        sum_mse_v += mse_v
                        sum_cos_k += cos_k
                        sum_cos_v += cos_v
                        count_acc += 1
                except Exception as _e:
                    # Non-fatal: continue
                    logger.debug(f"  Seq {seq_id}: accuracy proxy failed: {_e}")
                # Sanity check: ensure plugin returned dict-wrapped quantized entries
                try:
                    k_type = type(quantized_kv.get('k')).__name__
                    v_type = type(quantized_kv.get('v')).__name__
                    logger.debug(f"  Seq {seq_id}: types after quantize -> k: {k_type}, v: {v_type}")
                except Exception:
                    pass
                
                # Log quantized data size
                if quantized_kv is not kv:  # If quantization was applied
                    def q_bytes(entry):
                        if isinstance(entry, dict) and 'data' in entry:
                            bitwidth = entry.get('bitwidth', 8)
                            numel = entry['data'].size
                            data_bytes = (numel * bitwidth + 7) // 8
                            return data_bytes + 8 + 32
                        return entry.nbytes if hasattr(entry, 'nbytes') else len(str(entry).encode())

                    quant_size = sum(q_bytes(v) for v in quantized_kv.values())
                    logger.debug(f"  Seq {seq_id}: Quantized size: {quant_size} bytes")
                
                # Replace with quantized version
                layer_cache[seq_id] = quantized_kv
                total_quantized += 1
        
        # Get memory usage after quantization
        quantized_mem, _ = kv_store.get_memory_usage()
        
        # Calculate metrics
        compression_ratio = baseline_mem / quantized_mem if quantized_mem > 0 else 1.0
        memory_savings = (1 - (quantized_mem / baseline_mem)) * 100 if baseline_mem > 0 else 0
        avg_mse_k = (sum_mse_k / count_acc) if count_acc else 0.0
        avg_mse_v = (sum_mse_v / count_acc) if count_acc else 0.0
        avg_cos_k = (sum_cos_k / count_acc) if count_acc else 1.0
        avg_cos_v = (sum_cos_v / count_acc) if count_acc else 1.0
        
        # Store results
        result = {
            'bitwidth': bitwidth,
            'baseline_mb': baseline_mem / (1024**2),
            'quantized_mb': quantized_mem / (1024**2),
            'savings_percent': memory_savings,
            'compression_ratio': compression_ratio,
            'avg_mse_k': avg_mse_k,
            'avg_mse_v': avg_mse_v,
            'avg_cos_k': avg_cos_k,
            'avg_cos_v': avg_cos_v,
            'num_sequences': num_sequences,
            'seq_length': seq_length,
            'num_layers': num_layers,
            'timestamp': datetime.now().isoformat()
        }
        results.append(result)
        
        # Clean up
        plugin.on_shutdown()
        
        # Print results
        print("\n" + "="*50)
        print(f"{bitwidth}-bit Quantization Results")
        print("="*50)
        print(f"Baseline memory:    {result['baseline_mb']:.2f} MB")
        print(f"Quantized memory:   {result['quantized_mb']:.2f} MB")
        print(f"Memory savings:     {result['savings_percent']:.1f}%")
        print(f"Compression ratio:  {result['compression_ratio']:.2f}x")
        print(f"Avg MSE (k/v):     {result['avg_mse_k']:.6f} / {result['avg_mse_v']:.6f}")
        print(f"Avg Cos (k/v):     {result['avg_cos_k']:.6f} / {result['avg_cos_v']:.6f}")
        print("="*50)
    
    # Save results to CSV
    save_results_to_csv(results)
    print(f"\nDetailed results saved to: outputs/kv_savings.csv")

def save_results_to_csv(results: List[Dict], filename: str = "outputs/kv_savings.csv"):
    """Save quantization results to a CSV file."""
    if not results:
        return
    
    # Create outputs directory if it doesn't exist
    output_dir = Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Use a fixed filename for simplicity
    filename = "kv_savings.csv"
    
    # Prepare CSV data
    file_exists = output_dir.joinpath(filename).exists()
    
    with open(output_dir / filename, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        if not file_exists:
            writer.writeheader()
        writer.writerows(results)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='KV Quantization Demo')
    parser.add_argument('--num_sequences', type=int, default=10,
                       help='Number of sequences to process')
    parser.add_argument('--seq_length', type=int, default=1024,
                       help='Length of each sequence in tokens')
    parser.add_argument('--num_layers', type=int, default=32,
                       help='Number of transformer layers')
    parser.add_argument('--bitwidths', type=int, nargs='+', default=[16, 8, 4, 2],
                       help='Bitwidths to test (space-separated)')
    
    args = parser.parse_args()
    
    run_demo(
        num_sequences=args.num_sequences,
        seq_length=args.seq_length,
        num_layers=args.num_layers,
        bitwidths=args.bitwidths
    )
