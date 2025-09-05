"""
LMCache Reuse Demo

This script demonstrates KV cache reuse using the LMCache plugin.
It shows the performance improvement when the same sequences are processed multiple times.
"""
import time
import random
import numpy as np
from typing import List, Dict, Any, Optional
import argparse
import logging
import csv
from pathlib import Path
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add parent directory to path to allow imports
import sys
sys.path.append(str(Path(__file__).parent.parent))

from kvopt.plugins.lmcache_plugin import LMCachePlugin

class MockLLM:
    """Mock LLM that simulates KV cache generation."""
    
    def __init__(self, cache_plugin: LMCachePlugin = None):
        self.cache = cache_plugin
        self.generation_time = 0.01  # seconds per token
        
    def generate(self, sequence_id: str, tokens: List[int]) -> Dict[str, Any]:
        """Generate KV cache for a sequence."""
        # Check cache first
        if self.cache:
            cached = self.cache.check_cache(sequence_id, tokens)
            if cached:
                logger.info(f"Cache HIT for sequence {sequence_id}")
                return cached
        
        # Simulate KV cache generation (expensive operation)
        num_tokens = len(tokens)
        time.sleep(self.generation_time * num_tokens)
        
        # Generate mock KV cache
        hidden_size = 4096  # Example hidden size
        num_heads = 32     # Example number of attention heads
        head_dim = hidden_size // num_heads
        
        kv_cache = {
            'k': np.random.randn(num_tokens, num_heads, head_dim).astype(np.float32),
            'v': np.random.randn(num_tokens, num_heads, head_dim).astype(np.float32),
            'sequence_id': sequence_id,
            'tokens': tokens.copy()
        }
        
        # Update cache
        if self.cache:
            self.cache.update_cache(sequence_id, tokens, kv_cache)
            
        return kv_cache

def generate_sequence(length: int) -> List[int]:
    """Generate a random sequence of token IDs."""
    return [random.randint(0, 50000) for _ in range(length)]

def measure_ttf(llm: MockLLM, sequences: List[Dict]) -> float:
    """Measure Time To First Token (TTFT) for a list of sequences."""
    start_time = time.time()
    
    for seq in sequences:
        llm.generate(seq['id'], seq['tokens'])
        
    total_time = time.time() - start_time
    avg_ttf = total_time / len(sequences)
    return avg_ttf

def save_metrics_to_csv(metrics: Dict[str, Any], filename: str = "kv_reuse.csv"):
    """Save metrics to a CSV file."""
    # Create outputs directory if it doesn't exist
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)
    
    # Prepare CSV data
    csv_path = output_dir / filename
    file_exists = csv_path.exists()
    
    with open(csv_path, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=metrics.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(metrics)

def run_demo(num_sequences: int = 10, seq_length: int = 100, use_cache: bool = True, backend: str = "fakeredis://"):
    """Run the LMCache demo."""
    logger.info(f"Starting LMCache demo with {num_sequences} sequences (backend={backend}, cache={'on' if use_cache else 'off'})")
    
    # Initialize metrics dictionary
    metrics = {
        'timestamp': datetime.now().isoformat(),
        'num_sequences': num_sequences,
        'seq_length': seq_length,
        'use_cache': use_cache,
        'cache_hits': 0,
        'cache_misses': 0,
        'hit_rate': 0.0,
        'time_without_cache': 0.0,
        'time_with_cache': 0.0,
        'speedup': 1.0
    }
    
    # Initialize cache plugin if enabled
    cache_plugin = LMCachePlugin({
        'enabled': use_cache,
        'backend': backend,
        'ttl': 3600,
        'min_sequence_length': 10
    }) if use_cache else None
    
    if cache_plugin:
        cache_plugin.on_startup()
    
    # Initialize mock LLM
    llm = MockLLM(cache_plugin)
    
    # Generate test sequences (some will be repeated)
    sequences = []
    for i in range(num_sequences):
        # Repeat some sequences to demonstrate cache hits
        if i > 0 and i % 3 == 0:
            # Reuse a previous sequence
            seq_id = f"repeated_{i//3}"
            tokens = sequences[i-3]['tokens']
        else:
            seq_id = f"seq_{i:03d}"
            tokens = generate_sequence(seq_length)
            
        sequences.append({'id': seq_id, 'tokens': tokens})
    
    # Warm-up run (not measured)
    _ = measure_ttf(llm, sequences[:2])
    
    # Benchmark without cache
    if use_cache:
        cache_plugin.config.enabled = False
    
    start_time = time.time()
    avg_ttf_no_cache = measure_ttf(llm, sequences)
    time_no_cache = time.time() - start_time
    
    # Benchmark with cache
    if use_cache:
        cache_plugin.config.enabled = True
        start_time = time.time()
        avg_ttf_with_cache = measure_ttf(llm, sequences)
        time_with_cache = time.time() - start_time
        
        # Get cache metrics and merge without overwriting the base metrics dict
        plugin_metrics = cache_plugin.get_metrics()
        hit_rate = plugin_metrics.get('hit_rate', 0) * 100
        
        # Update aggregate metrics
        metrics.update({
            'cache_hits': plugin_metrics.get('hits', 0),
            'cache_misses': plugin_metrics.get('misses', 0),
            'hit_rate': hit_rate / 100,  # decimal in CSV
            'time_without_cache': time_no_cache,
            'time_with_cache': time_with_cache,
            'speedup': time_no_cache / time_with_cache if time_with_cache > 0 else 1.0
        })
        
        # Save metrics to CSV
        save_metrics_to_csv(metrics)
        
        # Print results
        print("\n" + "="*50)
        print("LMCache Demo Results")
        print("="*50)
        print(f"Number of sequences: {num_sequences}")
        print(f"Sequence length: {seq_length} tokens")
        print(f"Cache hits: {metrics['cache_hits']}")
        print(f"Cache misses: {metrics['cache_misses']}")
        print(f"Cache hit rate: {hit_rate:.1f}%")
        print("-"*50)
        print(f"Time without cache: {time_no_cache:.2f}s")
        print(f"Time with cache:    {time_with_cache:.2f}s")
        print(f"Speedup: {time_no_cache/time_with_cache:.2f}x")
        print(f"Results saved to: outputs/kv_reuse.csv")
        print("="*50 + "\n")
    
    # Clean up
    if cache_plugin:
        cache_plugin.on_shutdown()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='LMCache Reuse Demo')
    parser.add_argument('--num_sequences', type=int, default=10,
                       help='Number of sequences to process')
    parser.add_argument('--seq_length', type=int, default=100,
                       help='Length of each sequence in tokens')
    parser.add_argument('--no_cache', action='store_true',
                       help='Disable caching for baseline measurement')
    parser.add_argument('--backend', type=str, default='fakeredis://',
                       help='Cache backend URL (e.g., fakeredis:// or redis://localhost:6379)')
    
    args = parser.parse_args()
    
    run_demo(
        num_sequences=args.num_sequences,
        seq_length=args.seq_length,
        use_cache=not args.no_cache,
        backend=args.backend
    )
