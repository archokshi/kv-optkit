"""
Action types and simple data models used by KV-OptKit Autopilot.

This version aligns with unit tests in tests/test_guard.py by exposing
ActionType, KVRef(sequence_id), Action(action_type, target, params),
Plan with estimation fields, and PlanStatus enum.
"""
import time
from dataclasses import dataclass, field, asdict, replace
from enum import Enum
from typing import Dict, List, Optional, Any


class ActionType(str, Enum):
    REUSE = "REUSE"
    EVICT = "EVICT"
    OFFLOAD = "OFFLOAD"
    QUANTIZE = "QUANTIZE"


class PlanStatus(str, Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    RUNNING = "running"  # compatibility alias used by some tests
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass
class KVRef:
    sequence_id: str
    start_token: str = ""
    end_token: str = ""

    def dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for API responses."""
        return {
            "sequence_id": self.sequence_id,
            "start_token": self.start_token,
            "end_token": self.end_token
        }
    
    def model_dump(self) -> Dict[str, Any]:
        """Pydantic v2 compatibility alias."""
        return self.dict()


@dataclass
class Action:
    action_type: ActionType
    target: KVRef
    params: Dict[str, Any] = field(default_factory=dict)

    def dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for API responses."""
        return {
            "action_type": self.action_type.value,
            "target": self.target.dict() if self.target else None,
            "params": self.params or {}
        }
    
    def model_dump(self) -> Dict[str, Any]:
        """Pydantic v2 compatibility alias."""
        return self.dict()


@dataclass
class Plan:
    actions: List[Action]
    priority: str
    estimated_hbm_reduction: float
    estimated_accuracy_impact: float
    plan_id: Optional[str] = None
    id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    status: "PlanStatus" = PlanStatus.PENDING

    def __post_init__(self):
        # Sync fields so callers can use either 'plan_id' or 'id'
        if self.plan_id and not self.id:
            self.id = self.plan_id
        elif self.id and not self.plan_id:
            self.plan_id = self.id

    def copy(self, update: Optional[Dict[str, Any]] = None) -> "Plan":
        # Provide pydantic-like .copy(update=...) for test compatibility
        base = self
        if update:
            base = replace(
                self,
                **{k: update[k] for k in update.keys() if hasattr(self, k)}
            )
            # keep id/plan_id in sync if one is updated
            if "plan_id" in update and not update.get("id"):
                base.id = update["plan_id"]
            if "id" in update and not update.get("plan_id"):
                base.plan_id = update["id"]
        return base

    def dict(self) -> Dict[str, Any]:
        """Serialize Plan to a dictionary for API responses and tests.

        Ensures action list and status are rendered to simple JSON-friendly types.
        """
        return {
            "plan_id": self.plan_id,
            "id": self.id,
            "actions": [a.dict() for a in (self.actions or [])],
            "priority": self.priority,
            "estimated_hbm_reduction": float(self.estimated_hbm_reduction),
            "estimated_accuracy_impact": float(self.estimated_accuracy_impact),
            "created_at": float(self.created_at),
            "status": self.status.value if isinstance(self.status, PlanStatus) else str(self.status),
        }

    def model_dump(self) -> Dict[str, Any]:
        """Pydantic v2 compatibility alias."""
        return self.dict()


@dataclass
class ActionResult:
    success: bool
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def dict(self) -> Dict[str, Any]:
        return asdict(self)


class ActionExecutor:  # pragma: no cover - simple implementation for router
    def __init__(self, adapter: Any):
        self.adapter = adapter
        self._tx_log: List[Action] = []

    def execute(self, action: Action) -> ActionResult:
        payload: Dict[str, Any] = {
            "action_type": action.action_type.value,
            "sequence_id": action.target.sequence_id,
        }
        # Merge params; translate keys where the simulator expects different names
        params = dict(action.params or {})
        if action.action_type == ActionType.QUANTIZE and "scale" in params and "factor" not in params:
            params["factor"] = params["scale"]
        payload.update(params)

        try:
            success = bool(self.adapter.execute_action(payload))
            if success:
                self._tx_log.append(action)
            return ActionResult(success=success, details={"payload": payload})
        except Exception as e:
            return ActionResult(success=False, details={"error": str(e), "payload": payload})

    def execute_plan(self, plan: "Plan", shadow_mode: bool = False) -> tuple[bool, List[ActionResult]]:
        results: List[ActionResult] = []
        all_ok = True
        for a in plan.actions:
            res = self.execute(a)
            results.append(res)
            if not res.success and not shadow_mode:
                all_ok = False
                break
        return all_ok, results

    def rollback_plan(self, plan: "Plan") -> bool:
        # Best-effort rollback; only QUANTIZE has a reversible counterpart in simulator
        try:
            for a in reversed(self._tx_log):
                if a.action_type == ActionType.QUANTIZE:
                    payload = {
                        "action_type": "DEQUANTIZE",
                        "sequence_id": a.target.sequence_id,
                    }
                    self.adapter.execute_action(payload)
            self._tx_log.clear()
            return True
        except Exception:
            return False
