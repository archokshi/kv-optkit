from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Literal, Optional, Union, Type, Any
import yaml
from pydantic import BaseModel, Field, validator, root_validator
from enum import Enum
import importlib


class SLOSettings(BaseModel):
    latency_p95_ms: float = 2000.0
    max_accuracy_delta_pct: float = 0.5


class BudgetSettings(BaseModel):
    hbm_util_target: float = 0.85
    offload_bw_gbps: float = 120.0


class PolicySettings(BaseModel):
    keep_recent_tokens: int = 4096
    eviction: List[str] = Field(default_factory=lambda: ["age_decay"])
    tiers: List[str] = Field(default_factory=lambda: ["HBM", "DDR", "CXL", "NVMe"])


class GuardrailSettings(BaseModel):
    ab_shadow_fraction: float = 0.05
    rollback_on_acc_delta: bool = True


class AdapterSettings(BaseModel):
    """Adapter configuration for server startup."""
    type: Literal["sim", "vllm", "tgi", "trtllm", "deepspeed"] = "sim"
    # Optional fields for adapters; passed through to adapter implementations
    hbm_capacity_gb: Optional[float] = None
    bytes_per_token: Optional[float] = None
    # VLLM-specific placeholders
    endpoint: Optional[str] = None
    api_key: Optional[str] = None


class PluginType(str, Enum):
    """Supported plugin types."""
    KV_CACHE = "kv_cache"
    QUANTIZATION = "quantization"
    EVICTION = "eviction"
    MONITORING = "monitoring"


class PluginConfig(BaseModel):
    """Base configuration for all plugins."""
    enabled: bool = True
    priority: int = 0
    plugin_type: PluginType
    
    class Config:
        # Be permissive so sample configs with additional hints don't fail validation
        extra = "ignore"


class LMCacheConfig(PluginConfig):
    """Configuration for LMCache plugin."""
    plugin_type: PluginType = PluginType.KV_CACHE
    backend: str = "redis://localhost:6379"
    ttl: int = 3600
    min_sequence_length: int = 1
    max_memory_mb: int = 1024


class KIVIConfig(PluginConfig):
    """Configuration for KIVI quantization plugin."""
    plugin_type: PluginType = PluginType.QUANTIZATION
    bitwidth: int = 4
    group_size: int = 64
    min_tokens: int = 0
    enabled: bool = True


from .plugin_manager import PluginManager as PluginManagerImpl
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .plugin_manager import PluginManager


class Config(BaseModel):
    slo: SLOSettings = Field(default_factory=SLOSettings)
    budgets: BudgetSettings = Field(default_factory=BudgetSettings)
    policy: PolicySettings = Field(default_factory=PolicySettings)
    guardrails: GuardrailSettings = Field(default_factory=GuardrailSettings)
    adapter: AdapterSettings = Field(default_factory=AdapterSettings)
    
    # Plugins configuration - accept any plugin config type
    plugins: Dict[str, Any] = Field(
        default_factory=dict,
        description="Plugin configurations keyed by plugin name"
    )
    
    # Plugin manager instance (not serialized)
    _plugin_manager: Optional['PluginManager'] = None
    
    @property
    def plugin_manager(self) -> PluginManagerImpl:
        """Get or create the plugin manager."""
        if self._plugin_manager is None:
            self._plugin_manager = PluginManagerImpl(self)
            self._plugin_manager.load_plugins()
        return self._plugin_manager
    
    @classmethod
    def from_yaml(cls, path: Union[str, Path]) -> 'Config':
        with open(path, 'r') as f:
            data = yaml.safe_load(f) or {}
            
        # Adapter section
        if 'adapter' in data and isinstance(data['adapter'], dict):
            data['adapter'] = AdapterSettings(**data['adapter'])
        else:
            data['adapter'] = AdapterSettings()

        # Convert plugin configs to proper types
        if 'plugins' in data:
            plugins_raw = data['plugins']
            plugin_configs: Dict[str, Any] = {}

            def add_plugin(plugin_name: str, cfg: dict, group: Optional[str] = None):
                # Remove fields not accepted by PluginConfig/children
                cfg = dict(cfg or {})
                cfg.pop('name', None)

                key = plugin_name
                lname = plugin_name.lower()
                gname = (group or '').lower()

                if lname == 'lmcache' or gname in ('reuse', 'kv_cache'):
                    plugin_configs[key] = LMCacheConfig(**cfg)
                elif lname == 'kivi' or gname in ('quantization',):
                    plugin_configs[key] = KIVIConfig(**cfg)
                else:
                    # Fallback: try to infer plugin_type from group or cfg
                    inferred_type = cfg.get('plugin_type')
                    if inferred_type is None and gname:
                        try:
                            inferred_type = PluginType(gname)  # may raise ValueError
                        except Exception:
                            inferred_type = PluginType.KV_CACHE
                    plugin_configs[key] = PluginConfig(
                        plugin_type=inferred_type if isinstance(inferred_type, PluginType) else PluginType(str(inferred_type)) if inferred_type else PluginType.KV_CACHE,
                        **{k: v for k, v in cfg.items() if k != 'plugin_type'}
                    )

            if isinstance(plugins_raw, dict):
                # Two supported shapes:
                # 1) Flat: {"lmcache": {..}, "kivi": {..}}
                # 2) Grouped: {"reuse": [{name: lmcache, ...}], "quantization": [{name: kivi, ...}]}
                for group_or_name, val in plugins_raw.items():
                    if isinstance(val, list):
                        for item in val:
                            pname = item.get('name') if isinstance(item, dict) else None
                            if not pname:
                                continue  # skip invalid entries
                            add_plugin(pname, item, group=group_or_name)
                    elif isinstance(val, dict):
                        # Flat mapping: key is the plugin name
                        add_plugin(group_or_name, val, group=None)
                    else:
                        # Unsupported shape; skip
                        continue
            elif isinstance(plugins_raw, list):
                # List of plugin dicts with required 'name'
                for item in plugins_raw:
                    if not isinstance(item, dict) or 'name' not in item:
                        continue
                    add_plugin(item['name'], item, group=None)

            data['plugins'] = plugin_configs
            
        return cls(**data)
    
    def to_yaml(self, path: Union[str, Path]):
        # Don't serialize the plugin manager
        data = self.model_dump(exclude={'_plugin_manager'})
        with open(path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False)
    
    def __del__(self):
        """Ensure plugins are properly shut down."""
        try:
            if hasattr(self, '_plugin_manager') and self._plugin_manager:
                self._plugin_manager.shutdown()
        except Exception:
            pass  # Ignore errors during cleanup


class TelemetryData(BaseModel):
    hbm_used_gb: float
    hbm_total_gb: float
    ddr_used_gb: float
    p95_latency_ms: float
    sequences: List[dict]
    timestamp_s: float

    @property
    def hbm_utilization(self) -> float:
        return self.hbm_used_gb / self.hbm_total_gb if self.hbm_total_gb > 0 else 0.0


class Recommendation(BaseModel):
    action: str
    detail: str
    estimated_hbm_savings_gb: float
    risk: str  # 'low', 'medium', 'high'


class AdvisorReport(BaseModel):
    hbm_utilization: float
    hbm_used_gb: float
    p95_latency_ms: float
    sequences: List[dict]
    recommendations: List[Recommendation]
    notes: List[str] = Field(default_factory=list)


class SequenceInfo(BaseModel):
    seq_id: str
    length_tokens: int
    created_at: float
    last_accessed: float
    
    @property
    def age_seconds(self) -> float:
        return self.last_accessed - self.created_at
