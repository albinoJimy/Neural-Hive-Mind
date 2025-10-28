#!/usr/bin/env python3
"""
Test runner for the gateway-intencoes service

This script provides different ways to run tests:
- Unit tests only (fast, no external dependencies)
- Integration tests (requires Docker for testcontainers)
- All tests
- Code coverage reports
"""

import sys
import subprocess
import argparse
from pathlib import Path


def run_command(cmd: list, description: str) -> bool:
    """Run a command and return success status"""
    print(f"\n=== {description} ===")
    print(f"Running: {' '.join(cmd)}")

    result = subprocess.run(cmd, cwd=Path(__file__).parent)
    if result.returncode != 0:
        print(f"❌ {description} failed with exit code {result.returncode}")
        return False
    else:
        print(f"✅ {description} completed successfully")
        return True


def main():
    parser = argparse.ArgumentParser(description="Run tests for gateway-intencoes")
    parser.add_argument(
        "--type",
        choices=["unit", "integration", "all"],
        default="unit",
        help="Type of tests to run (default: unit)"
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Generate coverage report"
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Run tests in parallel"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    # Base pytest command
    cmd = ["python", "-m", "pytest"]

    # Test type selection
    if args.type == "unit":
        cmd.extend(["-m", "not integration"])
        print("Running unit tests only (fast, no external dependencies)")
    elif args.type == "integration":
        cmd.extend(["-m", "integration"])
        print("Running integration tests (requires Docker)")
    else:
        print("Running all tests")

    # Coverage
    if args.coverage:
        cmd.extend(["--cov=src", "--cov-report=html", "--cov-report=term"])

    # Parallel execution
    if args.parallel:
        cmd.extend(["-n", "auto"])

    # Verbose output
    if args.verbose:
        cmd.append("-v")

    # Run tests
    success = run_command(cmd, f"Running {args.type} tests")

    if args.coverage and success:
        print("\n📊 Coverage report generated in htmlcov/index.html")

    # Code quality checks (optional)
    if args.type == "all":
        print("\n=== Code Quality Checks ===")

        # Type checking
        run_command(["python", "-m", "mypy", "src"], "Type checking with mypy")

        # Code formatting
        run_command(["python", "-m", "black", "--check", "src", "tests"], "Code formatting check")

        # Import sorting
        run_command(["python", "-m", "isort", "--check-only", "src", "tests"], "Import sorting check")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())