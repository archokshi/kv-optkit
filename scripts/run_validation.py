"""
Validation script for KV-OptKit Autopilot.

This script runs all tests and verifies the demo functionality.
"""
import subprocess
import sys
import os
import json
import time
from typing import Dict, Any, Tuple, Optional
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))

# Configuration
TEST_DIR = PROJECT_ROOT / "tests"
EXAMPLES_DIR = PROJECT_ROOT / "examples"
TEST_FILES = [
    "test_policy_engine.py",
    "test_guard.py",
    "test_autopilot_api.py"
]
DEMO_SCRIPT = "demo_autopilot.py"
SERVER_URL = "http://localhost:9000"
SERVER_START_TIMEOUT = 10  # seconds


def run_command(cmd: str, cwd: Optional[str] = None) -> Tuple[bool, str]:
    """Run a shell command and return (success, output)."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd or PROJECT_ROOT,
            capture_output=True,
            text=True
        )
        return (
            result.returncode == 0,
            f"Command: {cmd}\n{result.stdout}\n{result.stderr}"
        )
    except Exception as e:
        return False, f"Error running '{cmd}': {str(e)}"


def run_tests() -> Tuple[bool, str]:
    """Run all unit tests."""
    print("\n=== Running Unit Tests ===")
    all_passed = True
    output = []
    
    for test_file in TEST_FILES:
        test_path = TEST_DIR / test_file
        print(f"\nRunning {test_file}...")
        success, result = run_command(f"python -m pytest {test_path} -v")
        output.append(f"=== {test_file} ===\n{result}")
        if not success:
            all_passed = False
            print(f"❌ {test_file} failed")
        else:
            print(f"✅ {test_file} passed")
    
    return all_passed, "\n".join(output)


def start_test_server() -> Tuple[bool, Optional[subprocess.Popen], str]:
    """Start the test server in a subprocess."""
    print("\n=== Starting Test Server ===")
    try:
        # Start the server in a separate process
        server_process = subprocess.Popen(
            ["uvicorn", "kvopt.server.main:app", "--host", "0.0.0.0", "--port", "9000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait for server to start
        print("Waiting for server to start...")
        time.sleep(2)  # Give server time to start
        
        # Verify server is running
        try:
            import requests
            response = requests.get(f"{SERVER_URL}/health")
            if response.status_code == 200:
                print("✅ Test server started successfully")
                return True, server_process, "Server started successfully"
            else:
                return False, server_process, f"Server returned status {response.status_code}"
        except Exception as e:
            return False, server_process, f"Failed to connect to server: {str(e)}"
            
    except Exception as e:
        return False, None, f"Failed to start server: {str(e)}"


def stop_test_server(server_process: Optional[subprocess.Popen]) -> str:
    """Stop the test server."""
    if server_process:
        try:
            server_process.terminate()
            server_process.wait(timeout=5)
            return "Test server stopped"
        except Exception as e:
            return f"Error stopping test server: {str(e)}"
    return "No server process to stop"


def run_demo() -> Tuple[bool, str]:
    """Run the demo script and verify its output."""
    print("\n=== Running Demo ===")
    demo_path = EXAMPLES_DIR / DEMO_SCRIPT
    
    if not demo_path.exists():
        return False, f"Demo script not found at {demo_path}"
    
    success, output = run_command(f"python {demo_path} --server {SERVER_URL}")
    
    if success:
        print("✅ Demo completed successfully")
    else:
        print("❌ Demo failed")
    
    return success, output


def run_integration_tests() -> Tuple[bool, str]:
    """Run integration tests against the running server."""
    print("\n=== Running Integration Tests ===")
    
    try:
        import requests
        
        # Test 1: Create a plan
        print("Testing plan creation...")
        response = requests.post(
            f"{SERVER_URL}/autopilot/plan",
            json={"target_hbm_util": 0.7, "max_actions": 3}
        )
        
        if response.status_code != 200:
            return False, f"Failed to create plan: {response.text}"
            
        plan_data = response.json()
        plan_id = plan_data.get("plan_id")
        
        if not plan_id:
            return False, "No plan_id in response"
            
        print(f"✅ Created plan {plan_id}")
        
        # Test 2: Get plan status
        print("Testing plan status...")
        response = requests.get(f"{SERVER_URL}/autopilot/plan/{plan_id}")
        
        if response.status_code != 200:
            return False, f"Failed to get plan status: {response.text}"
            
        status_data = response.json()
        print(f"✅ Plan status: {status_data.get('status')}")
        
        # Test 3: Get metrics
        print("Testing metrics endpoint...")
        response = requests.get(f"{SERVER_URL}/autopilot/metrics")
        
        if response.status_code != 200:
            return False, f"Failed to get metrics: {response.text}"
            
        metrics = response.json()
        print(f"✅ Retrieved metrics: {json.dumps(metrics, indent=2)}")
        
        return True, "Integration tests completed successfully"
        
    except Exception as e:
        return False, f"Integration test error: {str(e)}"


def main() -> int:
    """Main validation function."""
    print("=== KV-OptKit Autopilot Validation ===")
    
    # Run unit tests
    tests_passed, test_output = run_tests()
    if not tests_passed:
        print("\n❌ Unit tests failed. Aborting validation.")
        print("\nTest Output:")
        print(test_output)
        return 1
    
    # Start test server
    server_success, server_process, server_msg = start_test_server()
    if not server_success:
        print(f"\n❌ Failed to start test server: {server_msg}")
        return 1
    
    try:
        # Run integration tests
        integration_success, integration_output = run_integration_tests()
        if not integration_success:
            print(f"\n❌ Integration tests failed: {integration_output}")
            return 1
        
        # Run demo
        demo_success, demo_output = run_demo()
        if not demo_success:
            print(f"\n❌ Demo failed: {demo_output}")
            return 1
        
        print("\n=== Validation Completed Successfully ===")
        return 0
        
    finally:
        # Ensure server is stopped
        print("\nStopping test server...")
        stop_msg = stop_test_server(server_process)
        print(stop_msg)


if __name__ == "__main__":
    sys.exit(main())
