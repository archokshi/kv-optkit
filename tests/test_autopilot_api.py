"""
Tests for the Autopilot API endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from typing import Dict, Any, List, Optional
import json

from kvopt.server.main import app
from kvopt.agent import Plan, Action, ActionType, KVRef, PlanStatus

# Create a test client
client = TestClient(app)

# Mock data for testing
TEST_PLAN = Plan(
    plan_id="test_plan_123",
    actions=[
        Action(
            action_type=ActionType.EVICT,
            target=KVRef(sequence_id="seq1"),
            params={"reason": "test"}
        )
    ],
    priority="medium",
    estimated_hbm_reduction=0.1,
    estimated_accuracy_impact=0.01,
    status=PlanStatus.PENDING
)


def test_create_plan():
    """Test creating a new optimization plan."""
    # Mock the policy engine and action executor
    with patch('kvopt.server.routers.autopilot.POLICY_ENGINE') as mock_engine, \
         patch('kvopt.server.routers.autopilot.ACTION_EXECUTOR') as mock_executor:
        
        # Configure the mocks
        mock_engine.generate_plan.return_value = TEST_PLAN
        mock_executor.execute_plan.return_value = (True, None)
        
        # Make the request
        response = client.post(
            "/autopilot/plan",
            json={
                "target_hbm_util": 0.7,
                "max_actions": 5,
                "priority": "high"
            }
        )
        
        # Check the response
        assert response.status_code == 200
        data = response.json()
        assert data["plan_id"] == "test_plan_123"
        assert data["status"] == "pending"
        assert len(data["actions"]) == 1
        assert data["actions"][0]["action_type"] == "EVICT"
        
        # Verify the policy engine was called with the correct parameters
        mock_engine.generate_plan.assert_called_once()
        args, kwargs = mock_engine.generate_plan.call_args
        assert kwargs["target_hbm_util"] == 0.7
        assert kwargs["max_actions"] == 5
        assert kwargs["priority"] == "high"


def test_get_plan_status():
    """Test retrieving the status of a plan."""
    # First create a plan
    with patch('kvopt.server.routers.autopilot.POLICY_ENGINE') as mock_engine, \
         patch('kvopt.server.routers.autopilot.ACTION_EXECUTOR') as mock_executor:
        
        # Configure the mocks
        test_plan = TEST_PLAN.copy(update={"status": PlanStatus.COMPLETED})
        mock_engine.generate_plan.return_value = test_plan
        mock_executor.execute_plan.return_value = (True, None)
        
        # Create a plan
        create_response = client.post("/autopilot/plan", json={"target_hbm_util": 0.7})
        plan_id = create_response.json()["plan_id"]
        
        # Mock the in-memory storage for the GET request
        with patch('kvopt.server.routers.autopilot.PLANS', {plan_id: test_plan}):
            # Get the plan status
            response = client.get(f"/autopilot/plan/{plan_id}")
            
            # Check the response
            assert response.status_code == 200
            data = response.json()
            assert data["plan_id"] == plan_id
            assert data["status"] == "completed"


def test_cancel_plan():
    """Test cancelling a running plan."""
    # Create a test plan
    test_plan = TEST_PLAN.copy(update={"status": PlanStatus.RUNNING})
    plan_id = test_plan.plan_id
    
    # Mock the in-memory storage and executor
    with patch('kvopt.server.routers.autopilot.PLANS', {plan_id: test_plan}), \
         patch('kvopt.server.routers.autopilot.ACTION_EXECUTOR') as mock_executor:
        
        # Configure the executor to return success on cancel
        mock_executor.cancel_plan.return_value = True
        
        # Cancel the plan
        response = client.post(f"/autopilot/plan/{plan_id}/cancel")
        
        # Check the response
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"
        assert data["plan_id"] == plan_id
        
        # Verify the executor was called
        mock_executor.cancel_plan.assert_called_once_with(plan_id)


def test_get_metrics():
    """Test retrieving execution metrics."""
    # Mock the guard to return test metrics
    test_metrics = {
        "total_plans": 10,
        "recent_plans": 5,
        "success_rate": 0.9,
        "rollback_rate": 0.1,
        "avg_hbm_reduction": 0.25,
        "avg_accuracy_impact": 0.02,
        "avg_execution_time_ms": 150.5
    }
    
    with patch('kvopt.server.routers.autopilot.GUARD') as mock_guard:
        mock_guard.get_metrics.return_value = test_metrics
        
        # Get the metrics
        response = client.get("/autopilot/metrics")
        
        # Check the response
        assert response.status_code == 200
        data = response.json()
        assert data == test_metrics
        
        # Verify the guard was called
        mock_guard.get_metrics.assert_called_once()


def test_plan_not_found():
    """Test handling of non-existent plan."""
    # Try to get a non-existent plan
    response = client.get("/autopilot/plan/non_existent_plan")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
    
    # Try to cancel a non-existent plan
    response = client.post("/autopilot/plan/non_existent_plan/cancel")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_invalid_plan_creation():
    """Test plan creation with invalid parameters."""
    # Test with invalid target HBM utilization
    response = client.post(
        "/autopilot/plan",
        json={"target_hbm_util": 1.5}  # Invalid: > 1.0
    )
    assert response.status_code == 422  # Validation error
    
    # Test with invalid priority
    response = client.post(
        "/autopilot/plan",
        json={"priority": "invalid_priority"}
    )
    assert response.status_code == 422  # Validation error
    
    # Test with negative max_actions
    response = client.post(
        "/autopilot/plan",
        json={"max_actions": -1}
    )
    assert response.status_code == 422  # Validation error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
