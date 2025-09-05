import pytest
from unittest.mock import MagicMock

from kvopt.agent.guard import Guard, GuardConfig
from kvopt.agent.actions import Plan, Action, ActionType, KVRef


def test_guard_triggers_rollback_when_accuracy_exceeds_budget():
    guard = Guard(GuardConfig(shadow_fraction=0.0, max_accuracy_delta=0.05, rollback_on_high_impact=True))

    plan = Plan(
        actions=[Action(ActionType.QUANTIZE, KVRef("seq-1"), {"scale": 1.0})],
        priority="medium",
        estimated_hbm_reduction=0.1,
        estimated_accuracy_impact=0.10,  # exceeds 0.05
        id="plan-high-impact",
    )

    executor = MagicMock()
    executor.execute_plan.return_value = (True, {})

    metrics = guard.execute_with_guard(plan, executor)

    assert metrics.status == "rolled_back"
    assert metrics.rollback_triggered is True
    assert metrics.rollback_reason is not None
    executor.rollback_plan.assert_called_once_with(plan)
