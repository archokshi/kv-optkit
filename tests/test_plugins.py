"""
Tests for KV-OptKit plugins.
"""
import pytest
import os
import numpy as np
import tempfile
import os
from pathlib import Path

# Add parent directory to path to allow imports
import sys
sys.path.append(str(Path(__file__).parent.parent))

if os.getenv("KVOPT_LMCACHE", "0") == "1":
    from kvopt.plugins.lmcache_plugin import LMCachePlugin, LMCacheConfig  # type: ignore
from kvopt.plugins.kivi_plugin import KIVIPlugin, KIVIConfig

@pytest.mark.skipif(os.getenv("KVOPT_LMCACHE", "0") != "1", reason="LMCache disabled (set KVOPT_LMCACHE=1 to enable tests)")
class TestLMCachePlugin:
    """Tests for LMCachePlugin."""
    
    def test_plugin_initialization(self):
        """Test LMCachePlugin initialization with default config."""
        plugin = LMCachePlugin({})
        assert plugin.config.enabled is True
        assert plugin.config.backend == "redis://localhost:6379"
        assert plugin.config.ttl == 3600
    
    def test_cache_operations(self):
        """Test cache check and update operations."""
        plugin = LMCachePlugin({
            'backend': 'fakeredis://',
            'min_sequence_length': 1
        })
        
        # Initialize plugin
        plugin.on_startup()
        
        # Test data
        seq_id = "test_sequence"
        tokens = [1, 2, 3, 4, 5]
        kv_data = {"mock": True}
        
        # Cache should be empty initially
        assert plugin.check_cache(seq_id, tokens) is None
        
        # Update cache
        plugin.update_cache(seq_id, tokens, kv_data)
        
        # Should be able to retrieve from cache
        cached = plugin.check_cache(seq_id, tokens)
        assert cached is not None
        # With metadata storage, we expect lightweight fields only
        assert cached.get('sequence_id') == seq_id
        assert cached.get('token_count') == len(tokens)
        
        # Different sequence_id but same tokens should still be a cache hit (cache-by-content)
        cached2 = plugin.check_cache("different_seq", tokens)
        assert cached2 is not None
        assert cached2.get('token_count') == len(tokens)
        
        # Clean up
        plugin.on_shutdown()
    
    def test_metrics(self):
        """Test metrics collection."""
        plugin = LMCachePlugin({'min_sequence_length': 1, 'backend': 'fakeredis://'})
        plugin.on_startup()
        
        tokens = [1, 2, 3]
        
        # Initial metrics
        metrics = plugin.get_metrics()
        assert metrics['hits'] == 0
        assert metrics['misses'] == 0
        
        # After a miss
        plugin.check_cache("test", tokens)
        metrics = plugin.get_metrics()
        assert metrics['misses'] == 1
        assert metrics['hits'] == 0
        
        # After adding to cache and hitting
        plugin.update_cache("test", tokens, {'mock': True})
        plugin.check_cache("test", tokens)
        metrics = plugin.get_metrics()
        assert metrics['hits'] == 1
        
        plugin.on_shutdown()

class TestKIVIPlugin:
    """Tests for KIVIPlugin."""
    
    @pytest.fixture
    def sample_kv_data(self):
        """Sample KV cache data for testing."""
        return {
            'k': np.random.rand(10, 8, 128).astype(np.float32),
            'v': np.random.rand(10, 8, 128).astype(np.float32)
        }
    
    def test_plugin_initialization(self):
        """Test KIVIPlugin initialization with default config."""
        plugin = KIVIPlugin({})
        assert plugin.config.enabled is True
        assert plugin.config.bitwidth == 2
        assert plugin.config.group_size == 64
    
    def test_quantization(self, sample_kv_data):
        """Test quantization and dequantization round trip."""
        plugin = KIVIPlugin({
            'bitwidth': 4,
            'min_tokens': 0
        })
        
        plugin.on_startup()
        
        # Test quantization
        quantized = plugin.quantize(sample_kv_data, layer_idx=0, token_pos=0)
        
        # Check if data was quantized
        assert isinstance(quantized['k'], dict)
        assert 'data' in quantized['k']
        assert 'scale' in quantized['k']
        assert 'zero_point' in quantized['k']
        
        # Test dequantization
        dequantized = plugin.dequantize(quantized, layer_idx=0, token_pos=0)
        
        # Shape should be preserved
        assert dequantized['k'].shape == sample_kv_data['k'].shape
        assert dequantized['v'].shape == sample_kv_data['v'].shape
        
        # Some error is expected due to quantization
        assert not np.array_equal(dequantized['k'], sample_kv_data['k'])
        
        plugin.on_shutdown()
    
    def test_quantization_threshold(self, sample_kv_data):
        """Test that min_tokens threshold is respected."""
        plugin = KIVIPlugin({
            'bitwidth': 4,
            'min_tokens': 20  # Higher than our test data length (10)
        })
        
        plugin.on_startup()
        
        # Should not quantize due to min_tokens threshold
        result = plugin.quantize(sample_kv_data, layer_idx=0, token_pos=0)
        assert result is sample_kv_data  # Should return original
        
        # Should quantize for token_pos >= min_tokens
        result = plugin.quantize(sample_kv_data, layer_idx=0, token_pos=25)
        assert isinstance(result['k'], dict)  # Should be quantized
        
        plugin.on_shutdown()
    
    def test_metrics(self, sample_kv_data):
        """Test metrics collection."""
        plugin = KIVIPlugin({'min_tokens': 0})
        plugin.on_startup()
        
        # Initial metrics
        metrics = plugin.get_metrics()
        assert metrics['quantized_blocks'] == 0
        assert metrics['memory_saved_mb'] == 0.0
        
        # After quantization
        plugin.quantize(sample_kv_data, layer_idx=0, token_pos=0)
        metrics = plugin.get_metrics()
        assert metrics['quantized_blocks'] > 0
        assert metrics['memory_saved_mb'] > 0
        
        plugin.on_shutdown()

@pytest.mark.skipif(os.getenv("KVOPT_LMCACHE", "0") != "1", reason="LMCache disabled (set KVOPT_LMCACHE=1 to enable tests)")
def test_plugin_integration():
    """Test that both plugins can work together."""
    # This is a simple integration test to verify both plugins can be used together
    # without conflicts
    
    # Initialize plugins
    lmcache = LMCachePlugin({
        'enabled': True,
        'backend': 'fakeredis://',
        'min_sequence_length': 1
    })
    
    kivi = KIVIPlugin({
        'enabled': True,
        'min_tokens': 0
    })
    
    try:
        lmcache.on_startup()
        kivi.on_startup()
        
        # Create test data
        tokens = [1, 2, 3, 4, 5]
        kv_data = {
            'k': np.random.rand(5, 8, 128).astype(np.float32),
            'v': np.random.rand(5, 8, 128).astype(np.float32)
        }
        
        # Test LMCache
        lmcache.update_cache("test", tokens, kv_data)
        cached = lmcache.check_cache("test", tokens)
        assert cached is not None
        
        # Test KIVI
        quantized = kivi.quantize(kv_data, layer_idx=0, token_pos=0)
        assert isinstance(quantized['k'], dict)
        
        # Test metrics
        lmcache_metrics = lmcache.get_metrics()
        kivi_metrics = kivi.get_metrics()
        
        assert lmcache_metrics['hits'] >= 0
        assert kivi_metrics['quantized_blocks'] >= 0
        
    finally:
        lmcache.on_shutdown()
        kivi.on_shutdown()
