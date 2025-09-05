import time
import pytest
from datetime import datetime, timedelta

from kvopt.config import Config, TelemetryData, SequenceInfo
from kvopt.agent.policy import PolicyEngine


def create_test_telemetry(
    hbm_used_gb: float = 0.0,
    hbm_total_gb: float = 80.0,
    ddr_used_gb: float = 0.0,
    p95_latency_ms: float = 100.0,
    sequences: list = None
) -> TelemetryData:
    """Helper function to create test telemetry data."""
    if sequences is None:
        sequences = []
    
    return TelemetryData(
        hbm_used_gb=hbm_used_gb,
        hbm_total_gb=hbm_total_gb,
        ddr_used_gb=ddr_used_gb,
        p95_latency_ms=p95_latency_ms,
        sequences=sequences,
        timestamp_s=time.time()
    )


def test_policy_under_utilization():
    """Test that no recommendations are generated when under utilization."""
    # Create a test config with high utilization target
    config = Config(budgets={"hbm_util_target": 0.9}, slo={"latency_p95_ms": 2000.0})
    policy = PolicyEngine(config)
    
    # Create telemetry with low utilization
    telemetry = create_test_telemetry(
        hbm_used_gb=40.0,  # 50% of 80GB
        hbm_total_gb=80.0
    )
    
    # Analyze and check recommendations
    report = policy.analyze(telemetry)
    assert len(report.recommendations) == 0
    assert "System within target utilization" in report.notes


def test_policy_high_utilization():
    """Test that recommendations are generated when over utilization."""
    # Create a test config with low utilization target
    config = Config(budgets={"hbm_util_target": 0.5}, slo={"latency_p95_ms": 2000.0})
    policy = PolicyEngine(config)
    
    # Create telemetry with high utilization (75% of 80GB)
    telemetry = create_test_telemetry(
        hbm_used_gb=60.0,
        hbm_total_gb=80.0,
        sequences=[
            {"seq_id": "seq1", "length_tokens": 1000, "last_accessed": time.time() - 10},
            {"seq_id": "seq2", "length_tokens": 2000, "last_accessed": time.time() - 300}  # 5 minutes old
        ]
    )
    
    # Analyze and check recommendations
    report = policy.analyze(telemetry)
    assert len(report.recommendations) > 0
    assert any(rec.action == "evict_old_sequences" for rec in report.recommendations)
    assert "HBM utilization" in report.notes[0]


def test_policy_high_latency():
    """Test that latency-related recommendations are generated when latency is high."""
    # Create a test config with strict latency SLO
    config = Config(
        budgets={"hbm_util_target": 0.9},
        slo={"latency_p95_ms": 100.0}  # Very strict SLO
    )
    policy = PolicyEngine(config)
    
    # Create telemetry with high latency
    telemetry = create_test_telemetry(
        hbm_used_gb=40.0,  # 50% of 80GB
        hbm_total_gb=80.0,
        p95_latency_ms=500.0  # Exceeds SLO
    )
    
    # Analyze and check recommendations
    report = policy.analyze(telemetry)
    assert len(report.recommendations) > 0
    assert any("increase_keep_recent_tokens" in rec.action for rec in report.recommendations)
    assert any("exceeds SLO" in note for note in report.notes)


def test_sequence_eviction_recommendation():
    """Test that old sequences are recommended for eviction."""
    config = Config(
        budgets={"hbm_util_target": 0.5},
        policy={"keep_recent_tokens": 1000}
    )
    policy = PolicyEngine(config)
    
    # Create telemetry with some old sequences
    now = time.time()
    telemetry = create_test_telemetry(
        hbm_used_gb=60.0,  # 75% of 80GB
        hbm_total_gb=80.0,
        sequences=[
            {"seq_id": "old1", "length_tokens": 1000, "last_accessed": now - 300},  # 5 minutes old
            {"seq_id": "old2", "length_tokens": 2000, "last_accessed": now - 60},  # 1 minute old
            {"seq_id": "new1", "length_tokens": 500, "last_accessed": now - 10}   # 10 seconds old
        ]
    )
    
    # Analyze and check recommendations
    report = policy.analyze(telemetry)
    assert len(report.recommendations) > 0
    
    # Check that we have an eviction recommendation
    eviction_recs = [r for r in report.recommendations if r.action == "evict_old_sequences"]
    assert len(eviction_recs) > 0
    assert "old sequences" in eviction_recs[0].detail.lower()
    assert eviction_recs[0].estimated_hbm_savings_gb > 0
