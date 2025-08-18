"""Test runner script for MesmerGlass test suite.

This script provides convenient ways to run different test categories.
"""

import sys
import subprocess
import argparse
from pathlib import Path

def run_tests(test_type="all", verbose=False, coverage=False):
    """Run tests with specified options."""
    
    # Try to use virtual environment Python first
    venv_python = Path(".venv/Scripts/python.exe")
    if venv_python.exists():
        python_cmd = str(venv_python)
    else:
        python_cmd = "python"
    
    # Base pytest command
    cmd = [python_cmd, "-m", "pytest"]
    
    if verbose:
        cmd.extend(["-v", "-s"])
    
    if coverage:
        cmd.extend(["--cov=mesmerglass", "--cov-report=html", "--cov-report=term"])
    
    # Add test selection based on type
    if test_type == "fast":
        cmd.extend(["-m", "not slow"])
    elif test_type == "slow":
        cmd.extend(["-m", "slow"])
    elif test_type == "integration":
        cmd.extend(["-m", "integration"])
    elif test_type == "bluetooth":
        cmd.extend(["-m", "bluetooth"])
    elif test_type == "unit":
        cmd.extend(["-m", "not integration and not bluetooth"])
    
    # Add test path
    cmd.append("mesmerglass/tests")
    
    print(f"Running command: {' '.join(cmd)}")
    return subprocess.run(cmd).returncode

def main():
    """Main test runner function."""
    parser = argparse.ArgumentParser(description="MesmerGlass Test Runner")
    parser.add_argument(
        "test_type", 
        choices=["all", "fast", "slow", "unit", "integration", "bluetooth"],
        default="all",
        nargs="?",
        help="Type of tests to run"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("-c", "--coverage", action="store_true", help="Run with coverage")
    
    args = parser.parse_args()
    
    print(f"🧪 MesmerGlass Test Runner")
    print(f"Running {args.test_type} tests...")
    print()
    
    exit_code = run_tests(args.test_type, args.verbose, args.coverage)
    
    if exit_code == 0:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed!")
    
    return exit_code

if __name__ == "__main__":
    sys.exit(main())
