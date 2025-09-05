#!/usr/bin/env python3
"""
Test script for the enhanced plugin system.
"""
import logging
import sys
import traceback
from pathlib import Path

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.DEBUG,  # Set to DEBUG for more detailed output
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Enable debug logging for kvopt modules
for module in ['kvopt', 'kvopt.plugins', 'kvopt.config']:
    logging.getLogger(module).setLevel(logging.DEBUG)

def test_plugin_loading():
    """Test loading and initializing plugins with detailed logging."""
    logger.info("Starting plugin loading test...")
    
    try:
        from kvopt.config import Config, PluginConfig, PluginType
        from kvopt.plugins import ReusePlugin, QuantizationPlugin
        logger.debug("Successfully imported required modules")
        
        # Create a test config
        logger.info("Creating test configuration...")
        
        # Import plugin config classes
        from kvopt.plugins.lmcache_plugin import LMCacheConfig
        from kvopt.plugins.kivi_plugin import KIVIConfig
        
        config = Config(
            plugins={
                "lmcache": LMCacheConfig(
                    name="lmcache",
                    enabled=True,
                    plugin_type=PluginType.KV_CACHE,
                    backend="redis://localhost:6379"
                ),
                "kivi": KIVIConfig(
                    name="kivi",
                    enabled=True,
                    plugin_type=PluginType.QUANTIZATION,
                    bitwidth=2,
                    group_size=64
                )
            }
        )
        logger.debug("Test configuration created successfully")
    except Exception as e:
        logger.error(f"Failed to create test config: {e}")
        logger.debug(traceback.format_exc())
        raise
    
    # Test plugin manager
    try:
        logger.info("Accessing plugin manager...")
        pm = config.plugin_manager
        logger.info(f"Plugin manager initialized. Loaded plugins: {list(pm.plugins.keys())}")
        
        # Test getting plugins
        logger.info("Testing plugin retrieval...")
        lmcache = pm.get_plugin("lmcache")
        kivi = pm.get_plugin("kivi")
        
        logger.debug(f"LMCache plugin: {'Found' if lmcache else 'Not found'}")
        logger.debug(f"KIVI plugin: {'Found' if kivi else 'Not found'}")
        
        assert lmcache is not None, "LMCache plugin not loaded"
        assert kivi is not None, "KIVI plugin not loaded"
        
        # Test type-based lookup
        logger.info("Testing type-based plugin lookup...")
        reuse_plugins = pm.get_plugins_by_type(ReusePlugin)
        quant_plugins = pm.get_plugins_by_type(QuantizationPlugin)
        
        logger.debug(f"Found {len(reuse_plugins)} reuse plugins")
        logger.debug(f"Found {len(quant_plugins)} quantization plugins")
        
        assert len(reuse_plugins) > 0, "No reuse plugins found"
        assert len(quant_plugins) > 0, "No quantization plugins found"
        
        logger.info("All plugin tests passed!")
        
    except Exception as e:
        logger.error(f"Plugin test failed: {e}")
        logger.debug(traceback.format_exc())
        raise
    finally:
        # Clean up
        try:
            logger.info("Shutting down plugins...")
            pm.shutdown()
            logger.info("Plugin shutdown complete")
        except Exception as e:
            logger.error(f"Error during plugin shutdown: {e}")
            logger.debug(traceback.format_exc())

def setup_environment():
    """Set up the Python environment for testing."""
    import os
    import site
    
    # Add project root to Python path
    project_root = str(Path(__file__).parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    # Enable debug logging for all kvopt modules
    for name in logging.root.manager.loggerDict:
        if name.startswith('kvopt'):
            logging.getLogger(name).setLevel(logging.DEBUG)
    
    logger.info("Environment setup complete")
    logger.debug(f"Python path: {sys.path}")

if __name__ == "__main__":
    try:
        setup_environment()
        logger.info("Starting plugin system test...")
        test_plugin_loading()
        logger.info("✅ Plugin system test completed successfully!")
    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        logger.debug(f"Python path: {sys.path}")
        logger.debug(f"Current working directory: {os.getcwd()}")
        logger.debug(f"Files in current directory: {os.listdir('.')}")
        if 'kvopt' in sys.modules:
            logger.debug(f"kvopt module path: {sys.modules['kvopt'].__file__}")
        raise
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        logger.debug(f"Error details: {traceback.format_exc()}")
        raise
