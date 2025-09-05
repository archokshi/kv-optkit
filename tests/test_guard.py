"""
Unit tests for the Guard class.
"""
import pytest
from unittest.mock import MagicMock, patch
from typing import Dict, Any, List, Optional
import time

from kvopt.agent.guard import Guard, GuardMetrics, GuardConfig
from kvopt.agent import Action, ActionType, KVRef, Plan, PlanStatus


def test_guard_initialization():
    """Test that Guard initializes with default and custom config."""
    # Test with default config
    guard = Guard()
    assert guard.config.shadow_fraction == 0.1
    assert guard.config.max_accuracy_delta == 0.05
    assert guard.config.enabled is True
    
    # Test with custom config
    custom_config = GuardConfig(
        shadow_fraction=0.2,
        max_accuracy_delta=0.1,
        enabled=False,
        accuracy_weights={"evict": 1.0, "offload": 0.8, "quantize": 0.5}
    )
    guard = Guard(config=custom_config)
    assert guard.config.shadow_fraction == 0.2
    assert guard.config.max_accuracy_delta == 0.1
    assert guard.config.enabled is False
    assert guard.config.accuracy_weights == {"evict": 1.0, "offload": 0.8, "quantize": 0.5}


def test_should_use_shadow_mode():
    """Test the shadow mode selection logic."""
    # Test with shadow_fraction = 0.0 (never use shadow mode)
    guard = Guard(GuardConfig(shadow_fraction=0.0))
    assert not guard._should_use_shadow_mode()
    
    # Test with shadow_fraction = 1.0 (always use shadow mode)
    guard = Guard(GuardConfig(shadow_fraction=1.0))
    assert guard._should_use_shadow_mode()
    
    # Test with shadow_fraction = 0.5 (probabilistic)
    guard = Guard(GuardConfig(shadow_fraction=0.5))
    with patch('random.random', return_value=0.3):
        assert guard._should_use_shadow_mode()
    with patch('random.random', return_value=0.7):
        assert not guard._should_use_shadow_mode()


def test_calculate_accuracy_proxy():
    """Test the accuracy proxy calculation."""
    guard = Guard()
    
    # Test with no actions
    assert guard._calculate_accuracy_proxy([]) == 1.0
    
    # Test with different action types
    actions = [
        Action(action_type=ActionType.EVICT, target=KVRef(sequence_id="seq1"), params={"reason": "test"}),
        Action(action_type=ActionType.OFFLOAD, target=KVRef(sequence_id="seq2"), params={"tier": "DDR"}),
        Action(action_type=ActionType.QUANTIZE, target=KVRef(sequence_id="seq3"), params={"scale": 0.5}),
    ]
    
    # Default weights: evict=1.0, offload=0.5, quantize=0.1
    # Expected: 1.0 * 1.0 + 1.0 * 0.5 + 0.5 * 0.1 = 1.55 / 3 = ~0.5167
    proxy = guard._calculate_accuracy_proxy(actions)
    assert 0.51 <= proxy <= 0.52
    
    # Test with custom weights
    guard = Guard(GuardConfig(accuracy_weights={"evict": 2.0, "offload": 1.0, "quantize": 0.5}))
    # Expected: 1.0 * 2.0 + 1.0 * 1.0 + 0.5 * 0.5 = 3.25 / 3 = ~1.083
    proxy = guard._calculate_accuracy_proxy(actions)
    assert 1.08 <= proxy <= 1.09


def test_validate_actions():
    """Test action validation logic."""
    guard = Guard()
    
    # Test with valid actions
    actions = [
        Action(action_type=ActionType.EVICT, target=KVRef(sequence_id="seq1"), params={"reason": "test"}),
        Action(action_type=ActionType.OFFLOAD, target=KVRef(sequence_id="seq2"), params={"tier": "DDR"}),
    ]
    assert guard.validate_actions(actions) is True
    
    # Test with invalid action
    invalid_actions = actions + [
        Action(action_type=ActionType.QUANTIZE, target=KVRef(sequence_id="seq3"), params={"invalid": True})
    ]
    assert guard.validate_actions(invalid_actions) is False


