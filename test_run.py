"""
Simple test script to verify PolicyEngine functionality.
"""
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath('.'))

from kvopt.config import Config, TelemetryData, SequenceInfo
from kvopt.agent.policy import PolicyEngine

def main():
    print("Testing PolicyEngine...")
    
    # Create a test config
    config = Config()
    print("\nConfig created successfully:")
    print(f"- SLO max_accuracy_delta_pct: {config.slo.max_accuracy_delta_pct}")
    print(f"- Budget hbm_util_target: {config.budget.hbm_util_target}")
    
    # Create a test telemetry
    telemetry = TelemetryData(
        hbm_used_gb=70.0,  # 70GB used out of 80GB (87.5% utilization)
        hbm_total_gb=80.0,
        ddr_used_gb=0.0,
        p95_latency_ms=100.0,
        sequences=[],
        timestamp_s=0.0
    )
    
    # Initialize the policy engine
    engine = PolicyEngine(config)
    print("\nPolicyEngine initialized successfully")
    
    # Analyze the telemetry
    report = engine.analyze(telemetry)
    print("\nAnalysis complete. Report:")
    print(f"- HBM utilization: {report.hbm_utilization:.1%}")
    print(f"- Recommendations: {len(report.recommendations)}")
    
    if report.recommendations:
        print("\nRecommendations:")
        for i, rec in enumerate(report.recommendations, 1):
            print(f"{i}. {rec.action}: {rec.detail} (Risk: {rec.risk})")

if __name__ == "__main__":
    main()
