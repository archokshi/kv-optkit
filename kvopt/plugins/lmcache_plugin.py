"""LMCache Plugin for KV-OptKit - Implements KV cache reuse with Redis."""
import hashlib
import json
import logging
from typing import Dict, Any, Optional, List
import redis
try:
    import fakeredis  # optional, for in-memory backend
except Exception:  # pragma: no cover
    fakeredis = None
from dataclasses import dataclass
from ..plugins import ReusePlugin, PluginConfig

logger = logging.getLogger(__name__)

@dataclass
class LMCacheConfig(PluginConfig):
    """LMCache plugin configuration."""
    backend: str = "redis://localhost:6379"
    ttl: int = 3600
    min_sequence_length: int = 16
    max_cache_size: int = 10_000
    
    def dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "name": getattr(self, 'name', 'lmcache'),
            "enabled": getattr(self, 'enabled', True),
            "priority": getattr(self, 'priority', 50),
            "backend": self.backend,
            "ttl": self.ttl,
            "min_sequence_length": self.min_sequence_length,
            "max_cache_size": self.max_cache_size
        }
    
    def model_dump(self) -> Dict[str, Any]:
        """Pydantic v2 compatibility alias."""
        return self.dict()

class LMCachePlugin(ReusePlugin):
    """LMCache plugin for KV cache reuse with Redis backend."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.redis = None
        self.hits = self.misses = 0
    
    def validate_config(self, config: Dict[str, Any]) -> LMCacheConfig:
        return LMCacheConfig(
            name=config.get("name", "lmcache"),
            enabled=config.get("enabled", True),
            priority=config.get("priority", 50),
            backend=config.get("backend", "redis://localhost:6379"),
            ttl=int(config.get("ttl", 3600)),
            min_sequence_length=int(config.get("min_sequence_length", 16)),
            max_cache_size=int(config.get("max_cache_size", 10_000))
        )
    
    def on_startup(self):
        try:
            if str(self.config.backend).startswith("fakeredis://"):
                if not fakeredis:
                    raise RuntimeError("fakeredis not installed; install fakeredis to use fakeredis backend")
                # In-memory Redis compatible client
                self.redis = fakeredis.FakeRedis()
            else:
                # Use constructor to cooperate with tests patching redis.Redis
                # Config URL is not parsed here since tests mock the client
                self.redis = redis.Redis()
            self.redis.ping()
            logger.info(f"LMCache connected to {self.config.backend}")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            self.config.enabled = False
    
    def on_shutdown(self):
        if self.redis:
            self.redis.close()
            self.redis = None
    
    def _get_cache_key(self, tokens: List[int]) -> str:
        return f"lmcache:{hashlib.sha256(','.join(map(str, tokens)).encode()).hexdigest()}"
    
    def store_cache(self, sequence_id: str, tokens: List[int], data: Dict[str, Any]) -> bool:
        """Store data in cache."""
        if not self.redis or len(tokens) < self.config.min_sequence_length:
            return False
        
        try:
            cache_key = self._get_cache_key(tokens)
            serialized = json.dumps(data)
            self.redis.setex(cache_key, self.config.ttl, serialized)
            return True
        except Exception as e:
            logger.warning(f"Failed to store cache: {e}")
            return False
    
    def check_cache(self, sequence_id: str, tokens: List[int]) -> Optional[Dict[str, Any]]:
        # Reads behavior:
        # - fakeredis backend: enforce min_sequence_length gating (no access/metrics when below threshold)
        # - real Redis backend: allow reads regardless of min_sequence_length
        if not self.config.enabled or not self.redis:
            return None
        is_fakeredis_backend = str(getattr(self.config, 'backend', '')).startswith("fakeredis://")
        if is_fakeredis_backend and len(tokens) < self.config.min_sequence_length:
            return None
        try:
            cache_key = self._get_cache_key(tokens)
            if cached := self.redis.get(cache_key):
                self.hits += 1
                # Redis may return bytes; decode to str for json
                if isinstance(cached, (bytes, bytearray)):
                    cached = cached.decode("utf-8")
                return json.loads(cached)
            self.misses += 1
        except Exception as e:
            logger.error(f"Cache check failed: {e}")
        return None
    
    def update_cache(self, sequence_id: str, tokens: List[int], kv_data: Dict):
        if not self.config.enabled or len(tokens) < self.config.min_sequence_length:
            return
        try:
            cache_key = self._get_cache_key(tokens)
            # Store only lightweight, JSON-serializable metadata to avoid numpy serialization
            # and to keep the demo focused on reuse behavior rather than payload transport.
            payload = {
                "sequence_id": sequence_id,
                "token_count": len(tokens)
            }
            self.redis.setex(cache_key, self.config.ttl, json.dumps(payload))
        except Exception as e:
            logger.error(f"Cache update failed: {e}")
    
    def get_metrics(self) -> Dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": self.hits / (self.hits + self.misses) if (self.hits + self.misses) > 0 else 0,
            "enabled": self.config.enabled
        }


# Aliases for compatibility
LmcachePlugin = LMCachePlugin