def test_execute_with_guard_success():
    """Test successful execution with guard."""
    guard = Guard(GuardConfig(shadow_fraction=0.0))  # Disable shadow mode
    plan = Plan(
        actions=[Action(action_type=ActionType.EVICT, target=KVRef(sequence_id="seq1"))],
        priority="medium",
        estimated_hbm_reduction=0.1,
        estimated_accuracy_impact=0.01
    )
    
    # Mock the executor
    executor = MagicMock()
    executor.execute_plan.return_value = (True, None)
    
    # Execute the plan
    metrics = guard.execute_with_guard(plan, executor)
    
    # Verify the results
    assert metrics.status == "completed"
    assert metrics.rollback_triggered is False
    assert metrics.accuracy_impact == 0.01
    assert metrics.hbm_reduction == 0.1
    assert metrics.execution_time_ms > 0
    
    # Verify the executor was called
    executor.execute_plan.assert_called_once()


def test_execute_with_guard_rollback():
    """Test execution with guard-triggered rollback."""
    # Configure guard to be very sensitive to accuracy impact
    guard = Guard(GuardConfig(
        shadow_fraction=0.0,  # Disable shadow mode
        max_accuracy_delta=0.01,  # Very sensitive to accuracy impact
        rollback_on_high_impact=True
    ))
    
    plan = Plan(
        actions=[Action(action_type=ActionType.EVICT, target=KVRef(sequence_id="seq1"))],
        priority="high",
        estimated_hbm_reduction=0.2,
        estimated_accuracy_impact=0.05  # Exceeds max_accuracy_delta
    )
    
    # Mock the executor to simulate successful execution
    executor = MagicMock()
    executor.execute_plan.return_value = (True, None)
    
    # Execute the plan
    metrics = guard.execute_with_guard(plan, executor)
    
    # Verify the results
    assert metrics.status == "rolled_back"
    assert metrics.rollback_triggered is True
    assert "Accuracy impact" in metrics.rollback_reason
    
    # Verify rollback was called
    assert executor.rollback_plan.call_count == 1


def test_shadow_execution():
    """Test shadow execution mode."""
    guard = Guard(GuardConfig(shadow_fraction=1.0))  # Always use shadow mode
    
    plan = Plan(
        actions=[Action(action_type=ActionType.EVICT, target=KVRef(sequence_id="seq1"))],
        priority="medium",
        estimated_hbm_reduction=0.1,
        estimated_accuracy_impact=0.01
    )
    
    # Mock the executor
    executor = MagicMock()
    executor.execute_plan.return_value = (True, None)
    
    # Execute in shadow mode
    metrics = guard.execute_with_guard(plan, executor)
    
    # Verify the results
    assert metrics.status == "completed"
    assert metrics.shadow_mode is True
    assert metrics.rollback_triggered is False
    
    # Verify the executor was called with shadow_mode=True
    args, kwargs = executor.execute_plan.call_args
    assert kwargs.get("shadow_mode") is True


def test_metrics_aggregation():
    """Test that metrics are properly aggregated."""
    guard = Guard()
    
    # Add some test metrics
    test_metrics = [
        GuardMetrics(
            plan_id=f"plan_{i}",
            status="completed",
            execution_time_ms=100 + i * 10,
            hbm_reduction=0.1 * (i + 1),
            accuracy_impact=0.01 * (i + 1),
            shadow_mode=False,
            rollback_triggered=False
        )
        for i in range(5)
    ]
    
    # Add metrics to guard
    for metric in test_metrics:
        guard.metrics[metric.plan_id] = metric
    
    # Get aggregated metrics
    aggregated = guard.get_metrics()
    
    # Verify the aggregated metrics
    assert aggregated["total_plans"] == 5
    assert aggregated["success_rate"] == 1.0
    assert aggregated["rollback_rate"] == 0.0
    assert 0.1 <= aggregated["avg_hbm_reduction"] <= 0.5
    assert 0.01 <= aggregated["avg_accuracy_impact"] <= 0.05
    assert 100 <= aggregated["avg_execution_time_ms"] <= 140
    assert aggregated["shadow_mode_fraction"] == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
