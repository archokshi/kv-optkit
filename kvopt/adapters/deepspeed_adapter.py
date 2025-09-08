"""
DeepSpeed-MII adapter skeleton (Phase 5).
Implements the Adapter interface with placeholder telemetry and no-op actions.
"""
from typing import Dict, Any, List
from .base import Adapter


class DeepSpeedMIIAdapter(Adapter):
    def __init__(self, config: Dict[str, Any]):
        self.config = config or {}
        self.__class__._instance = self

    def get_telemetry(self) -> Dict[str, Any]:
        hbm_total = float(self.config.get("hbm_capacity_gb") or 80.0)
        hbm_used = float(self.config.get("hbm_used_gb") or 0.55)
        p95 = float(self.config.get("p95_latency_ms") or 28.0)
        return {
            "adapter": "deepspeed",
            "hbm_used_gb": hbm_used,
            "hbm_total_gb": hbm_total,
            "p95_latency_ms": p95,
            "sequences": [],
        }

    def execute_action(self, action: Dict[str, Any]) -> bool:
        return False

    def get_sequences(self) -> List[Dict[str, Any]]:
        return []

    def capabilities(self) -> set:
        # Start as observe-only (L0). Consider L1/L2 as stats and wrappers improve.
        return set()
