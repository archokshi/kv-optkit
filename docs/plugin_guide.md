# KV-OptKit Plugin System Guide

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Plugin Types](#plugin-types)
3. [Creating a New Plugin](#creating-a-new-plugin)
4. [Plugin Lifecycle](#plugin-lifecycle)
5. [Best Practices](#best-practices)
6. [Example Plugins](#example-plugins)
7. [Troubleshooting](#troubleshooting)

## Architecture Overview

The KV-OptKit plugin system is designed to be extensible and modular. The main components are:

- **PluginManager**: Manages the lifecycle of all plugins
- **BasePlugin**: Abstract base class for all plugins
- **PluginConfig**: Base configuration class for plugins
- **PluginType**: Enum defining different types of plugins

## Plugin Types

KV-OptKit supports the following plugin types:

1. **KV_CACHE**: For key-value cache implementations (e.g., LMCache)
2. **QUANTIZATION**: For model quantization (e.g., KIVI)
3. **OTHER**: For custom plugin types

## Creating a New Plugin

### 1. Create a new plugin file

Create a new Python file in `kvopt/plugins/` with the naming convention `{plugin_name}_plugin.py`.

### 2. Define Plugin Configuration

```python
from dataclasses import dataclass
from ..plugins import PluginConfig, PluginType

@dataclass
class MyPluginConfig(PluginConfig):
    """Configuration for MyPlugin."""
    param1: str = "default_value"
    param2: int = 42
    plugin_type: PluginType = PluginType.OTHER
```

### 3. Implement the Plugin

```python
from ..plugins import BasePlugin

class MyPlugin(BasePlugin):
    """My custom plugin implementation."""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.initialized = False
    
    def validate_config(self, config: dict) -> MyPluginConfig:
        """Validate and convert configuration."""
        return MyPluginConfig(**config)
    
    def on_startup(self):
        """Initialize the plugin."""
        self.initialized = True
    
    def on_shutdown(self):
        """Clean up resources."""
        self.initialized = False
    
    def get_metrics(self) -> dict:
        """Return plugin metrics."""
        return {"initialized": self.initialized}
```

## Plugin Lifecycle

1. **Loading**: The plugin is imported and instantiated
2. **Initialization**: `on_startup()` is called
3. **Operation**: Plugin methods are called during normal operation
4. **Shutdown**: `on_shutdown()` is called when the application exits

## Best Practices

1. **Error Handling**: Always handle errors gracefully and log them
2. **Resource Management**: Clean up resources in `on_shutdown()`
3. **Configuration**: Use `PluginConfig` for type-safe configuration
4. **Logging**: Use the module-level logger for debugging
5. **Dependencies**: Keep dependencies minimal and document them

## Example Plugins

### LMCache (KV_CACHE)
Implements Redis-based KV cache reuse.

### KIVI (QUANTIZATION)
Implements kernel-inspired vector quantization.

## Troubleshooting

### Common Issues

1. **Plugin not loading**:
   - Check the plugin file is in `kvopt/plugins/`
   - Verify the class name follows the `{Name}Plugin` convention
   - Check for import errors in the plugin file

2. **Configuration issues**:
   - Ensure all required parameters are provided
   - Check parameter types match the configuration class

3. **Dependency issues**:
   - Make sure all dependencies are installed
   - Check for version conflicts

### Debugging

Enable debug logging to see detailed plugin loading information:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Conclusion

The KV-OptKit plugin system provides a flexible way to extend the framework's functionality. By following these guidelines, you can create robust and maintainable plugins.
