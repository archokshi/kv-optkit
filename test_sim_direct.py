#!/usr/bin/env python3
"""
Direct test of sim adapter to isolate the issue.
"""
import requests
import json

BASE_URL = "http://localhost:9000"

def test_health():
    """Test if server is responding."""
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"Health check: {response.status_code} - {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Health check failed: {e}")
        return False

def test_sim_reset():
    """Test sim reset endpoint."""
    try:
        response = requests.post(f"{BASE_URL}/sim/reset", timeout=5)
        print(f"Reset: {response.status_code} - {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Reset failed: {e}")
        return False

def test_sim_submit():
    """Test sim submit endpoint."""
    try:
        data = {"seq_id": "test123", "tokens": 100}
        response = requests.post(
            f"{BASE_URL}/sim/submit", 
            json=data,
            timeout=5
        )
        print(f"Submit: {response.status_code}")
        if response.status_code == 200:
            print(f"Submit response: {response.json()}")
        else:
            print(f"Submit error: {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"Submit failed: {e}")
        return False

def test_debug_routes():
    """Test debug routes endpoint."""
    try:
        response = requests.get(f"{BASE_URL}/debug/routes", timeout=5)
        print(f"Debug routes: {response.status_code}")
        if response.status_code == 200:
            routes = response.json()
            print(f"Available routes: {len(routes)}")
            sim_routes = [r for r in routes if '/sim' in r]
            print(f"Sim routes: {sim_routes}")
        else:
            print(f"Debug routes error: {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"Debug routes failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing KV-OptKit sim endpoints...")
    
    if not test_health():
        print("Server is not responding. Please start it first.")
        exit(1)
    
    test_debug_routes()
    test_sim_reset()
    test_sim_submit()
