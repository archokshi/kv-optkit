#!/usr/bin/env python3
"""Test script to verify Python environment and imports."""
import sys
import os
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def test_imports():
    """Test importing required modules."""
    logger.info("Testing imports...")
    
    # Print Python info
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Python path: {sys.path}")
    logger.info(f"Current working directory: {os.getcwd()}")
    
    # Try importing key modules
    try:
        import kvopt
        logger.info(f"Successfully imported kvopt from: {kvopt.__file__}")
        
        from kvopt.config import Config, PluginType
        logger.info("Successfully imported Config and PluginType")
        
        from kvopt.plugins import ReusePlugin, QuantizationPlugin
        logger.info("Successfully imported plugin base classes")
        
        from kvopt.plugins.lmcache_plugin import LMCacheConfig
        from kvopt.plugins.kivi_plugin import KIVIConfig
        logger.info("Successfully imported plugin configs")
        
        return True
        
    except ImportError as e:
        logger.error(f"Import error: {e}")
        logger.error(f"Python path: {sys.path}")
        logger.error(f"Current directory contents: {os.listdir('.')}")
        if 'kvopt' in sys.modules:
            logger.error(f"kvopt module path: {sys.modules['kvopt'].__file__}")
        return False

if __name__ == "__main__":
    if test_imports():
        logger.info("✅ All imports successful!")
    else:
        logger.error("❌ Some imports failed")
