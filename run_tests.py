"""Run all tests with proper Python path setup."""
import os
import sys
import pytest

if __name__ == "__main__":
    # Add project root to Python path
    project_root = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, project_root)
    
    # Run pytest with verbosity
    sys.exit(pytest.main(["-v", "tests"]))
