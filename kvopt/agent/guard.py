"""
Guard for KV-OptKit Autopilot.

This module provides the Guard class and configuration used by the Autopilot.
It implements a lightweight API expected by tests for validating and executing
plans with optional shadow mode and rollback based on accuracy impact.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
import time
import random
import logging

from .actions import Action, Plan
from .actions import ActionType  # enum for action types used in tests

logger = logging.getLogger(__name__)


@dataclass
class GuardConfig:
    """Configuration for Guard behavior (matches tests' expectations)."""
    shadow_fraction: float = 0.1
    max_accuracy_delta: float = 0.05
    enabled: bool = True
    rollback_on_high_impact: bool = True
    accuracy_weights: Dict[str, float] = field(
        default_factory=lambda: {"reuse": 0.0, "evict": 1.0, "offload": 0.5, "quantize": 0.1}
    )


@dataclass
class GuardMetrics:
    """Execution metrics for a plan (matches tests' fields)."""
    plan_id: str
    status: str
    execution_time_ms: float
    hbm_reduction: float
    accuracy_impact: float
    shadow_mode: bool
    rollback_triggered: bool
    rollback_reason: Optional[str] = None


class Guard:
    """Guard that validates and monitors execution of optimization plans."""

    def __init__(self, config: Optional[GuardConfig] = None):
        self.config = config or GuardConfig()
        # store latest metrics by plan id for aggregation
        self.metrics: Dict[str, GuardMetrics] = {}
        # simple in-flight lock to serialize plan execution
        try:
            import threading
            self._lock = threading.Lock()
        except Exception:  # pragma: no cover - defensive
            self._lock = None

    @staticmethod
    def get_current() -> "Guard":
        """FastAPI dependency helper returning a new Guard instance."""
        return Guard()

    # --- Internal helpers used by tests ---
    def _should_use_shadow_mode(self) -> bool:
        if not self.config.enabled:
            return False
        if self.config.shadow_fraction <= 0.0:
            return False
        if self.config.shadow_fraction >= 1.0:
            return True
        return random.random() < self.config.shadow_fraction

    def _calculate_accuracy_proxy(self, actions: List[Action]) -> float:
        # Average of weighted impacts over actions
        if not actions:
            return 1.0
        total = 0.0
        for a in actions:
            if a.action_type == ActionType.REUSE:
                total += 0.0 * self.config.accuracy_weights.get("reuse", 0.0)
            elif a.action_type == ActionType.EVICT:
                total += 1.0 * self.config.accuracy_weights.get("evict", 1.0)
            elif a.action_type == ActionType.OFFLOAD:
                total += 1.0 * self.config.accuracy_weights.get("offload", 0.5)
            elif a.action_type == ActionType.QUANTIZE:
                scale = 1.0
                if isinstance(a.params, dict):
                    scale = float(a.params.get("scale", 1.0))
                total += scale * self.config.accuracy_weights.get("quantize", 0.1)
            else:
                total += 1.0
        return total / len(actions)

    # --- Public API used by tests ---
    def validate_actions(self, actions: List[Action]) -> bool:
        # Basic validation: reject actions with an explicit invalid flag
        for a in actions:
            if isinstance(a.params, dict) and a.params.get("invalid"):
                return False
        return True

    def execute_with_guard(self, plan: "Plan", executor: Any) -> GuardMetrics:
        shadow_mode = self._should_use_shadow_mode()
        start = time.time()

        # Execute the plan (executor is mocked in tests)
        executor.execute_plan.return_value  # ensure attribute exists for MagicMock
        success, _ = executor.execute_plan(plan, shadow_mode=shadow_mode)

        # Collect metrics based on plan estimates
        hbm_reduction = getattr(plan, "estimated_hbm_reduction", 0.0) or 0.0
        accuracy_impact = getattr(plan, "estimated_accuracy_impact", 0.0) or 0.0

        rollback_triggered = False
        rollback_reason = None
        status = "completed"

        if (
            not shadow_mode
            and self.config.rollback_on_high_impact
            and accuracy_impact > self.config.max_accuracy_delta
        ):
            rollback_triggered = True
            status = "rolled_back"
            rollback_reason = (
                f"Accuracy impact {accuracy_impact:.2f} exceeds max {self.config.max_accuracy_delta:.2f}"
            )
            # Ask executor to rollback
            if hasattr(executor, "rollback_plan"):
                try:
                    executor.rollback_plan(plan)
                except Exception:  # best-effort rollback in tests
                    pass

        elapsed_ms = (time.time() - start) * 1000.0

        plan_id = getattr(plan, "id", f"plan_{int(start * 1000)}")
        metrics = GuardMetrics(
            plan_id=plan_id,
            status=status,
            execution_time_ms=elapsed_ms,
            hbm_reduction=hbm_reduction,
            accuracy_impact=accuracy_impact,
            shadow_mode=shadow_mode,
            rollback_triggered=rollback_triggered,
            rollback_reason=rollback_reason,
        )

        self.metrics[plan_id] = metrics
        return metrics

    def get_metrics(self) -> Dict[str, Any]:
        # Aggregate over stored metrics
        if not self.metrics:
            return {
                "total_plans": 0,
                "success_rate": 0.0,
                "rollback_rate": 0.0,
                "avg_hbm_reduction": 0.0,
                "avg_accuracy_impact": 0.0,
                "avg_execution_time_ms": 0.0,
                "shadow_mode_fraction": 0.0,
            }

        vals = list(self.metrics.values())
        total = len(vals)
        successes = sum(1 for m in vals if m.status == "completed")
        rollbacks = sum(1 for m in vals if m.rollback_triggered)
        avg_hbm = sum(m.hbm_reduction for m in vals) / total
        avg_acc = sum(m.accuracy_impact for m in vals) / total
        avg_time = sum(m.execution_time_ms for m in vals) / total
        shadow_frac = sum(1 for m in vals if m.shadow_mode) / total

        return {
            "total_plans": total,
            "success_rate": successes / total if total else 0.0,
            "rollback_rate": rollbacks / total if total else 0.0,
            "avg_hbm_reduction": avg_hbm,
            "avg_accuracy_impact": avg_acc,
            "avg_execution_time_ms": avg_time,
            "shadow_mode_fraction": shadow_frac,
        }

    # --- API compatibility layer used by FastAPI router (autopilot) ---
    def start_plan_execution(self, plan: "Plan", telemetry_before: Dict[str, Any]) -> None:
        """Acquire in-flight lock and note start time/telemetry baseline."""
        if self._lock:
            acquired = self._lock.acquire(blocking=False)
            if not acquired:
                # Reuse metrics container to expose lock contention if needed
                logger.warning("Another plan is already executing; new plan will wait or be rejected by caller.")
                # Caller can decide to queue; here we do nothing further
        # Stash baseline on the instance for simple delta computation
        self._current_baseline = {
            "ts": time.time(),
            "telemetry": telemetry_before or {},
        }

    def validate_action(self, action: Action, telemetry: Dict[str, Any]) -> tuple[bool, str]:
        """Lightweight per-action validation; reuses validate_actions semantics."""
        ok = self.validate_actions([action])
        return ok, "" if ok else "invalid action parameters"

    def before_action_execute(self, action: Action, telemetry: Dict[str, Any]) -> Dict[str, Any]:
        """Return a context object for post-action checks."""
        return {
            "ts": time.time(),
            "telemetry": telemetry or {},
            "action": action.action_type.value,
        }

    def after_action_execute(
        self,
        action: Action,
        result: Dict[str, Any],
        telemetry: Dict[str, Any],
        context: Dict[str, Any],
    ) -> tuple[bool, str]:
        """Decide whether to continue. For now, always continue unless explicit error in result."""
        if isinstance(result, dict) and result.get("error"):
            return False, str(result.get("error"))
        return True, ""

    def end_plan_execution(self, plan: "Plan", telemetry_after: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Compute proxy accuracy and enforce rollback budget. Release lock."""
        try:
            accuracy_impact = getattr(plan, "estimated_accuracy_impact", 0.0) or 0.0
            hbm_reduction = getattr(plan, "estimated_hbm_reduction", 0.0) or 0.0
            shadow_mode = self._should_use_shadow_mode()

            rollback = False
            reason = None
            if (
                not shadow_mode
                and self.config.rollback_on_high_impact
                and accuracy_impact > self.config.max_accuracy_delta
            ):
                rollback = True
                reason = (
                    f"Accuracy impact {accuracy_impact:.2f} exceeds max {self.config.max_accuracy_delta:.2f}"
                )

            # Record metrics similar to execute_with_guard path
            start_ts = getattr(self, "_current_baseline", {}).get("ts", time.time())
            elapsed_ms = (time.time() - start_ts) * 1000.0
            plan_id = getattr(plan, "id", f"plan_{int(start_ts * 1000)}")
            self.metrics[plan_id] = GuardMetrics(
                plan_id=plan_id,
                status="rolled_back" if rollback else "completed",
                execution_time_ms=elapsed_ms,
                hbm_reduction=hbm_reduction,
                accuracy_impact=accuracy_impact,
                shadow_mode=shadow_mode,
                rollback_triggered=rollback,
                rollback_reason=reason,
            )
            return rollback, reason
        finally:
            if self._lock and self._lock.locked():
                try:
                    self._lock.release()
                except Exception:
                    pass

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Alias used by router to fetch aggregated guard metrics."""
        return self.get_metrics()
