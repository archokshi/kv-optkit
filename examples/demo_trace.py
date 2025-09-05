#!/usr/bin/env python3
"""
Demo script for KV-OptKit that shows how to interact with the API.
This script demonstrates submitting sequences, checking the advisor report,
and simulating a simple workload.
"""
import time
import random
import requests
from typing import List, Dict, Any, Optional

# Configuration
BASE_URL = "http://localhost:9000"


def print_report(report: Optional[Dict[str, Any]]) -> None:
    """Print a formatted advisor report."""
    if not report:
        print("No report available - server may not be running")
        return
        
    print("\n" + "="*80)
    print(f"KV-OptKit Advisor Report (HBM: {report.get('hbm_utilization', 0):.1%} used)")
    print("-" * 80)
    
    # Print sequences
    sequences = report.get('sequences', [])
    if sequences:
        print(f"\nActive Sequences ({len(sequences)}):")
        for seq in sequences[:5]:  # Show first 5 sequences
            print(f"  - {seq.get('seq_id', 'unknown')}: {seq.get('length_tokens', 0)} tokens")
        if len(sequences) > 5:
            print(f"  ... and {len(sequences) - 5} more")
    
    # Print recommendations
    recommendations = report.get('recommendations', [])
    if recommendations:
        print("\nRecommendations:")
        for i, rec in enumerate(recommendations, 1):
            print(f"  {i}. [{rec.get('risk', 'N/A').upper()}] {rec.get('action', 'No action')}")
            print(f"     {rec.get('detail', 'No details')}")
            print(f"     Estimated savings: {rec.get('estimated_hbm_savings_gb', 0):.2f}GB")
    else:
        print("\nNo recommendations at this time.")
    
    # Print notes
    notes = report.get('notes', [])
    if notes:
        print("\nNotes:")
        for note in notes:
            print(f"  - {note}")
    
    print("="*80 + "\n")


def get_advisor_report() -> Optional[Dict[str, Any]]:
    """Get the current advisor report."""
    try:
        response = requests.get(f"{BASE_URL}/advisor/report", timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error getting advisor report: {e}")
        return None


def submit_sequence(seq_id: str, tokens: int) -> bool:
    """Submit a sequence to the simulator."""
    try:
        response = requests.post(
            f"{BASE_URL}/sim/submit",
            json={"seq_id": seq_id, "tokens": tokens},
            timeout=5
        )
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"Error submitting sequence {seq_id}: {e}")
        return False


def finish_sequence(seq_id: str) -> bool:
    """Mark a sequence as finished."""
    try:
        response = requests.delete(
            f"{BASE_URL}/sim/finish/{seq_id}",
            timeout=5
        )
        return response.status_code == 200
    except requests.RequestException:
        return False


def reset_simulator() -> None:
    """Reset the simulator state."""
    try:
        response = requests.post(
            f"{BASE_URL}/sim/reset",
            timeout=5
        )
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error resetting simulator: {e}")


def generate_workload(num_sequences: int = 10) -> List[Dict[str, Any]]:
    """Generate a simple workload of sequences."""
    sequences = []
    for i in range(num_sequences):
        seq_id = f"seq_{i+1}"
        tokens = random.randint(100, 5000)  # Random sequence length
        sequences.append({"id": seq_id, "tokens": tokens})
    return sequences


def run_demo():
    """Run the demo workflow."""
    print("KV-OptKit Demo")
    print("==============\n")
    
    # First check if server is running
    try:
        response = requests.get(f"{BASE_URL}/healthz", timeout=2)
        if response.status_code != 200:
            print("Error: Server is not responding. Please start the server first.")
            print("Run this command in a separate terminal:")
            print("python -m kvopt.server.main --engine sim --config config/sample_config.yaml")
            return
    except requests.RequestException:
        print("Error: Could not connect to the server. Please make sure it's running.")
        print("Run this command in a separate terminal:")
        print("python -m kvopt.server.main --engine sim --config config/sample_config.yaml")
        return
    
    # Reset simulator to start fresh
    print("Resetting simulator...")
    reset_simulator()
    
    # Initial report (should be empty)
    print("\nInitial state:")
    report = get_advisor_report()
    print_report(report)
    
    # Generate and submit some sequences
    print("Submitting sequences...")
    sequences = generate_workload(15)
    for seq in sequences:
        submit_sequence(seq["id"], seq["tokens"])
    
    # Get report with sequences
    print("\nAfter submitting sequences:")
    report = get_advisor_report()
    print_report(report)
    
    # Simulate some time passing
    print("Simulating time passing (5s)...")
    time.sleep(5)
    
    # Get updated report
    print("\nAfter some time:")
    report = get_advisor_report()
    print_report(report)
    
    # Finish some sequences
    print("Finishing some sequences...")
    for seq in sequences[:5]:  # Finish first 5 sequences
        finish_sequence(seq["id"])
    
    # Get final report
    print("\nFinal state:")
    report = get_advisor_report()
    print_report(report)
    
    print("Demo complete!")


if __name__ == "__main__":
    run_demo()
