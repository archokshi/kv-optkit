"""Integration test for Planner + Guard + MockExecutor."""
from unittest.mock import MagicMock

from kvopt.agent.planner import Planner, PlannerInputs
from kvopt.agent.guard import Guard, GuardConfig


def test_planner_guard_integration():
    # Setup
    planner = Planner(quantize_scale=0.1)  # Higher scale for more accuracy impact
    guard = Guard(GuardConfig(shadow_fraction=0.0, max_accuracy_delta=0.05))
    executor = MagicMock()
    executor.execute_plan.return_value = (True, {})

    # Test within budget
    inputs = PlannerInputs(
        hbm_util_current=0.90,
        hbm_util_target=0.85,
        sequences=["s1", "s2"],
    )
    plan = planner.make_plan(inputs)
    metrics = guard.execute_with_guard(plan, executor)
    assert metrics.status == "completed"
    assert not metrics.rollback_triggered

    # Test exceeds budget - manually set high accuracy impact to trigger rollback
    plan.estimated_accuracy_impact = 0.1  # Force high impact
    guard = Guard(GuardConfig(shadow_fraction=0.0, max_accuracy_delta=0.01))  # Strict
    executor.rollback_plan = MagicMock(return_value=(True, {}))
    metrics = guard.execute_with_guard(plan, executor)
    assert metrics.status == "rolled_back"
