#!/usr/bin/env python3
"""
Autopilot Demo for KV-OptKit

This script demonstrates the Autopilot feature that automatically optimizes
KV cache usage under HBM pressure. It shows how to:
1. Submit sequences to the system
2. Enable and configure Autopilot
3. Monitor optimization decisions
4. View before/after metrics
"""
import time
import random
import requests
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum
import json

# Configuration
BASE_URL = "http://localhost:8000"
AUTOPILOT_ENDPOINT = f"{BASE_URL}/autopilot"
SEQUENCES_ENDPOINT = f"{BASE_URL}/sequences"
METRICS_ENDPOINT = f"{BASE_URL}/metrics"
HEALTH_ENDPOINT = f"{BASE_URL}/health"

class ActionType(str, Enum):
    EVICT = "evict"
    OFFLOAD = "offload"
    QUANTIZE = "quantize"
    DEQUANTIZE = "dequantize"

def print_header(title: str) -> None:
    """Print a formatted section header."""
    print("\n" + "=" * 80)
    print(f" {title.upper()} ")
    print("=" * 80)

def print_metrics(metrics: Dict[str, Any]) -> None:
    """Print formatted metrics."""
    print("\nCurrent Metrics:")
    print(f"  • HBM Usage: {metrics.get('hbm_used_gb', 0):.2f}GB / {metrics.get('hbm_total_gb', 0):.1f}GB")
    print(f"  • KV Cache Entries: {metrics.get('kv_entries', 0)}") 
    print(f"  • Sequences: {metrics.get('active_sequences', 0)} active")
    print(f"  • Memory Pressure: {metrics.get('memory_pressure', 0):.1%}")

def get_metrics() -> Dict[str, Any]:
    """Get current system metrics."""
    try:
        response = requests.get(METRICS_ENDPOINT)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error getting metrics from {METRICS_ENDPOINT}: {e}")
        # Return mock data for demo purposes
        return {
            "hbm_used_gb": 30.5,
            "hbm_total_gb": 80.0,
            "kv_entries": 150,
            "active_sequences": 10,
            "memory_pressure": 0.65
        }

def submit_sequence(seq_id: str, length: int) -> bool:
    """Submit a sequence to the system."""
    try:
        response = requests.post(
            SEQUENCES_ENDPOINT,
            json={"sequence_id": seq_id, "length_tokens": length}
        )
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Error submitting sequence {seq_id} to {SEQUENCES_ENDPOINT}: {e}")
        print("Note: The sequences endpoint may not be implemented yet. Using mock submission.")
        return True  # Return True to continue demo

def enable_autopilot(dry_run: bool = True) -> bool:
    """Enable Autopilot with default configuration."""
    config = {
        "enabled": True,
        "dry_run": dry_run,
        "guardrails": {
            "max_accuracy_delta_pct": 0.5,
            "shadow_fraction": 0.05,
            "min_confidence": 0.8
        },
        "budgets": {
            "max_hbm_gb": 40,
            "target_hbm_gb": 35
        }
    }
    
    try:
        response = requests.post(
            f"{AUTOPILOT_ENDPOINT}/config",
            json=config
        )
        response.raise_for_status()
        print("✅ Autopilot enabled")
        print(f"   - Mode: {'Dry Run' if dry_run else 'Active'}")
        print(f"   - Max HBM: {config['budgets']['max_hbm_gb']}GB")
        return True
    except Exception as e:
        print(f"❌ Failed to enable Autopilot at {AUTOPILOT_ENDPOINT}/config: {e}")
        print("Note: The autopilot endpoint may not be implemented yet. Continuing with mock data.")
        return True  # Return True to continue demo

def get_autopilot_status() -> Dict[str, Any]:
    """Get current Autopilot status."""
    try:
        response = requests.get(f"{AUTOPILOT_ENDPOINT}/status")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error getting Autopilot status: {e}")
        return {}

def generate_workload(num_sequences: int = 10) -> List[Tuple[str, int]]:
    """Generate a realistic workload of sequences."""
    sequences = []
    for i in range(1, num_sequences + 1):
        seq_id = f"seq_{i:03d}"
        # Vary sequence lengths between 100-2000 tokens
        length = random.randint(100, 2000)
        sequences.append((seq_id, length))
    return sequences

def run_demo() -> None:
    """Run the Autopilot demo."""
    print_header("KV-OptKit Autopilot Demo")
    print("This demo will:")
    print("1. Submit a workload of sequences")
    print("2. Enable Autopilot in dry-run mode")
    print("3. Show optimization decisions")
    print("4. Compare metrics before/after")
    
    # Initial metrics
    print_header("Initial State")
    initial_metrics = get_metrics()
    print_metrics(initial_metrics)
    
    # Submit workload
    print_header("Submitting Workload")
    sequences = generate_workload(num_sequences=15)
    for seq_id, length in sequences:
        if submit_sequence(seq_id, length):
            print(f"✅ Submitted sequence {seq_id} ({length} tokens)")
    
    # Show metrics after workload
    time.sleep(2)  # Give system time to process
    print_header("After Workload Submission")
    workload_metrics = get_metrics()
    print_metrics(workload_metrics)
    
    # Enable Autopilot
    print_header("Enabling Autopilot")
    if not enable_autopilot(dry_run=True):
        print("❌ Cannot continue without Autopilot")
        return
    
    # Monitor Autopilot
    print_header("Monitoring Autopilot")
    print("Autopilot is analyzing and making optimization decisions...")
    
    for _ in range(5):  # Check status 5 times
        status = get_autopilot_status()
        if status.get("enabled"):
            print(f"\nAutopilot Status:")
            print(f"  • State: {status.get('state', 'unknown')}")
            print(f"  • Active Plan: {status.get('active_plan', 'None')}")
            print(f"  • Optimizations Applied: {status.get('optimizations_applied', 0)}")
            print(f"  • HBM Saved: {status.get('hbm_saved_gb', 0):.2f}GB")
        time.sleep(2)
    
    # Final metrics
    print_header("Final Metrics")
    final_metrics = get_metrics()
    print_metrics(final_metrics)
    
    # Show before/after comparison
    print_header("Results Summary")
    print(f"{'Metric':<20} | {'Before':>15} | {'After':>15} | {'Change':>15}")
    print("-" * 70)
    
    metrics_to_compare = [
        ("HBM Usage (GB)", "hbm_used_gb", "{:.2f}"),
        ("KV Entries", "kv_entries", "{:,}"),
        ("Active Sequences", "active_sequences", "{}"),
    ]
    
    for label, key, fmt in metrics_to_compare:
        before = workload_metrics.get(key, 0)
        after = final_metrics.get(key, 0)
        change = after - before if isinstance(before, (int, float)) else "N/A"
        
        print(f"{label:<20} | {fmt.format(before):>15} | {fmt.format(after):>15} | {fmt.format(change) if isinstance(change, (int, float)) else change:>15}")
    
    print("\n✅ Demo complete!")

if __name__ == "__main__":
    run_demo()
