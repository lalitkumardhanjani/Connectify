#!/usr/bin/env python3
"""
Connectify Pipeline Test Runner
================================
Runs the complete test suite with rich terminal output and an HTML report.

Usage:
    python tests/run_all_tests.py                # Full suite
    python tests/run_all_tests.py --unit         # Unit tests only
    python tests/run_all_tests.py --integration  # Integration tests only
    python tests/run_all_tests.py --multi-user   # Multi-user tests only
    python tests/run_all_tests.py --coverage     # With coverage report
"""

import subprocess
import sys
import os
import argparse
from datetime import datetime

# Ensure we run from the project root regardless of cwd
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)


def run_suite(paths: list, extra_args: list = None, coverage: bool = False) -> int:
    """Runs pytest on the given paths and returns the exit code."""
    extra_args = extra_args or []

    report_path = os.path.join(
        SCRIPT_DIR, f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    )

    cmd = [sys.executable, "-m", "pytest"] + paths + [
        "-v",
        "--tb=short",
        f"--html={report_path}",
        "--self-contained-html",
        "-p", "no:warnings",
    ] + extra_args

    if coverage:
        cmd += [
            "--cov=pipelines",
            "--cov=core",
            "--cov=config",
            "--cov-report=term-missing",
            f"--cov-report=html:{os.path.join(SCRIPT_DIR, 'coverage_html')}",
        ]

    print("\n" + "=" * 70)
    print("  CONNECTIFY PIPELINE TEST SUITE")
    print("=" * 70)
    print(f"  Running: {' '.join(paths)}")
    print(f"  Report:  {report_path}")
    print("=" * 70 + "\n")

    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="Connectify Pipeline Test Runner")
    parser.add_argument("--unit",        action="store_true", help="Run unit tests only")
    parser.add_argument("--integration", action="store_true", help="Run integration tests only")
    parser.add_argument("--multi-user",  action="store_true", help="Run multi-user tests only")
    parser.add_argument("--coverage",    action="store_true", help="Generate coverage report")
    parser.add_argument("--fast",        action="store_true", help="Skip slow concurrent tests")
    args = parser.parse_args()

    extra = []
    if args.fast:
        extra += ["-k", "not Concurrent"]

    if args.unit:
        paths = [os.path.join(SCRIPT_DIR, "unit")]
    elif args.integration:
        paths = [os.path.join(SCRIPT_DIR, "integration")]
    elif args.multi_user:
        paths = [os.path.join(SCRIPT_DIR, "multi_user")]
    else:
        paths = [SCRIPT_DIR]

    exit_code = run_suite(paths, extra_args=extra, coverage=args.coverage)

    print("\n" + "=" * 70)
    if exit_code == 0:
        print("  [PASS]  ALL TESTS PASSED")
    else:
        print("  [FAIL]  SOME TESTS FAILED - check the report above")
    print("=" * 70 + "\n")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
