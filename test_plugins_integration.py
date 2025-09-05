#!/usr/bin/env python3
"""Integration tests for KV-OptKit plugins."""
import sys
import os
import logging
import unittest
from unittest.mock import patch, MagicMock
import numpy as np
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class TestPlugins(unittest.TestCase):
    """Test plugin loading and basic functionality."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment."""
        # Enable debug logging for all kvopt modules
        for name in logging.root.manager.loggerDict:
            if name.startswith('kvopt'):
                logging.getLogger(name).setLevel(logging.DEBUG)
    
    def test_plugin_loading(self):
        """Test that plugins can be loaded and initialized."""
        from kvopt.config import Config
        from kvopt.plugins.lmcache_plugin import LMCacheConfig
        from kvopt.plugins.kivi_plugin import KIVIConfig
        
        # Create a test config
        config = Config(
            plugins={
                "lmcache": LMCacheConfig(
                    name="lmcache",
                    enabled=True,
                    backend="redis://localhost:6379"
                ),
                "kivi": KIVIConfig(
                    name="kivi",
                    enabled=True,
                    bitwidth=2,
                    group_size=64
                )
            }
        )
        
        # Test that plugins were loaded
        self.assertIn("lmcache", config.plugins)
        self.assertIn("kivi", config.plugins)
        
        # Test plugin manager
        pm = config.plugin_manager
        self.assertIsNotNone(pm)
        
        # Test getting plugins
        lmcache = pm.get_plugin("lmcache")
        kivi = pm.get_plugin("kivi")
        self.assertIsNotNone(lmcache)
        self.assertIsNotNone(kivi)
    
    @patch('redis.Redis')
    def test_lmcache_plugin(self, mock_redis):
        """Test LMCache plugin with mocked Redis."""
        from kvopt.plugins.lmcache_plugin import LMCachePlugin, LMCacheConfig
        
        # Setup mock Redis
        mock_redis.return_value.ping.return_value = True
        mock_redis.return_value.get.return_value = None
        
        # Create and initialize plugin
        config = LMCacheConfig(
            name="test_lmcache",
            backend="redis://localhost:6379",
            ttl=3600
        )
        plugin = LMCachePlugin(config.model_dump())
        plugin.on_startup()
        
        # Test cache miss
        result = plugin.check_cache("test", [1, 2, 3])
        self.assertIsNone(result)
        
        # Test cache hit - mock the Redis get method properly
        test_data = {"key": "value"}
        mock_redis.return_value.get.return_value = '{"key": "value"}'
        result = plugin.check_cache("test", [1, 2, 3])
        self.assertEqual(result, test_data)
        
        # Clean up
        plugin.on_shutdown()
    
    def test_kivi_plugin(self):
        """Test KIVI plugin functionality."""
        from kvopt.plugins.kivi_plugin import KIVIPlugin, KIVIConfig
        
        # Create and initialize plugin
        config = KIVIConfig(
            name="test_kivi",
            bitwidth=2,
            group_size=8,
            min_tokens=1  # Lower for testing
        )
        plugin = KIVIPlugin(config.model_dump())
        plugin.on_startup()
        
        # Test quantization
        test_data = {
            "cache": {
                "key": np.random.rand(1, 32, 16, 64).astype(np.float32),
                "value": np.random.rand(1, 32, 16, 64).astype(np.float32)
            },
            "layer_idx": 0,
            "token_pos": 0
        }
        
        # Test quantization
        quantized = plugin.quantize(
            kv_data=test_data["cache"],
            layer_idx=test_data["layer_idx"],
            token_pos=test_data["token_pos"]
        )
        
        # Test dequantization
        dequantized = plugin.dequantize(
            kv_data=quantized,
            layer_idx=test_data["layer_idx"],
            token_pos=test_data["token_pos"]
        )
        
        # Verify shapes
        for k in test_data["cache"]:
            self.assertEqual(
                test_data["cache"][k].shape,
                dequantized[k].shape,
                f"Shape mismatch for {k}"
            )
        
        # Clean up
        plugin.on_shutdown()

if __name__ == "__main__":
    # Set up environment
    os.environ["PYTHONPATH"] = str(Path(__file__).parent)
    
    # Run tests
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
