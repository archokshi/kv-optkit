"""Enhanced Plugin Manager for KV-OptKit"""
import importlib
import traceback
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, Any, List, Optional, TypeVar, Type, Generic, Iterator

from .config import PluginConfig, PluginType
from .plugins import BasePlugin, ReusePlugin, QuantizationPlugin

T = TypeVar('T', bound=BasePlugin)

logger = logging.getLogger(__name__)

class PluginState(Enum):
    LOADED = auto()
    INITIALIZED = auto()
    ERROR = auto()

@dataclass
class PluginInfo:
    """Plugin metadata and state."""
    name: str
    instance: BasePlugin
    state: PluginState = PluginState.LOADED
    dependencies: List[str] = field(default_factory=list)
    error: Optional[str] = None
    # Optional metadata captured during load for diagnostics
    module: Any | None = None
    config: Dict[str, Any] | None = None

class PluginManager:
    """Manages plugin lifecycle with dependency support."""
    
    def __init__(self, config: Any):
        self.plugins: Dict[str, PluginInfo] = {}
        self.config = config
    
    def load_plugins(self) -> None:
        """Load and initialize plugins with dependency resolution."""
        if not hasattr(self.config, 'plugins'):
            logger.info("No plugins configured")
            return
        
        # Load all plugins
        import os
        lmcache_allowed = os.getenv("KVOPT_LMCACHE", "0") == "1"
        for name, config in self.config.plugins.items():
            if not config.enabled:
                continue
            # Temporarily disable LMCache plugin unless explicitly enabled via env
            if name.lower() == "lmcache" and not lmcache_allowed:
                logger.info("LMCache plugin disabled (set KVOPT_LMCACHE=1 to enable in this run)")
                continue
            self._load_plugin(name, config)
        
        # Initialize plugins in dependency order
        self._initialize_plugins()

    # Public alias expected by some callers/tests
    def initialize_plugins(self) -> None:
        self._initialize_plugins()
    
    def _load_plugin(self, name: str, config: PluginConfig) -> None:
        """Load a plugin without initializing it."""
        logger.debug(f"Loading plugin: {name}")
        
        try:
            # Import plugin module
            module_name = f"kvopt.plugins.{name.lower()}_plugin"
            logger.debug(f"Importing module: {module_name}")
            module = importlib.import_module(module_name)
            
            # Get plugin class
            class_name = f"{name[0].upper()}{name[1:]}Plugin"
            logger.debug(f"Looking for class: {class_name}")
            plugin_class = getattr(module, class_name)
            
            # Create plugin instance
            logger.debug(f"Creating instance with config: {config}")
            plugin = plugin_class(config.dict())
            
            # Store plugin info
            self.plugins[name] = PluginInfo(
                name=name,
                instance=plugin,
                module=module,
                config=config.dict(),
                dependencies=getattr(config, 'dependencies', [])
            )
            logger.info(f"✅ Successfully loaded plugin: {name}")
            
        except ModuleNotFoundError as e:
            error_msg = f"Plugin module not found: {e}"
            logger.error(error_msg)
            raise ImportError(error_msg) from e
            
        except AttributeError as e:
            error_msg = f"Plugin class not found in module: {e}"
            logger.error(error_msg)
            raise ImportError(error_msg) from e
            
        except Exception as e:
            error_msg = f"Failed to load plugin {name}: {str(e)}"
            logger.error(error_msg)
            logger.debug(f"Error details: {traceback.format_exc()}")
            raise RuntimeError(error_msg) from e
    
    def _initialize_plugins(self) -> None:
        """Initialize plugins in dependency order."""
        initialized = set()
        
        while len(initialized) < len(self.plugins):
            made_progress = False
            
            for name, info in self.plugins.items():
                if name in initialized:
                    continue
                    
                # Check if all dependencies are met
                deps_met = all(dep in initialized for dep in info.dependencies)
                
                if deps_met:
                    try:
                        if hasattr(info.instance, 'on_startup'):
                            info.instance.on_startup()
                        info.state = PluginState.INITIALIZED
                        initialized.add(name)
                        made_progress = True
                        logger.info(f"Initialized plugin: {name}")
                    except Exception as e:
                        info.state = PluginState.ERROR
                        info.error = str(e)
                        logger.error(f"Failed to initialize plugin {name}: {e}")
                        made_progress = True  # Don't get stuck on errors
            
            if not made_progress:
                uninitialized = set(self.plugins.keys()) - initialized
                raise RuntimeError(
                    f"Circular or missing dependencies detected. "
                    f"Uninitialized plugins: {uninitialized}"
                )
    
    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        """Get a plugin instance by name."""
        return self.plugins[name].instance if name in self.plugins else None
        
    def get_plugins_by_type(self, plugin_type: Type[T]) -> List[T]:
        """Get all plugins of a specific type."""
        return [
            info.instance for info in self.plugins.values()
            if isinstance(info.instance, plugin_type)
        ]
        
    def get_plugin_by_type(self, plugin_type: Type[T]) -> Optional[T]:
        """Get the first plugin of a specific type."""
        plugins = self.get_plugins_by_type(plugin_type)
        return plugins[0] if plugins else None
        
    def __iter__(self) -> Iterator[BasePlugin]:
        """Iterate over all plugin instances."""
        return (info.instance for info in self.plugins.values())
    
    def shutdown(self) -> None:
        """Shutdown all plugins in reverse initialization order."""
        for name in reversed(list(self.plugins.keys())):
            try:
                if hasattr(self.plugins[name].instance, 'on_shutdown'):
                    self.plugins[name].instance.on_shutdown()
                logger.info(f"Shut down plugin: {name}")
            except Exception as e:
                logger.error(f"Error shutting down plugin {name}: {e}")
