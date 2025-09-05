"""
Demo of the KV-OptKit configuration system with plugins.

This script shows how to load a configuration with plugins and use them.
"""
import sys
from pathlib import Path

# Add parent directory to path to allow imports
sys.path.append(str(Path(__file__).parent.parent))

from kvopt.config import Config

def main(config_path: str):
    """Load configuration and demonstrate plugin usage."""
    print(f"Loading configuration from {config_path}")
    
    # Load configuration
    config = Config.from_yaml(config_path)
    
    # Access plugin manager (this will automatically load all enabled plugins)
    plugin_manager = config.plugin_manager
    
    # Get all loaded plugins
    print("\nLoaded plugins:")
    for name, plugin in plugin_manager.plugins.items():
        # Get the plugin class (convert to proper case: lmcache -> LMCachePlugin, kivi -> KIVIPlugin)
        class_name = f"{name[0].upper()}{name[1:]}Plugin"
        plugin_class = plugin.__class__
        print(f"- {plugin_class.__name__} (priority: {plugin.config.priority if hasattr(plugin, 'config') else 'N/A'})")
    
    # Example: Get all quantization plugins
    quant_plugins = plugin_manager.get_plugins_by_type("quantization")
    if quant_plugins:
        print("\nQuantization plugins:")
        for plugin in quant_plugins:
            print(f"- {plugin.__class__.__name__} (bitwidth: {getattr(plugin.config, 'bitwidth', 'N/A')})")
    
    # Example: Get a specific plugin
    lmcache = plugin_manager.get_plugin("lmcache")
    if lmcache:
        print(f"\nLMCache plugin backend: {lmcache.config.backend}")
    
    # Configuration will be automatically saved when the script exits
    # and plugins will be properly shut down

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Demo KV-OptKit configuration with plugins')
    parser.add_argument('--config', type=str, default='examples/config_with_plugins.yaml',
                      help='Path to configuration file')
    
    args = parser.parse_args()
    main(args.config)
